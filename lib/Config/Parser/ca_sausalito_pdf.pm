package Config::Parser::ca_sausalito_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        schema => 'staging',
        table_name => 'stg_ca_sausalito_pdf',
        skip_lines => 1,
        truncate_if_exists => 1,

        columns => [
            ['permit_number',   'text', 'trim'],
            ['permit_type',     'text', 'trim'],
            ['address',         'text', 'trim'],
            ['valuation',       'text', undef],
            ['issued_date',     'text', undef],
            ['subtype',         'text', 'trim'],
            ['parcel_number',   'text', 'trim'],
            ['fee',             'text', undef],
            ['applied_date',    'text', undef],
            ['status',          'text', 'trim'],
            ['paid_fee',        'text', undef],
            ['owner_name',      'text', 'trim'],
            ['contractor_name', 'text', 'trim'],
        ],
    };
}

1;