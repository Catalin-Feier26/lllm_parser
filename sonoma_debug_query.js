const coll = db.raw_permits;

// Optional: set this to one parser run if needed.
// Example:
// const runId = "run_20260625_xxxxxx_xxxx";
const runId = null;

// Broad Sonoma filter.
// This should work even if the source is stored as county, municipality, parser name, or config module.
let sourceFilter = {
"source.state": "CA",
$or: [
    { "source.county": /Sonoma/i },
    { "source.municipality": /Sonoma/i },
    { "provenance.config_module": /sonoma/i },
    { "provenance.parser_name": /Sonoma/i },
    { "provenance.csv_file_name": /Sonoma/i }
]
};

if (runId !== null) {
sourceFilter["provenance.parser_run_id"] = runId;
}

const fields = [
"permit_number",
"status",
"permit_type",
"applied_date",
"issued_date",
"address",
"parcel_number",
"fee",
"valuation",
"description"
];

const missingMarkers = [
null, "", " ", "-", "--", "N/A", "NA", "n/a",
"None", "NONE", "null", "NULL", "Not Identified"
];

print("\n=== TOTAL SONOMA RAW RECORDS ===");
printjson({
total_records: coll.countDocuments(sourceFilter),
filter_used: sourceFilter
});

print("\n=== SOURCE / RUN BREAKDOWN ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $group: {
    _id: {
        parser_run_id: "$provenance.parser_run_id",
        parser_name: "$provenance.parser_name",
        csv_file_name: "$provenance.csv_file_name",
        config_module: "$provenance.config_module",
        state: "$source.state",
        county: "$source.county",
        municipality: "$source.municipality"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } }
]).forEach(doc => printjson(doc));

print("\n=== FIELD COMPLETENESS ===");
fields.forEach(field => {
const path = "data." + field;
const total = coll.countDocuments(sourceFilter);

const present = coll.countDocuments({
    ...sourceFilter,
    [path]: { $exists: true, $nin: missingMarkers }
});

const distinctValues = coll.distinct(path, {
    ...sourceFilter,
    [path]: { $exists: true, $nin: missingMarkers }
});

printjson({
    field: field,
    total: total,
    present: present,
    missing_or_empty: total - present,
    present_rate: total === 0 ? 0 : Number((present / total).toFixed(4)),
    distinct_count: distinctValues.length
});
});

print("\n=== FIELD TYPE CHECK ===");
fields.forEach(field => {
const path = "$data." + field;

print("\n--- TYPES: " + field + " ---");
coll.aggregate([
    { $match: sourceFilter },
    {
    $project: {
        value_type: { $type: path }
    }
    },
    {
    $group: {
        _id: "$value_type",
        count: { $sum: 1 }
    }
    },
    { $sort: { count: -1 } }
]).forEach(doc => printjson(doc));
});

print("\n=== TOP VALUES: PERMIT TYPE ===");
coll.aggregate([
{
    $match: {
    ...sourceFilter,
    "data.permit_type": { $exists: true, $nin: missingMarkers }
    }
},
{
    $group: {
    _id: "$data.permit_type",
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 80 }
]).forEach(doc => printjson(doc));

print("\n=== TOP VALUES: STATUS ===");
coll.aggregate([
{
    $match: {
    ...sourceFilter,
    "data.status": { $exists: true, $nin: missingMarkers }
    }
},
{
    $group: {
    _id: "$data.status",
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 50 }
]).forEach(doc => printjson(doc));

print("\n=== PERMIT NUMBER PREFIX BREAKDOWN ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    permit_number: "$data.permit_number",
    permit_type: "$data.permit_type",
    status: "$data.status",
    permit_number_prefix_match: {
        $regexFind: {
        input: { $ifNull: ["$data.permit_number", ""] },
        regex: /^([A-Z]+)/
        }
    },
    permit_number_year_match: {
        $regexFind: {
        input: { $ifNull: ["$data.permit_number", ""] },
        regex: /^[A-Z]+(\d{2})-/
        }
    }
    }
},
{
    $project: {
    permit_number: 1,
    permit_type: 1,
    status: 1,
    permit_number_prefix: {
        $ifNull: [
        { $arrayElemAt: ["$permit_number_prefix_match.captures", 0] },
        "UNKNOWN"
        ]
    },
    permit_number_year: {
        $ifNull: [
        { $arrayElemAt: ["$permit_number_year_match.captures", 0] },
        "UNKNOWN"
        ]
    }
    }
},
{
    $group: {
    _id: {
        permit_number_prefix: "$permit_number_prefix",
        permit_number_year: "$permit_number_year"
    },
    count: { $sum: 1 },
    example_permit_number: { $first: "$permit_number" },
    example_permit_type: { $first: "$permit_type" },
    example_status: { $first: "$status" }
    }
},
{ $sort: { count: -1 } }
]).forEach(doc => printjson(doc));

print("\n=== PERMIT TYPE / STATUS COMBINATIONS ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $group: {
    _id: {
        permit_type: "$data.permit_type",
        status: "$data.status"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 80 }
]).forEach(doc => printjson(doc));

print("\n=== ADDRESS LOCATION CODE BREAKDOWN ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    address: "$data.address",
    permit_type: "$data.permit_type",
    status: "$data.status",
    location_code_match: {
        $regexFind: {
        input: { $ifNull: ["$data.address", ""] },
        regex: /\[([A-Z]+)\]\s*$/
        }
    }
    }
},
{
    $project: {
    address: 1,
    permit_type: 1,
    status: 1,
    location_code: {
        $ifNull: [
        { $arrayElemAt: ["$location_code_match.captures", 0] },
        "UNKNOWN"
        ]
    }
    }
},
{
    $group: {
    _id: "$location_code",
    count: { $sum: 1 },
    example_address: { $first: "$address" },
    example_permit_type: { $first: "$permit_type" },
    example_status: { $first: "$status" }
    }
},
{ $sort: { count: -1 } }
]).forEach(doc => printjson(doc));

print("\n=== LOCATION CODE / PERMIT TYPE COMBINATIONS ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    permit_type: "$data.permit_type",
    status: "$data.status",
    location_code_match: {
        $regexFind: {
        input: { $ifNull: ["$data.address", ""] },
        regex: /\[([A-Z]+)\]\s*$/
        }
    }
    }
},
{
    $project: {
    permit_type: 1,
    status: 1,
    location_code: {
        $ifNull: [
        { $arrayElemAt: ["$location_code_match.captures", 0] },
        "UNKNOWN"
        ]
    }
    }
},
{
    $group: {
    _id: {
        location_code: "$location_code",
        permit_type: "$permit_type"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 100 }
]).forEach(doc => printjson(doc));

print("\n=== DUPLICATE PERMIT NUMBERS ===");
coll.aggregate([
{
    $match: {
    ...sourceFilter,
    "data.permit_number": { $exists: true, $nin: missingMarkers }
    }
},
{
    $group: {
    _id: "$data.permit_number",
    count: { $sum: 1 },
    example_status: { $first: "$data.status" },
    example_permit_type: { $first: "$data.permit_type" },
    example_address: { $first: "$data.address" }
    }
},
{ $match: { count: { $gt: 1 } } },
{ $sort: { count: -1 } },
{ $limit: 50 }
]).forEach(doc => printjson(doc));

print("\n=== FEE TOP VALUES ===");
coll.aggregate([
{
    $match: {
    ...sourceFilter,
    "data.fee": { $exists: true, $nin: missingMarkers }
    }
},
{
    $group: {
    _id: "$data.fee",
    count: { $sum: 1 },
    example_permit_type: { $first: "$data.permit_type" }
    }
},
{ $sort: { count: -1 } },
{ $limit: 50 }
]).forEach(doc => printjson(doc));

print("\n=== PERMIT TYPE / FEE COMBINATIONS ===");
coll.aggregate([
{
    $match: {
    ...sourceFilter,
    "data.permit_type": { $exists: true, $nin: missingMarkers },
    "data.fee": { $exists: true, $nin: missingMarkers }
    }
},
{
    $group: {
    _id: {
        permit_type: "$data.permit_type",
        fee: "$data.fee"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 80 }
]).forEach(doc => printjson(doc));

print("\n=== VALUATION ZERO / NONZERO BREAKDOWN ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    permit_type: "$data.permit_type",
    status: "$data.status",
    valuation_clean: {
        $replaceAll: {
        input: {
            $replaceAll: {
            input: { $toString: { $ifNull: ["$data.valuation", ""] } },
            find: { $literal: "$" },
            replacement: ""
            }
        },
        find: ",",
        replacement: ""
        }
    }
    }
},
{
    $project: {
    permit_type: 1,
    status: 1,
    valuation_num: {
        $convert: {
        input: "$valuation_clean",
        to: "double",
        onError: null,
        onNull: null
        }
    }
    }
},
{
    $project: {
    permit_type: 1,
    status: 1,
    valuation_group: {
        $cond: [
        { $eq: ["$valuation_num", 0] },
        "zero",
        {
            $cond: [
            { $gt: ["$valuation_num", 0] },
            "nonzero",
            "missing_or_invalid"
            ]
        }
        ]
    }
    }
},
{
    $group: {
    _id: {
        permit_type: "$permit_type",
        status: "$status",
        valuation_group: "$valuation_group"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 80 }
]).forEach(doc => printjson(doc));

print("\n=== TOP DESCRIPTION KEYWORDS BY SIMPLE REGEX ===");
const keywordRegexes = [
{ name: "roof", regex: /roof|re-roof|reroof|shingle|squers|squares/i },
{ name: "furnace_hvac", regex: /furnace|fau|a\/c|air condition|heat pump|mini split|ducting|duct/i },
{ name: "electrical_panel", regex: /electrical|panel|meter|wiring|outlet|fixtures|pv rated/i },
{ name: "water_heater_plumbing", regex: /water heater|plumbing|fixture|piping|sewer|water closet|lavatory/i },
{ name: "solar_pv", regex: /solar|pv|photovoltaic|battery|powerwall|module/i },
{ name: "gas", regex: /gas line|gas/i },
{ name: "septic_well", regex: /septic|well/i },
{ name: "fire_damage", regex: /fire|lightning|lnu/i },
{ name: "commercial", regex: /commercial|office|tenant/i },
{ name: "sfd", regex: /sfd|single family/i },
{ name: "test", regex: /test/i }
];

keywordRegexes.forEach(k => {
const count = coll.countDocuments({
    ...sourceFilter,
    "data.description": k.regex
});

printjson({
    keyword: k.name,
    matching_records: count
});
});

print("\n=== PERMIT TYPE / DESCRIPTION KEYWORD COMBINATIONS ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    permit_type: "$data.permit_type",
    status: "$data.status",
    description: "$data.description",
    keyword: {
        $switch: {
        branches: [
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /roof|re-roof|reroof|shingle|squers|squares/i } }, then: "roof" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /furnace|fau|a\/c|air condition|heat pump|mini split|ducting|duct/i } }, then: "furnace_hvac" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /electrical|panel|meter|wiring|outlet|fixtures|pv rated/i } }, then: "electrical_panel" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /water heater|plumbing|fixture|piping|sewer|water closet|lavatory/i } }, then: "water_heater_plumbing" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /solar|pv|photovoltaic|battery|powerwall|module/i } }, then: "solar_pv" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /gas line|gas/i } }, then: "gas" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /septic|well/i } }, then: "septic_well" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /fire|lightning|lnu/i } }, then: "fire_damage" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /commercial|office|tenant/i } }, then: "commercial" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /sfd|single family/i } }, then: "sfd" },
            { case: { $regexMatch: { input: { $ifNull: ["$data.description", ""] }, regex: /test/i } }, then: "test" }
        ],
        default: "other"
        }
    }
    }
},
{
    $group: {
    _id: {
        permit_type: "$permit_type",
        status: "$status",
        keyword: "$keyword"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 100 }
]).forEach(doc => printjson(doc));

print("\n=== SAMPLE RECORDS WITH MISSING VALUES ===");
coll.find(
{
    ...sourceFilter,
    $or: fields.map(field => ({
    ["data." + field]: { $in: missingMarkers }
    }))
},
{
    _id: 0,
    raw_permit_id: 1,
    "data.permit_number": 1,
    "data.status": 1,
    "data.permit_type": 1,
    "data.applied_date": 1,
    "data.issued_date": 1,
    "data.address": 1,
    "data.parcel_number": 1,
    "data.fee": 1,
    "data.valuation": 1,
    "data.description": 1,
    "provenance.csv_row_number": 1,
    "provenance.parser_run_id": 1
}
).limit(30).forEach(doc => printjson(doc));

print("\n=== COMPLETE-ISH RECORDS FOR PATTERN ANALYSIS ===");
coll.find(
{
    ...sourceFilter,
    "data.permit_number": { $exists: true, $nin: missingMarkers },
    "data.permit_type": { $exists: true, $nin: missingMarkers },
    "data.status": { $exists: true, $nin: missingMarkers },
    "data.description": { $exists: true, $nin: missingMarkers },
    "data.address": { $exists: true, $nin: missingMarkers }
},
{
    _id: 0,
    raw_permit_id: 1,
    "data.permit_number": 1,
    "data.status": 1,
    "data.permit_type": 1,
    "data.applied_date": 1,
    "data.issued_date": 1,
    "data.address": 1,
    "data.parcel_number": 1,
    "data.fee": 1,
    "data.valuation": 1,
    "data.description": 1,
    "provenance.csv_row_number": 1,
    "provenance.parser_run_id": 1
}
).limit(30).forEach(doc => printjson(doc));