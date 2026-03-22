package Config::Parser::co_larimer_countywide_pdf;

use strict;
use warnings;
use v5.30;

sub config {
    return {
        skip_lines           => 1,
        clear_target_on_load => 1,
        target_collection    => 'raw_permits',

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