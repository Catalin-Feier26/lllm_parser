package Config::Parser::la_east_baton_rouge_parish_csv;

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
            state        => 'LA',
            county       => 'EastBatonRougeParish',
            municipality => 'BatonRouge',
        },

        csv => {
            skip_lines => 1,
            sep_char   => ',',
            batch_size => 500,
        },

        columns => [
            ['permit_number',   'trim'],
            ['permit_type',     'trim'],
            ['parcel_number',   'trim'],
            ['valuation',       undef],
            ['fee',             undef],
            ['applied_date',    undef],
            ['issued_date',     undef],
            ['address',         'trim'],
            ['owner_name',      'trim'],
            ['applicant_name',  'trim'],
            ['contractor_name', 'trim'],
            ['description',     'trim'],
        ],
    };
}

1;
