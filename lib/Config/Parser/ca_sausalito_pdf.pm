package Config::Parser::ca_sausalito_pdf;

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
            ['address',         'trim'],
            ['valuation',       undef],
            ['issued_date',     undef],
            ['subtype',         'trim'],
            ['parcel_number',   'trim'],
            ['fee',             undef],
            ['applied_date',    undef],
            ['status',          'trim'],
            ['paid_fee',        undef],
            ['owner_name',      'trim'],
            ['contractor_name', 'trim'],
        ],
    };
}

1;