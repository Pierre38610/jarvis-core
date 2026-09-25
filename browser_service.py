"""Shim de rétrocompatibilité pour browser_service. Redirige vers services.browser_service."""

from services.browser_service import (
    search_web,
    browse_page,
    run_browser_task,
    open_browser_window,
    interact_web_page,
    prepare_web_cart_or_checkout,
    send_page_to_kindle,
    list_installed_chrome_extensions,
    get_installed_chrome_extensions,
    extract_clean_article,
    SCREENSHOT_PATH,
    STATIC_DIR
)

__all__ = [
    "search_web",
    "browse_page",
    "run_browser_task",
    "open_browser_window",
    "interact_web_page",
    "prepare_web_cart_or_checkout",
    "send_page_to_kindle",
    "list_installed_chrome_extensions",
    "get_installed_chrome_extensions",
    "extract_clean_article",
    "SCREENSHOT_PATH",
    "STATIC_DIR"
]

