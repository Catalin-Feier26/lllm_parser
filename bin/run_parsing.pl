use strict;
use warnings;
use v5.30;
use lib 'lib';

use Getopt::Long;
use Pod::Usage;
use Path::Tiny;
use Module::Runtime qw(use_module);
use DB::Mongo::Utils qw(insert_one_doc);

my $DIR_INCOMING = path('data/incoming');
my $DIR_ARCHIVE  = path('data/archive');

my $parser_name;
my $file_name;
my $state;
my $county;
my $help;
my $debug = 0;
my $config_file;

GetOptions(
    'state|s=s'       => \$state,
    'county|c=s'      => \$county,
    'name|n=s'        => \$parser_name,
    'file_name|f=s'   => \$file_name,
    'help|h'          => \&help,
    'debug|d'         => \$debug,
    'config_file|C=s' => \$config_file,
) or pod2usage(2);

pod2usage(1) if $help;
pod2usage(-msg => "Error: Missing arguments.", -exitval => 1)
    unless $state && $county && $parser_name && $file_name;

my $input_path = $DIR_INCOMING->child($file_name);
die "Input file '$file_name' does not exist in '$DIR_INCOMING'.\n"
    unless $input_path->exists;

my $output_csv_path = $DIR_ARCHIVE->child(
    $input_path->basename(qr/\.[^.]+$/) . ".csv"
);

my @t = localtime();
my $run_id = sprintf(
    "run_%04d%02d%02d_%02d%02d%02d",
    $t[5] + 1900, $t[4] + 1, $t[3], $t[2], $t[1], $t[0]
);

my $parser_module = 'Parser::' . $state . '::' . $county . '::' . $parser_name;

eval {
    use_module($parser_module);

    my $parser = $parser_module->new(
        file   => $input_path,
        output => $output_csv_path,
        debug  => $debug,
    );

    my $parse_result = $parser->parse();

    my $analytics    = $parse_result->{analytics};
    my $permit_count = $parse_result->{permit_count} // 0;

    if ($config_file) {
        system(
            "perl", "bin/load_csv_to_mongo.pl",
            "--config_file", $config_file,
            "--csv",         $output_csv_path->stringify,
            "--run_id",      $run_id,
            "--source_file", $file_name,
            "--parser_name", $parser_name,
            "--state",       $state,
            "--county",      $county
        ) == 0 or die "Failed to load CSV into MongoDB (exit=" . ($? >> 8) . ")\n";
    }

    insert_one_doc('parser_analytics', {
        run_id       => $run_id,
        source_file  => $file_name,
        parser_name  => $parser_name,
        state        => $state,
        county       => $county,
        csv_file     => $output_csv_path->basename,
        permit_count => $permit_count,
        analytics    => $analytics,
        created_at   => scalar localtime,
    });

    1;
};

die "Error loading parser module '$parser_module': $@\n" if $@;