use strict;
use warnings;
use v5.30;

use lib 'lib';
use Getopt::Long;
use Pod::Usage;
use Path::Tiny;
use Module::Runtime qw(use_module);
use Text::CSV_XS;

use DB::pg ();
use DB::PG::Utils ();

my $config_file;
my $csv_file;
my $run_id;
my $source_file;
my $help;

GetOptions(
    'config_file|c=s' => \$config_file,
    'csv|f=s' => \$csv_file,
    'run_id|r=s' => \$run_id,
    'source_file|s=s' => \$source_file,
    'help|h' => \$help,
) or pod2usage(2);

pod2usage(1) if $help;
pod2usage(-msg => "Missing --config_file and/or --csv", -exitval => 1)
    unless $config_file && $csv_file;

my $csv_path = path($csv_file);
die "CSV not found: $csv_path\n" unless $csv_path->exists;

$run_id //= make_run_id();
$source_file //= build_source_file_tag($csv_path);

my $cfg_module = "Config::Parser::$config_file";
use_module($cfg_module);

my $cfg = $cfg_module->config();

my $dbh = DB::pg::connect_db();

my $schema = $cfg->{schema} // 'public';
my $table = $cfg->{table_name} // die "Missing 'table_name' in config\n";
my $skip = $cfg->{skip_lines} // 0;

my @csv_cols = @{$cfg->{columns} // die "Missing 'columns' in config\n"};

my $table_cfg = {
    schema => $schema,
    table_name => $table,
    columns    => [
        (map { +{ name => $_->[0], type => $_->[1], nullable => 1 } } @csv_cols),

        { name => 'run_id',      type => 'text', nullable => 0 },
        { name => 'source_file', type => 'text', nullable => 0 },
        { name => 'loaded_at',   type => 'timestamptz', nullable => 0, default_sql => 'now()' },
    ],
};

DB::PG::Utils::create_table($dbh, $table_cfg);

if ($cfg->{truncate_if_exists}) {
    DB::PG::Utils::truncate_table($dbh, $schema, $table);
}

my $rows = load_csv_into_table($dbh, $cfg, $csv_path, $run_id, $source_file, $skip);

print "Loaded $rows rows into $schema.$table | run_id=$run_id | source_file=$source_file\n";

sub load_csv_into_table {
    my ($dbh, $cfg, $csv_path, $run_id, $source_file, $skip) = @_;

    my $schema = $cfg->{schema} // 'public';
    my $table  = $cfg->{table_name};

    my @cols = map { $_->[0] } @{$cfg->{columns}};
    my @insert_cols = (@cols, 'run_id', 'source_file'); # loaded_at uses default

    my $full_table = $dbh->quote_identifier($schema) . "." . $dbh->quote_identifier($table);
    my $col_list   = join(",", map { $dbh->quote_identifier($_) } @insert_cols);
    my $ph         = join(",", ("?") x @insert_cols);

    my $sth = $dbh->prepare("INSERT INTO $full_table ($col_list) VALUES ($ph)");

    open(my $fh, "<:encoding(utf-8)", $csv_path->stringify)
        or die "Cannot open CSV $csv_path: $!\n";

    my $csv = Text::CSV_XS->new({ binary => 1, auto_diag => 1 });

    for (1..$skip) { scalar <$fh>; }

    my $count = 0;

    $dbh->begin_work;
    eval {
        while (my $row = $csv->getline($fh)) {
            die "Column count mismatch: expected ".scalar(@cols)." got ".scalar(@$row)."\n"
                if @$row != @cols;

            for my $i (0..$#$row) {
                my $mask = $cfg->{columns}[$i][2];
                $row->[$i] = apply_mask($row->[$i], $mask);
            }

            $sth->execute(@$row, $run_id, $source_file);
            $count++;
        }

        $dbh->commit;
        1;
    } or do {
        my $err = $@ || "unknown error";
        eval { $dbh->rollback; };
        die "Load failed: $err";
    };

    close($fh);
    return $count;
}

sub apply_mask {
    my ($v, $mask) = @_;
    return undef if !defined $v;

    $v =~ s/\r//g;
    $v =~ s/^\s+|\s+$//g;

    return $v if !$mask;

    if ($mask eq 'trim') {
        return $v;
    }
    if ($mask eq 'money') {
        $v =~ s/[^0-9.\-]//g;
        return length($v) ? $v : undef;
    }
    if ($mask eq 'mdy') {
        return $v;
    }

    return $v;
}

sub make_run_id {
    my @t = localtime();
    return sprintf("run_%04d%02d%02d_%02d%02d%02d", $t[5]+1900, $t[4]+1, $t[3], $t[2], $t[1], $t[0]);
}

sub build_source_file_tag {
    my ($csv_path) = @_;
    my @t = localtime();
    my $date = sprintf("%04d_%02d_%02d", $t[5]+1900, $t[4]+1, $t[3]);
    return $date . "_" . $csv_path->basename;
}