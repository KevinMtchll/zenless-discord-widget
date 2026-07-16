"""
Renders the /status stat card: a pre-made background PNG with live
get_zzz_notes() values drawn on top via Pillow.

Test layout. every coordinate lives in COORDS below
so positions can be tuned without touching the drawing logic. Values are
printed as plain text only; bars/shading/etc. are left for later.
"""

import io
from enum import Enum as PyEnum
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
STATUS_BG_PATH = ASSETS_DIR / "status_bg.webp"
FONT_PATH = ASSETS_DIR / "status_font.ttf"

FONT_SIZE_LARGE = 24
FONT_SIZE_SMALL = 16
TEXT_COLOR = "black"

COORDS: dict[str, tuple[int, int]] = {
    "battery": (40, 35),
    "engagement": (207, 35),
    "weekly_task": (374, 35),
    "hollow_bounty": (541, 35),
    "member_card": (708, 35),
    "temple_running": (875, 35),
}

# Loaded once at import time rather than per-request.
_bg_template: Image.Image | None = None
_font_large: ImageFont.FreeTypeFont | None = None
_font_small: ImageFont.FreeTypeFont | None = None


def _ensure_loaded() -> None:
    """Lazy-load the template/fonts on first use so importing this module
    doesn't fail just because assets haven't been dropped in yet."""
    global _bg_template, _font_large, _font_small
    if _bg_template is not None:
        return

    if not STATUS_BG_PATH.exists():
        raise FileNotFoundError(
            f"Missing status card background at {STATUS_BG_PATH}. "
            "Drop your pre-made PNG there before using /status."
        )
    if not FONT_PATH.exists():
        raise FileNotFoundError(
            f"Missing font at {FONT_PATH}. Bundle a .ttf there -- system "
            "fonts aren't guaranteed to exist on the deploy VM."
        )

    _bg_template = Image.open(STATUS_BG_PATH).convert("RGBA")
    _font_large = ImageFont.truetype(str(FONT_PATH), FONT_SIZE_LARGE)
    _font_small = ImageFont.truetype(str(FONT_PATH), FONT_SIZE_SMALL)


def _field_str(value) -> str:
    """Same normalization as currency.py -- some genshin.py fields come
    back as Enum members rather than plain strings/ints."""
    return value.value if isinstance(value, PyEnum) else value


def build_status_card(notes) -> io.BytesIO:
    """notes: the result of client.get_zzz_notes(). Returns a PNG buffer
    ready to hand to discord.File."""
    _ensure_loaded()

    img = _bg_template.copy()  # don't mutate the cached template
    draw = ImageDraw.Draw(img)

    battery = notes.battery_charge
    draw.text(
        COORDS["battery"],
        f"{battery.current}/{battery.max}",
        font=_font_large,
        fill=TEXT_COLOR,
    )

    engagement = notes.engagement
    draw.text(
        COORDS["engagement"],
        f"{engagement.current}/{engagement.max}",
        font=_font_small,
        fill=TEXT_COLOR,
    )

    weekly = notes.weekly_task
    draw.text(
        COORDS["weekly_task"],
        f"{weekly.cur_point}/{weekly.max_point}",
        font=_font_small,
        fill=TEXT_COLOR,
    )

    bounty = notes.hollow_zero.bounty_commission
    draw.text(
        COORDS["hollow_bounty"],
        f"{bounty.cur_completed}/{bounty.total}",
        font=_font_small,
        fill=TEXT_COLOR,
    )

    member_card = notes.member_card
    member_status = "Active" if member_card.is_open else "Inactive"
    draw.text(
        COORDS["member_card"],
        member_status,
        font=_font_small,
        fill=TEXT_COLOR,
    )

    temple = notes.temple_running
    draw.text(
        COORDS["temple_running"],
        f"Lvl {temple.level}",
        font=_font_small,
        fill=TEXT_COLOR,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf