package Config::Parser::fl_collier_naples_xlsx;

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
            state        => 'FL',
            county       => 'Collier',
            municipality => 'Naples',
        },

        csv => {
            skip_lines => 1,
            sep_char   => ',',
            batch_size => 500,
        },

        columns => [
            ['permit_number',       'trim'],
            ['valuation',           undef],
            ['building_type',       'trim'],
            ['permit_class',        'trim'],
            ['permit_type',         'trim'],
            ['status',              'trim'],
            ['address',             'trim'],
            ['parcel_number',       'trim'],
            ['issued_date',         undef],
            ['applied_date',        undef],
            ['total_sf',            undef],
            ['total_units',         undef],
            ['const_type',          'trim'],
            ['owner_name',          'trim'],
            ['owner_city',          'trim'],
            ['owner_state',         'trim'],
            ['owner_zip',           'trim'],
            ['owner_location',      'trim'],
            ['contractor_type',     'trim'],
            ['license_number',      'trim'],
            ['contractor_name',     'trim'],
            ['contractor_city',     'trim'],
            ['contractor_state',    'trim'],
            ['contractor_zip',      'trim'],
            ['contractor_location', 'trim'],
        ],
    };
}

1;
