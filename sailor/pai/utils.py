"""Module for various utility functions, in particular those related to fetching data from remote oauth endpoints."""


from ..utils.config import SailorConfig
from ..assetcentral.utils import AssetcentralEntity


def _pai_application_url():
    """Return the PredictiveAssetInsights (PAI) application URL from the SailorConfig."""
    return SailorConfig.get('predictive_asset_insights', 'application_url')

def _check_top_entries(query_params, nro_readings):
    #check we have all wanted entries
    p = {}
    top_entries = 0
    skip_entries = 0 
    
    if '$top'in query_params: 
        top_entries = query_params['$top'] 

    if '$skip' in query_params:
        skip_entries = query_params['$skip']
        
    p['$skip'] = skip_entries + nro_readings
    p['$top'] = top_entries - nro_readings 
    return(p)
        

class PredictiveAssetInsightsEntity(AssetcentralEntity):
    """Common base class for Pai entities."""

    def __repr__(self) -> str:
        """Return a very short string representation."""
        return f'"{self.__class__.__name__}(id="{self.id}")'
