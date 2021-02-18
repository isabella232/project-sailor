from collections import defaultdict
from io import BytesIO
from unittest.mock import patch, call

import pytest
import pandas as pd

from sailor.sap_iot.fetch import _start_bulk_timeseries_data_export, _check_bulk_timeseries_export_status,\
    _get_exported_bulk_timeseries_data, _process_one_file, get_indicator_data
from sailor.sap_iot import TimeseriesDataset
from sailor.assetcentral.indicators import IndicatorSet
from sailor.assetcentral.equipment import EquipmentSet
from sailor.utils.oauth_wrapper import RequestError
from sailor.utils.utils import DataNotFoundWarning


@pytest.fixture()
def make_csv_bytes():
    def maker(group_id=1):
        data = '''
        _TIME,I_indicator_id_1,I_indicator_id_2,indicatorGroupId,modelId,templateId,equipmentId
        1601683140000,3.4,1.78,IG_indicator_group_id_{},model_id,template_id_1,equipment_id_1
        1601683140000,4.5,2.4,IG_indicator_group_id_{},model_id,template_id_1,equipment_id_2
        1601683180000,4.3,78.1,IG_indicator_group_id_{},model_id,template_id_1,equipment_id_1
        1601683180000,5.4,4.2,IG_indicator_group_id_{},model_id,template_id_1,equipment_id_2
        1601683140000,13.4,11.78,IG_indicator_group_id_{},model_id,template_id_2,equipment_id_1
        1601683140000,14.5,12.4,IG_indicator_group_id_{},model_id,template_id_2,equipment_id_2
        1601683180000,14.3,178.1,IG_indicator_group_id_{},model_id,template_id_2,equipment_id_1
        1601683180000,15.4,14.2,IG_indicator_group_id_{},model_id,template_id_2,equipment_id_2
        '''.format(*[group_id]*8)

        return ''.join(data.split(' ')).encode()
    return maker


class TestRawDataAsyncFunctions:
    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_export_start_request_delegate_call(self, mock_fetch, mock_config):
        mock_config.config.sap_iot = defaultdict(str, export_url='EXPORT_BASE_URL')
        expected_url = 'EXPORT_BASE_URL/v1/InitiateDataExport/indicator_group_id?timerange=start_date-end_date'

        _start_bulk_timeseries_data_export('start_date', 'end_date', 'indicator_group_id')

        mock_fetch.assert_called_once_with(expected_url, 'POST')

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_export_status_request_delegate_call(self, mock_fetch, mock_config):
        mock_config.config.sap_iot = defaultdict(str, export_url='EXPORT_BASE_URL')
        mock_fetch.return_value = dict(Status='The file is available for download.')
        expected_url = 'EXPORT_BASE_URL/v1/DataExportStatus?requestId=export_id'

        _check_bulk_timeseries_export_status('export_id')

        mock_fetch.assert_called_once_with(expected_url, 'GET')

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    @patch('sailor.sap_iot.fetch.zipfile.ZipFile')
    def test_export_get_data_request_delegate_call(self, mock_zipfile, mock_fetch, mock_config):
        mock_config.config.sap_iot = defaultdict(str, download_url='DOWNLOAD_BASE_URL')
        expected_url = "DOWNLOAD_BASE_URL/v1/DownloadData('export_id')"
        mock_fetch.return_value = b''

        with pytest.raises(RuntimeError):
            _get_exported_bulk_timeseries_data('export_id', IndicatorSet([]), EquipmentSet([]))

        mock_fetch.assert_called_once_with(expected_url, 'GET')

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_export_get_data_request_invalid_zipfile_response(self, mock_fetch, mock_config):
        mock_fetch.return_value = b''

        with pytest.raises(RuntimeError) as exception_info:
            _get_exported_bulk_timeseries_data('export_id', IndicatorSet([]), EquipmentSet([]))

        assert str(exception_info.value) == 'Downloaded file is corrupted, can not process contents.'

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_export_get_data_request_empty_zipfile_response(self, mock_fetch, mock_config):
        mock_fetch.return_value = bytes.fromhex('504B050600000000000000000000000000000000000000000000')  # minimal zip

        with pytest.raises(RuntimeError) as exception_info:
            _get_exported_bulk_timeseries_data('export_id', IndicatorSet([]), EquipmentSet([]))

        assert str(exception_info.value) == 'Downloaded File did not have any content.'

    @patch('sailor.sap_iot.fetch.zipfile')
    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_export_get_data_request_empty_gzip_content(self, mock_fetch, mock_zipfile, mock_config):
        mock_fetch.return_value = b''
        mock_zipfile.ZipFile.return_value.filelist = ['inner_file_1', 'inner_file_2']
        mock_zipfile.ZipFile.return_value.read.return_value = b''

        with pytest.raises(RuntimeError) as exception_info:
            _get_exported_bulk_timeseries_data('export_id', IndicatorSet([]), EquipmentSet([]))

        assert str(exception_info.value) == 'Downloaded File did not have any content.'

    @patch('sailor.sap_iot.fetch.zipfile')
    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_export_get_data_request_invalid_gzip_content(self, mock_fetch, mock_zipfile, mock_config):
        mock_fetch.return_value = b''
        mock_zipfile.ZipFile.return_value.filelist = ['inner_file_1', 'inner_file_2']
        mock_zipfile.ZipFile.return_value.read.return_value = b'INVALID'

        with pytest.raises(RuntimeError) as exception_info:
            _get_exported_bulk_timeseries_data('export_id', IndicatorSet([]), EquipmentSet([]))

        assert str(exception_info.value) == 'Downloaded file is corrupted, can not process contents.'

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    @pytest.mark.parametrize('description,response,expected', [
        ('available status', 'The file is available for download.', True),
        ('unavailable status', 'Request for data download is submitted.', False),
    ])
    def test_export_status_request_good_response(self, mock_fetch, mock_config, response, expected, description):
        mock_fetch.return_value = dict(Status=response)

        assert _check_bulk_timeseries_export_status('export_id') == expected

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    @pytest.mark.parametrize('description,response', [
        ('empty status', ''),
        ('None status', None),
        ('Failed status', 'File download has failed. Re-initiate the request for data export.')
    ])
    def test_export_status_request_bad_response(self, mock_fetch, mock_config, response, description):
        mock_fetch.return_value = dict(Status=response)

        with pytest.raises(RuntimeError) as exception_info:
            _check_bulk_timeseries_export_status('export_id')

        assert str(exception_info.value) == str(response)

    @pytest.mark.parametrize('description,indicator_ids,template_ids,equipment_ids,expected_rows', [
        ('filter_indicator', [1, 1], [1, 2], [1, 2], 4),
        ('filter_template', [1, 2], [1, 2], [1, 2], 4),
        ('filter_equipment', [1, 2, 1, 2], [1, 1, 2, 2], [1], 2),
        ('no filters', [1, 2, 1, 2], [1, 1, 2, 2], [1, 2], 4)
    ])
    def test_process_one_file_filtering(self, make_csv_bytes, make_indicator_set, make_equipment_set,
                                        indicator_ids, template_ids, equipment_ids, expected_rows, description):
        indicator_set = make_indicator_set(propertyId=[f'indicator_id_{x}' for x in indicator_ids],
                                           categoryID=[f'template_id_{x}' for x in template_ids],
                                           pstid=['indicator_group_id_1'] * len(indicator_ids))
        equipment_set = make_equipment_set(equipmentId=[f'equipment_id_{x}' for x in equipment_ids])
        expected_columns = ['timestamp', 'equipment_id', 'equipment_model_id']
        expected_columns += [indicator._unique_id for indicator in indicator_set]
        expected_equipments = {equipment.id for equipment in equipment_set}

        data = _process_one_file(BytesIO(make_csv_bytes()), indicator_set, equipment_set)

        assert isinstance(data, pd.DataFrame)
        assert list(data.columns) == expected_columns
        assert len(data) == expected_rows
        assert set(data['equipment_id'].unique()) == expected_equipments

    def test_process_one_file_missing_indicator_warning(self, make_csv_bytes, make_indicator_set, make_equipment_set):
        indicator_set = make_indicator_set(propertyId=[f'indicator_id_{x}' for x in [1, 2, 3]],
                                           categoryID=[f'template_id_{x}' for x in [1, 1, 1]],
                                           pstid=['indicator_group_id_1'] * 3)
        equipment_set = make_equipment_set(equipmentId=[f'equipment_id_{x}' for x in [1, 2]])
        expected_columns = ['timestamp', 'equipment_id', 'equipment_model_id']
        expected_columns += [indicator._unique_id for indicator in indicator_set]

        with pytest.warns(DataNotFoundWarning, match='Could not find any data for indicator.*indicator_id_3.*'):
            _process_one_file(BytesIO(make_csv_bytes()), indicator_set, equipment_set)


class TestRawDataWrapperFunction:
    @patch('sailor.sap_iot.fetch.gzip.GzipFile')
    @patch('sailor.sap_iot.fetch.zipfile')
    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_get_indicator_data_two_indicator_groups(self, mock_fetch, mock_zipfile, mock_gzip, mock_config,
                                                     make_indicator_set, make_equipment_set, make_csv_bytes):
        mock_config.config.sap_iot = defaultdict(str, export_url='EXPORT_URL', download_url='DOWNLOAD_URL')

        indicator_set = make_indicator_set(propertyId=[f'indicator_id_{x}' for x in [1, 2, 1, 2]],
                                           categoryID=[f'template_id_{x}' for x in [1, 1, 2, 2]],
                                           pstid=[f'indicator_group_id_{x}' for x in [1, 1, 2, 2]])
        equipment_set = make_equipment_set(equipmentId=[f'equipment_id_{x}' for x in [1, 2]])

        mock_fetch.side_effect = [
            {'RequestId': 'test_request_id_1'}, {'RequestId': 'test_request_id_2'},
            {'Status': 'The file is available for download.'}, b'mock_zip_content',
            {'Status': 'The file is available for download.'}, b'mock_zip_content',
        ]
        mock_zipfile.ZipFile.return_value.filelist = ['inner_file_1']
        mock_zipfile.ZipFile.return_value.read.return_value = b'mock_gzip_content'
        mock_gzip.side_effect = [BytesIO(make_csv_bytes(1)), BytesIO(make_csv_bytes(2))]

        expected_calls = [
            call('EXPORT_URL/v1/InitiateDataExport/IG_indicator_group_id_1?timerange=2020-01-01-2020-02-01', 'POST'),
            call('EXPORT_URL/v1/InitiateDataExport/IG_indicator_group_id_2?timerange=2020-01-01-2020-02-01', 'POST'),
            call('EXPORT_URL/v1/DataExportStatus?requestId=test_request_id_1', 'GET'),
            call("DOWNLOAD_URL/v1/DownloadData('test_request_id_1')", 'GET'),
            call('EXPORT_URL/v1/DataExportStatus?requestId=test_request_id_2', 'GET'),
            call("DOWNLOAD_URL/v1/DownloadData('test_request_id_2')", 'GET'),
        ]

        expected_columns = ['timestamp', 'equipment_id', 'equipment_model_id']
        expected_columns += [indicator._unique_id for indicator in indicator_set]

        wrapper = get_indicator_data('2020-01-01T00:00:00Z', '2020-02-01T00:00:00Z', indicator_set, equipment_set)

        mock_fetch.assert_has_calls(expected_calls)
        assert isinstance(wrapper, TimeseriesDataset)
        assert set(wrapper._df.columns) == set(expected_columns)
        assert len(wrapper._df) == 4
        assert set(wrapper._df['equipment_id'].unique()) == {'equipment_id_1', 'equipment_id_2'}

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    def test_get_indicator_data_requesterror_handled(self, mock_fetch, mock_config, make_indicator_set):
        mock_fetch.side_effect = RequestError('msg', '400', 'reason',
                                              '{"message": "Data not found for the requested date range"}')
        indicator_set = make_indicator_set(propertyId=['indicator_id_1', 'indicator_id_2'])

        with pytest.warns(DataNotFoundWarning, match='No data for indicator group IG_group_id.*'):
            get_indicator_data('2020-01-01T00:00:00Z', '2020-02-01T00:00:00Z', indicator_set, EquipmentSet([]))

    @patch('sailor.sap_iot.fetch.OAuthFlow.fetch_endpoint_data')
    @pytest.mark.parametrize('description,content', [
        ('not json', 'foo'),
        ('empty', ''),
        ('wrong content', '{"message": "Test Content"}'),
        ('no field', '{"some_other_field": "Test Content"}')
    ])
    def test_get_indicator_data_requesterror_unhandled(self, mock_fetch, mock_config, make_indicator_set,
                                                       content, description):
        mock_fetch.side_effect = RequestError(content, '400', 'reason', content)
        indicator_set = make_indicator_set(propertyId=['indicator_id_1', 'indicator_id_2'])

        with pytest.raises(RequestError) as exception_info:
            get_indicator_data('2020-01-01T00:00:00Z', '2020-02-01T00:00:00Z', indicator_set, EquipmentSet([]))

        assert str(exception_info.value) == content
