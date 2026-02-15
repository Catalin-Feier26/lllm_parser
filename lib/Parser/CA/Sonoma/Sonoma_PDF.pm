package Parser::CA::Sonoma::Sonoma_PDF;

use strict;
use warnings;

use base 'Parser::Base';

use Text::CSV;
use XML::Simple;
use Data::Dumper;

sub parse {
    my ($self) = @_;
    
    $self->{logger}->log_info("Started parsing the file: $self->{file}");

    my $xml_file = $self->_convert_pdf_to_xml();
    my ($INPUT, $OUTPUT, $csv) = $self->_prepare_io_files($xml_file);

    $self->_parse_xml($INPUT, $OUTPUT, $csv);
    $self->cleanup_temp_file($xml_file);
    $self->{logger}->log_info("Removed $xml_file temporary file.");

    return;
}

sub _parse_xml {
    my ($self, $INPUT, $OUTPUT, $csv) = @_;

    my $permit = {};
    my $permit_count = 0;

    my $xs = XML::Simple->new(
        ForceArray => ['text', 'page'],
        KeyAttr => [],
    );

    my $data = $xs->XMLin($INPUT);
    my $pages = $data->{page} || [];

    for my $page (@$pages) {
        $self->{logger}->log_debug("Processing page number: $page->{number}");
        ($permit, $permit_count) = $self->_process_page($page, $permit, $permit_count, $csv, $OUTPUT);
    }

    if ($permit->{permit_number}) {
        $csv->print_hr($OUTPUT, $self->_clean_data($permit));
        $permit_count++;
    }

    $self->{logger}->log_summary("Done parsing, obtained $permit_count number of permits");

    close $INPUT;
    close $OUTPUT;
}

sub _process_page {
    my ($self, $page, $permit, $permit_count, $csv, $OUTPUT) = @_;

    for my $text (@{$page->{text}}) {
        next unless $text->{font} && $text->{font} eq '1';
        next unless $self->_is_valid_line($text->{content});

        my $content = $text->{content};
        ($permit, $permit_count) = $self->_parse_line($content, $permit, $text, $csv, $OUTPUT, $permit_count);
    }

    return ($permit, $permit_count);
}

sub _parse_line {
    my ($self, $content, $permit, $text, $csv, $OUTPUT, $permit_count) = @_;

    my $left = $text->{left};

    if ($left > 20 && $left < 50) {
        if ($permit->{permit_number}) {
            $permit = $self->_clean_data($permit);
            $csv->print_hr($OUTPUT, $permit);
            $permit_count++;
            $permit = {};
        }
        $permit->{permit_number} = $content;
    } elsif ($left > 110 && $left < 140) {
        $permit->{status} .= ' ' . $content;
    } elsif ($left > 160 && $left < 220) {
        $permit->{permit_type} .= ' ' . $content;
    } elsif ($left > 280 && $left < 330) {
        $permit->{applied_date} = $content;
    } elsif ($left > 350 && $left < 400) {
        $permit->{issued_date} = $content;
    } elsif ($left > 420 && $left < 500) {
        $permit->{address} .= ' ' . $content;
    } elsif ($left > 660 && $left < 1000) {
        $permit->{description} .= ' ' . $content;
    } elsif ($left > 1060 && $left < 1120) {
        $permit->{parcel_number} = $content;
    } elsif ($left > 1180 && $left < 1240) {
        $permit->{fee} = $content;
    } elsif ($left > 1280 && $left < 1320) {
        $permit->{valuation} = $content;
    }

    return ($permit, $permit_count);
}

sub _convert_pdf_to_xml {
    my ($self) = @_;

    my $xml_file = $self->{file};
    $xml_file =~ s/\.pdf$/.xml/i;

    my $command = "pdftohtml -xml -nodrm -q '$self->{file}' '$xml_file'";
    system($command) == 0 or die "Failed to convert PDF to XML: $!";

    $self->{logger}->log_info("Converted PDF to XML: $xml_file");

    return $xml_file;
}

sub _prepare_io_files {
    my ($self, $xml_file) = @_;

    open (my $OUTPUT, '>:encoding(utf8)', $self->{output})
        or die "Could not open file '$self->{output}' $!\n";

    open (my $INPUT, '<:encoding(utf8)', $xml_file)
        or die "Could not open file '$xml_file' $!\n";

    my $csv = Text::CSV->new({
        binary => 1,
        sep_char => ',',
        eol => "\n",
        quote_char => '"',
        auto_diag => 1,
    });

    my @columns = $self->_get_columns();
    $csv->column_names(\@columns);

    $csv->print_hr($OUTPUT, { map { $_ => $_ } @columns });

    return ($INPUT, $OUTPUT, $csv);
}

sub _is_valid_line {
    my ($self, $line) = @_;

    return 0 unless $line;
    return 0 if $line =~ /page\s+\d+/i;
    return 0 if $line =~ /construction\-application\-\d+/i;

    return 1;
}

sub _get_columns {
    my ($self) = @_;

    return qw( permit_number status permit_type applied_date issued_date address 
        parcel_number fee valuation description );
}

sub _clean_data {
    my ($self, $permit) = @_;

    for my $key (keys %$permit) {
        next unless $permit->{$key};

        $permit->{$key} =~ s/[\r\n]+/ /g;
        $permit->{$key} =~ s/&amp;/&/g;
        $permit->{$key} = $self->_cleanup_spaces($permit->{$key});
    }
    return $permit;
}

sub _cleanup_spaces {
    my ($self, $data) = @_;

    return undef unless $data;

    $data =~ s/^\s+|\s+$//g;
    $data =~ s/\s{2,}/ /g;

    return $data;
}

1;