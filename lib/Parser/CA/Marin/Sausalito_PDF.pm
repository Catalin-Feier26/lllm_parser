package Parser::CA::Marin::Sausalito_PDF;

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
        $self->_parse_line($line, $permit, $csv, $OUTPUT);
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
    my ($self, $line, $permit, $csv, $OUTPUT) = @_;

    if ($line =~ /\s+([A-Z]+\d{3,6}\-\d{3,6})\s{2,}(.*?)\s{2,}(.*?)\s{2,}\$(.*)$/ix) {
        if ($permit->{permit_number}) {
            $csv->print_hr($OUTPUT, $permit);
            $permit = {};
        }
        $permit->{permit_number} = $1;
        $permit->{permit_type} = $2;
        $permit->{address} = $3;
        $permit->{valuation} = $4;
    } elsif ($line =~ /^\s+(\d{1,2}\/\d{1,2}\/\d{4})\s{2,}(.*?)\s{2,}((:?\d{1,6}\-?)+)\s{2,}\$(.*)$/ix) {
        $permit->{issued_date} = $1;
        $permit->{subtype} = $2;
        $permit->{parcel_number} = $3;
        $permit->{fee} = $5;
    } elsif ($line =~ /^\s+(\d{1,2}\/\d{1,2}\/\d{4})\s{2,}(.*?)\s{2,}(.*?)\s{2,}\$(.*)$/ix) {
        $permit->{applied_date} = $1;
        $permit->{status} = $2;
        $permit->{paid_fee} = $4;
    } elsif ($line =~ /^\s*owner\s*name\:\s*(.*)$/ix) {
        $permit->{owner_name} = $1;
    } elsif ($line =~ /^\s*contractor\s*name\:\s*(.*)$/ix) {
        $permit->{contractor_name} = $1;
    }

    return $permit;
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

    return qw( permit_number permit_type address valuation issued_date subtype parcel_number
        fee applied_date status paid_fee owner_name contractor_name );
}

sub _is_valid_line {
    my ($self, $line) = @_;

    return 0 unless $line;
    return 0 if $line =~ /^\s*$/;
    return 0 if $line =~ /permits\s*.*?\s*with\s*fees\s*and\s*values/ix;
    return 0 if $line =~ /^\s{20,}City\s*of\s*sausalito$/ix;
    return 0 if $line =~ /^\s{30,}date\srange\sbetween\s.*?\sand\s.*$/ix;
    return 0 if $line =~ /permit\s*number\s*permit\s*type\s*address\s*valuation/ix;
    return 0 if $line =~ /issued\s*date\s*permit\s*subtype\s*parcel/ix;
    return 0 if $line =~ /applied\s*date\s*status\s*subdivision\s*total/ix;
    return 0 if $line =~ /\s{30,}(total)?\s*Number\s*of\s*.*?\s*permits\:/ix;
    return 0 if $line =~ /\s{30,}(total)?\s*(valuation|fees\s*charged|fees\s*paid)\s*\:?\s+/ix;
    return 0 if $line =~ /^printed\:?\s+.*?\d+\s*of\s*\d+/ix;

    return 1;
}


1;