from datetime import datetime

from pydantic import BaseModel, Field

from core.crypto_utils import decrypt_str, encrypt_str


class HoyoCookies(BaseModel):
    """Plaintext Hoyoverse cookies. Only ever held in memory and should never
    written to MongoDB directly."""

    ltoken_v2: str
    ltuid_v2: int

    def to_encrypted(self) -> "HoyoCookiesEncrypted":
        return HoyoCookiesEncrypted(
            ltoken_v2=encrypt_str(self.ltoken_v2),
            ltuid_v2=encrypt_str(str(self.ltuid_v2)),
        )


class HoyoCookiesEncrypted(BaseModel):
    """Encrypts both cookie fields as Fernet
    ciphertext strings. Call .to_plain() to get usable values back."""

    ltoken_v2: str
    ltuid_v2: str

    def to_plain(self) -> HoyoCookies:
        return HoyoCookies(
            ltoken_v2=decrypt_str(self.ltoken_v2),
            ltuid_v2=int(decrypt_str(self.ltuid_v2)),
        )


class UserConfig(BaseModel):
    userId: str          # Discord User ID
    appId: str            # Discord Application ID
    hoyoCookies: HoyoCookiesEncrypted
    hoyoUid: int           # ZZZ UID
    # Manual widget-slot -> agent-id assignments from /set_agents, in slot
    # order (index 0 = agent_1, ... index 3 = agent_4). A slot left as None
    # falls back to automatic S/A-rarity ranking in main.py.
    selectedAgentIds: list[int | None] = Field(default_factory=lambda: [None, None, None, None])
    lastUpdated: datetime = Field(default_factory=datetime.utcnow)