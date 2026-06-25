package Config::Parser::ca_hermosa_beach_pdf;

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
            county       => 'LosAngeles',
            municipality => 'HermosaBeach',
        },

        csv => {
            skip_lines => 1,
            sep_char   => ',',
            batch_size => 500,
        },

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
