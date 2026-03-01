package Utils::Date;

use strict;
use warnings;
use Time::Piece;

use constant DEFAULT_DATE => '1900-01-01';

sub to_ymd_or_default {
    my ($s) = @_;
    my $d = to_ymd($s);
    return $d // DEFAULT_DATE;
}

sub to_ymd {
    my ($s) = @_;

    return undef unless defined $s;

    $s =~ s/^\s+|\s+$//g;
    return undef if $s eq '';
    
    $s =~ s/[,]+$//;
    $s =~ s/\s+/ /g;
    $s =~ s/\s+\d{1,2}:\d{2}:\d{2}.*$//;

    for my $fmt ('%Y-%m-%d', '%m/%d/%Y', '%d.%m.%Y') {
        my $tp;
        eval { $tp = Time::Piece->strptime($s, $fmt); 1 } or next;
        return $tp->strftime('%Y-%m-%d') if $tp;
    }

    return undef;
}

1;