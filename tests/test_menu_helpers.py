"""Tests for pure helpers in rover.menu.

Covers _fmt_tokens boundary values:
  - 0 → "0"
  - 999 → "999"
  - 1000 → "1.0k"
  - 1234 → "1.2k"
  - 999_999 → "1000.0k"  (just under 1M — should be in k, not M)
  - 1_000_000 → "1.0M"
  - 1_234_567 → "1.2M"

Also covers _now_str returns a non-empty string (smoke test for the helper
used by _render_menu — we don't snapshot the exact value, just prove it runs).
"""

from __future__ import annotations


from rover.menu import _fmt_tokens, _now_str


class TestFmtTokens:
    def test_zero(self):
        assert _fmt_tokens(0) == "0"

    def test_below_thousand(self):
        assert _fmt_tokens(999) == "999"

    def test_exactly_one_thousand(self):
        assert _fmt_tokens(1000) == "1.0k"

    def test_one_thousand_two_hundred_thirty_four(self):
        assert _fmt_tokens(1234) == "1.2k"

    def test_just_below_one_million(self):
        # 999_999 < 1_000_000 so it should format as k
        result = _fmt_tokens(999_999)
        assert result.endswith("k")

    def test_exactly_one_million(self):
        assert _fmt_tokens(1_000_000) == "1.0M"

    def test_large_millions(self):
        assert _fmt_tokens(1_234_567) == "1.2M"


class TestNowStr:
    def test_returns_non_empty_string(self):
        result = _now_str()
        assert isinstance(result, str)
        assert len(result) > 0
