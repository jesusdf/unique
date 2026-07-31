# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for the ``corpus_diff`` result-comparator normalizer (audit A10-H).

The comparator canonicalizes driver-representation differences (a datetime vs its
ISO string, a JSON blob vs its parsed dict, interval objects) so equal *values*
compare equal across engines — WITHOUT loosening real comparisons. Every upgrade
carries a negative test proving it does not over-normalize.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from helpers.corpus_diff import normalize_cell, normalize_rows


class _IntervalYM:
    """Stand-in for oracledb.IntervalYM (year-month interval), duck-typed."""

    def __init__(self, years: int, months: int) -> None:
        self.years = years
        self.months = months


class TestDatetimeCanonicalization:
    def test_space_string_matches_datetime_object(self) -> None:
        # One driver returns a datetime, another the same instant as text.
        assert normalize_cell("2020-01-01 10:30:00") == normalize_cell(
            dt.datetime(2020, 1, 1, 10, 30, 0)
        )

    def test_tz_aware_matches_naive_wall_clock(self) -> None:
        assert normalize_cell(
            dt.datetime(2020, 6, 15, 10, 30, tzinfo=dt.UTC)
        ) == normalize_cell(dt.datetime(2020, 6, 15, 10, 30))

    def test_midnight_datetime_collapses_to_date(self) -> None:
        assert normalize_cell(dt.datetime(2020, 1, 1, 0, 0, 0)) == normalize_cell(
            dt.date(2020, 1, 1)
        )
        assert normalize_cell("2020-01-01 00:00:00") == normalize_cell(
            dt.date(2020, 1, 1)
        )

    def test_time_string_and_object_match_across_fraction_widths(self) -> None:
        # SQL Server TIME(7) renders 7 fractional digits; another engine none.
        assert (
            normalize_cell("10:30:45")
            == normalize_cell("10:30:45.0000000")
            == normalize_cell(dt.time(10, 30, 45))
        )

    def test_negative_different_instants_stay_different(self) -> None:
        assert normalize_cell("2020-01-01 10:30:00") != normalize_cell(
            "2020-01-01 10:30:01"
        )

    def test_negative_fractional_second_rounding_stays_a_mismatch(self) -> None:
        # ts-frac-seconds: .123456 vs .123457 is a real value difference.
        assert normalize_cell("2020-01-01T10:20:30.123456") != normalize_cell(
            "2020-01-01T10:20:30.123457"
        )

    def test_negative_date_string_never_equals_an_integer(self) -> None:
        # ts-cast-int-datetime: a DATE vs the integer 19000102 must stay apart.
        assert normalize_cell("2020-01-01") != normalize_cell(19000102)
        assert normalize_cell("1900-01-02") != normalize_cell(19000102)


class TestIntervalCanonicalization:
    def test_equal_day_intervals_match(self) -> None:
        assert normalize_cell(dt.timedelta(days=1, hours=1)) == normalize_cell(
            dt.timedelta(seconds=90000)
        )

    def test_equal_year_month_intervals_match(self) -> None:
        assert normalize_cell(_IntervalYM(1, 2)) == normalize_cell(_IntervalYM(0, 14))

    def test_negative_year_month_never_equals_a_day_count(self) -> None:
        # 1 year 2 months != 425 days — must stay a mismatch (brief A10-H).
        assert normalize_cell(_IntervalYM(1, 2)) != normalize_cell(
            dt.timedelta(days=425)
        )

    def test_negative_different_day_intervals_differ(self) -> None:
        assert normalize_cell(dt.timedelta(days=1)) != normalize_cell(
            dt.timedelta(days=2)
        )


class TestJsonCanonicalization:
    def test_whitespace_only_difference_matches(self) -> None:
        assert normalize_cell("[1, 2]") == normalize_cell("[1,2]")

    def test_parsed_object_matches_json_text(self) -> None:
        assert normalize_cell({"b": 2, "a": 1}) == normalize_cell('{"a": 1, "b": 2}')

    def test_parsed_list_matches_json_text_with_scalars(self) -> None:
        assert normalize_cell([1, "a", None, True]) == normalize_cell(
            '[1, "a", null, true]'
        )

    def test_negative_different_json_stays_different(self) -> None:
        assert normalize_cell('{"a": 1}') != normalize_cell('{"a": 2}')

    def test_negative_comma_list_not_parsed_as_json(self) -> None:
        # '1,2' is not JSON (does not start with { or [) — must not equal '12'.
        assert normalize_cell("1,2") != normalize_cell("12")

    def test_negative_json_true_scalar_not_equal_to_one(self) -> None:
        # A bare 'true'/'1' are scalars, not object/array JSON, so they are not
        # JSON-normalized and stay distinct strings.
        assert normalize_cell("true") != normalize_cell("1")


class TestNoOverNormalization:
    def test_plain_strings_untouched(self) -> None:
        assert normalize_cell("hello") == "hello"
        assert normalize_cell("12") == "12"
        assert normalize_cell("1,2") == "1,2"

    def test_non_json_brace_text_left_as_is(self) -> None:
        # Starts with '{' but is not JSON — kept verbatim, not silently dropped.
        assert normalize_cell("{not json}") == "{not json}"

    def test_rows_still_order_insensitive(self) -> None:
        assert normalize_rows([(2,), (1,)]) == normalize_rows([(1,), (2,)])


class TestNumericTolerance:
    """Brief A10-T2 (maintainer decision 2026-07-31): same value + precision
    diff = match, via rounding to the COARSER operand's own precision. See the
    ``corpus_diff`` module docstring for the full rule and its justification."""

    # -- positive pairs: same value, different display precision -> MATCH --

    def test_avg_style_repeating_decimal_matches_shorter_display(self) -> None:
        assert normalize_cell(0.333333) == normalize_cell(0.3333)

    def test_more_decimals_matches_fewer(self) -> None:
        assert normalize_cell(1.6667) == normalize_cell(1.666666)

    def test_trailing_zero_scale_matches(self) -> None:
        assert normalize_cell(Decimal("5.5")) == normalize_cell(Decimal("5.50"))

    def test_float_chain_rounding_matches_via_the_coarser_side(self) -> None:
        # Caught by coarser-precision rounding alone, no relative-epsilon
        # fallback needed here: 1.0 has 1 decimal digit, which already forces
        # 0.999999 down to the same 1-decimal-place value.
        assert normalize_cell(1.0) == normalize_cell(0.999999)

    def test_int_and_equal_float_match(self) -> None:
        assert normalize_cell(2.0) == normalize_cell(2)

    def test_reversed_repeating_decimal_matches(self) -> None:
        assert normalize_cell(0.6667) == normalize_cell(0.666667)

    def test_transcendental_float_noise_matches_via_relative_epsilon(self) -> None:
        # Live regression (ts-trig / my-trig-suite, caught by the FE gate):
        # Oracle's TAN vs SQL Server's TAN/COT agree to ~15 significant
        # digits, not bit-for-bit — both operands report full float
        # precision, so coarser-precision rounding alone is a no-op here;
        # only the relative-epsilon fallback bridges it.
        assert normalize_cell(0.6420926159343306) == normalize_cell(0.6420926159343308)

    def test_relative_epsilon_does_not_mask_a_real_difference(self) -> None:
        # A ~3% relative gap must stay a mismatch even though both operands
        # are "full precision" floats — the fallback is bound far tighter.
        assert normalize_cell(0.3333333333333) != normalize_cell(0.3433333333333)

    # -- negative pairs: must stay a mismatch --

    def test_different_ints_stay_different(self) -> None:
        assert normalize_cell(1) != normalize_cell(2)

    def test_same_precision_different_value_stays_different(self) -> None:
        assert normalize_cell(0.3333) != normalize_cell(0.3433)

    def test_date_looking_int_never_matches_a_date_string(self) -> None:
        assert normalize_cell(19000102) != normalize_cell("2020-01-01")

    def test_int_vs_half_unit_float_stays_different(self) -> None:
        # 123 vs 123.5 is a real value difference, not a precision artifact —
        # coarsening 123.5 to 0 decimal places rounds it to 124, not 123.
        assert normalize_cell(123) != normalize_cell(123.5)

    def test_datetime_fractional_seconds_untouched_by_numeric_tolerance(self) -> None:
        # A different normalizer (temporal strings are matched before numeric
        # tolerance ever runs) — .123456 vs .123457 must stay a mismatch.
        assert normalize_cell("2020-01-01T10:20:30.123456") != normalize_cell(
            "2020-01-01T10:20:30.123457"
        )

    # -- zero-adjacent guard --

    def test_zero_matches_pure_float_noise(self) -> None:
        assert normalize_cell(0.0) == normalize_cell(1e-12)

    def test_zero_does_not_match_a_real_small_value(self) -> None:
        # Without the guard, coarsening to 0 int decimal places would round
        # 0.4 down to 0 and falsely match — the guard forces an absolute
        # epsilon instead whenever either side is exactly zero.
        assert normalize_cell(0) != normalize_cell(0.4)

    def test_zero_does_not_match_a_small_but_real_decimal(self) -> None:
        assert normalize_cell(0.0) != normalize_cell(0.0004)

    # -- string scope: entirely-numeric text gets the same tolerance --

    def test_pure_fractional_string_gets_numeric_tolerance(self) -> None:
        assert normalize_cell("5.50") == normalize_cell("5.5")
        assert normalize_cell("0.333333") == normalize_cell("0.3333")

    def test_number_embedded_in_longer_text_is_not_touched(self) -> None:
        # Never a substring of longer text — 'd=0.333333' stays a plain,
        # distinct string even though the embedded numbers would tolerate.
        assert normalize_cell("d=0.333333") != normalize_cell("d=0.3333")
        assert isinstance(normalize_cell("d=0.333333"), str)

    def test_bare_integer_string_stays_a_plain_string(self) -> None:
        # No decimal point -> out of scope, left exactly as before (no need
        # for tolerance on an exact integer string).
        assert normalize_cell("12") == "12"
        assert isinstance(normalize_cell("12"), str)
