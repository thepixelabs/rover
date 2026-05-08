"""Tests for rover's project-aware tmux wrapping of altergo launches.

The contract:
  - When wrap_tmux=True, tmux is available, and we're NOT inside tmux,
    _exec_altergo must call session_manager.new_attached_session with
    cmd=[altergo, account, ...] and a session name derived from
    <project>/<account>/<provider>.
  - When inside tmux (TMUX env set), wrapping is skipped regardless.
  - When wrap_tmux=False, wrapping is skipped.
  - When tmux is unavailable, wrapping is skipped.
  - When the session already exists, _prompt_attach_or_new is consulted
    and 'attach' routes to attach_session, 'new' creates a unique name,
    'cancel' aborts.
"""

from __future__ import annotations

import pathlib
import pytest

from rover.altergo_launcher import (
    _derive_session_name,
    _sanitize_tmux_segment,
    _exec_altergo,
)


# ---------------------------------------------------------------------------
# _sanitize_tmux_segment
# ---------------------------------------------------------------------------

class TestSanitize:
    def test_alnum_unchanged(self):
        assert _sanitize_tmux_segment("dispatch") == "dispatch"

    def test_slash_allowed(self):
        assert _sanitize_tmux_segment("a/b") == "a/b"

    def test_hyphen_allowed(self):
        assert _sanitize_tmux_segment("my-project") == "my-project"

    def test_underscore_allowed(self):
        assert _sanitize_tmux_segment("my_project") == "my_project"

    def test_dot_replaced(self):
        assert _sanitize_tmux_segment("my.project") == "my-project"

    def test_colon_replaced(self):
        assert _sanitize_tmux_segment("a:b") == "a-b"

    def test_whitespace_replaced(self):
        assert _sanitize_tmux_segment("has spaces") == "has-spaces"

    def test_empty_string(self):
        assert _sanitize_tmux_segment("") == "unknown"

    def test_all_unsafe(self):
        assert _sanitize_tmux_segment("...") == "unknown"

    def test_leading_trailing_hyphens_stripped(self):
        assert _sanitize_tmux_segment(".foo.") == "foo"


# ---------------------------------------------------------------------------
# _derive_session_name
# ---------------------------------------------------------------------------

class TestDeriveName:
    def test_normal(self):
        n = _derive_session_name(pathlib.Path("/x/dispatch"), "bob", "claude")
        assert n == "dispatch/bob/claude"

    def test_native(self):
        n = _derive_session_name(pathlib.Path("/x/myapp"), "native", "codex")
        assert n == "myapp/native/codex"

    def test_project_with_dots(self):
        n = _derive_session_name(pathlib.Path("/x/my.repo"), "work", "gemini")
        assert n == "my-repo/work/gemini"

    def test_none_project_falls_back_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        n = _derive_session_name(None, "bob", "claude")
        assert n.endswith("/bob/claude")
        # basename of tmp_path appears as first segment
        assert n.startswith(tmp_path.name + "/")

    def test_account_with_unsafe_chars(self):
        n = _derive_session_name(pathlib.Path("/x/foo"), "bad:acct", "claude")
        assert n == "foo/bad-acct/claude"


# ---------------------------------------------------------------------------
# _exec_altergo wrapping behaviour
# ---------------------------------------------------------------------------

_FAKE_ALTERGO_BIN = "/usr/local/bin/altergo"


@pytest.fixture()
def patch_tmux_available(monkeypatch):
    """Make session_manager.is_available return True (overrides fake_execvp's override)."""
    monkeypatch.setattr("rover.session_manager.is_available", lambda: True)


@pytest.fixture()
def patch_no_tmux_env(monkeypatch):
    """Ensure we're NOT inside a tmux session for the purposes of the test."""
    monkeypatch.delenv("TMUX", raising=False)


@pytest.fixture()
def patch_which_altergo(monkeypatch):
    import shutil as _shutil
    monkeypatch.setattr(_shutil, "which", lambda name: _FAKE_ALTERGO_BIN)


@pytest.fixture()
def patch_wrap_on(monkeypatch):
    monkeypatch.setattr(
        "rover.config.load_config",
        lambda: {"wrap_tmux": True},
    )


@pytest.fixture()
def patch_wrap_off(monkeypatch):
    monkeypatch.setattr(
        "rover.config.load_config",
        lambda: {"wrap_tmux": False},
    )


class TestWrapsWhenEnabled:
    def test_new_session_called_with_project_name(
        self, monkeypatch, patch_tmux_available, patch_no_tmux_env,
        patch_which_altergo, patch_wrap_on, tmp_path,
    ):
        """When wrapping, session name starts with the project basename."""
        calls = []
        def record_new_attached(name, *, cwd, cmd):
            calls.append(("new_attached", name, cwd, cmd))
            return 0
        monkeypatch.setattr(
            "rover.session_manager.new_attached_session", record_new_attached,
        )
        monkeypatch.setattr("rover.session_manager.has_session", lambda n: False)

        proj = tmp_path / "myproj"
        proj.mkdir()
        from rich.console import Console
        _exec_altergo(
            Console(quiet=True),
            project_path=proj,
            chosen_account="bob",
            chosen_provider=None,
            yolo=False,
            yolo_resume=False,
        )

        assert len(calls) == 1
        _tag, name, cwd, cmd = calls[0]
        assert name.startswith("myproj/bob/")
        assert cwd == str(proj)
        assert cmd[0] == _FAKE_ALTERGO_BIN
        assert cmd[1] == "bob"

    def test_skipped_when_inside_tmux(
        self, monkeypatch, patch_tmux_available, patch_which_altergo,
        patch_wrap_on, tmp_path, fake_execvp,
    ):
        """If TMUX env is set, skip wrapping and use the direct path."""
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1,0")
        # fake_execvp already disables tmux availability; re-enable to prove
        # the TMUX env check is what's skipping wrap.
        monkeypatch.setattr("rover.session_manager.is_available", lambda: True)

        called = []
        monkeypatch.setattr(
            "rover.session_manager.new_attached_session",
            lambda *a, **kw: called.append("wrapped") or 0,
        )

        proj = tmp_path / "myproj"
        proj.mkdir()
        from rich.console import Console
        with pytest.raises(SystemExit):
            _exec_altergo(
                Console(quiet=True),
                project_path=proj,
                chosen_account="bob",
                chosen_provider=None,
                yolo=False,
                yolo_resume=False,
            )

        assert called == [], "should NOT wrap when already inside tmux"
        # Direct path should have recorded the altergo argv via fake_execvp
        assert fake_execvp[0][1][0] == _FAKE_ALTERGO_BIN
        assert fake_execvp[0][1][1] == "bob"

    def test_skipped_when_wrap_tmux_off(
        self, monkeypatch, patch_tmux_available, patch_no_tmux_env,
        patch_which_altergo, patch_wrap_off, tmp_path, fake_execvp,
    ):
        """wrap_tmux=False → direct exec, no tmux session created."""
        called = []
        monkeypatch.setattr(
            "rover.session_manager.new_attached_session",
            lambda *a, **kw: called.append("wrapped") or 0,
        )
        # Re-enable tmux availability to isolate the wrap_tmux flag behavior.
        monkeypatch.setattr("rover.session_manager.is_available", lambda: True)

        proj = tmp_path / "myproj"
        proj.mkdir()
        from rich.console import Console
        with pytest.raises(SystemExit):
            _exec_altergo(
                Console(quiet=True),
                project_path=proj,
                chosen_account="bob",
                chosen_provider=None,
                yolo=False,
                yolo_resume=False,
            )

        assert called == []
        assert fake_execvp[0][1][0] == _FAKE_ALTERGO_BIN

    def test_skipped_when_tmux_unavailable(
        self, monkeypatch, patch_no_tmux_env,
        patch_which_altergo, patch_wrap_on, tmp_path, fake_execvp,
    ):
        """tmux not on PATH → direct exec."""
        # fake_execvp already patched is_available=False — leave it.
        called = []
        monkeypatch.setattr(
            "rover.session_manager.new_attached_session",
            lambda *a, **kw: called.append("wrapped") or 0,
        )

        proj = tmp_path / "myproj"
        proj.mkdir()
        from rich.console import Console
        with pytest.raises(SystemExit):
            _exec_altergo(
                Console(quiet=True),
                project_path=proj,
                chosen_account="bob",
                chosen_provider=None,
                yolo=False,
                yolo_resume=False,
            )

        assert called == []


class TestCollisionPrompt:
    def test_attach_existing(
        self, monkeypatch, patch_tmux_available, patch_no_tmux_env,
        patch_which_altergo, patch_wrap_on, tmp_path,
    ):
        """When session exists and user picks Attach, attach_session is called."""
        monkeypatch.setattr("rover.session_manager.has_session", lambda n: True)
        monkeypatch.setattr(
            "rover.altergo_launcher._prompt_attach_or_new",
            lambda c, n: "attach",
        )

        attached = []
        monkeypatch.setattr(
            "rover.session_manager.attach_session",
            lambda name: attached.append(name),
        )
        created = []
        monkeypatch.setattr(
            "rover.session_manager.new_attached_session",
            lambda *a, **kw: created.append(a) or 0,
        )

        proj = tmp_path / "myproj"
        proj.mkdir()
        from rich.console import Console
        _exec_altergo(
            Console(quiet=True),
            project_path=proj,
            chosen_account="bob",
            chosen_provider=None,
            yolo=False,
            yolo_resume=False,
        )
        assert len(attached) == 1 and attached[0].startswith("myproj/bob/")
        assert created == []

    def test_new_instance_gets_unique_name(
        self, monkeypatch, patch_tmux_available, patch_no_tmux_env,
        patch_which_altergo, patch_wrap_on, tmp_path,
    ):
        """Picking 'new' suffixes with #2 via unique_session_name."""
        monkeypatch.setattr("rover.session_manager.has_session", lambda n: True)
        monkeypatch.setattr(
            "rover.altergo_launcher._prompt_attach_or_new",
            lambda c, n: "new",
        )
        monkeypatch.setattr(
            "rover.session_manager.unique_session_name",
            lambda base: f"{base}#2",
        )

        created = []
        monkeypatch.setattr(
            "rover.session_manager.new_attached_session",
            lambda name, *, cwd, cmd: created.append(name) or 0,
        )

        proj = tmp_path / "myproj"
        proj.mkdir()
        from rich.console import Console
        _exec_altergo(
            Console(quiet=True),
            project_path=proj,
            chosen_account="bob",
            chosen_provider=None,
            yolo=False,
            yolo_resume=False,
        )
        assert len(created) == 1 and created[0].endswith("#2")

    def test_cancel_aborts(
        self, monkeypatch, patch_tmux_available, patch_no_tmux_env,
        patch_which_altergo, patch_wrap_on, tmp_path,
    ):
        """Picking 'cancel' returns without creating or attaching."""
        monkeypatch.setattr("rover.session_manager.has_session", lambda n: True)
        monkeypatch.setattr(
            "rover.altergo_launcher._prompt_attach_or_new",
            lambda c, n: "cancel",
        )
        created, attached = [], []
        monkeypatch.setattr(
            "rover.session_manager.new_attached_session",
            lambda *a, **kw: created.append(a) or 0,
        )
        monkeypatch.setattr(
            "rover.session_manager.attach_session",
            lambda name: attached.append(name),
        )

        proj = tmp_path / "myproj"
        proj.mkdir()
        from rich.console import Console
        _exec_altergo(
            Console(quiet=True),
            project_path=proj,
            chosen_account="bob",
            chosen_provider=None,
            yolo=False,
            yolo_resume=False,
        )
        assert created == [] and attached == []
