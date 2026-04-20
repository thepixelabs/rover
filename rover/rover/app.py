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
    border: solid #1a1a3a;
}
DataTable > .datatable--header {
    background: #1a1a3a;
    color: #00d7ff;
}
#status-bar {
    height: 1;
    dock: bottom;
    background: #1a1a3a;
    color: #808080;
}
#session-panel {
    height: auto;
    border: solid #1a1a3a;
    margin-top: 1;
}
Label.panel-title {
    color: #00d7ff;
    text-style: bold;
}
"""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("m", "return_to_menu", "Menu", show=True),
        Binding("s", "push_screen('settings')", "Settings"),
        Binding("question_mark", "push_screen('help')", "Help"),
        Binding("r", "refresh_data", "Refresh"),
    ]

    _start_on_settings: bool = False

    def __init__(self, hours: float = 2.0) -> None:
        super().__init__()
        self.hours = hours
        self.config = load_config()

    def on_mount(self) -> None:
        # Import here to avoid circular imports at module load time; sibling
        # screens (detail, settings) may not exist yet during development.
        from rover.screens.dashboard import DashboardScreen

        settings_screen = None
        try:
            from rover.screens.settings import SettingsScreen

            settings_screen = SettingsScreen()
            self.install_screen(settings_screen, name="settings")
        except ImportError:
            # Sibling agent's screens not yet written — degrade gracefully so
            # the dashboard still works independently during development.
            pass

        if getattr(self, "_start_on_settings", False) and settings_screen is not None:
            self.push_screen(settings_screen)
        else:
            dashboard = DashboardScreen(
                port=self.config["dispatch_port"],
                hours=self.hours,
            )
            self.push_screen(dashboard)

        refresh_seconds = float(self.config.get("refresh_seconds", 30))
        self.set_interval(refresh_seconds, self._auto_refresh)

    def _auto_refresh(self) -> None:
        """Called by the interval timer to refresh the dashboard."""
        try:
            from rover.screens.dashboard import DashboardScreen

            dashboard = self.query_one(DashboardScreen)
            dashboard.refresh_data()
        except Exception:
            pass

    def action_refresh_data(self) -> None:
        """Bound to 'r' — immediately refresh the dashboard."""
        try:
            from rover.screens.dashboard import DashboardScreen

            self.query_one(DashboardScreen).refresh_data()
        except Exception:
            pass

    def action_return_to_menu(self) -> None:
        """Exit Textual and return to the session menu."""
        self.exit()
