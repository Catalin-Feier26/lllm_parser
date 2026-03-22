use strict;
use warnings;
use v5.30;

use Test::More;
use lib 'lib';

BEGIN {
    use_ok('DB::Mongo::Connection');
}

my $db;
eval {
    $db = DB::Mongo::Connection::get_db();
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("Could not connect to MongoDB: $error");
};

ok(defined $db, 'Database handle was returned');

my $collection_name = 'test_connection';
my $collection      = $db->get_collection($collection_name);

ok(defined $collection, 'Collection handle was returned');

my $inserted_id;
eval {
    my $result = $collection->insert_one({
        message    => 'MongoDB test connection works',
        test_file  => '02-mongo-connect.t',
        created_at => scalar localtime,
    });

    $inserted_id = $result->inserted_id;
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("Could not insert test document: $error");
};

ok(defined $inserted_id, 'Inserted document has an id');

eval {
    $collection->delete_one({ _id => $inserted_id });
    1;
} or do {
    my $error = $@ || 'Unknown error';
    diag("Cleanup failed: $error");
};

pass('Cleanup completed or was attempted');

done_testing();