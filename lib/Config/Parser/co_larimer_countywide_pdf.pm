package Config::Parser::co_larimer_countywide_pdf;

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
            state        => 'CO',
            county       => 'Larimer',
            municipality => 'CountyWide',
        },

        csv => {
            skip_lines => 1,
            sep_char   => ',',
            batch_size => 500,
        },

        columns => [
            ['permit_number',   'trim'],
            ['permit_type',     'trim'],
            ['status',          'trim'],
            ['issued_date',     undef],
            ['parcel_number',   'trim'],
            ['address',         'trim'],
            ['valuation',       undef],
            ['fee',             undef],
            ['owner_name',      'trim'],
            ['contractor_name', 'trim'],
        ],
    };
}

1;
