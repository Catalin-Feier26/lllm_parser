package Config::Parser::co_larimer_countywide_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        schema => 'staging',
        table_name => 'stg_co_larimer_countywide_pdf',
        skip_lines => 1,
        truncate_if_exists => 0,

        columns => [
            ['permit_number',   'text', 'trim'],
            ['permit_type',     'text', 'trim'],
            ['status',          'text', 'trim'],
            ['issued_date',     'text', undef],
            ['parcel_number',   'text', 'trim'],
            ['address',         'text', 'trim'],
            ['valuation',       'text', undef],
            ['fee',             'text', undef],
            ['owner_name',      'text', 'trim'],
            ['contractor_name', 'text', 'trim'],
        ],
    };
}

1;