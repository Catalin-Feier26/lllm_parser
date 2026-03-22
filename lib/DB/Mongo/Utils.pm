package DB::Mongo::Utils;

use strict;
use warnings;
use v5.30;

use Exporter 'import';

use DB::Mongo::Connection ();

our @EXPORT_OK = qw(
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
);

sub get_collection {
    my ($collection_name) = @_;

    die "Missing collection name\n"
        unless defined $collection_name && length $collection_name;

    my $db = DB::Mongo::Connection::get_db();

    return $db->get_collection($collection_name);
}

sub insert_one_doc {
    my ($collection_name, $doc) = @_;

    die "Missing document for insert_one_doc\n"
        unless defined $doc && ref $doc eq 'HASH';

    my $collection = get_collection($collection_name);
    my $result     = $collection->insert_one($doc);

    return $result;
}

sub insert_many_docs {
    my ($collection_name, $docs) = @_;

    die "Missing documents for insert_many_docs\n"
        unless defined $docs && ref $docs eq 'ARRAY';

    my $collection = get_collection($collection_name);
    my $result     = $collection->insert_many($docs);

    return $result;
}

sub find_one_doc {
    my ($collection_name, $filter, $options) = @_;

    $filter  //= {};
    $options //= {};

    die "Filter must be a hashref\n"
        unless ref $filter eq 'HASH';

    die "Options must be a hashref\n"
        unless ref $options eq 'HASH';

    my $collection = get_collection($collection_name);

    return $collection->find_one($filter, $options);
}

sub find_docs {
    my ($collection_name, $filter, $options) = @_;

    $filter  //= {};
    $options //= {};

    die "Filter must be a hashref\n"
        unless ref $filter eq 'HASH';

    die "Options must be a hashref\n"
        unless ref $options eq 'HASH';

    my $collection = get_collection($collection_name);
    my $cursor     = $collection->find($filter, $options);

    my @docs = $cursor->all;

    return \@docs;
}

sub update_one_doc {
    my ($collection_name, $filter, $update, $options) = @_;

    $options //= {};

    die "Filter must be a hashref\n"
        unless defined $filter && ref $filter eq 'HASH';

    die "Update must be a hashref\n"
        unless defined $update && ref $update eq 'HASH';

    die "Options must be a hashref\n"
        unless ref $options eq 'HASH';

    my $collection = get_collection($collection_name);

    return $collection->update_one($filter, $update, $options);
}

sub upsert_one_doc {
    my ($collection_name, $filter, $update) = @_;

    die "Filter must be a hashref\n"
        unless defined $filter && ref $filter eq 'HASH';

    die "Update must be a hashref\n"
        unless defined $update && ref $update eq 'HASH';

    my $collection = get_collection($collection_name);

    return $collection->update_one(
        $filter,
        $update,
        { upsert => 1 },
    );
}

sub delete_one_doc {
    my ($collection_name, $filter) = @_;

    die "Filter must be a hashref\n"
        unless defined $filter && ref $filter eq 'HASH';

    my $collection = get_collection($collection_name);

    return $collection->delete_one($filter);
}

sub delete_many_docs {
    my ($collection_name, $filter) = @_;

    $filter //= {};

    die "Filter must be a hashref\n"
        unless ref $filter eq 'HASH';

    my $collection = get_collection($collection_name);

    return $collection->delete_many($filter);
}

sub clear_collection {
    my ($collection_name) = @_;

    my $collection = get_collection($collection_name);

    return $collection->delete_many({});
}

sub drop_collection {
    my ($collection_name) = @_;

    my $collection = get_collection($collection_name);

    return $collection->drop;
}

sub create_indexes {
    my ($collection_name, $indexes) = @_;

    die "Indexes must be an arrayref\n"
        unless defined $indexes && ref $indexes eq 'ARRAY';

    my $collection = get_collection($collection_name);

    my @results;
    for my $index_spec (@{$indexes}) {
        die "Each index spec must be a hashref\n"
            unless ref $index_spec eq 'HASH';

        my $keys    = $index_spec->{keys};
        my $options = $index_spec->{options} // {};

        die "Index spec is missing keys hashref\n"
            unless defined $keys && ref $keys eq 'HASH';

        die "Index options must be a hashref\n"
            unless ref $options eq 'HASH';

        push @results, $collection->indexes->create_one($keys, $options);
    }

    return \@results;
}

sub count_docs {
    my ($collection_name, $filter) = @_;

    $filter //= {};

    die "Filter must be a hashref\n"
        unless ref $filter eq 'HASH';

    my $collection = get_collection($collection_name);

    return $collection->count_documents($filter);
}

sub document_exists {
    my ($collection_name, $filter) = @_;

    my $doc = find_one_doc($collection_name, $filter);

    return defined $doc ? 1 : 0;
}

1;