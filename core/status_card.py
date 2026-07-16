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
STATUS_BG_PATH = ASSETS_DIR / "status_bg.jpg"
FONT_PATH = ASSETS_DIR / "status_font.ttf"

FONT_SIZE_LARGE = 48
FONT_SIZE_SMALL = 24
LABEL_COLOR = "white"
VALUE_COLOR = "yellow"
SUBTEXT_COLOR = "gray"

COORDS: dict[str, tuple[int, int]] = {
    "text_battery": (60, 470),
    "battery": (170, 540),

    "text_engagement": (588, 70),
    "engagement": (1600, 70),

    "text_member_card": (588, 170),
    "exp_member_card": (1600, 220),
    "member_card": (1600, 170),

    "text_weekly_task": (588, 270),
    "exp_weekly_task": (1600, 320),
    "weekly_task": (1600, 270),

    "text_hollow_bounty": (588, 370),
    "exp_hollow_bounty": (1600, 420),
    "hollow_bounty": (1600, 370),
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
    return value.value if isinstance(value, PyEnum) else value


def _days_only(delta) -> str:
    return str(delta).split(",")[0]


def _draw_stat(
    draw: ImageDraw.ImageDraw,
    label: str,
    label_pos: tuple[int, int],
    value: str,
    value_pos: tuple[int, int],
    sub: str | None = None,
    sub_pos: tuple[int, int] | None = None,
) -> None:
    """One row of the card: a label, its value, and an optional gray
    subtext line underneath (e.g. a refresh/expiry countdown)."""
    draw.text(label_pos, label, font=_font_large, fill=LABEL_COLOR)
    draw.text(value_pos, value, font=_font_large, fill=VALUE_COLOR)
    if sub is not None and sub_pos is not None:
        draw.text(sub_pos, sub, font=_font_small, fill=SUBTEXT_COLOR)


def build_status_card(notes) -> io.BytesIO:
    """notes: the result of client.get_zzz_notes(). Returns a PNG buffer
    ready to hand to discord.File."""
    _ensure_loaded()

    img = _bg_template.copy()  # don't mutate the cached template
    draw = ImageDraw.Draw(img)

    battery = notes.battery_charge
    _draw_stat(
        draw,
        "Battery Charge",
        COORDS["text_battery"],
        f"{battery.current}/{battery.max}",
        COORDS["battery"],
    )

    engagement = notes.engagement
    _draw_stat(
        draw,
        "Engagement Today:",
        COORDS["text_engagement"],
        f"{engagement.current}/{engagement.max}",
        COORDS["engagement"],
    )

    member_card = notes.member_card
    member_status = "Active" if member_card.is_open else "Inactive"
    _draw_stat(
        draw,
        "Inter-Knot Membership:",
        COORDS["text_member_card"],
        member_status,
        COORDS["member_card"],
        sub=f"Expires in {_days_only(member_card.exp_time)}" if member_card.is_open else None,
        sub_pos=COORDS["exp_member_card"],
    )

    weekly = notes.weekly_task
    _draw_stat(
        draw,
        "Ridu Weekly Points:",
        COORDS["text_weekly_task"],
        f"{weekly.cur_point}/{weekly.max_point}",
        COORDS["weekly_task"],
        sub=f"Refreshes in {_days_only(weekly.refresh_time)}",
        sub_pos=COORDS["exp_weekly_task"],
    )

    bounty = notes.hollow_zero.bounty_commission
    _draw_stat(
        draw,
        "Bounty Commission Progress:",
        COORDS["text_hollow_bounty"],
        f"{bounty.cur_completed}/{bounty.total}",
        COORDS["hollow_bounty"],
        sub=f"Refreshes in {_days_only(bounty.refresh_time)}",
        sub_pos=COORDS["exp_hollow_bounty"],
    )

    buf = io.BytesIO()
    img.save(buf, format="webp")
    buf.seek(0)
    return buf