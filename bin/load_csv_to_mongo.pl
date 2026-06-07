use strict;
use warnings;
use v5.30;

use lib 'lib';

use Getopt::Long;
use Pod::Usage;
use Path::Tiny;
use Module::Runtime qw(use_module);
use Text::CSV_XS;
use POSIX qw(strftime);

use DB::Mongo::Utils qw(
    insert_many_docs
    clear_collection
);

my $config_file;
my $csv_file;
my $run_id;
my $input_file_id;
my $output_csv_file_id;
my $parser_name;
my $state;
my $county;
my $help;

GetOptions(
    'config_file|c=s'        => \$config_file,
    'csv|f=s'                => \$csv_file,
    'run_id|r=s'             => \$run_id,
    'input_file_id=s'        => \$input_file_id,
    'output_csv_file_id=s'   => \$output_csv_file_id,
    'parser_name|p=s'        => \$parser_name,
    'state=s'                => \$state,
    'county=s'               => \$county,
    'help|h'                 => \$help,
) or pod2usage(2);

pod2usage(1) if $help;
pod2usage(
    -msg     => 'Missing required arguments: --config_file, --csv, --run_id, --input_file_id and --output_csv_file_id',
    -exitval => 1,
) unless $config_file && $csv_file && $run_id && $input_file_id && $output_csv_file_id;

my $csv_path = path($csv_file);
die "CSV not found: $csv_path\n" unless $csv_path->exists;

my $cfg_module = "Config::Parser::$config_file";
use_module($cfg_module);

my $cfg = $cfg_module->config();

my $csv_cfg           = $cfg->{csv} // {};
my $skip              = $csv_cfg->{skip_lines} // $cfg->{skip_lines} // 0;
my $sep_char          = $csv_cfg->{sep_char} // ',';
my $batch_size        = $csv_cfg->{batch_size} // 500;
my $target_collection = $cfg->{target_collection} // 'raw_permits';
my @columns           = @{ $cfg->{columns} // die "Missing 'columns' in config\n" };

if ($cfg->{clear_target_on_load}) {
    clear_collection($target_collection);
}

my $rows_loaded = load_csv_into_mongo(
    cfg                => $cfg,
    cfg_module         => $cfg_module,
    csv_path           => $csv_path,
    run_id             => $run_id,
    input_file_id      => $input_file_id,
    output_csv_file_id => $output_csv_file_id,
    parser_name        => $parser_name,
    state              => $state,
    county             => $county,
    skip               => $skip,
    sep_char           => $sep_char,
    batch_size         => $batch_size,
    target_collection  => $target_collection,
);

say "Loaded $rows_loaded rows into $target_collection | parser_run_id=$run_id";

sub load_csv_into_mongo {
    my %args = @_;

    my $cfg     = $args{cfg};
    my @columns = @{ $cfg->{columns} };
    my @names   = map { $_->[0] } @columns;

    open(my $fh, '<:encoding(utf-8)', $args{csv_path}->stringify)
        or die "Cannot open CSV $args{csv_path}: $!\n";

    my $csv = Text::CSV_XS->new({
        binary    => 1,
        auto_diag => 1,
        sep_char  => $args{sep_char},
    });

    for (1 .. $args{skip}) {
        scalar <$fh>;
    }

    my @documents;
    my $rows_loaded = 0;
    my $csv_row_number = $args{skip};

    while (my $row = $csv->getline($fh)) {
        $csv_row_number++;

        die "Column count mismatch at CSV row $csv_row_number: expected "
            . scalar(@names) . ' got ' . scalar(@$row) . "\n"
            if @$row != @names;

        my %data;
        for my $i (0 .. $#names) {
            my $column_name = $columns[$i][0];
            my $mask        = $columns[$i][1];

            $data{$column_name} = apply_mask($row->[$i], $mask);
        }

        push @documents, {
            raw_permit_id => sprintf('%s_row_%06d', $args{run_id}, $csv_row_number),
            record_type   => $cfg->{record_type} // 'permit',
            source        => build_source_metadata($cfg, $args{state}, $args{county}),
            data          => \%data,
            provenance    => {
                parser_run_id      => $args{run_id},
                input_file_id      => $args{input_file_id},
                output_csv_file_id => $args{output_csv_file_id},
                csv_file_name      => $args{csv_path}->basename,
                csv_row_number     => $csv_row_number,
                parser_name        => $args{parser_name},
                config_module      => $args{cfg_module},
                config_version     => $cfg->{config_version},
                loaded_at          => iso_timestamp(),
            },
        };

        if (@documents >= $args{batch_size}) {
            insert_many_docs($args{target_collection}, \@documents);
            $rows_loaded += scalar @documents;
            @documents = ();
        }
    }

    close($fh);

    if (@documents) {
        insert_many_docs($args{target_collection}, \@documents);
        $rows_loaded += scalar @documents;
    }

    return $rows_loaded;
}

sub build_source_metadata {
    my ($cfg, $state, $county) = @_;

    my %source = %{ $cfg->{source} // {} };

    $source{state}  //= $state  if defined $state;
    $source{county} //= $county if defined $county;

    return \%source;
}

sub apply_mask {
    my ($value, $mask) = @_;
    return undef unless defined $value;

    $value =~ s/\r//g;
    $value =~ s/^\s+|\s+$//g;

    return undef unless length $value;
    return $value unless defined $mask && length $mask;

    if ($mask eq 'trim') {
        return $value;
    }

    if ($mask eq 'money') {
        $value =~ s/[^0-9.\-]//g;
        return length($value) ? $value : undef;
    }

    if ($mask eq 'integer') {
        $value =~ s/[^0-9\-]//g;
        return length($value) ? $value : undef;
    }

    if ($mask eq 'mdy') {
        return $value;
    }

    die "Unknown mask '$mask' in parser config\n";
}

sub iso_timestamp {
    return strftime('%Y-%m-%dT%H:%M:%SZ', gmtime());
}
