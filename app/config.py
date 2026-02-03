"""Urbix API — Configuration"""

# QLD ArcGIS REST Services
QLD_BASE_URL = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services"

# PlanningCadastre layers
PARCELS_URL = f"{QLD_BASE_URL}/PlanningCadastre/LandParcelPropertyFramework/MapServer/4"
ADDRESSES_URL = f"{QLD_BASE_URL}/PlanningCadastre/LandParcelPropertyFramework/MapServer/0"
PROPERTIES_URL = f"{QLD_BASE_URL}/PlanningCadastre/LandParcelPropertyFramework/MapServer/50"
TENURE_URL = f"{QLD_BASE_URL}/PlanningCadastre/LandParcelPropertyFramework/MapServer/13"
LGA_URL = f"{QLD_BASE_URL}/PlanningCadastre/LandParcelPropertyFramework/MapServer/20"
LOCALITY_URL = f"{QLD_BASE_URL}/PlanningCadastre/LandParcelPropertyFramework/MapServer/19"
LAND_USE_URL = f"{QLD_BASE_URL}/PlanningCadastre/LandUse/FeatureServer/0"

# Default query params
DEFAULT_SR = 4326  # WGS84 for API responses
NATIVE_SR = 4283   # GDA94 (QLD native)
MAX_RECORDS = 10
