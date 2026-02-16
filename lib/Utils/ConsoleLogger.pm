package Utils::ConsoleLogger;

use strict;
use warnings;

sub new {
    my ($class, %args) = @_;
    print "Creating ConsoleLogger with args: ", join(", ", map { "$_ => $args{$_}" } keys %args), "\n" if $args{debug};
    my $self = { debug => $args{debug} // 0 };

    bless $self, $class;
    return $self;
}

sub log_info {
    my ($self, $message) = @_;
    print "[INFO] $message\n";
}

sub log_debug {
    my ($self, $message) = @_;
    if ($self->{debug}) {
        print "[DEBUG] $message\n";
    }
}

sub log_error {
    my ($self, $message) = @_;
    print "[ERROR] $message\n";
}

sub log_warning {
    my ($self, $message) = @_;
    print "[WARNING] $message\n";
}

sub log_summary {
    my ($self, $message) = @_;
    print "[SUMMARY] $message\n";
}

sub log_exit_with_error {
    my ($self, $message) = @_;
    print "[ERROR] $message\n";
    exit 1;
}

1;