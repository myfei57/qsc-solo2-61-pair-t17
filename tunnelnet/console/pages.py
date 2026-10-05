"""Static console pages served from the web directory."""

from __future__ import annotations

import os

from .http import Response, error_response, html_response, redirect_response

PAGE_FILES: dict[str, str] = {
    "cabins": "cabins.html",
    "env": "env.html",
    "patrols": "patrols.html",
    "alarms": "alarms.html",
}


def page_file(path: str) -> str | None:
    """Resolve a URL path such as ``/cabins`` to its file name."""

    return PAGE_FILES.get(path.strip("/"))


def load_page(web_dir: str, filename: str) -> Response:
    """Read one page from the web directory."""

    try:
        with open(os.path.join(web_dir, filename), encoding="utf-8") as handle:
            return html_response(handle.read())
    except OSError:
        return error_response(404, f"page {filename} not found")


def root_redirect() -> Response:
    return redirect_response("/cabins")
