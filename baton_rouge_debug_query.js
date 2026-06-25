const coll = db.raw_permits;

// Optional: set this if you want only one parser run.
// Example:
// const runId = "run_20260624_xxxxxx_xxxx";
const runId = null;

// Main Baton Rouge filter.
// If your municipality name is stored differently, change /Baton/i.
let sourceFilter = {
"source.state": "LA",
"source.municipality": /Baton/i
};

// If needed, add county after checking source breakdown.
// Example:
// sourceFilter["source.county"] = "EastBatonRouge";

if (runId !== null) {
sourceFilter["provenance.parser_run_id"] = runId;
}

const fields = [
"permit_number",
"permit_type",
"parcel_number",
"valuation",
"fee",
"applied_date",
"issued_date",
"address",
"owner_name",
"applicant_name",
"contractor_name",
"description"
];

const missingMarkers = [
null, "", " ", "-", "--", "N/A", "NA", "n/a",
"None", "NONE", "null", "NULL", "Not Identified"
];

print("\n=== TOTAL BATON ROUGE RAW RECORDS ===");
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

print("\n=== PERMIT TYPE RESIDENTIAL / COMMERCIAL BREAKDOWN ===");
coll.aggregate([
{
    $match: {
    ...sourceFilter,
    "data.permit_type": { $exists: true, $nin: missingMarkers }
    }
},
{
    $project: {
    permit_type: "$data.permit_type",
    permit_use_match: {
        $regexFind: {
        input: "$data.permit_type",
        regex: /\(([RC])\)/
        }
    }
    }
},
{
    $project: {
    permit_type: 1,
    permit_use: {
        $switch: {
        branches: [
            {
            case: {
                $eq: [
                { $arrayElemAt: ["$permit_use_match.captures", 0] },
                "R"
                ]
            },
            then: "Residential"
            },
            {
            case: {
                $eq: [
                { $arrayElemAt: ["$permit_use_match.captures", 0] },
                "C"
                ]
            },
            then: "Commercial"
            }
        ],
        default: "Unknown"
        }
    }
    }
},
{
    $group: {
    _id: "$permit_use",
    count: { $sum: 1 },
    example_permit_type: { $first: "$permit_type" }
    }
},
{ $sort: { count: -1 } }
]).forEach(doc => printjson(doc));

print("\n=== PERMIT TYPE BASE CATEGORY BREAKDOWN ===");
coll.aggregate([
{
    $match: {
    ...sourceFilter,
    "data.permit_type": { $exists: true, $nin: missingMarkers }
    }
},
{
    $project: {
    permit_type: "$data.permit_type",
    permit_type_base: {
        $trim: {
        input: {
            $replaceAll: {
            input: {
                $replaceAll: {
                input: "$data.permit_type",
                find: " (R)",
                replacement: ""
                }
            },
            find: " (C)",
            replacement: ""
            }
        }
        }
    }
    }
},
{
    $group: {
    _id: "$permit_type_base",
    count: { $sum: 1 },
    example_permit_type: { $first: "$permit_type" }
    }
},
{ $sort: { count: -1 } },
{ $limit: 80 }
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

print("\n=== PERMIT TYPE / VALUATION ZERO VS NONZERO ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    permit_type: "$data.permit_type",
    valuation_raw: "$data.valuation",
    valuation_num: {
        $convert: {
        input: "$data.valuation",
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
{ name: "occupancy", regex: /occupancy/i },
{ name: "electrical", regex: /electrical|service rebuild|meter|panel|wire|wiring/i },
{ name: "plumbing", regex: /plumbing|water heater|sewer|gas|pipe|drain/i },
{ name: "mechanical", regex: /mechanical|duct|hvac|air condition|furnace/i },
{ name: "remodel", regex: /remodel|renovation|alteration|repair/i },
{ name: "flood", regex: /flood/i },
{ name: "sign", regex: /sign/i },
{ name: "roof", regex: /roof/i }
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
    description: "$data.description",
    keyword: {
        $switch: {
        branches: [
            { case: { $regexMatch: { input: "$data.description", regex: /occupancy/i } }, then: "occupancy" },
            { case: { $regexMatch: { input: "$data.description", regex: /electrical|service rebuild|meter|panel|wire|wiring/i } }, then: "electrical" },
            { case: { $regexMatch: { input: "$data.description", regex: /plumbing|water heater|sewer|gas|pipe|drain/i } }, then: "plumbing" },
            { case: { $regexMatch: { input: "$data.description", regex: /mechanical|duct|hvac|air condition|furnace/i } }, then: "mechanical" },
            { case: { $regexMatch: { input: "$data.description", regex: /remodel|renovation|alteration|repair/i } }, then: "remodel_repair" },
            { case: { $regexMatch: { input: "$data.description", regex: /flood/i } }, then: "flood" },
            { case: { $regexMatch: { input: "$data.description", regex: /sign/i } }, then: "sign" },
            { case: { $regexMatch: { input: "$data.description", regex: /roof/i } }, then: "roof" }
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
    "data.permit_type": 1,
    "data.parcel_number": 1,
    "data.valuation": 1,
    "data.fee": 1,
    "data.applied_date": 1,
    "data.issued_date": 1,
    "data.address": 1,
    "data.owner_name": 1,
    "data.applicant_name": 1,
    "data.contractor_name": 1,
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
    "data.description": { $exists: true, $nin: missingMarkers },
    "data.address": { $exists: true, $nin: missingMarkers }
},
{
    _id: 0,
    raw_permit_id: 1,
    "data.permit_number": 1,
    "data.permit_type": 1,
    "data.parcel_number": 1,
    "data.valuation": 1,
    "data.fee": 1,
    "data.applied_date": 1,
    "data.issued_date": 1,
    "data.address": 1,
    "data.owner_name": 1,
    "data.applicant_name": 1,
    "data.contractor_name": 1,
    "data.description": 1,
    "provenance.csv_row_number": 1,
    "provenance.parser_run_id": 1
}
).limit(30).forEach(doc => printjson(doc));