package Config::Parser::fl_collier_naples_xlsx;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        schema => 'staging',
        table_name => 'stg_fl_collier_naples_xlsx',
        skip_lines => 1,
        truncate_if_exists => 0,

        columns => [
            ['permit_number',       'text', 'trim'],
            ['valuation',           'text', undef],
            ['permit_type',         'text', 'trim'],
            ['status',              'text', 'trim'],
            ['address',             'text', 'trim'],
            ['parcel_number',       'text', 'trim'],
            ['issued_date',         'text', undef],
            ['applied_date',        'text', undef],
            ['owner_name',          'text', 'trim'],
            ['owner_location',      'text', 'trim'],
            ['contractor_name',     'text', 'trim'],
            ['contractor_location', 'text', 'trim'],
        ],
    };
}

1;