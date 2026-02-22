use strict;
use warnings;
use v5.30;

use lib 'lib';

use DB::pg;
use DB::Pg::Utils ();

my $dbh = DB::pg::connect_db();

my ($now) = $dbh->selectrow_array('SELECT now()');
print "DB OK. now() = $now\n";

my $cfg = {
    schema     => 'staging',
    table_name => 'test_utils',

    columns => [
        { name => 'id',         type => 'bigserial', nullable => 0 },
        { name => 'permit_number', type => 'text',   nullable => 0 },
        { name => 'issued_date', type => 'date',     nullable => 1 },
        { name => 'run_id',     type => 'text',      nullable => 0 },
        { name => 'loaded_at',  type => 'timestamptz', nullable => 0, default_sql => 'now()' },
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

print "Ensuring schema/table...\n";
DB::Pg::Utils::create_or_truncate_table($dbh, $cfg);

print "Creating indexes...\n";
DB::Pg::Utils::create_indexes($dbh, $cfg);
DB::Pg::Utils::create_unique_indexes($dbh, $cfg);

print "Checking exists...\n";
die "Table should exist but doesn't\n"
    unless DB::Pg::Utils::table_exists($dbh, 'staging', 'test_utils');

print "Inserting a row...\n";
$dbh->do(
    'INSERT INTO staging.test_utils (permit_number, issued_date, run_id) VALUES (?, ?, ?)',
    undef,
    'ABC-123', '2025-01-15', 'run_test_1'
);

my ($count) = $dbh->selectrow_array('SELECT count(*) FROM staging.test_utils');
print "Row count after insert: $count\n";
die "Expected 1 row\n" unless $count == 1;

print "Testing unique index (should fail on duplicate)...\n";
my $dup_ok = eval {
    $dbh->do(
        'INSERT INTO staging.test_utils (permit_number, issued_date, run_id) VALUES (?, ?, ?)',
        undef,
        'ABC-123', '2025-01-15', 'run_test_1'
    );
    1;
};
if ($dup_ok) {
    die "ERROR: duplicate insert succeeded; unique index not working\n";
} else {
    print "Duplicate insert blocked (good)\n";
}

print "Truncating...\n";
DB::Pg::Utils::truncate_table($dbh, 'staging', 'test_utils', restart_identity => 1);

($count) = $dbh->selectrow_array('SELECT count(*) FROM staging.test_utils');
print "Row count after truncate: $count\n";
die "Expected 0 rows\n" unless $count == 0;

print "Dropping...\n";
DB::Pg::Utils::drop_table($dbh, 'staging', 'test_utils');

my $exists = DB::Pg::Utils::table_exists($dbh, 'staging', 'test_utils');
die "Table should be dropped but still exists\n" if $exists;

print "ALL GOOD\n";