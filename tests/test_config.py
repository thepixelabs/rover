"""Tests for rover.config — config load/save/defaults.

Covers:
  - Module imports cleanly
  - DEFAULT_CONFIG contains the expected keys
  - load_config returns a dict that includes all DEFAULT_CONFIG keys
  - load_config does not raise when the config file does not exist
  - load_config falls back to defaults for missing keys
  - save_config writes a readable JSON file with the expected content
  - load_config recovers from a corrupt (invalid JSON) config file
"""

from __future__ import annotations

import json

import rover.config as config_module
from rover.config import DEFAULT_CONFIG, load_config, save_config


# ── TestModuleContract ─────────────────────────────────────────────────────────

class TestModuleContract:
    def test_module_imports_cleanly(self) -> None:
        """rover.config is importable without side-effects or errors."""
        assert config_module is not None

    def test_default_config_is_dict(self) -> None:
        """DEFAULT_CONFIG is a plain dict."""
        assert isinstance(DEFAULT_CONFIG, dict)

    def test_default_config_has_expected_keys(self) -> None:
        """Known keys used throughout the codebase are present in DEFAULT_CONFIG."""
        required_keys = {
            "nickname",
            "dispatch_port",
            "theme",
            "header_font",
            "show_tmux",
            "wrap_tmux",
            "time_window_hours",
            "refresh_seconds",
        }
        missing = required_keys - DEFAULT_CONFIG.keys()
        assert not missing, f"Missing keys in DEFAULT_CONFIG: {missing}"

    def test_default_dispatch_port_is_integer(self) -> None:
        """dispatch_port default is an integer so callers can pass it to httpx directly."""
        assert isinstance(DEFAULT_CONFIG["dispatch_port"], int)


# ── TestLoadConfigDefaults ─────────────────────────────────────────────────────

class TestLoadConfigDefaults:
    def test_load_config_returns_dict(self, tmp_path, monkeypatch) -> None:
        """load_config always returns a dict, never None."""
        monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / ".rover")
        monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / ".rover" / "config.json")
        monkeypatch.setattr(config_module, "_CONFIG_TMP", tmp_path / ".rover" / "config.json.tmp")
        monkeypatch.setattr(config_module, "_OLD_CONFIG", tmp_path / ".dispatch-tui" / "config.json")
        result = load_config()
        assert isinstance(result, dict)

    def test_load_config_no_exception_when_file_absent(self, tmp_path, monkeypatch) -> None:
        """load_config does not raise when config.json does not exist."""
        monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / ".rover")
        monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / ".rover" / "config.json")
        monkeypatch.setattr(config_module, "_CONFIG_TMP", tmp_path / ".rover" / "config.json.tmp")
        monkeypatch.setattr(config_module, "_OLD_CONFIG", tmp_path / ".dispatch-tui" / "config.json")
        # config.json does not exist — must not raise
        result = load_config()
        assert result is not None

    def test_load_config_contains_all_default_keys(self, tmp_path, monkeypatch) -> None:
        """When there is no saved file, load_config returns every key from DEFAULT_CONFIG."""
        monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / ".rover")
        monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / ".rover" / "config.json")
        monkeypatch.setattr(config_module, "_CONFIG_TMP", tmp_path / ".rover" / "config.json.tmp")
        monkeypatch.setattr(config_module, "_OLD_CONFIG", tmp_path / ".dispatch-tui" / "config.json")
        result = load_config()
        for key in DEFAULT_CONFIG:
            assert key in result, f"Expected key '{key}' in loaded config"

    def test_load_config_saved_value_overrides_default(self, tmp_path, monkeypatch) -> None:
        """A value persisted on disk takes precedence over the DEFAULT_CONFIG value."""
        rover_dir = tmp_path / ".rover"
        rover_dir.mkdir(parents=True)
        config_file = rover_dir / "config.json"
        config_file.write_text(
            json.dumps({"dispatch_port": 9999}), encoding="utf-8"
        )
        monkeypatch.setattr(config_module, "CONFIG_DIR", rover_dir)
        monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
        monkeypatch.setattr(config_module, "_CONFIG_TMP", rover_dir / "config.json.tmp")
        monkeypatch.setattr(config_module, "_OLD_CONFIG", tmp_path / ".dispatch-tui" / "config.json")
        result = load_config()
        assert result["dispatch_port"] == 9999

    def test_load_config_recovers_from_corrupt_json(self, tmp_path, monkeypatch) -> None:
        """A corrupt config file is treated as empty; defaults are returned without crashing."""
        rover_dir = tmp_path / ".rover"
        rover_dir.mkdir(parents=True)
        config_file = rover_dir / "config.json"
        config_file.write_text("{ this is not valid json }", encoding="utf-8")
        monkeypatch.setattr(config_module, "CONFIG_DIR", rover_dir)
        monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
        monkeypatch.setattr(config_module, "_CONFIG_TMP", rover_dir / "config.json.tmp")
        monkeypatch.setattr(config_module, "_OLD_CONFIG", tmp_path / ".dispatch-tui" / "config.json")
        result = load_config()
        assert isinstance(result, dict)
        assert "dispatch_port" in result


# ── TestSaveConfig ─────────────────────────────────────────────────────────────

class TestSaveConfig:
    def test_save_config_writes_json_file(self, tmp_path, monkeypatch) -> None:
        """save_config produces a readable JSON file at CONFIG_FILE."""
        rover_dir = tmp_path / ".rover"
        rover_dir.mkdir(parents=True)
        config_file = rover_dir / "config.json"
        monkeypatch.setattr(config_module, "CONFIG_DIR", rover_dir)
        monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
        monkeypatch.setattr(config_module, "_CONFIG_TMP", rover_dir / "config.json.tmp")
        cfg = {**DEFAULT_CONFIG, "nickname": "tester"}
        save_config(cfg)
        assert config_file.exists()
        on_disk = json.loads(config_file.read_text(encoding="utf-8"))
        assert on_disk["nickname"] == "tester"

    def test_save_config_is_round_trippable(self, tmp_path, monkeypatch) -> None:
        """A dict saved by save_config is faithfully returned by load_config."""
        rover_dir = tmp_path / ".rover"
        rover_dir.mkdir(parents=True)
        config_file = rover_dir / "config.json"
        monkeypatch.setattr(config_module, "CONFIG_DIR", rover_dir)
        monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
        monkeypatch.setattr(config_module, "_CONFIG_TMP", rover_dir / "config.json.tmp")
        monkeypatch.setattr(config_module, "_OLD_CONFIG", tmp_path / ".dispatch-tui" / "config.json")
        cfg = {**DEFAULT_CONFIG, "theme": "ocean", "dispatch_port": 5000}
        save_config(cfg)
        reloaded = load_config()
        assert reloaded["theme"] == "ocean"
        assert reloaded["dispatch_port"] == 5000
