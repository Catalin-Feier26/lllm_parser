const coll = db.raw_permits;

const runId = "run_20260624_215219_1133";

const sourceFilter = {
"source.state": "CO",
"source.county": "Larimer",
"source.municipality": "CountyWide",
"provenance.parser_run_id": runId
};

// For all Larimer runs later, use this instead:
// const sourceFilter = {
//   "source.state": "CO",
//   "source.county": "Larimer",
//   "source.municipality": "CountyWide"
// };

const fields = [
"permit_number",
"permit_type",
"status",
"issued_date",
"parcel_number",
"address",
"valuation",
"fee",
"owner_name",
"contractor_name"
];

const missingMarkers = [
null, "", " ", "-", "--", "N/A", "NA", "n/a",
"None", "NONE", "null", "NULL", "Not Identified"
];

print("\n=== TOTAL LARIMER RAW RECORDS ===");
printjson({
total_records: coll.countDocuments(sourceFilter)
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
        config_module: "$provenance.config_module"
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
{ $limit: 50 }
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

print("\n=== PERMIT NUMBER CATEGORY BREAKDOWN ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    permit_number: "$data.permit_number",
    permit_type: "$data.permit_type",
    status: "$data.status",
    permit_number_category_match: {
        $regexFind: {
        input: "$data.permit_number",
        regex: /^\d{2}-([A-Z]+)/
        }
    }
    }
},
{
    $project: {
    permit_number: 1,
    permit_type: 1,
    status: 1,
    permit_number_category: {
        $ifNull: [
        { $arrayElemAt: ["$permit_number_category_match.captures", 0] },
        "UNKNOWN"
        ]
    }
    }
},
{
    $group: {
    _id: "$permit_number_category",
    count: { $sum: 1 },
    example_permit_number: { $first: "$permit_number" },
    example_permit_type: { $first: "$permit_type" }
    }
},
{ $sort: { count: -1 } }
]).forEach(doc => printjson(doc));

print("\n=== PERMIT NUMBER CATEGORY / PERMIT TYPE COMBINATIONS ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $project: {
    permit_number: "$data.permit_number",
    permit_type: "$data.permit_type",
    status: "$data.status",
    permit_number_category_match: {
        $regexFind: {
        input: "$data.permit_number",
        regex: /^\d{2}-([A-Z]+)/
        }
    }
    }
},
{
    $project: {
    permit_number: 1,
    permit_type: 1,
    status: 1,
    permit_number_category: {
        $ifNull: [
        { $arrayElemAt: ["$permit_number_category_match.captures", 0] },
        "UNKNOWN"
        ]
    }
    }
},
{
    $group: {
    _id: {
        permit_number_category: "$permit_number_category",
        permit_type: "$permit_type"
    },
    count: { $sum: 1 },
    example_permit_number: { $first: "$permit_number" }
    }
},
{ $sort: { count: -1 } },
{ $limit: 80 }
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
    "data.status": 1,
    "data.issued_date": 1,
    "data.parcel_number": 1,
    "data.address": 1,
    "data.valuation": 1,
    "data.fee": 1,
    "data.owner_name": 1,
    "data.contractor_name": 1,
    "provenance.csv_row_number": 1
}
).limit(30).forEach(doc => printjson(doc));

print("\n=== COMPLETE-ISH RECORDS FOR PATTERN ANALYSIS ===");
coll.find(
{
    ...sourceFilter,
    "data.permit_number": { $exists: true, $nin: missingMarkers },
    "data.permit_type": { $exists: true, $nin: missingMarkers },
    "data.status": { $exists: true, $nin: missingMarkers },
    "data.address": { $exists: true, $nin: missingMarkers }
},
{
    _id: 0,
    raw_permit_id: 1,
    "data.permit_number": 1,
    "data.permit_type": 1,
    "data.status": 1,
    "data.issued_date": 1,
    "data.parcel_number": 1,
    "data.address": 1,
    "data.valuation": 1,
    "data.fee": 1,
    "data.owner_name": 1,
    "data.contractor_name": 1,
    "provenance.csv_row_number": 1
}
).limit(30).forEach(doc => printjson(doc));