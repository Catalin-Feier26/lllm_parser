package Config::Parser::la_east_baton_rouge_parish_csv;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        schema => 'staging',
        table_name => 'stg_la_east_baton_rouge_parish_csv',
        skip_lines => 1,
        truncate_if_exists => 0,

        columns => [
            ['permit_number',   'text', 'trim'],
            ['permit_type',     'text', 'trim'],
            ['parcel_number',   'text', 'trim'],
            ['valuation',       'text', undef],
            ['fee',             'text', undef],
            ['applied_date',    'text', undef],
            ['issued_date',     'text', undef],
            ['address',         'text', 'trim'],
            ['owner_name',      'text', 'trim'],
            ['applicant_name',  'text', 'trim'],
            ['contractor_name', 'text', 'trim'],
            ['description',     'text', 'trim'],
        ],
    };
}

1;