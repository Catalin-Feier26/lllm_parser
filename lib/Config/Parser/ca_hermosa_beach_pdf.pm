package Config::Parser::ca_hermosa_beach_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        schema => 'staging',
        table_name => 'stg_ca_hermosa_beach_pdf',
        skip_lines => 1,
        truncate_if_exists => 1,

        columns => [
            ['permit_number', 'text', 'trim'],
            ['permit_type', 'text', 'trim'],
            ['sub_type', 'text', 'trim'],
            ['status', 'text', 'trim'],
            ['parcel_number', 'text', 'trim'],
            ['issued_date', 'text', undef],
            ['address', 'text', 'trim'],
            ['description', 'text', 'trim'],
            ['owner_name', 'text', 'trim'],
            ['contractor_name', 'text', 'trim'],
            ['valuation', 'text', undef],
            ['fee', 'text', undef],
            ['paid_fee', 'text', undef],
        ],
    };
}

1;