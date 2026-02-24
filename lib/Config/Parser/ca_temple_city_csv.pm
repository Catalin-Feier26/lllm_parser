package Config::Parser::ca_temple_city_csv;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        schema => 'staging',
        table_name => 'stg_ca_temple_city_csv',
        skip_lines => 1,
        truncate_if_exists => 0,

        columns => [
            ['address',         'text', 'trim'],
            ['parcel_number',   'text', 'trim'],
            ['permit_number',   'text', 'trim'],
            ['permit_type',     'text', 'trim'],
            ['description',     'text', 'trim'],
            ['valuation',       'text', undef],
            ['status',          'text', 'trim'],
            ['applied_date',    'text', undef],
            ['issued_date',     'text', undef],
            ['contractor_name', 'text', 'trim'],
        ],
    };
}

1;
