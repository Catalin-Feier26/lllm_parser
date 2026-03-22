package Config::Parser::la_east_baton_rouge_parish_csv;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        skip_lines           => 1,
        clear_target_on_load => 1,
        target_collection    => 'raw_permits',

        columns => [
            ['permit_number',   'trim'],
            ['permit_type',     'trim'],
            ['parcel_number',   'trim'],
            ['valuation',       undef],
            ['fee',             undef],
            ['applied_date',    undef],
            ['issued_date',     undef],
            ['address',         'trim'],
            ['owner_name',      'trim'],
            ['applicant_name',  'trim'],
            ['contractor_name', 'trim'],
            ['description',     'trim'],
        ],
    };
}

1;