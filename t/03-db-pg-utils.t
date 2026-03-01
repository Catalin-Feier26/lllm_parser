use strict;
use warnings;
use v5.30;

use lib 'lib';

use Test::More;

use DB::pg ();
use DB::PG::Utils qw(
    table_exists
    create_or_truncate_table
    truncate_table
    drop_table
    create_indexes
    create_unique_indexes
);

my $dbh;
eval { $dbh = DB::pg::connect_db(); 1 }
    or die "Failed to connect: $@";

ok($dbh, 'connected to db');

my $cfg = {
    schema     => 'staging',
    table_name => 'test_utils',

    columns => [
        { name => 'id',            type => 'bigserial',   nullable => 0 },
        { name => 'permit_number', type => 'text',        nullable => 0 },
        { name => 'issued_date',   type => 'date',        nullable => 1 },
        { name => 'run_id',        type => 'text',        nullable => 0 },
        { name => 'loaded_at',     type => 'timestamptz', nullable => 0, default_sql => 'now()' },
    ],

    primary_key => ['id'],

    indexes => [
        { name => 'idx_test_utils_run_id', columns => ['run_id'] },
        { name => 'idx_test_utils_permit', columns => ['permit_number'] },
    ],

    unique_indexes => [
        { name => 'ux_test_utils_key', columns => ['permit_number', 'run_id'] },
    ],

    restart_identity => 1,
};

ok(create_or_truncate_table($dbh, $cfg), 'create_or_truncate_table');

ok(create_indexes($dbh, $cfg), 'create_indexes');
ok(create_unique_indexes($dbh, $cfg), 'create_unique_indexes');

ok(table_exists($dbh, 'staging', 'test_utils'), 'table exists');

$dbh->do(
    'INSERT INTO staging.test_utils (permit_number, issued_date, run_id) VALUES (?, ?, ?)',
    undef,
    'ABC-123', '2025-01-15', 'run_test_1'
);

my ($count) = $dbh->selectrow_array('SELECT count(*) FROM staging.test_utils');
is($count, 1, 'row count after insert is 1');

my $dup_ok = eval {
    $dbh->do(
        'INSERT INTO staging.test_utils (permit_number, issued_date, run_id) VALUES (?, ?, ?)',
        undef,
        'ABC-123', '2025-01-15', 'run_test_1'
    );
    1;
};
ok(!$dup_ok, 'duplicate insert blocked by unique index');

ok(truncate_table($dbh, 'staging', 'test_utils', restart_identity => 1), 'truncate_table');

($count) = $dbh->selectrow_array('SELECT count(*) FROM staging.test_utils');
is($count, 0, 'row count after truncate is 0');

ok(drop_table($dbh, 'staging', 'test_utils'), 'drop_table');

ok(!table_exists($dbh, 'staging', 'test_utils'), 'table dropped');

done_testing();