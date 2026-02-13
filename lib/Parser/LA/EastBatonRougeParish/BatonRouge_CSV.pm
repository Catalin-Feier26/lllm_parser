package Parser::LA::EastBatonRougeParish::BatonRouge_CSV;

use strict;
use warnings;

use base 'Parser::Base';

use Text::CSV_XS;

sub parse {
	my ($self) = @_;

	$self->{logger}->log_info("Started parsing the file: $self->{file}");

	my ($INPUT, $OUTPUT, $in_csv, $out_csv) = $self->_prepare_io_files($self->{file});
	my $permit_count = $self->_parse_csv_file($INPUT, $OUTPUT, $in_csv, $out_csv);

	$self->{logger}->log_summary("Done parsing, obtained $permit_count number of permits");

	return;
}

sub _parse_csv_file {
	my ($self, $INPUT, $OUTPUT, $in_csv, $out_csv) = @_;

	my $permit_count = 0;

	$in_csv->getline($INPUT);

	while (my $row = $in_csv->getline_hr($INPUT)) {

		for my $key (keys %$row) {
			next unless defined $row->{$key};
			$row->{$key} =~ s/\s{2,}/ /g;
			$row->{$key} =~ s/["\s]+$//;
			$row->{$key} =~ s/^\s+//;
            $row->{$key} =~ s/^\s*(NULL|N\/A)\s*$//i;
		}
		
		$out_csv->print_hr($OUTPUT, $row);
		
		$permit_count++;
		
		$self->{logger}->log_debug("Currently parsed $permit_count permits")
			if $permit_count % 5000 == 0;
	}

	close $INPUT;
	close $OUTPUT;

	return $permit_count;
}

sub _prepare_io_files {
	my ($self, $input_file) = @_;

	open (my $INPUT, '<:encoding(utf8)', $input_file)
		or die "Could not open file '$input_file' $!\n";

	open (my $OUTPUT, '>:encoding(utf8)', $self->{output})
		or die "Could not open file '$self->{output}' $!\n";

	my $input_csv = Text::CSV_XS->new({
		binary => 1,
		sep_char => ',',
		auto_diag => 1,
		quote_char => '"',
		allow_whitespace => 1,
		allow_loose_quotes => 1,
		escape_char => undef,
	});

	my $output_csv = Text::CSV_XS->new({
		binary => 1,
		sep_char => ',',
		eol => "\n",
		auto_diag => 1,
		quote_char => '"',
	});

	my @input_columns = $self->_get_columns();
	my @output_columns = $self->_get_output_columns();

	$input_csv->column_names(\@input_columns);
	$output_csv->column_names(\@output_columns);

	$output_csv->print($OUTPUT, \@output_columns);

	return ($INPUT, $OUTPUT, $input_csv, $output_csv);
}

sub _get_columns {
	my ($self) = @_;
	return qw( internal_id permit_number permit_type designation description parcel_number subdivision
		square_footage valuation fee applied_date issued_date full_address address city state zip parish_name
		owner_name applicant_name contractor_name contractor_adress latitude longitude geolocation );
}

sub _get_output_columns {
	my ($self) = @_;
	return qw ( permit_number permit_type parcel_number valuation fee applied_date issued_date address owner_name
		applicant_name contractor_name description );
}

1;