"""Main Textual application for rover."""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from rover.config import load_config


class DispatchTuiApp(App):
    """rover: on-the-go companion for dispatch agents."""

    CSS = """
Screen {
    background: #0d0d1a;
}
DataTable {
    height: auto;
    border: none;
}
DataTable > .datatable--header {
    background: #1a1a3a;
    color: #00d7ff;
}
DataTable > .datatable--cursor {
    background: #1a2a3a;
    color: #ffffff;
}
"""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("m", "return_to_menu", "Menu", show=True),
        Binding("s", "push_screen('settings')", "Settings"),
    ]

    _start_on_settings: bool = False

    def __init__(self, hours: float = 2.0) -> None:
        super().__init__()
        self.hours = hours
        self.config = load_config()

    def on_mount(self) -> None:
        from rover.screens.dashboard import DashboardScreen

        settings_screen = None
        try:
            from rover.screens.settings import SettingsScreen

            settings_screen = SettingsScreen()
            self.install_screen(settings_screen, name="settings")
        except ImportError:
            pass

        try:
            from rover.screens.activity import ActivityScreen  # noqa: F401 — verify importable
        except ImportError:
            pass

        if getattr(self, "_start_on_settings", False) and settings_screen is not None:
            self.push_screen(settings_screen)
        else:
            dashboard = DashboardScreen(
                port=self.config["dispatch_port"],
                hours=self.hours,
            )
            self.push_screen(dashboard)

        # 5-second auto-refresh — faster than the old 30s default so the
        # dashboard feels live without hammering the server.
        self.set_interval(5.0, self._auto_refresh)

    def _auto_refresh(self) -> None:
        """Triggered every 5 s to keep the dashboard current."""
        try:
            from rover.screens.dashboard import DashboardScreen

            dashboard = self.query_one(DashboardScreen)
            dashboard.refresh_data()
        except Exception:
            pass

    def action_return_to_menu(self) -> None:
        """Exit Textual and return to the session menu."""
        self.exit()
