package Config::Parser::fl_collier_naples_xlsx;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        skip_lines           => 1,
        clear_target_on_load => 1,
        target_collection    => 'raw_permits',

        columns => [
            ['permit_number',       'trim'],
            ['valuation',           undef],
            ['permit_type',         'trim'],
            ['status',              'trim'],
            ['address',             'trim'],
            ['parcel_number',       'trim'],
            ['issued_date',         undef],
            ['applied_date',        undef],
            ['owner_name',          'trim'],
            ['owner_location',      'trim'],
            ['contractor_name',     'trim'],
            ['contractor_location', 'trim'],
        ],
    };
}

1;