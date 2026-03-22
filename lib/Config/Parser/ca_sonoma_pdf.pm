package Config::Parser::ca_sonoma_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        skip_lines           => 1,
        clear_target_on_load => 1,
        target_collection    => 'raw_permits',

        columns => [
            ['permit_number', 'trim'],
            ['status',        'trim'],
            ['permit_type',   'trim'],
            ['applied_date',  undef],
            ['issued_date',   undef],
            ['address',       'trim'],
            ['parcel_number', 'trim'],
            ['fee',           undef],
            ['valuation',     undef],
            ['description',   'trim'],
        ],
    };
}

1;