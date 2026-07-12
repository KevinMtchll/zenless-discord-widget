"""
Shared genshin.Client construction and the process-wide rate-limiting semaphore.
"""

import asyncio

import genshin

from core.user_config import UserConfig

# Caps concurrent HoYoLAB requests across ALL users at once. This VM has
# one shared IP, so many users hitting /currency or /set_agents at the same
# moment can trip HoYoLAB's own rate limiting even though each individual
# user is well within their personal per-command cooldown. Calls queue up
# and wait for a slot rather than firing all at once.
HOYOLAB_SEMAPHORE = asyncio.Semaphore(3)


def build_client(config: UserConfig) -> genshin.Client:
    """Construct a genshin.Client from a decrypted UserConfig. Does not
    make any network calls itself. Callers should wrap actual API calls
    in `async with HOYOLAB_SEMAPHORE:`."""
    cookies = config.hoyoCookies.to_plain()
    return genshin.Client(
        cookies={"ltoken_v2": cookies.ltoken_v2, "ltuid_v2": cookies.ltuid_v2},
        game=genshin.Game.ZZZ,
        region=genshin.Region.OVERSEAS,  # use CHINESE if this is a CN account
        uid=config.hoyoUid,
    )