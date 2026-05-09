"""Tests for rover.sessions_index.

Covers:
  - _decode_project_path: happy path, leading dash, empty string, no dashes
  - _clean: code fence stripping, whitespace collapse
  - _extract_text: str content, list-of-blocks content, non-str/non-list
  - _is_real_user_message: real messages vs. tool_result echoes, edge types
  - _scan_session_preview: real tmp file, 40-line cap, empty file
  - list_altergo_sessions(): dedup by session_id, sort order, missing-dir resilience,
    empty account resilience, multi-session sort
"""

from __future__ import annotations

import json


from rover.sessions_index import (
    _clean,
    _decode_project_path,
    _extract_text,
    _is_real_user_message,
    _scan_session_preview,
    list_altergo_sessions,
    _MAX_SCAN_LINES,
    _PREVIEW_MAX,
)


# ---------------------------------------------------------------------------
# _decode_project_path
# ---------------------------------------------------------------------------

class TestDecodeProjectPath:
    def test_leading_dash_becomes_root_slash(self):
        # Leading dash is replaced with `/`; subsequent dashes become `/`.
        # -home-alice-projects-foo → /home/alice/projects/foo
        assert _decode_project_path("-home-alice-projects-foo") == "/home/alice/projects/foo"

    def test_no_leading_dash_replaces_all_dashes(self):
        # Without a leading dash, every dash becomes a slash
        assert _decode_project_path("home-user-proj") == "home/user/proj"

    def test_empty_string_returns_empty(self):
        assert _decode_project_path("") == ""

    def test_single_word_no_dashes(self):
        assert _decode_project_path("myproject") == "myproject"


# ---------------------------------------------------------------------------
# _clean
# ---------------------------------------------------------------------------

class TestClean:
    def test_collapses_whitespace(self):
        assert _clean("  hello   world  ") == "hello world"

    def test_strips_code_fence(self):
        result = _clean("before\n```python\nprint('hi')\n```\nafter")
        assert "[code]" in result
        assert "print" not in result

    def test_empty_string(self):
        assert _clean("") == ""


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_string_content_returned_as_is(self):
        assert _extract_text("hello world") == "hello world"

    def test_list_of_text_blocks_joined(self):
        content = [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
        result = _extract_text(content)
        assert "first" in result
        assert "second" in result

    def test_list_skips_non_text_blocks(self):
        content = [
            {"type": "tool_use", "id": "x"},
            {"type": "text", "text": "visible"},
        ]
        assert _extract_text(content) == "visible"

    def test_non_string_non_list_returns_empty(self):
        assert _extract_text(None) == ""  # type: ignore[arg-type]
        assert _extract_text(42) == ""    # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _is_real_user_message
# ---------------------------------------------------------------------------

class TestIsRealUserMessage:
    def test_string_content_real_message(self):
        obj = {"type": "user", "message": {"content": "Hello!"}}
        assert _is_real_user_message(obj) is True

    def test_blank_string_content_not_real(self):
        obj = {"type": "user", "message": {"content": "   "}}
        assert _is_real_user_message(obj) is False

    def test_tool_result_only_not_real(self):
        obj = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "abc", "content": "done"}
                ]
            },
        }
        assert _is_real_user_message(obj) is False

    def test_text_block_in_list_is_real(self):
        obj = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "text", "text": "Refactor this module"}
                ]
            },
        }
        assert _is_real_user_message(obj) is True

    def test_non_user_type_not_real(self):
        obj = {"type": "assistant", "message": {"content": "Sure!"}}
        assert _is_real_user_message(obj) is False

    def test_missing_message_key_not_real(self):
        obj = {"type": "user"}
        assert _is_real_user_message(obj) is False


# ---------------------------------------------------------------------------
# _scan_session_preview
# ---------------------------------------------------------------------------

class TestScanSessionPreview:
    def test_returns_first_user_message_text(self, tmp_path):
        line = json.dumps({
            "type": "user",
            "message": {"content": "Refactor the authentication module"}
        })
        f = tmp_path / "session.jsonl"
        f.write_text(line + "\n", encoding="utf-8")
        preview = _scan_session_preview(f)
        assert "Refactor" in preview

    def test_empty_file_returns_empty_string(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        assert _scan_session_preview(f) == ""

    def test_preview_truncated_to_max_chars(self, tmp_path):
        long_text = "x" * 200
        line = json.dumps({"type": "user", "message": {"content": long_text}})
        f = tmp_path / "long.jsonl"
        f.write_text(line + "\n", encoding="utf-8")
        preview = _scan_session_preview(f)
        assert len(preview) <= _PREVIEW_MAX

    def test_stops_after_max_scan_lines(self, tmp_path):
        """Should stop scanning at _MAX_SCAN_LINES — put the real message past the limit."""
        # _MAX_SCAN_LINES non-user lines, then one real user message
        non_user = json.dumps({"type": "assistant", "message": {"content": "ok"}})
        real_user = json.dumps({"type": "user", "message": {"content": "Should not appear"}})
        lines = [non_user] * _MAX_SCAN_LINES + [real_user]
        f = tmp_path / "deep.jsonl"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # The real user message is beyond the scan limit — preview should be empty
        assert _scan_session_preview(f) == ""

    def test_nonexistent_file_returns_empty_string(self, tmp_path):
        assert _scan_session_preview(tmp_path / "no_such.jsonl") == ""

    def test_skips_tool_result_lines(self, tmp_path):
        tool_result = json.dumps({
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "x", "content": "done"}]
            }
        })
        real_user = json.dumps({"type": "user", "message": {"content": "Real question"}})
        f = tmp_path / "mixed.jsonl"
        f.write_text(tool_result + "\n" + real_user + "\n", encoding="utf-8")
        preview = _scan_session_preview(f)
        assert "Real question" in preview


# ---------------------------------------------------------------------------
# list_altergo_sessions() — integration
# ---------------------------------------------------------------------------

class TestListAltergoSessions:
    def test_returns_list(self, fake_altergo_tree):
        sessions = list_altergo_sessions()
        assert isinstance(sessions, list)

    def test_deduplicates_by_session_id(self, fake_altergo_tree):
        """uuid-1 appears in acct-alpha AND in the native .claude dir — only one record."""
        sessions = list_altergo_sessions()
        ids = [s.session_id for s in sessions]
        assert len(ids) == len(set(ids)), "Duplicate session_ids found"

    def test_sorted_most_recent_first(self, fake_altergo_tree):
        sessions = list_altergo_sessions()
        if len(sessions) >= 2:
            mtimes = [s.modified_at for s in sessions]
            assert mtimes == sorted(mtimes, reverse=True)

    def test_missing_accounts_dir_returns_empty(self, tmp_path, monkeypatch):
        """When ~/.altergo/accounts does not exist, returns [] without raising."""
        import rover.sessions_index as si
        monkeypatch.setattr(si, "_ACCOUNTS_DIR", tmp_path / "nonexistent")
        monkeypatch.setattr(si, "_MAIN_CLAUDE", tmp_path / "nonexistent_claude")
        result = list_altergo_sessions()
        assert result == []

    def test_empty_account_dir_yields_no_sessions(self, fake_altergo_tree):
        """acct-beta has an empty session file — its preview should be empty string."""
        sessions = list_altergo_sessions()
        beta_sessions = [s for s in sessions if s.account == "acct-beta"]
        assert len(beta_sessions) >= 1
        for s in beta_sessions:
            assert s.preview == ""

    def test_session_record_fields_populated(self, fake_altergo_tree):
        """acct-alpha session should have account, provider, project_path, session_id set."""
        sessions = list_altergo_sessions()
        alpha = next((s for s in sessions if s.account == "acct-alpha"), None)
        assert alpha is not None
        assert alpha.provider == "claude"
        assert alpha.project_path != ""
        assert alpha.session_id != ""
        assert alpha.modified_at > 0

    def test_dedup_across_two_accounts_keeps_most_recent(self, tmp_path, monkeypatch):
        """Two managed accounts with the same session UUID → one record (most recent)."""
        import json as _json
        import os as _os
        import time as _time

        acct_a = tmp_path / ".altergo" / "accounts" / "acct-a" / ".claude" / "projects" / "-proj"
        acct_b = tmp_path / ".altergo" / "accounts" / "acct-b" / ".claude" / "projects" / "-proj"
        acct_a.mkdir(parents=True)
        acct_b.mkdir(parents=True)

        uuid = "aaaaaaaa-1111-2222-3333-444444444444"
        real_line = _json.dumps(
            {"type": "user", "message": {"content": "hello"}}
        )

        old = acct_a / f"{uuid}.jsonl"
        new = acct_b / f"{uuid}.jsonl"
        old.write_text(real_line + "\n", encoding="utf-8")
        new.write_text(real_line + "\n", encoding="utf-8")
        _os.utime(old, (_time.time() - 1000, _time.time() - 1000))  # older

        import rover.sessions_index as si
        monkeypatch.setattr(si, "_ACCOUNTS_DIR", tmp_path / ".altergo" / "accounts")
        monkeypatch.setattr(si, "_MAIN_CLAUDE", tmp_path / "no-native")

        sessions = list_altergo_sessions()
        matching = [s for s in sessions if s.session_id == uuid]
        assert len(matching) == 1, "Same UUID across two accounts must dedup to one record"
        assert matching[0].account == "acct-b", "Most recent (acct-b) should win"

    def test_dedup_prefers_account_over_native(self, fake_altergo_tree):
        """When an id exists in both an account and native, the account wins
        even if native is more recent (account context carries the project
        dir rover actually needs)."""
        sessions = list_altergo_sessions()
        uuid_1 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        matching = [s for s in sessions if s.session_id == uuid_1]
        assert len(matching) == 1
        assert matching[0].account == "acct-alpha", "account must beat native"
