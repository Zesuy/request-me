import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_id: str
    app_secret: str
    owner_openid: str
    bridge_tokens: dict[str, str]
    host: str = "127.0.0.1"
    port: int = 8080


def load_settings() -> Settings:
    load_dotenv()
    app_id, secret = os.getenv("QQ_APPID", ""), os.getenv("QQ_SECRET", "")
    owner = os.getenv("REQUEST_ME_OWNER_OPENID", "").strip()
    bridges = json.loads(os.getenv("REQUEST_ME_BRIDGE_TOKENS", "{}"))
    if not app_id or not secret or not owner:
        raise ValueError("QQ_APPID, QQ_SECRET and REQUEST_ME_OWNER_OPENID are required")
    if not isinstance(bridges, dict) or not bridges or any(
        not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in bridges.items()
    ):
        raise ValueError("REQUEST_ME_BRIDGE_TOKENS must map bridge IDs to nonempty tokens")
    if len(set(bridges.values())) != len(bridges):
        raise ValueError("each bridge must use a distinct token")
    return Settings(app_id, secret, owner, bridges,
                    os.getenv("REQUEST_ME_HOST", "127.0.0.1"), int(os.getenv("REQUEST_ME_PORT", "8080")))
