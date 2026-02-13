package Parser::CA::LosAngeles::HermosaBeach_PDF;

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
        if ($line =~ /^\s*record\s*\#\:/i) {
            if ($permit->{permit_number}) {
                $csv->print_hr($OUTPUT, $permit);
                $permit_count++;
                $permit = {};
            }
            $self->_parse_line($line, $permit);
        } else {
            $self->_accumulate_line($line, $permit);
        }
    }
    if ($permit->{permit_number}) {
        $csv->print_hr($OUTPUT, $permit);
        $permit_count++;
    }

    close $INPUT;
    close $OUTPUT;
    return $permit_count;
}

sub _parse_line {
    my ($self, $line, $permit) = @_;

    if ($line =~ /^\s*record\s*\#\:\s*(?<permit_number>\S+)\s{4,}type\:\s*
        (?<permit_type>.*?)\s{3,}sub\s*type\:\s*
        (?<sub_type>.*?)(\s{3,}status\:\s*|\$)
        (?<status>.*)$/ix)
    {
        $permit->{$_} = $+{$_} for keys %+;
    }
}

sub _accumulate_line {
    my ($self, $line, $permit) = @_;

    if ($line =~ /^\s*Parcel\:\s*(?<parcel_number>.*?)\s{3,}issued\s*date\:\s*
        (?<issued_date>\d{1,2}\/\d{1,2}\/\d{4})(\s{3,}sq\s*ft|\$)/ix)
    {
        $permit->{$_} = $+{$_} for keys %+;
    } elsif ($line =~ /^\s*address\:\s*(?<address>.*?)\s{3,}/ix) {
        $permit->{address} = $+{address};
    } elsif ($line =~ /^\s*description\:\s*(?<description>.*?)$/ix) {
        $permit->{description} = $+{description};
    } elsif ($line =~ /^\s*Owner\:\s*(?<Owner>.*?)\s{3,}class/ix) {
        $permit->{owner_name} = $+{Owner};
    } elsif ($line =~ /^\s*Contractor\:\s*(?<Contractor>.*?)\s{3,}pools/ix) {
        $permit->{contractor_name} = $+{Contractor};
    } elsif ($line =~ /\s{3,}fees\s*collected\:\s*(?<paid_fee>.*?)(\s{3,}Balance|$)/ix) {
        $permit->{paid_fee} = $+{paid_fee};
    } elsif ($line =~ /\s*valuation\:\s*(?<valuation>.*?)\s{3,}
        fees\s*required\:\s*(?<fee>.*?)(\s{3,}|$)/ix) 
    {
        $permit->{valuation} = $+{valuation};
        $permit->{fee} = $+{fee};
    }
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

sub _get_output_columns {
    my ($self) = @_;

    return qw ( permit_number permit_type sub_type status
        parcel_number issued_date address description
        owner_name contractor_name valuation fee paid_fee);
}

sub _is_valid_line {
    my ($self, $line) = @_;

    return 0 unless $line;
    return 0 if $line =~ /^\s*$/;
    return 0 if $line =~ /city of hermosa beach/i;
    return 0 if $line =~ /building records for/i;
    return 0 if $line =~ /Totals\:/i;
    return 0 if $line =~ /selected records/i;
    return 0 if $line =~ /^\s{3,}Valuation/i;

    return 1;
}

1;