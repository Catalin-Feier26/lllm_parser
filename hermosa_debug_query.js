const coll = db.raw_permits;

const sourceFilter = {
"source.municipality": "HermosaBeach",
"source.state": "CA",
"source.county": "LosAngeles"
};

const fields = [
"permit_number",
"status",
"description",
"parcel_number",
"paid_fee",
"sub_type",
"issued_date",
"owner_name",
"address",
"permit_type",
"fee",
"valuation",
"contractor_name",
"contractor_address",
"contractor_phone"
];

const missingMarkers = [
null, "", " ", "-", "--", "N/A", "NA", "n/a",
"None", "NONE", "null", "NULL"
];

print("\n=== TOTAL HERMOSA BEACH RAW RECORDS ===");
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

print("\n=== TOP VALUES: CATEGORICAL / IMPORTANT FIELDS ===");
[
"permit_type",
"sub_type",
"status",
"paid_fee",
"fee",
"valuation"
].forEach(field => {
const path = "data." + field;

print("\n--- TOP VALUES: " + field + " ---");
coll.aggregate([
    {
    $match: {
        ...sourceFilter,
        [path]: { $exists: true, $nin: missingMarkers }
    }
    },
    {
    $group: {
        _id: "$" + path,
        count: { $sum: 1 }
    }
    },
    { $sort: { count: -1 } },
    { $limit: 25 }
]).forEach(doc => printjson(doc));
});

print("\n=== TOP PERMIT TYPE / SUB TYPE / STATUS COMBINATIONS ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $group: {
    _id: {
        permit_type: "$data.permit_type",
        sub_type: "$data.sub_type",
        status: "$data.status"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 30 }
]).forEach(doc => printjson(doc));

print("\n=== TOP PERMIT TYPE / SUB TYPE / PAID FEE COMBINATIONS ===");
coll.aggregate([
{ $match: sourceFilter },
{
    $group: {
    _id: {
        permit_type: "$data.permit_type",
        sub_type: "$data.sub_type",
        paid_fee: "$data.paid_fee"
    },
    count: { $sum: 1 }
    }
},
{ $sort: { count: -1 } },
{ $limit: 30 }
]).forEach(doc => printjson(doc));

print("\n=== SAMPLE RECORDS WITH MISSING IMPORTANT FIELDS ===");
coll.find(
{
    ...sourceFilter,
    $or: [
    { "data.permit_type": { $exists: false } },
    { "data.permit_type": { $in: missingMarkers } },
    { "data.sub_type": { $exists: false } },
    { "data.sub_type": { $in: missingMarkers } },
    { "data.valuation": { $exists: false } },
    { "data.valuation": { $in: missingMarkers } },
    { "data.fee": { $exists: false } },
    { "data.fee": { $in: missingMarkers } },
    { "data.paid_fee": { $exists: false } },
    { "data.paid_fee": { $in: missingMarkers } },
    { "data.contractor_name": { $exists: false } },
    { "data.contractor_name": { $in: missingMarkers } },
    { "data.owner_name": { $exists: false } },
    { "data.owner_name": { $in: missingMarkers } }
    ]
},
{
    raw_permit_id: 1,
    source: 1,
    "data.permit_number": 1,
    "data.status": 1,
    "data.permit_type": 1,
    "data.sub_type": 1,
    "data.issued_date": 1,
    "data.address": 1,
    "data.parcel_number": 1,
    "data.description": 1,
    "data.paid_fee": 1,
    "data.fee": 1,
    "data.valuation": 1,
    "data.owner_name": 1,
    "data.contractor_name": 1,
    provenance: 1
}
).limit(20).forEach(doc => printjson(doc));

print("\n=== COMPLETE-ISH RECORDS FOR PATTERN ANALYSIS ===");
coll.find(
{
    ...sourceFilter,
    "data.permit_number": { $exists: true, $nin: missingMarkers },
    "data.permit_type": { $exists: true, $nin: missingMarkers },
    "data.sub_type": { $exists: true, $nin: missingMarkers },
    "data.status": { $exists: true, $nin: missingMarkers },
    "data.description": { $exists: true, $nin: missingMarkers },
    "data.address": { $exists: true, $nin: missingMarkers }
},
{
    raw_permit_id: 1,
    "data.permit_number": 1,
    "data.status": 1,
    "data.permit_type": 1,
    "data.sub_type": 1,
    "data.issued_date": 1,
    "data.address": 1,
    "data.parcel_number": 1,
    "data.description": 1,
    "data.paid_fee": 1,
    "data.fee": 1,
    "data.valuation": 1,
    "data.owner_name": 1,
    "data.contractor_name": 1
}
).limit(20).forEach(doc => printjson(doc));