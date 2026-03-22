use strict;
use warnings;
use v5.30;

use lib 'lib';

use Getopt::Long;
use Pod::Usage;
use Path::Tiny;
use Module::Runtime qw(use_module);
use Text::CSV_XS;

use DB::Mongo::Utils qw(
    insert_one_doc
    insert_many_docs
    clear_collection
);

my $config_file;
my $csv_file;
my $run_id;
my $source_file;
my $parser_name;
my $state;
my $county;
my $help;

GetOptions(
    'config_file|c=s' => \$config_file,
    'csv|f=s'         => \$csv_file,
    'run_id|r=s'      => \$run_id,
    'source_file|s=s' => \$source_file,
    'parser_name|p=s' => \$parser_name,
    'state=s'         => \$state,
    'county=s'        => \$county,
    'help|h'          => \$help,
) or pod2usage(2);

pod2usage(1) if $help;
pod2usage(
    -msg     => 'Missing required arguments: --config_file and/or --csv',
    -exitval => 1
) unless $config_file && $csv_file;

my $csv_path = path($csv_file);
die "CSV not found: $csv_path\n" unless $csv_path->exists;

$run_id      //= make_run_id();
$source_file //= $csv_path->basename;

my $cfg_module = "Config::Parser::$config_file";
use_module($cfg_module);

my $cfg = $cfg_module->config();

my $skip              = $cfg->{skip_lines} // 0;
my $target_collection = $cfg->{target_collection} // 'raw_permits';
my @csv_cols          = @{ $cfg->{columns} // die "Missing 'columns' in config\n" };

if ($cfg->{clear_target_on_load}) {
    clear_collection($target_collection);
}

my $rows_loaded = load_csv_into_mongo(
    $cfg,
    $csv_path,
    $run_id,
    $source_file,
    $parser_name,
    $state,
    $county,
    $skip,
    $target_collection,
);

insert_parser_run(
    run_id            => $run_id,
    source_file       => $source_file,
    parser_name       => $parser_name,
    state             => $state,
    county            => $county,
    config_file       => $config_file,
    csv_file          => $csv_path->basename,
    rows_loaded       => $rows_loaded,
    target_collection => $target_collection,
    status            => 'completed',
);

say "Loaded $rows_loaded rows into $target_collection | run_id=$run_id | source_file=$source_file";

sub load_csv_into_mongo {
    my ($cfg, $csv_path, $run_id, $source_file, $parser_name, $state, $county, $skip, $target_collection) = @_;

    my @cols = map { $_->[0] } @{ $cfg->{columns} };

    open(my $fh, '<:encoding(utf-8)', $csv_path->stringify)
        or die "Cannot open CSV $csv_path: $!\n";

    my $csv = Text::CSV_XS->new({
        binary    => 1,
        auto_diag => 1,
    });

    for (1 .. $skip) {
        scalar <$fh>;
    }

    my @documents;
    my $count = 0;

    while (my $row = $csv->getline($fh)) {
        die "Column count mismatch: expected " . scalar(@cols) . " got " . scalar(@$row) . "\n"
            if @$row != @cols;

        my %data;
        for my $i (0 .. $#cols) {
            my $col_name = $cfg->{columns}[$i][0];
            my $mask     = $cfg->{columns}[$i][1];
            my $value    = apply_mask($row->[$i], $mask);

            $data{$col_name} = $value;
        }

        push @documents, {
            run_id      => $run_id,
            source_file => $source_file,
            parser_name => $parser_name,
            state       => $state,
            county      => $county,
            csv_file    => $csv_path->basename,
            loaded_at   => scalar localtime,
            data        => \%data,
        };

        $count++;
    }

    close($fh);

    insert_many_docs($target_collection, \@documents) if @documents;

    return $count;
}

sub insert_parser_run {
    my %args = @_;

    insert_one_doc('parser_runs', {
        run_id            => $args{run_id},
        source_file       => $args{source_file},
        parser_name       => $args{parser_name},
        state             => $args{state},
        county            => $args{county},
        config_file       => $args{config_file},
        csv_file          => $args{csv_file},
        target_collection => $args{target_collection},
        rows_loaded       => $args{rows_loaded},
        status            => $args{status},
        loaded_at         => scalar localtime,
    });

    return;
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
    return sprintf(
        'run_%04d%02d%02d_%02d%02d%02d',
        $t[5] + 1900, $t[4] + 1, $t[3], $t[2], $t[1], $t[0]
    );
}