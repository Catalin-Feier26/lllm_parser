package DB::Pg::Utils;

use strict;
use warnings;
use v5.30;

use Exporter 'import';

our @EXPORT_OK = qw(
    table_exists
    ensure_schema
    create_table
    truncate_table
    create_or_truncate_table
    drop_table
    create_indexes
    create_unique_indexes
    run_in_tx
);

sub table_exists {
    my ($dbh, $schema, $table) = @_;

    $schema //= 'public';

    my ($exists) = $dbh->selectrow_array(
        q{
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = ? AND table_name = ?
            )
        },
        undef,
        $schema, $table
    );

    return $exists ? 1 : 0;
}

sub ensure_schema {
    my ($dbh, $schema) = @_;

    return if !defined $schema || $schema eq 'public';

    $dbh->do('CREATE SCHEMA IF NOT EXISTS ' . $dbh->quote_identifier($schema));
    return 1;
}

sub create_table {
    my ($dbh, $cfg) = @_;

    my $schema = $cfg->{schema} // 'public';
    my $table  = $cfg->{table_name} // die "Missing table_name";
    my $cols   = $cfg->{columns}    // die "Missing columns";

    ensure_schema($dbh, $schema);

    my @defs;

    for my $c (@$cols) {
        my $name = $c->{name} // die "Column missing name";
        my $type = $c->{type} // die "Column $name missing type";

        my $nullable = exists $c->{nullable} ? $c->{nullable} : 1;

        my $def = $dbh->quote_identifier($name) . " $type";
        $def .= " NOT NULL" if !$nullable;

        if (exists $c->{default_sql}) {
            $def .= " DEFAULT $c->{default_sql}";
        }
        elsif (exists $c->{default}) {
            $def .= " DEFAULT " . $dbh->quote($c->{default});
        }

        push @defs, $def;
    }

    if (my $pk = $cfg->{primary_key}) {
        my $pk_sql = join(", ", map { $dbh->quote_identifier($_) } @$pk);
        push @defs, "PRIMARY KEY ($pk_sql)";
    }

    my $full = $dbh->quote_identifier($schema) . "." . $dbh->quote_identifier($table);

    my $sql = "CREATE TABLE IF NOT EXISTS $full (\n  " . join(",\n  ", @defs) . "\n)";
    $dbh->do($sql);

    return 1;
}

sub truncate_table {
    my ($dbh, $schema, $table, %opt) = @_;

    $schema //= 'public';

    my $full = $dbh->quote_identifier($schema) . "." . $dbh->quote_identifier($table);

    my $sql = "TRUNCATE TABLE $full";
    $sql .= " RESTART IDENTITY" if $opt{restart_identity};
    $dbh->do($sql);

    return 1;
}

sub create_or_truncate_table {
    my ($dbh, $cfg) = @_;

    my $schema = $cfg->{schema} // 'public';
    my $table  = $cfg->{table_name} // die "Missing table_name";

    create_table($dbh, $cfg);
    truncate_table(
        $dbh, $schema, $table,
        restart_identity => ($cfg->{restart_identity} // 0),
    );

    return 1;
}

sub drop_table {
    my ($dbh, $schema, $table, %opt) = @_;

    $schema //= 'public';

    my $full = $dbh->quote_identifier($schema) . "." . $dbh->quote_identifier($table);

    my $sql = "DROP TABLE IF EXISTS $full";
    $sql .= " CASCADE" if $opt{cascade};
    $dbh->do($sql);

    return 1;
}

sub create_indexes {
    my ($dbh, $cfg) = @_;

    my $schema = $cfg->{schema} // 'public';
    my $table  = $cfg->{table_name} // die "Missing table_name";
    my $idxs   = $cfg->{indexes} // [];

    return 1 if !@$idxs;

    my $full_table = $dbh->quote_identifier($schema) . "." . $dbh->quote_identifier($table);

    for my $i (@$idxs) {
        my $name = $i->{name} // die "Index missing name";
        my $cols = $i->{columns} // die "Index $name missing columns";

        my $cols_sql = join(", ", map { $dbh->quote_identifier($_) } @$cols);

        my $full_idx = $dbh->quote_identifier($name);

        $dbh->do("CREATE INDEX IF NOT EXISTS $full_idx ON $full_table ($cols_sql)");
    }

    return 1;
}

sub create_unique_indexes {
    my ($dbh, $cfg) = @_;

    my $schema = $cfg->{schema} // 'public';
    my $table  = $cfg->{table_name} // die "Missing table_name";
    my $idxs   = $cfg->{unique_indexes} // [];

    return 1 if !@$idxs;

    my $full_table = $dbh->quote_identifier($schema) . "." . $dbh->quote_identifier($table);

    for my $i (@$idxs) {
        my $name = $i->{name} // die "Unique index missing name";
        my $cols = $i->{columns} // die "Unique index $name missing columns";

        my $cols_sql = join(", ", map { $dbh->quote_identifier($_) } @$cols);

        my $full_idx = $dbh->quote_identifier($name);

        $dbh->do("CREATE UNIQUE INDEX IF NOT EXISTS $full_idx ON $full_table ($cols_sql)");
    }

    return 1;
}

sub run_in_tx {
    my ($dbh, $code) = @_;

    $dbh->begin_work;

    my $ok = eval { $code->(); 1 };
    if ($ok) {
        $dbh->commit;
        return 1;
    }

    my $err = $@ || "Unknown error";
    eval { $dbh->rollback };

    die "TX failed: $err";
}

1;