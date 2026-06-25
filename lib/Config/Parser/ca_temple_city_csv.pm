package Config::Parser::ca_temple_city_csv;

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
            municipality => 'TempleCity',
        },

        csv => {
            skip_lines => 1,
            sep_char   => ',',
            batch_size => 500,
        },

        columns => [
            ['address',         'trim'],
            ['parcel_number',   'trim'],
            ['permit_number',   'trim'],
            ['permit_type',     'trim'],
            ['description',     'trim'],
            ['valuation',       undef],
            ['status',          'trim'],
            ['applied_date',    undef],
            ['issued_date',     undef],
            ['contractor_name', 'trim'],
        ],
    };
}

1;
