try:
    from importlib.metadata import version, PackageNotFoundError

    __version__ = version("rover-tui")
except PackageNotFoundError:
    # Running from source without an installed package (e.g. during development
    # or in CI before the wheel is built). Fall back to the literal so that
    # `rover --version` still works in both contexts.
    __version__ = "0.3.4"
