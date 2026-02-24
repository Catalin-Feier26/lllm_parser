package Parser::CA::LosAngeles::TempleCity_CSV;

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

    my $in_csv = Text::CSV_XS->new({ binary => 1 });
    $in_csv->column_names($self->_get_columns());

    my $out_csv = Text::CSV_XS->new({ binary => 1, eol => "\n" });
    $out_csv->column_names($self->_get_output_columns());

    return ($INPUT, $OUTPUT, $in_csv, $out_csv);
}

sub _get_columns {
    my ($self) = @_;

    return qw ( address parcel_number permit_number permit_type sub_type description valuation status
        applied_date issued_date expire_date finaled_date contractor_name );
}

sub _get_output_columns {
    my ($self) = @_;

    return qw ( address parcel_number permit_number permit_type description valuation status
        applied_date issued_date contractor_name );
}
1;