package Config::Parser::ca_temple_city_csv;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        skip_lines           => 1,
        clear_target_on_load => 1,
        target_collection    => 'raw_permits',

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