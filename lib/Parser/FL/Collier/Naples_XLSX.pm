package Parser::FL::Collier::Naples_XLSX;

use strict;
use warnings;

use base 'Parser::Base';

use Text::CSV;
use Spreadsheet::Read;

use constant COL_MAP => {
    permit_number    => ['Permit Number', 'Permit #'],
    valuation        => ['Declared value', 'Valuation', 'Value'],
    permit_type      => ['permit type desc', 'permit type'],
    status           => ['permit status desc', 'permit status'],
    address          => ['job site address', 'job site', 'site address'],
    parcel_number    => ['parcel number', 'parcel #', 'property id'],
    issued_date      => ['issued date', 'issue date', 'date issued'],
    applied_date     => ['date applied', 'applied date', 'application date'],
    owner_name       => ['owner name', 'property owner'],
    owner_city       => ['city of owner', 'owner city', 'city'],
    owner_state      => ['state of owner', 'owner state', 'state'],
    owner_zip        => ['zip of owner', 'owner zip', 'zip'],
    contractor_name  => ['contractor name', 'contractor'],
    contractor_city  => ['city 1', 'contractor city', 'city 2'],
    contractor_state => ['state 1', 'contractor state', 'state 2'],
    contractor_zip   => ['zip 1', 'contractor zip', 'zip 2'],
};

sub parse {
    my ($self) = @_;

    $self->{logger}->log_info("Started parsing the file: $self->{file}");

    my ($OUTPUT, $csv) = $self->_prepare_io_files();

    my $permit_count = $self->_parse_xlsx_file($OUTPUT, $csv);

    $self->{logger}->log_summary("Done parsing, obtained $permit_count number of permits");

    close $OUTPUT;

    return;
}

sub _prepare_io_files {
    my ($self) = @_;

    my $output_file = $self->{output};

    open(my $OUTPUT, '>:encoding(utf8)', $output_file)
        or die "Could not open output file '$output_file': $!";

    my $csv = Text::CSV->new({
        binary     => 1,
        sep_char   => ',',
        eol        => "\n",
        quote_char => '"',
        auto_diag  => 1,
    });

    my @columns = $self->_get_output_columns();
    $csv->column_names(\@columns);

    # CSV header row
    $csv->print_hr($OUTPUT, { map { $_ => $_ } @columns });

    return ($OUTPUT, $csv);
}

sub _parse_xlsx_file {
    my ($self, $OUTPUT, $csv) = @_;

    my $file_path = "$self->{file}";
    my $book = ReadData($file_path);
    $self->{logger}->exit_with_error("Could not read XLSX file '$file_path'")
        unless $book && ref($book) eq 'ARRAY' && $book->[0]{sheets};

    my $sheet = $book->[1];
    $self->{logger}->exit_with_error("No worksheets found in XLSX file '$self->{file}'")
        unless $sheet;

    my ($header_row, $col_index) = $self->_find_header_row($sheet);

    my $permit_count = 0;

    for (my $r = $header_row + 1; $r <= ($sheet->{maxrow} || 0); $r++) {
        my $permit = $self->_parse_row($sheet, $r, $col_index);

        next unless $permit->{permit_number};

        $csv->print_hr($OUTPUT, $self->_clean_data($permit));
        $permit_count++;
    }

    return $permit_count;
}

sub _find_header_row {
    my ($self, $sheet) = @_;

    my $wanted = $self->_build_wanted_rows();

    my $best_row;
    my $best_hits = 0;
    my $best_map  = {};

    my $max_row = $sheet->{maxrow} || 0;
    $max_row = 100 if $max_row > 100;

    for my $r (1 .. $max_row) {
        my $row = $self->_get_row_values($sheet, $r);
        my %tmp;
        my $hits = 0;

        for my $c (0 .. $#$row) {
            my $val = $row->[$c];
            next unless defined $val && $val ne '';

            my $norm = $self->_norm($val);
            my $key  = $wanted->{$norm};
            next unless $key;

            next if exists $tmp{$key};

            $tmp{$key} = $c; 
            $hits++;
        }

        if ($hits > $best_hits) {
            $best_hits = $hits;
            $best_row  = $r;
            $best_map  = \%tmp;
        }
    }

    $self->{logger}->exit_with_error("Could not find a valid header row in the XLSX file (best hits: $best_hits)")
        unless $best_row && $best_hits >= 5;

    $self->{logger}->log_info("Identified header row at row $best_row with $best_hits hits");

    return ($best_row, $best_map);
}

sub _build_wanted_rows {
    my ($self) = @_;

    my %lookup;
    while (my ($out_key, $aliases) = each %{ +COL_MAP }) {
        for my $h (@$aliases) {
            $lookup{ $self->_norm($h) } = $out_key;
        }
    }

    return \%lookup;
}

sub _parse_row {
    my ($self, $sheet, $row_num, $col_index) = @_;

    my $row = $self->_get_row_values($sheet, $row_num);
    my $permit = {};

    for my $out_key (keys %{ +COL_MAP }) {
        my $col = $col_index->{$out_key};
        next unless defined $col; 

        my $val = $row->[$col];
        $permit->{$out_key} = defined $val ? $val : '';
    }

    return $permit;
}

sub _get_row_values {
    my ($self, $sheet, $r) = @_;

    my $max_col = $sheet->{maxcol} || 0;
    my @vals;

    for my $c (1 .. $max_col) {
        my $v = $sheet->{cell}[$c][$r];
        push @vals, (defined $v ? $v : '');
    }

    return \@vals;
}

sub _clean_data {
    my ($self, $permit) = @_;

    $permit->{owner_location} = $self->_format_location(
        $permit->{owner_city}, $permit->{owner_state}, $permit->{owner_zip}
    );
    $permit->{contractor_location} = $self->_format_location(
        $permit->{contractor_city}, $permit->{contractor_state}, $permit->{contractor_zip}
    );

    delete @{$permit}{qw(owner_city owner_state owner_zip contractor_city contractor_state contractor_zip)};

    for my $key (keys %$permit) {
        next unless defined $permit->{$key} && $permit->{$key} ne '';

        $permit->{$key} =~ s/[\r\n]+/ /g;
        $permit->{$key} = $self->_cleanup_spaces($permit->{$key});
    }

    return $permit;
}

sub _format_location {
    my ($self, $city, $state, $zip) = @_;

    $city  //= '';
    $state //= '';
    $zip   //= '';

    my $loc = $city;
    $loc .= ", $state" if $state ne '';
    $loc .= " $zip"    if $zip ne '';

    return $loc;
}

sub _cleanup_spaces {
    my ($self, $s) = @_;

    return '' unless defined $s;

    $s =~ s/\s+/ /g;
    $s =~ s/^\s+|\s+$//g;

    return $s;
}

sub _norm {
    my ($self, $s) = @_;

    return '' unless defined $s;

    $s =~ s/\r|\n/ /g;
    $s =~ s/\s+/ /g;
    $s =~ s/^\s+|\s+$//g;
    $s = lc $s;

    return $s;
}

sub _get_output_columns {
    my ($self) = @_;

    return qw(
        permit_number valuation permit_type status address parcel_number issued_date
        applied_date owner_name owner_location contractor_name contractor_location
    );
}

1;
