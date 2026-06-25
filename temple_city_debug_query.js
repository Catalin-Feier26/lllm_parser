    const coll = db.raw_permits;

    // Optional: set this if you want only one parser run.
    // Example:
    // const runId = "run_20260625_xxxxxx_xxxx";
    const runId = null;

    let sourceFilter = {
    "source.state": "CA",
    "source.municipality": /Temple/i
    };

    // If needed after checking source breakdown, add county:
    // sourceFilter["source.county"] = "LosAngeles";

    if (runId !== null) {
    sourceFilter["provenance.parser_run_id"] = runId;
    }

    const fields = [
    "address",
    "parcel_number",
    "permit_number",
    "permit_type",
    "description",
    "valuation",
    "status",
    "applied_date",
    "issued_date",
    "contractor_name",
    "owner_name",
    "fee"
    ];

    const missingMarkers = [
    null, "", " ", "-", "--", "N/A", "NA", "n/a",
    "None", "NONE", "null", "NULL", "Not Identified"
    ];

    print("\n=== TOTAL TEMPLE CITY RAW RECORDS ===");
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
            input: "$data.permit_number",
            regex: /^([A-Z]+)/
            }
        },
        permit_number_year_match: {
            $regexFind: {
            input: "$data.permit_number",
            regex: /^[A-Z](\d{2})-/
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

    print("\n=== CONTRACTOR TOP VALUES ===");
    coll.aggregate([
    {
        $match: {
        ...sourceFilter,
        "data.contractor_name": { $exists: true, $nin: missingMarkers }
        }
    },
    {
        $group: {
        _id: "$data.contractor_name",
        count: { $sum: 1 }
        }
    },
    { $sort: { count: -1 } },
    { $limit: 50 }
    ]).forEach(doc => printjson(doc));

    print("\n=== VALUATION ZERO / NONZERO BREAKDOWN ===");
    coll.aggregate([
    { $match: sourceFilter },
    {
        $project: {
        permit_type: "$data.permit_type",
        status: "$data.status",
        valuation_raw: "$data.valuation",
        valuation_clean: {
            $replaceAll: {
            input: {
                $replaceAll: {
                input: { $toString: "$data.valuation" },
                find: "$",
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
    { name: "addition", regex: /addition|add/i },
    { name: "adu", regex: /adu|accessory dwelling/i },
    { name: "garage", regex: /garage/i },
    { name: "remodel", regex: /remodel|interior remodel|renovation|alteration/i },
    { name: "bathroom", regex: /bathroom|bath/i },
    { name: "kitchen", regex: /kitchen/i },
    { name: "roof", regex: /roof|reroof|re-roof|shingle/i },
    { name: "solar", regex: /solar|module|battery|powerwall/i },
    { name: "sign", regex: /sign|channel letters/i },
    { name: "window", regex: /window|egress/i },
    { name: "pool", regex: /pool|spa/i },
    { name: "demolition", regex: /demo|demolition|demolish/i }
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

    print("\n=== STATUS / DESCRIPTION KEYWORD COMBINATIONS ===");
    coll.aggregate([
    { $match: sourceFilter },
    {
        $project: {
        status: "$data.status",
        permit_type: "$data.permit_type",
        description: "$data.description",
        keyword: {
            $switch: {
            branches: [
                { case: { $regexMatch: { input: "$data.description", regex: /adu|accessory dwelling/i } }, then: "adu" },
                { case: { $regexMatch: { input: "$data.description", regex: /addition|add/i } }, then: "addition" },
                { case: { $regexMatch: { input: "$data.description", regex: /garage/i } }, then: "garage" },
                { case: { $regexMatch: { input: "$data.description", regex: /remodel|interior remodel|renovation|alteration/i } }, then: "remodel" },
                { case: { $regexMatch: { input: "$data.description", regex: /bathroom|bath/i } }, then: "bathroom" },
                { case: { $regexMatch: { input: "$data.description", regex: /kitchen/i } }, then: "kitchen" },
                { case: { $regexMatch: { input: "$data.description", regex: /roof|reroof|re-roof|shingle/i } }, then: "roof" },
                { case: { $regexMatch: { input: "$data.description", regex: /solar|module|battery|powerwall/i } }, then: "solar" },
                { case: { $regexMatch: { input: "$data.description", regex: /sign|channel letters/i } }, then: "sign" },
                { case: { $regexMatch: { input: "$data.description", regex: /window|egress/i } }, then: "window" },
                { case: { $regexMatch: { input: "$data.description", regex: /pool|spa/i } }, then: "pool" },
                { case: { $regexMatch: { input: "$data.description", regex: /demo|demolition|demolish/i } }, then: "demolition" }
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
        "data.address": 1,
        "data.parcel_number": 1,
        "data.permit_number": 1,
        "data.permit_type": 1,
        "data.description": 1,
        "data.valuation": 1,
        "data.status": 1,
        "data.applied_date": 1,
        "data.issued_date": 1,
        "data.contractor_name": 1,
        "data.owner_name": 1,
        "data.fee": 1,
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
        "data.status": { $exists: true, $nin: missingMarkers },
        "data.address": { $exists: true, $nin: missingMarkers }
    },
    {
        _id: 0,
        raw_permit_id: 1,
        "data.address": 1,
        "data.parcel_number": 1,
        "data.permit_number": 1,
        "data.permit_type": 1,
        "data.description": 1,
        "data.valuation": 1,
        "data.status": 1,
        "data.applied_date": 1,
        "data.issued_date": 1,
        "data.contractor_name": 1,
        "provenance.csv_row_number": 1,
        "provenance.parser_run_id": 1
    }
    ).limit(30).forEach(doc => printjson(doc));