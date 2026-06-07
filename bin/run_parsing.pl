use strict;
use warnings;
use v5.30;
use lib 'lib';

use Getopt::Long;
use Pod::Usage;
use Path::Tiny;
use Module::Runtime qw(use_module);
use Digest::SHA ();
use POSIX qw(strftime);

use DB::Mongo::Utils qw(
	insert_one_doc
	update_one_doc
	count_docs
);

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
	'help|h'          => \$help,
	'debug|d'         => \$debug,
	'config_file|C=s' => \$config_file,
) or pod2usage(2);

pod2usage(1) if $help;
pod2usage(
	-msg     => 'Missing required arguments: --state, --county, --name, --file_name and --config_file',
	-exitval => 1,
) unless $state && $county && $parser_name && $file_name && $config_file;

my $input_path = $DIR_INCOMING->child($file_name);
die "Input file '$file_name' does not exist in '$DIR_INCOMING'.\n"
	unless $input_path->exists;

$DIR_ARCHIVE->mkpath unless $DIR_ARCHIVE->exists;

my $output_csv_path = $DIR_ARCHIVE->child(
	$input_path->basename(qr/\.[^.]+$/) . '.csv'
);

my $run_id        = make_run_id();
my $started_at    = iso_timestamp();
my $parser_module = 'Parser::' . $state . '::' . $county . '::' . $parser_name;
my $cfg_module    = 'Config::Parser::' . $config_file;

my $input_file_id;
my $output_csv_file_id;
my $run_registered = 0;

my $ok = eval {
	$input_file_id = register_source_file(
		file_id    => $run_id . '_input',
		file_path  => $input_path,
		file_role  => 'source_input',
		run_id     => $run_id,
		state      => $state,
		county     => $county,
	);

	insert_one_doc('parser_runs', {
		run_id             => $run_id,
		parser             => {
			name          => $parser_name,
			module        => $parser_module,
			config_module => $cfg_module,
		},
		source             => {
			state  => $state,
			county => $county,
		},
		input_file_id       => $input_file_id,
		output_csv_file_id  => undef,
		target_collection   => 'raw_permits',
		status              => 'running',
		rows_parsed         => undef,
		rows_loaded         => undef,
		started_at          => $started_at,
		completed_at        => undef,
		error_message       => undef,
	});
	$run_registered = 1;

	use_module($parser_module);

	my $parser = $parser_module->new(
		file   => $input_path,
		output => $output_csv_path,
		debug  => $debug,
	);

	my $parse_result = $parser->parse();
	my $analytics    = $parse_result->{analytics} // {};
	my $permit_count = $parse_result->{permit_count} // 0;

	die "Parser did not create output CSV '$output_csv_path'.\n"
		unless $output_csv_path->exists;

	$output_csv_file_id = register_source_file(
		file_id               => $run_id . '_csv',
		file_path             => $output_csv_path,
		file_role             => 'parser_output_csv',
		run_id                => $run_id,
		state                 => $state,
		county                => $county,
		derived_from_file_id  => $input_file_id,
	);

	use_module($cfg_module);
	my $cfg               = $cfg_module->config();
	my $target_collection = $cfg->{target_collection} // 'raw_permits';

	update_one_doc('parser_runs',
		{ run_id => $run_id },
		{ '$set' => {
			output_csv_file_id => $output_csv_file_id,
			target_collection  => $target_collection,
			rows_parsed        => $permit_count,
		} }
	);

	insert_one_doc('parser_analytics', {
		parser_run_id      => $run_id,
		input_file_id      => $input_file_id,
		output_csv_file_id => $output_csv_file_id,
		parser_name        => $parser_name,
		source             => {
			state  => $state,
			county => $county,
		},
		permit_count       => $permit_count,
		analytics          => $analytics,
		created_at         => iso_timestamp(),
	});

	system(
		'perl', 'bin/load_csv_to_mongo.pl',
		'--config_file',       $config_file,
		'--csv',               $output_csv_path->stringify,
		'--run_id',            $run_id,
		'--input_file_id',     $input_file_id,
		'--output_csv_file_id',$output_csv_file_id,
		'--parser_name',       $parser_name,
		'--state',             $state,
		'--county',            $county,
	) == 0 or die "Failed to load CSV into MongoDB (exit=" . ($? >> 8) . ").\n";

	my $rows_loaded = count_docs(
		$target_collection,
		{ 'provenance.parser_run_id' => $run_id }
	);

	update_one_doc('parser_runs',
		{ run_id => $run_id },
		{ '$set' => {
			status        => 'completed',
			rows_loaded   => $rows_loaded,
			completed_at  => iso_timestamp(),
			error_message => undef,
		} }
	);

	say "Completed parser run $run_id | parsed=$permit_count | loaded=$rows_loaded";
	1;
};

if (!$ok) {
	my $error = $@ || 'Unknown error';
	chomp $error;

	if ($run_registered) {
		eval {
			update_one_doc('parser_runs',
				{ run_id => $run_id },
				{ '$set' => {
					status        => 'failed',
					completed_at  => iso_timestamp(),
					error_message => $error,
				} }
			);
		};
	}

	die "Parser run '$run_id' failed: $error\n";
}

sub register_source_file {
	my %args = @_;

	my $file_path = $args{file_path};
	die "Missing file path for source file registration.\n"
		unless defined $file_path;
	die "Cannot register missing file '$file_path'.\n"
		unless $file_path->exists;

	my $doc = {
		file_id      => $args{file_id},
		file_name    => $file_path->basename,
		file_role    => $args{file_role},
		file_format  => file_extension($file_path),
		file_path    => $file_path->stringify,
		sha256       => sha256_for_file($file_path),
		size_bytes   => -s $file_path->stringify,
		parser_run_id => $args{run_id},
		source       => {
			state  => $args{state},
			county => $args{county},
		},
		created_at   => iso_timestamp(),
	};

	$doc->{derived_from_file_id} = $args{derived_from_file_id}
		if defined $args{derived_from_file_id};

	insert_one_doc('source_files', $doc);

	return $doc->{file_id};
}

sub sha256_for_file {
	my ($file_path) = @_;

	open(my $fh, '<:raw', $file_path->stringify)
		or die "Cannot open '$file_path' for hashing: $!\n";

	my $sha = Digest::SHA->new(256);
	$sha->addfile($fh);
	close($fh);

	return $sha->hexdigest;
}

sub file_extension {
	my ($file_path) = @_;

	my $name = $file_path->basename;
	return lc($1) if $name =~ /\.([^.]+)$/;
	return '';
}

sub iso_timestamp {
	return strftime('%Y-%m-%dT%H:%M:%SZ', gmtime());
}

sub make_run_id {
	return strftime('run_%Y%m%d_%H%M%S', gmtime()) . '_' . $$;
}
