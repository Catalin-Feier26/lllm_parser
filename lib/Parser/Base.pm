package Parser::Base;

use strict;
use warnings;
use v5.30;

use Utils::ConsoleLogger;

sub new {
	my ($class, %args) = @_;
	
	my $self = {
		file   => $args{file},   
		output => $args{output},
		debug => $args{debug}
	};

	$self->{logger} = Utils::ConsoleLogger->new( debug => $self->{debug} );

	bless $self, $class;
	return $self;
}

sub parse {
	my ($self) = @_;
	die "Parse method MUST BE IMPLEMENTED.\n";
}

sub cleanup_temp_file {
	my ($self, $file) = @_;

	return unless defined $file;

	if (-e $file) {
		unlink $file or warn "Warning: Could not delete temporary file '$file': $!\n";
	}
}

1;