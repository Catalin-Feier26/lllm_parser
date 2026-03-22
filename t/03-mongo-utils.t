use strict;
use warnings;
use v5.30;

use Test::More;
use lib 'lib';

BEGIN {
    use_ok('DB::Mongo::Utils', qw(
        get_collection
        insert_one_doc
        insert_many_docs
        find_one_doc
        find_docs
        update_one_doc
        upsert_one_doc
        delete_one_doc
        delete_many_docs
        clear_collection
        drop_collection
        create_indexes
        count_docs
        document_exists
    ));
}

my $collection_name = 'test_mongo_utils';

eval {
    clear_collection($collection_name);
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("Could not clear test collection before tests: $error");
};

pass('Test collection cleared before starting');

my $insert_one_result;
eval {
    $insert_one_result = insert_one_doc($collection_name, {
        permit_number => 'P-1001',
        owner_name    => 'Alice Johnson',
        city          => 'Cluj-Napoca',
        status        => 'raw',
    });
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("insert_one_doc failed: $error");
};

ok(defined $insert_one_result, 'insert_one_doc returned a result');
ok(defined $insert_one_result->inserted_id, 'insert_one_doc returned inserted_id');

my $doc = find_one_doc($collection_name, { permit_number => 'P-1001' });

ok(defined $doc, 'find_one_doc found inserted document');
is($doc->{owner_name}, 'Alice Johnson', 'Inserted document has correct owner_name');
is($doc->{status}, 'raw', 'Inserted document has correct status');

my $insert_many_result;
eval {
    $insert_many_result = insert_many_docs($collection_name, [
        {
            permit_number => 'P-1002',
            owner_name    => 'Bob Smith',
            city          => 'Bucharest',
            status        => 'raw',
        },
        {
            permit_number => 'P-1003',
            owner_name    => 'Carol White',
            city          => 'Iasi',
            status        => 'normalized',
        },
    ]);
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("insert_many_docs failed: $error");
};

ok(defined $insert_many_result, 'insert_many_docs returned a result');

my $count = count_docs($collection_name);
is($count, 3, 'count_docs returns 3 documents after inserts');

my $all_docs = find_docs($collection_name, {});
ok(ref $all_docs eq 'ARRAY', 'find_docs returned an arrayref');
is(scalar @$all_docs, 3, 'find_docs returned 3 documents');

my $update_result;
eval {
    $update_result = update_one_doc(
        $collection_name,
        { permit_number => 'P-1001' },
        { '$set' => { status => 'normalized' } },
    );
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("update_one_doc failed: $error");
};

ok(defined $update_result, 'update_one_doc returned a result');

$doc = find_one_doc($collection_name, { permit_number => 'P-1001' });
is($doc->{status}, 'normalized', 'update_one_doc updated the document');

my $upsert_result;
eval {
    $upsert_result = upsert_one_doc(
        $collection_name,
        { permit_number => 'P-2000' },
        { '$set' => {
            permit_number => 'P-2000',
            owner_name    => 'David Green',
            city          => 'Timisoara',
            status        => 'validated',
        }},
    );
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("upsert_one_doc failed: $error");
};

ok(defined $upsert_result, 'upsert_one_doc returned a result');
ok(document_exists($collection_name, { permit_number => 'P-2000' }), 'document_exists finds upserted document');

$count = count_docs($collection_name);
is($count, 4, 'count_docs returns 4 documents after upsert');

my $delete_one_result;
eval {
    $delete_one_result = delete_one_doc($collection_name, { permit_number => 'P-1002' });
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("delete_one_doc failed: $error");
};

ok(defined $delete_one_result, 'delete_one_doc returned a result');
ok(!document_exists($collection_name, { permit_number => 'P-1002' }), 'Deleted document no longer exists');

$count = count_docs($collection_name);
is($count, 3, 'count_docs returns 3 documents after delete_one_doc');

my $index_result;
eval {
    $index_result = create_indexes($collection_name, [
        {
            keys    => { permit_number => 1 },
            options => { unique => 1, name => 'permit_number_unique_idx' },
        },
        {
            keys    => { city => 1 },
            options => { name => 'city_idx' },
        },
    ]);
    1;
} or do {
    my $error = $@ || 'Unknown error';
    BAIL_OUT("create_indexes failed: $error");
};

ok(ref $index_result eq 'ARRAY', 'create_indexes returned an arrayref');
is(scalar @$index_result, 2, 'create_indexes created 2 indexes');

eval {
    clear_collection($collection_name);
    1;
} or do {
    my $error = $@ || 'Unknown error';
    diag("Final cleanup failed: $error");
};

is(count_docs($collection_name), 0, 'Collection is empty after final cleanup');

done_testing();