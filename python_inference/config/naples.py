TARGET_FIELD = "permit_class"

CORE_FEATURES = [
    "building_type",
    "permit_type",
    "const_type",
]

ENGINEERED_FEATURES = [
    "valuation_bucket",
    "total_units_group",
    "total_sf_nonzero",
]

KEEP_COLUMNS = [
    "permit_number",
    "building_type",
    "permit_type",
    "const_type",
    "valuation",
    "total_sf",
    "total_units",
    "permit_class",
]

RARE_CLASS_MAP = {
    "Residential-Hotel": "Other Special Residential",
    "Residential-Care-Assisted Living Facilities": "Other Special Residential",
}