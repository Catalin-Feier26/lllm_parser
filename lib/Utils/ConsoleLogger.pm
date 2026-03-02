package Utils::ConsoleLogger;

use strict;
use warnings;
use v5.30;

use POSIX qw(strftime);

sub new {
    my ($class, %args) = @_;

    my $self = {
        debug => $args{debug} ? 1 : 0,
    };

    return bless $self, $class;
}

sub log_info {
    my ($self, $message) = @_;
    $self->_log('INFO', $message);
    return;
}

sub log_debug {
    my ($self, $message) = @_;
    return unless $self->{debug};

    $self->_log('DEBUG', $message);
    return;
}

sub log_warning {
    my ($self, $message) = @_;
    $self->_log('WARNING', $message);
    return;
}

sub log_error {
    my ($self, $message) = @_;
    $self->_log('ERROR', $message);
    return;
}

sub log_summary {
    my ($self, $message) = @_;
    $self->_log('SUMMARY', $message);
    return;
}

sub log_exit_with_error {
    my ($self, $message) = @_;
    $self->log_error($message);
    exit 1;
}

sub _log {
    my ($self, $level, $message) = @_;

    $message //= '';
    $message =~ s/\s+\z//;

    my $time = strftime('%H:%M:%S', localtime);

    printf "[%s] [%s] %s\n", $time, $level, $message;

    return;
}

1;