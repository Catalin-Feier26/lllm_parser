use strict;
use warnings;

use lib 'lib';
use DB::pg;

my $dbh = DB::pg::connect_db();

my $dbh = DB::pg::connect_db();

my ($now) = $dbh->selectrow_array('SELECT NOW()');
print "DB OK. now(): $now\n";

$dbh->do('CREATE TABLE IF NOT EXISTS db_test (id serial primary key, msg text)');
$dbh->do('INSERT INTO db_test(msg) VALUES (?)', undef, 'hello from perl');
my ($count) = $dbh->selectrow_array('SELECT count(*) FROM db_test');
print "db_test rows: $count\n";