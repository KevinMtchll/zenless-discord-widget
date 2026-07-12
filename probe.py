"""
probe.py -- quick inspection tool for the shape of objects genshin.py
returns from HoYoLAB, using your own account cookies. Not part of the
running bot; run manually when you want to see what fields are available
on a record before wiring something new into widget.py.

Usage:
    python probe.py                     # focused: diary (all months) + notes only
    python probe.py --all               # full dump: accounts, agents, method discovery
    python probe.py --uid 1007516480
    python probe.py --structure-only    # field names + types only, no values
    python probe.py --out my_dump.txt   # override output filename

Output is written to a text file (default: probe_output_<timestamp>.txt
in the current directory) as well as printed to the console.

Cookies/UID are read from environment variables (see .env additions
below) rather than Mongo, since this is meant for quick local testing
against your own account -- it never touches the encrypted values
stored in production.

.env additions this script expects (separate from BOT_TOKEN etc.):
    PROBE_LTOKEN_V2=...
    PROBE_LTUID_V2=...
    PROBE_HOYO_UID=...
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from enum import Enum
from io import StringIO

import genshin
from dotenv import load_dotenv

load_dotenv()


def _to_plain(obj, _depth: int = 0, _max_depth: int = 6):
    """Recursively convert a genshin.py model (or list/dict of them) into
    plain Python data so json.dumps can print it. Handles pydantic v1/v2
    models, enums, datetimes, and falls back to str() for anything else."""
    if _depth > _max_depth:
        return "<max depth reached>"

    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, dict):
        return {k: _to_plain(v, _depth + 1, _max_depth) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [_to_plain(v, _depth + 1, _max_depth) for v in obj]

    # pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return _to_plain(obj.model_dump(), _depth + 1, _max_depth)
        except Exception:
            pass

    # pydantic v1 (older genshin.py versions)
    if hasattr(obj, "dict"):
        try:
            return _to_plain(obj.dict(), _depth + 1, _max_depth)
        except Exception:
            pass

    # last resort: public attributes only
    if hasattr(obj, "__dict__"):
        return _to_plain(
            {k: v for k, v in vars(obj).items() if not k.startswith("_")},
            _depth + 1,
            _max_depth,
        )

    return str(obj)


def _structure_only(obj, _depth: int = 0, _max_depth: int = 6):
    """Like _to_plain, but replaces leaf values with their type name instead
    of the actual value -- useful for a quick 'what fields exist' scan
    without a wall of real data."""
    if _depth > _max_depth:
        return "<max depth reached>"

    if isinstance(obj, dict):
        return {k: _structure_only(v, _depth + 1, _max_depth) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        if not obj:
            return f"[] (empty {type(obj).__name__})"
        first = obj[0] if isinstance(obj, (list, tuple)) else next(iter(obj))
        return [_structure_only(first, _depth + 1, _max_depth)]

    plain = _to_plain(obj, _depth, _max_depth)
    if isinstance(plain, dict):
        return _structure_only(plain, _depth, _max_depth)
    return type(obj).__name__


def dump(label: str, obj, structure_only: bool, out) -> None:
    header = f"\n{'=' * 60}\n{label}\n{'=' * 60}"
    data = _structure_only(obj) if structure_only else _to_plain(obj)
    body = json.dumps(data, indent=2, default=str)
    print(header)
    print(body)
    out.write(header + "\n")
    out.write(body + "\n")


def _log_line(out, line: str = "") -> None:
    print(line)
    out.write(line + "\n")


async def _call_safe(label: str, call, structure_only: bool, out):
    """Run one client call, dumping the result or the failure. Returns the
    raw result (or None on failure) so callers can pull data out of it,
    e.g. reading month_options off a diary response."""
    try:
        result = await call()
    except Exception as error:
        header = f"\n{'-' * 60}\n{label}  -- FAILED\n{'-' * 60}"
        body = repr(error)
        print(header)
        print(body)
        out.write(header + "\n")
        out.write(body + "\n")
        return None
    dump(label, result, structure_only, out)
    return result


def _resolve_enum_choices(annotation):
    """If `annotation` is an Enum class (or Optional[Enum]/Union[Enum, ...]),
    return a list of its members. Otherwise None. Used to discover valid
    values for a required keyword arg without hardcoding a guess."""
    args = getattr(annotation, "__args__", None)
    candidates = [annotation] if args is None else list(args)
    for cand in candidates:
        if isinstance(cand, type) and issubclass(cand, Enum):
            return list(cand)
    return None


async def probe_currency(client, hoyo_uid: int, structure_only: bool, out) -> None:
    """Focused probe: only the currency-relevant endpoints found so far --
    income diary (all available months) and real-time notes. Skips agent
    rosters, achievements, etc. since those aren't relevant to currency
    tracking and just add noise to the output."""
    _log_line(out, f"\n{'=' * 60}\nCurrency-relevant data\n{'=' * 60}")

    # First call with no month arg to discover which months are available.
    current_diary = await _call_safe(
        "get_zzz_diary() [current month]",
        lambda: client.get_zzz_diary(),
        structure_only,
        out,
    )

    month_options = []
    if isinstance(current_diary, dict):
        month_options = current_diary.get("month_options", [])
    elif current_diary is not None:
        month_options = getattr(current_diary, "month_options", [])

    other_months = [m for m in month_options if str(m) != str(getattr(current_diary, "data_month", None))]

    for month in other_months:
        await _call_safe(
            f"get_zzz_diary(month={month})",
            lambda m=month: client.get_zzz_diary(month=int(m)),
            structure_only,
            out,
        )

    # get_zzz_diary_detail() takes a required keyword-only `type` arg (an
    # enum -- which currency to break down day-by-day). Rather than guess
    # its values, introspect the method's own signature to find them.
    import inspect

    sig = inspect.signature(client.get_zzz_diary_detail)
    type_param = sig.parameters.get("type")
    type_choices = _resolve_enum_choices(type_param.annotation) if type_param else None

    if type_choices:
        _log_line(out, f"\nget_zzz_diary_detail 'type' choices discovered: {[c.name for c in type_choices]}")
    else:
        _log_line(
            out,
            "\nCould not introspect 'type' choices for get_zzz_diary_detail "
            f"(annotation: {getattr(type_param, 'annotation', None)!r}) -- skipping.",
        )

    if type_choices:
        for month in month_options:
            for type_choice in type_choices:
                await _call_safe(
                    f"get_zzz_diary_detail(month={month}, type={type_choice.name})",
                    lambda m=month, t=type_choice: client.get_zzz_diary_detail(month=int(m), type=t),
                    structure_only,
                    out,
                )

    await _call_safe(
        "get_zzz_notes()",
        lambda: client.get_zzz_notes(),
        structure_only,
        out,
    )


async def probe_all(client, hoyo_uid: int, structure_only: bool, out) -> None:
    """Original broad dump -- account info, agents, plus a keyword-based
    discovery scan of every client method. Noisier, but useful when
    hunting for a new endpoint rather than working with known ones."""
    endpoints = {
        "get_game_accounts()": lambda: client.get_game_accounts(),
        "get_zzz_user()": lambda: client.get_zzz_user(hoyo_uid),
        "get_zzz_agents()": lambda: client.get_zzz_agents(hoyo_uid),
    }
    for label, call in endpoints.items():
        await _call_safe(label, call, structure_only, out)

    _log_line(out, f"\n{'=' * 60}\nDiary/notes/log method discovery\n{'=' * 60}")
    keywords = ("diary", "note", "log", "currency", "wallet", "record")
    candidates = sorted(
        name
        for name in dir(client)
        if not name.startswith("_")
        and any(k in name.lower() for k in keywords)
        and callable(getattr(client, name, None))
    )
    if not candidates:
        _log_line(out, "No methods matched diary/note/log/currency/wallet/record keywords.")
        return

    _log_line(out, f"Candidate methods found: {candidates}\n")
    for name in candidates:
        method = getattr(client, name)
        for attempt in (lambda: method(), lambda: method(hoyo_uid), lambda: method(uid=hoyo_uid)):
            try:
                result = await attempt()
                dump(f"{name}() [discovered]", result, structure_only, out)
                break
            except TypeError:
                continue
            except Exception as error:
                header = f"\n{'-' * 60}\n{name}() [discovered]  -- FAILED\n{'-' * 60}"
                body = repr(error)
                print(header)
                print(body)
                out.write(header + "\n")
                out.write(body + "\n")
                break


async def probe(hoyo_uid: int, ltoken_v2: str, ltuid_v2: int, structure_only: bool, out, show_all: bool) -> None:
    client = genshin.Client(
        cookies={"ltoken_v2": ltoken_v2, "ltuid_v2": ltuid_v2},
        game=genshin.Game.ZZZ,
        region=genshin.Region.OVERSEAS,  # use CHINESE if this is a CN account
        uid=hoyo_uid,
    )

    if show_all:
        await probe_all(client, hoyo_uid, structure_only, out)
    else:
        await probe_currency(client, hoyo_uid, structure_only, out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect HoYoLAB/genshin.py record structure.")
    parser.add_argument("--uid", type=int, default=None, help="Override PROBE_HOYO_UID from .env")
    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="Print field names/types only, not actual values",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output text file path (default: probe_output_<timestamp>.txt)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Full broad dump (accounts, agents, method discovery) instead of the focused currency probe",
    )
    args = parser.parse_args()

    hoyo_uid = args.uid or int(os.environ["PROBE_HOYO_UID"])
    ltoken_v2 = os.environ["PROBE_LTOKEN_V2"]
    ltuid_v2 = int(os.environ["PROBE_LTUID_V2"])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or f"probe_output_{timestamp}.txt"

    with open(out_path, "w", encoding="utf-8") as out:
        out.write(f"probe.py run -- {datetime.now().isoformat()}\n")
        out.write(f"hoyo_uid={hoyo_uid}  structure_only={args.structure_only}  all={args.all}\n")
        asyncio.run(probe(hoyo_uid, ltoken_v2, ltuid_v2, args.structure_only, out, args.all))

    print(f"\nOutput written to: {os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()