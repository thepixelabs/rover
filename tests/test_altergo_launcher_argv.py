"""Tests for rover.altergo_launcher._exec_altergo argv construction.

Contract (from _exec_altergo source):
  - base argv when account is not "native":  [altergo_bin, chosen_account]
  - base argv when chosen_provider is set:   [altergo_bin, "native", chosen_provider]
  - yolo=True, yolo_resume=False  → appends "--yolo"
  - yolo_resume=True              → appends "--yolo-resume"
  - yolo_resume="<UUID>"          → appends "--yolo-resume=<UUID>"  (equals form)
  - yolo=False, yolo_resume=False → no extra flag

Also tests run_yolo_resume_pick with empty sessions list (returns without execvp).

Uses fake_execvp fixture (records calls, raises SystemExit(0)).
os.chdir is also patched via the fixture.
shutil.which is patched to return a fixed "altergo" path so the altergo_bin
branch is always taken, keeping argv[0] deterministic.
"""

from __future__ import annotations

import pathlib
import pytest

from rover.altergo_launcher import _exec_altergo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_ALTERGO_BIN = "/usr/local/bin/altergo"
_FAKE_UUID = "12345678-1234-1234-1234-123456789abc"


def _exec(
    monkeypatch,
    fake_execvp,
    *,
    chosen_account: str = "my-account",
    chosen_provider=None,
    yolo: bool = False,
    yolo_resume=False,
):
    """Patch shutil.which and call _exec_altergo; return the recorded argv."""
    import shutil as _shutil
    monkeypatch.setattr(_shutil, "which", lambda name: _FAKE_ALTERGO_BIN)

    from rich.console import Console
    console = Console(quiet=True)

    with pytest.raises(SystemExit):
        _exec_altergo(
            console,
            project_path=pathlib.Path("/tmp/myproject"),
            chosen_account=chosen_account,
            chosen_provider=chosen_provider,
            yolo=yolo,
            yolo_resume=yolo_resume,
        )

    assert len(fake_execvp) == 1, "execvp should be called exactly once"
    _file, argv = fake_execvp[0]
    return argv


# ---------------------------------------------------------------------------
# Base argv — account vs. native/provider path
# ---------------------------------------------------------------------------

class TestBaseArgv:
    def test_account_path_argv(self, monkeypatch, fake_execvp):
        """Given a named account (not native), argv is [altergo, account]."""
        argv = _exec(monkeypatch, fake_execvp, chosen_account="work-acct")
        assert argv[1] == "work-acct"
        assert len(argv) == 2  # no extra flags

    def test_native_provider_path_argv(self, monkeypatch, fake_execvp):
        """Given chosen_provider, argv is [altergo, 'native', provider]."""
        argv = _exec(
            monkeypatch, fake_execvp,
            chosen_account="native",
            chosen_provider="gemini",
        )
        assert argv[1] == "native"
        assert argv[2] == "gemini"

    def test_altergo_bin_is_argv0(self, monkeypatch, fake_execvp):
        argv = _exec(monkeypatch, fake_execvp)
        assert argv[0] == _FAKE_ALTERGO_BIN


# ---------------------------------------------------------------------------
# Yolo flags
# ---------------------------------------------------------------------------

class TestYoloFlags:
    def test_yolo_true_appends_yolo_flag(self, monkeypatch, fake_execvp):
        argv = _exec(monkeypatch, fake_execvp, yolo=True)
        assert "--yolo" in argv

    def test_yolo_false_no_extra_flag(self, monkeypatch, fake_execvp):
        argv = _exec(monkeypatch, fake_execvp, yolo=False)
        assert "--yolo" not in argv
        assert "--yolo-resume" not in " ".join(argv)

    def test_yolo_resume_true_appends_bare_flag(self, monkeypatch, fake_execvp):
        """yolo_resume=True → '--yolo-resume' (no UUID, no equals sign)."""
        argv = _exec(monkeypatch, fake_execvp, yolo_resume=True)
        assert "--yolo-resume" in argv
        # Must be bare — no equals form
        assert not any(a.startswith("--yolo-resume=") for a in argv)

    def test_yolo_resume_uuid_uses_equals_form(self, monkeypatch, fake_execvp):
        """yolo_resume='<UUID>' → '--yolo-resume=<UUID>' (equals form)."""
        argv = _exec(monkeypatch, fake_execvp, yolo_resume=_FAKE_UUID)
        assert f"--yolo-resume={_FAKE_UUID}" in argv

    def test_yolo_resume_uuid_does_not_append_bare_flag(self, monkeypatch, fake_execvp):
        argv = _exec(monkeypatch, fake_execvp, yolo_resume=_FAKE_UUID)
        assert "--yolo-resume" not in argv  # only the equals form should appear

    def test_yolo_resume_takes_precedence_over_yolo(self, monkeypatch, fake_execvp):
        """When yolo_resume is set, --yolo should not appear in argv."""
        argv = _exec(monkeypatch, fake_execvp, yolo=True, yolo_resume=_FAKE_UUID)
        assert "--yolo" not in argv
        assert f"--yolo-resume={_FAKE_UUID}" in argv


# ---------------------------------------------------------------------------
# Parametrized matrix: yolo x yolo_resume x account type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yolo", [False, True])
@pytest.mark.parametrize("yolo_resume", [False, True, _FAKE_UUID])
@pytest.mark.parametrize(
    "chosen_account,chosen_provider",
    [
        ("my-account", None),         # normal account path
        ("native", "claude"),         # native + provider path
    ],
)
def test_argv_matrix(monkeypatch, fake_execvp, yolo, yolo_resume, chosen_account, chosen_provider):
    """Smoke test: for every combination, execvp is called once and argv[0] is set."""
    argv = _exec(
        monkeypatch, fake_execvp,
        chosen_account=chosen_account,
        chosen_provider=chosen_provider,
        yolo=yolo,
        yolo_resume=yolo_resume,
    )
    assert len(argv) >= 2
    assert argv[0] == _FAKE_ALTERGO_BIN


# ---------------------------------------------------------------------------
# run_yolo_resume_pick — empty sessions path
# ---------------------------------------------------------------------------

class TestRunYoloResumePickEmptySessions:
    def test_returns_without_calling_execvp_when_no_sessions(self, monkeypatch, fake_execvp):
        """When list_altergo_sessions returns [], run_yolo_resume_pick must return
        without ever calling os.execvp."""
        import rover.sessions_index as si
        monkeypatch.setattr(si, "list_altergo_sessions", lambda: [])

        # The empty-sessions path shows a Textual error screen; stub it so the
        # test doesn't try to allocate a real TTY for the Textual app.
        import rover.altergo_launcher as al
        monkeypatch.setattr(al, "_show_yolo_pick_no_sessions", lambda: None)

        from rover.altergo_launcher import run_yolo_resume_pick

        run_yolo_resume_pick({}, lambda cfg: None)

        assert fake_execvp == [], "execvp must not be called when sessions list is empty"


# ---------------------------------------------------------------------------
# Altergo-not-found + project-path guard
# ---------------------------------------------------------------------------

class TestAltergoNotFound:
    def test_shows_not_found_screen_when_altergo_missing(self, monkeypatch, fake_execvp):
        """When shutil.which returns None, show the error and do NOT exec."""
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda name: None)

        # _show_altergo_not_found renders a Textual error screen; stub it so
        # the test doesn't try to allocate a real TTY for the Textual app.
        import rover.altergo_launcher as al
        shown: list = []
        monkeypatch.setattr(
            al, "_show_altergo_not_found",
            lambda: shown.append("shown"),
        )
        monkeypatch.setattr(
            "rover.altergo_launcher.os.chdir", lambda p: None
        )

        from rich.console import Console
        _exec_altergo(
            Console(quiet=True),
            project_path=pathlib.Path("/tmp/myproject"),
            chosen_account="my-account",
            chosen_provider=None,
            yolo=True,
            yolo_resume=False,
        )

        assert shown == ["shown"], "not-found screen should be shown"
        assert fake_execvp == [], "execvp must not be called when altergo is not on PATH"


class TestProjectPathGuard:
    def test_chdir_skipped_when_project_path_not_a_dir(self, monkeypatch, fake_execvp, tmp_path):
        """If the decoded project path doesn't exist, rover must NOT chdir into it."""
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda name: _FAKE_ALTERGO_BIN)

        chdir_calls: list = []
        monkeypatch.setattr(
            "rover.altergo_launcher.os.chdir",
            lambda p: chdir_calls.append(p),
        )

        bogus = tmp_path / "does" / "not" / "exist"
        from rich.console import Console
        with pytest.raises(SystemExit):
            _exec_altergo(
                Console(quiet=True),
                project_path=bogus,
                chosen_account="my-account",
                chosen_provider=None,
                yolo=False,
                yolo_resume=_FAKE_UUID,
            )

        assert chdir_calls == [], "chdir must not run when project_path.is_dir() is False"
        # argv was still built and exec'd — just with no chdir.
        assert fake_execvp and fake_execvp[0][1][0] == _FAKE_ALTERGO_BIN

    def test_chdir_runs_when_project_path_exists(self, monkeypatch, fake_execvp, tmp_path):
        import shutil as _shutil
        monkeypatch.setattr(_shutil, "which", lambda name: _FAKE_ALTERGO_BIN)

        chdir_calls: list = []
        monkeypatch.setattr(
            "rover.altergo_launcher.os.chdir",
            lambda p: chdir_calls.append(p),
        )

        real = tmp_path / "real-proj"
        real.mkdir()
        from rich.console import Console
        with pytest.raises(SystemExit):
            _exec_altergo(
                Console(quiet=True),
                project_path=real,
                chosen_account="acct",
                chosen_provider=None,
                yolo=True,
                yolo_resume=False,
            )

        # The launcher now returns to the menu loop after altergo exits, so it
        # captures cwd before chdir and restores it in a finally block. With
        # the fake recorder raising SystemExit mid-call, the finally still runs
        # — expect the project-dir chdir first, then a restore to original cwd.
        assert chdir_calls and chdir_calls[0] == real, \
            "first chdir must enter the real project dir"
