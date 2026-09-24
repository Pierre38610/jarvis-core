"""Shim de rétrocompatibilité pour browser_service. Redirige vers services.browser_service."""

from services.browser_service import (
    search_web,
    browse_page,
    run_browser_task,
    open_browser_window,
    SCREENSHOT_PATH,
    STATIC_DIR
)

__all__ = [
    "search_web",
    "browse_page",
    "run_browser_task",
    "open_browser_window",
    "SCREENSHOT_PATH",
    "STATIC_DIR"
]
