package Config::Parser::ca_sonoma_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        schema => 'staging',
        table_name => 'stg_ca_sonoma_pdf',
        skip_lines => 1,
        truncate_if_exists => 0,

        columns => [
            ['permit_number', 'text', 'trim'],
            ['status',        'text', 'trim'],
            ['permit_type',   'text', 'trim'],
            ['applied_date',  'text', undef],
            ['issued_date',   'text', undef],
            ['address',       'text', 'trim'],
            ['parcel_number', 'text', 'trim'],
            ['fee',           'text', undef],
            ['valuation',     'text', undef],
            ['description',   'text', 'trim'],
        ],
    };
}

1;