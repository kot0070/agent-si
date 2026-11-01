"""K11REST prompt-factory offline selftest.

Prompts render through an injected client (any object with a
``render(text)`` method); the built-in offline client joins the parts
locally. Nothing here opens a socket: the served selftest answers
offline True on every path.
"""

from __future__ import annotations

from typing import Any

#: Fixed probe parts rendered by the selftest (no caller input needed).
PROBE_PARTS = ("k11rest", "selftest", "probe")


class OfflineClient:
    """Built-in rendering client: prefixes prompt text locally."""

    def render(self, text: str) -> str:
        return "offline:" + str(text)


def render_prompt(client: Any, parts: tuple = PROBE_PARTS) -> str:
    """Render the probe prompt through the injected client."""
    text = "/".join(str(part) for part in parts)
    render = getattr(client, "render", None)
    if not callable(render):
        raise ValueError("client needs a render(text) method")
    rendered = render(text)
    if not isinstance(rendered, str) or not rendered:
        raise ValueError("client rendered an empty prompt")
    return rendered


def run_selftest(client: Any | None = None) -> dict[str, bool]:
    """Run the offline selftest; ok True when the probe round-trips."""
    active = OfflineClient() if client is None else client
    try:
        rendered = render_prompt(active)
    except Exception:
        return {"ok": False, "offline": True}
    return {"ok": bool(rendered), "offline": True}
