use strict;
use warnings;
use v5.30;

use lib 'lib';

use Test::More;

use DB::pg ();

my $dbh;
eval { $dbh = DB::pg::connect_db(); 1 }
    or die "Failed to connect: $@";

ok($dbh, 'got dbh');

my ($now) = $dbh->selectrow_array('SELECT NOW()');
ok($now, 'SELECT NOW() returned a value');

$dbh->do('CREATE SCHEMA IF NOT EXISTS staging');

$dbh->do(q{
    CREATE TABLE IF NOT EXISTS staging.db_test (
        id  serial PRIMARY KEY,
        msg text
    )
});

$dbh->do('TRUNCATE staging.db_test RESTART IDENTITY');

$dbh->do('INSERT INTO staging.db_test(msg) VALUES (?)', undef, 'hello from perl');

my ($count) = $dbh->selectrow_array('SELECT count(*) FROM staging.db_test');
is($count, 1, 'row count after insert is 1');

my ($msg) = $dbh->selectrow_array('SELECT msg FROM staging.db_test WHERE id = 1');
is($msg, 'hello from perl', 'inserted message matches');

done_testing();