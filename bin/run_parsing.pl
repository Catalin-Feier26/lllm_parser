use strict;
use warnings;
use v5.30;
use lib 'lib';
use Getopt::Long;
use Pod::Usage;
use Path::Tiny;
use Module::Runtime qw(use_module);

my $DIR_INCOMING = path('data/incoming');
my $DIR_ARCHIVE = path('data/archive');

my $parser_name;
my $file_name;
my $state;
my $county;
my $help;
my $debug = 0;

GetOptions(
    'state|s=s' => \$state,
    'county|c=s' => \$county,
    'name|n=s' => \$parser_name,
    'file_name|f=s' => \$file_name,
    'help|h' => \&help,
    'debug|d' => \$debug,
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

my $parser_module = 'Parser::' . $state . '::' . $county . '::' . $parser_name;
eval {
    use_module($parser_module);

    my $parser = $parser_module->new(
        file => $input_path,
        output => $output_csv_path,
        debug => $debug,
    );

    $parser->parse();
};

die "Error loading parser module '$parser_module': $@\n" if $@;