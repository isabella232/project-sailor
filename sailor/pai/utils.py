"""Module for various utility functions, in particular those related to fetching data from remote oauth endpoints."""

from ..utils.oauth_wrapper import get_oauth_client
from ..utils.config import SailorConfig
from ..assetcentral.utils import AssetcentralEntity, _compose_queries, _fetch_count


def _pai_application_url():
    """Return the PredictiveAssetInsights (PAI) application URL from the SailorConfig."""
    return SailorConfig.get('predictive_asset_insights', 'application_url')

def _fetch_data(endpoint_url, count_endpoint_url=(), unbreakable_filters=(), breakable_filters=(), query_params = None, client_name='predictive_asset_insights'):
    """Retrieve data from the AssetCentral service."""
    filters = _compose_queries(unbreakable_filters, breakable_filters)
    oauth_client = get_oauth_client(client_name)

    counts = _fetch_count(count_endpoint_url, unbreakable_filters, breakable_filters, client_name='predictive_asset_insights')  

    if '$skip'not in query_params:
        query_params['$skip'] = 0
        skip = 0
    else:
        skip  = query_params['$skip']

    if '$top'in query_params:
        counts  = query_params['$top']

    if '$orderby'not in query_params:
        query_params['$orderby'] = 'AlertId'

    if not filters:
        filters = ['']

    result = []
    while True:
        for filter_string in filters:
            params = {'$filter': filter_string} if filter_string else {}
            params['$format'] = 'json'
            params = {**params, **query_params}

            endpoint_data = oauth_client.request('GET', endpoint_url, params=params)

            for element in endpoint_data['d']['results']:
                result.append(element)

            skip = len(result)

        p = {}
        if skip < counts:
            p['$skip'] = skip
            query_params.update(p)
        else: break

        if len(result) == 0:
            warnings.warn(DataNotFoundWarning(), stacklevel=2)

    return result


class PredictiveAssetInsightsEntity(AssetcentralEntity):
    """Common base class for Pai entities."""

    def __repr__(self) -> str:
        """Return a very short string representation."""
        return f'"{self.__class__.__name__}(id="{self.id}")'
