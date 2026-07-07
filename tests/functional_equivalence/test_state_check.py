# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for the functional-equivalence state checker.

These exercise the pure normalize/compare core with no database, so the bulk of
the harness logic (where subtle false positives/negatives live) is verified in
isolation. The values mimic what each engine's driver returns: Decimal for
NUMBER/DECIMAL, int 0/1 or bool for BIT/BOOLEAN, datetime.date for DATE, padded
str for CHAR, etc.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

from tests.functional_equivalence.state_check import (
    NULL,
    check_state,
    check_table,
    load_expected_state,
    normalize,
)

_EXPECTED_PATH = Path(__file__).parent / "expected_state.yaml"


class TestNormalize:
    def test_bool_from_int(self) -> None:
        assert normalize(1, True) is True
        assert normalize(0, True) is False

    def test_bool_from_decimal(self) -> None:
        # Oracle NUMBER(1) often comes back as Decimal.
        assert normalize(Decimal("1"), True) is True
        assert normalize(Decimal("0"), False) is False

    def test_bool_from_text(self) -> None:
        assert normalize("true", True) is True
        assert normalize("f", False) is False

    def test_bool_from_bit_bytes(self) -> None:
        # MySQL / PostgreSQL return a BIT column as a raw byte.
        assert normalize(b"\x01", True) is True
        assert normalize(b"\x00", False) is False
        assert normalize(bytearray(b"\x01"), True) is True

    def test_decimal_fixes_scale(self) -> None:
        # 61.05 from different engines: Decimal, float-ish str, trailing zeros.
        assert normalize(Decimal("61.05"), "61.05") == "61.05"
        assert normalize(Decimal("61.0500"), "61.05") == "61.05"
        assert normalize("61.05", "61.05") == "61.05"

    def test_decimal_rounds_to_expected_scale(self) -> None:
        assert normalize(Decimal("10"), "10.00") == "10.00"

    def test_int(self) -> None:
        assert normalize(Decimal("3"), 3) == 3
        assert normalize(3, 3) == 3

    def test_string_trims_char_padding(self) -> None:
        assert normalize("Widget   ", "Widget") == "Widget"

    def test_date_from_date_object(self) -> None:
        assert normalize(dt.date(2024, 1, 15), "2024-01-15") == "2024-01-15"

    def test_date_from_datetime(self) -> None:
        assert normalize(dt.datetime(2024, 1, 15, 9, 30), "2024-01-15") == "2024-01-15"

    def test_null_becomes_sentinel(self) -> None:
        assert normalize(None, "anything") == NULL
        assert normalize(None, 5) == NULL


class TestLoadExpectedState:
    def test_loads_canonical_spec(self) -> None:
        state = load_expected_state(_EXPECTED_PATH)
        names = {t.name for t in state.tables}
        assert names == {
            "customer",
            "product",
            "invoice",
            "invoice_line",
            "payment",
            "app_flag",
        }
        invoice = state.table("invoice")
        assert invoice.row_count == 2
        assert invoice.primary_key == "id"


class TestCheckTable:
    def test_matching_rows_pass(self) -> None:
        state = load_expected_state(_EXPECTED_PATH)
        product = state.table("product")
        # Simulate a driver returning Decimal prices and padded names.
        actual = [
            {"id": 1, "name": "Widget", "unit_price": Decimal("10.00")},
            {"id": 2, "name": "Gadget", "unit_price": Decimal("25.50")},
        ]
        assert check_table(product, actual) == []

    def test_wrong_value_is_reported(self) -> None:
        state = load_expected_state(_EXPECTED_PATH)
        product = state.table("product")
        actual = [
            {"id": 1, "name": "Widget", "unit_price": Decimal("10.00")},
            {"id": 2, "name": "Gadget", "unit_price": Decimal("99.99")},
        ]
        mismatches = check_table(product, actual)
        assert len(mismatches) == 1
        assert "unit_price" in str(mismatches[0])

    def test_wrong_row_count_is_reported(self) -> None:
        state = load_expected_state(_EXPECTED_PATH)
        product = state.table("product")
        actual = [{"id": 1, "name": "Widget", "unit_price": Decimal("10.00")}]
        mismatches = check_table(product, actual)
        assert any("row_count" in str(m) for m in mismatches)

    def test_missing_row_is_reported(self) -> None:
        state = load_expected_state(_EXPECTED_PATH)
        product = state.table("product")
        actual = [
            {"id": 1, "name": "Widget", "unit_price": Decimal("10.00")},
            {"id": 3, "name": "Sprocket", "unit_price": Decimal("25.50")},
        ]
        mismatches = check_table(product, actual)
        # id=2 missing (row_count still 2, but pk 2 absent).
        assert any("missing row id=2" in str(m) for m in mismatches)

    def test_bool_is_paid_round_trips(self) -> None:
        state = load_expected_state(_EXPECTED_PATH)
        invoice = state.table("invoice")
        actual = [
            {
                "id": 1,
                "customer_id": 1,
                "issued_on": dt.date(2024, 1, 15),
                "total": Decimal("61.05"),
                "is_paid": 0,
            },
            {
                "id": 2,
                "customer_id": 2,
                "issued_on": dt.date(2024, 2, 1),
                "total": Decimal("39.05"),
                "is_paid": 1,
            },
        ]
        assert check_table(invoice, actual) == []


class TestCheckState:
    def test_full_state_via_read_table(self) -> None:
        state = load_expected_state(_EXPECTED_PATH)
        # A read_table that returns exactly the expected rows (as a driver would).
        tables = {
            "customer": [
                {
                    "id": 1,
                    "name": "Acme",
                    "email": "billing@acme.test",
                    "notes": "no payment",
                },
                {
                    "id": 2,
                    "name": "Globex",
                    "email": "ap@globex.test",
                    "notes": "paid",
                },
            ],
            "product": [
                {"id": 1, "name": "Widget", "unit_price": Decimal("10.00")},
                {"id": 2, "name": "Gadget", "unit_price": Decimal("25.50")},
            ],
            "invoice": [
                {
                    "id": 1,
                    "customer_id": 1,
                    "issued_on": "2024-01-15",
                    "total": Decimal("61.05"),
                    "is_paid": 0,
                },
                {
                    "id": 2,
                    "customer_id": 2,
                    "issued_on": "2024-02-01",
                    "total": Decimal("39.05"),
                    "is_paid": 1,
                },
            ],
            "invoice_line": [
                {
                    "id": 1,
                    "invoice_id": 1,
                    "product_id": 1,
                    "qty": 3,
                    "unit_price": Decimal("10.00"),
                    "line_total": Decimal("30.00"),
                },
                {
                    "id": 2,
                    "invoice_id": 1,
                    "product_id": 2,
                    "qty": 1,
                    "unit_price": Decimal("25.50"),
                    "line_total": Decimal("25.50"),
                },
                {
                    "id": 3,
                    "invoice_id": 2,
                    "product_id": 1,
                    "qty": 1,
                    "unit_price": Decimal("10.00"),
                    "line_total": Decimal("10.00"),
                },
                {
                    "id": 4,
                    "invoice_id": 2,
                    "product_id": 2,
                    "qty": 1,
                    "unit_price": Decimal("25.50"),
                    "line_total": Decimal("25.50"),
                },
            ],
            "payment": [
                {
                    "id": 1,
                    "invoice_id": 2,
                    "paid_on": "2024-02-05",
                    "amount": Decimal("39.05"),
                },
            ],
            "app_flag": [
                {"id": 1, "flag_name": "audit_log", "enabled": True, "note": "on"},
                {"id": 2, "flag_name": "beta_ui", "enabled": False, "note": None},
            ],
        }
        mismatches = check_state(state, lambda name: tables[name])
        assert mismatches == [], "\n".join(str(m) for m in mismatches)


class TestTriggerMaintainedExclusion:
    """Columns marked trigger_maintained can be excluded from assertion.

    A set-based source trigger is a documented divergence on MySQL/Oracle
    (no transition tables), so its maintained values are out of scope there
    (TODO: 'assert trigger-maintained values on PostgreSQL (+ T-SQL)').
    """

    def _expected(self):
        import textwrap

        from tests.functional_equivalence.state_check import load_expected_state

        text = textwrap.dedent("""
            version: 1
            tables:
              invoice:
                row_count: 1
                rows:
                  - { id: 1, customer_id: 2, total: "61.05" }
            trigger_maintained:
              invoice: [total]
            """)
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(text)
            p = Path(f.name)
        return load_expected_state(p)

    def test_mismatch_reported_by_default(self):
        from tests.functional_equivalence.state_check import check_state

        expected = self._expected()
        rows = {"invoice": [{"id": 1, "customer_id": 2, "total": "0.00"}]}
        mismatches = check_state(expected, lambda t: rows[t])
        assert mismatches, "total mismatch must be reported by default"

    def test_ignored_when_flagged(self):
        from tests.functional_equivalence.state_check import check_state

        expected = self._expected()
        rows = {"invoice": [{"id": 1, "customer_id": 2, "total": "0.00"}]}
        mismatches = check_state(
            expected, lambda t: rows[t], ignore_trigger_maintained=True
        )
        assert mismatches == []

    def test_other_columns_still_asserted_when_flagged(self):
        from tests.functional_equivalence.state_check import check_state

        expected = self._expected()
        rows = {"invoice": [{"id": 1, "customer_id": 9, "total": "0.00"}]}
        mismatches = check_state(
            expected, lambda t: rows[t], ignore_trigger_maintained=True
        )
        assert mismatches, "non-trigger columns must still be asserted"
