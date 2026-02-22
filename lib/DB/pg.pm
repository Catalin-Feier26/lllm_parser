package DB::pg;

use strict;
use warnings;
use v5.30;

use DBI;

sub connect_db {
    my (%opt) = @_;

    my $host = $opt{host} // $ENV{DB_HOST} // 'localhost';
    my $port = $opt{port} // $ENV{DB_PORT} // 5432;
    my $name = $opt{name} // $ENV{DB_NAME} // 'thesis';
    my $user = $opt{user} // $ENV{DB_USER} // 'thesis';
    my $pass = $opt{pass} // $ENV{DB_PASS} // 'thesis';

    my $dsn = "dbi:Pg:dbname=$name;host=$host;port=$port";

    my $dbh = DBI->connect(
        $dsn, $user, $pass, 
        { 
            RaiseError => 1,
            PrintError => 0,
            AutoCommit => 1,
            pg_enable_utf8 => 1,
        }
    );
    
    return $dbh;
}

1;