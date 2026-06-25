package Config::Parser::ca_sonoma_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        config_version       => '1.0',
        record_type          => 'permit',
        target_collection    => 'raw_permits',
        clear_target_on_load => 0,

        source => {
            state        => 'CA',
            county       => 'Sonoma',
            municipality => 'PermitSonoma',
        },

        csv => {
            skip_lines => 1,
            sep_char   => ',',
            batch_size => 500,
        },

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
