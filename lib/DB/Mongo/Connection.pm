package DB::Mongo::Connection;

use strict;
use warnings;
use v5.30;

use MongoDB ();

my $CLIENT;
my $DB;

sub get_client {
    return $CLIENT if defined $CLIENT;

    my $uri = $ENV{MONGO_URI}
        // die "Missing MONGO_URI environment variable\n";

    $CLIENT = MongoDB->connect(
        $uri,
        {
            server_selection_timeout_ms => 5000,
        }
    );

    return $CLIENT;
}

sub get_db {
    return $DB if defined $DB;

    my $db_name = $ENV{MONGO_DB_NAME}
        // die "Missing MONGO_DB_NAME environment variable\n";

    my $client = get_client();
    $DB = $client->get_database($db_name);

    return $DB;
}

1;