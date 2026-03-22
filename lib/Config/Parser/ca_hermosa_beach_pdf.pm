package Config::Parser::ca_hermosa_beach_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        skip_lines => 1,
        clear_target_on_load => 1,
        target_collection    => 'raw_permits',

        columns => [
            ['permit_number',   'trim'],
            ['permit_type',     'trim'],
            ['sub_type',        'trim'],
            ['status',          'trim'],
            ['parcel_number',   'trim'],
            ['issued_date',     undef],
            ['address',         'trim'],
            ['description',     'trim'],
            ['owner_name',      'trim'],
            ['contractor_name', 'trim'],
            ['valuation',       undef],
            ['fee',             undef],
            ['paid_fee',        undef],
        ],
    };
}

1;