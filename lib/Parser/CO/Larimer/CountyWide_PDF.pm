package Parser::CO::Larimer::CountyWide_PDF;

use strict;
use warnings;

use base 'Parser::Base';

use Text::CSV;

sub parse {
    my ($self) = @_;

    $self->{logger}->log_info("Started parsing the file:$self->{file}");

    my $txt_file = $self->_convert_pdf_to_text();
    my ($INPUT, $OUTPUT, $csv) = $self->_prepare_io_files($txt_file);

    my $permit_count = $self->_parse_txt_file($INPUT, $OUTPUT, $csv);

    $self->{logger}->log_summary("Done parsing, obtained $permit_count number of permits");
    $self->cleanup_temp_file($txt_file);
    $self->{logger}->log_info("Removed $txt_file temporary file.");

    return;
}

sub _parse_txt_file {
    my ($self, $INPUT, $OUTPUT, $csv) = @_;

    my $permit = {};
    my $permit_count = 0;
    while (my $line = <$INPUT>) {
        chomp $line;

        next unless $self->_is_valid_line($line);
        if ($line =~ /^\s*permit\s*\#\:?/i) {
            if ($permit->{permit_number}) {
                $csv->print_hr($OUTPUT, $permit);
                $permit_count++;
                $permit = {};
            }
            $permit = $self->_parse_line($line, $permit);
        } else {
            $permit = $self->_parse_continuation($line, $permit);
        }
    }
    if ($permit->{permit_number}) {
        $csv->print_hr($OUTPUT, $permit);
        $permit_count++;
    }

    return $permit_count;
}

sub _parse_line {
    my ($self, $line, $permit) = @_;

    if ($line =~ /^\s*permit\s*\#\:\s*(?<pm>.*?)\s+permit\s*type\:?
        (?<type>.*?)\s+permit\s*status\:?\s*(?<status>.*?)\s+
        issued\s+date\:?\s*(?<date>.*?)$/ix) 
    {
        $permit->{permit_number} = $+{pm};
        $permit->{permit_type} = $+{type};
        $permit->{status} = $+{status};
        $permit->{issued_date} = $+{date};
    }

    return $permit;
}

sub _parse_continuation {
    my ($self, $line, $permit) = @_;

    if ($line =~ /^\s*parcel\s*\#\:?\s*(.*?)\s+work\s+class/i) {
        $permit->{parcel_number} = $1;
    } elsif ($line =~ /^\s*valuation\:?\s*(.*?)\s+fees\s+req\:?\s+
        (.*?)\s+fees\s+col\:/ix) 
    {
        $permit->{valuation} = $1;
        $permit->{fee} = $2;
    } elsif ($line =~ /owner\(\s*s?\)\:?\s*(.*?)\s{3,}.*?$/i) {
        $permit->{owner_name} = $1;
    } elsif ($line =~ /contractors\(\s*s?\)\:?\s*(.*?)\s{3,}.*?$/i) {
        $permit->{contractor_name} = $1;
    } elsif ($line =~ /^\f?(?<address>\d+\s+.*?)$/i) {
        $permit->{address} = $+{address};
    }

    return $permit;
}

sub _prepare_io_files {
    my ($self, $txt_file) = @_;

    my $input_file = $txt_file;
    my $output_file = $self->{output};

    open (my $INPUT, '<:encoding(utf8)', $input_file)
        or die "Could not open input file '$input_file': $!\n";

    open (my $OUTPUT, '>:encoding(utf8)', $output_file)
        or die "Could not open output file '$output_file': $!\n";

    my $csv = Text::CSV->new({
        binary => 1,
        sep_char => ',',
        eol => "\n",
        quote_char => '"',
        auto_diag => 1,
    });

    my @columns = $self->_get_output_columns();
    $csv->column_names(\@columns);

    $csv->print_hr($OUTPUT, { map { $_ => $_ } @columns });

    return ($INPUT, $OUTPUT, $csv);
}

sub _convert_pdf_to_text {
    my ($self) = @_;

    my $txt_file = $self->{file} =~ s/\.pdf$/.txt/r;
    $txt_file .= '.txt' if $txt_file eq $self->{file};

    my $cmd = "pdftotext -layout -enc UTF-8 \"$self->{file}\" \"$txt_file\"";
    
    $self->{logger}->log_info("Running command: $cmd");
    
    my $result = system($cmd);
    
    if ($result != 0) {
        if (-e $txt_file && -s $txt_file > 0) {
            $self->{logger}->log_warn("pdftotext returned exit code $result, but output file exists.");
        } else {
            die "Failed to convert PDF to text. Exit code: $result\n";
        }
    }

    $self->{logger}->log_info("Converted PDF to text: $txt_file");

    return $txt_file;
}

sub _get_output_columns {
    return qw ( permit_number permit_type status issued_date parcel_number address 
        valuation fee owner_name contractor_name );
}

sub _is_valid_line {
    my ($self, $line) = @_;

    return 0 unless $line;
    return 0 if $line =~ /^\s*$/;
    return 0 if $line =~ /Larimer County Building Permits/i;
    return 0 if $line =~ /Page \d+ of \d+/i;

    return 1;
}

1;