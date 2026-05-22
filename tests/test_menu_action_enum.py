"""Tests for the MenuAction enum in rover.menu.

Verifies the contract that __main__.py depends on: all three members
exist, are importable, and carry string values.  If a rename or deletion
ever breaks __main__, one of these tests will fail first.
"""

from __future__ import annotations

from enum import Enum

from rover.menu import MenuAction


class TestMenuActionMembers:
    def test_menu_action_quit_exists(self) -> None:
        """MenuAction.QUIT is importable and its value is a non-empty string."""
        assert hasattr(MenuAction, "QUIT")
        assert isinstance(MenuAction.QUIT.value, str)
        assert MenuAction.QUIT.value != ""

    def test_menu_action_dispatch_exists(self) -> None:
        """MenuAction.DISPATCH exists for backward compat with __main__.py."""
        assert hasattr(MenuAction, "DISPATCH")
        assert isinstance(MenuAction.DISPATCH, MenuAction)

    def test_menu_action_settings_exists(self) -> None:
        """MenuAction.SETTINGS exists and is a member of the enum."""
        assert hasattr(MenuAction, "SETTINGS")
        assert isinstance(MenuAction.SETTINGS, MenuAction)

    def test_menu_action_members_are_strings(self) -> None:
        """Every MenuAction member carries a string value."""
        for member in MenuAction:
            assert isinstance(member.value, str), (
                f"MenuAction.{member.name}.value is {type(member.value).__name__}, expected str"
            )

    def test_menu_action_is_enum(self) -> None:
        """MenuAction itself is an Enum subclass, not just a namespace."""
        assert issubclass(MenuAction, Enum)
