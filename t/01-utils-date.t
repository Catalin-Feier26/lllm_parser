use strict;
use warnings;
use v5.30;

use lib 'lib';

use Test::More;

use Utils::Date ();

is(Utils::Date::to_ymd('2025-01-22'), '2025-01-22', 'already normalized');
is(Utils::Date::to_ymd('08/12/2025'), '2025-08-12', 'MM/DD/YYYY');
is(Utils::Date::to_ymd('22.01.2025'), '2025-01-22', 'DD.MM.YYYY');
is(Utils::Date::to_ymd('22.01.2025 09:55:29'), '2025-01-22', 'drops time');
is(Utils::Date::to_ymd(' 22.01.2025 09:55:29, '), '2025-01-22', 'trims + drops comma');

ok(!defined(Utils::Date::to_ymd(undef)), 'undef -> undef');
ok(!defined(Utils::Date::to_ymd('')), 'empty -> undef');
ok(!defined(Utils::Date::to_ymd('bad')), 'bad -> undef');

is(Utils::Date::to_ymd_or_default(undef), '1900-01-01', 'default for undef');
is(Utils::Date::to_ymd_or_default(''), '1900-01-01', 'default for empty');
is(Utils::Date::to_ymd_or_default('bad'), '1900-01-01', 'default for bad');
is(Utils::Date::to_ymd_or_default('22.01.2025 09:55:29'), '2025-01-22', 'keeps valid');

done_testing();