from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

from .security import PasswordHash

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

@dataclass
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_password_hash: str = os.getenv("ADMIN_PASSWORD_HASH", "")
    secret_key: str = os.getenv("SECRET_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./quest_bot.db")
    group_chat_id: int = int(os.getenv("GROUP_CHAT_ID", "0"))

    def __post_init__(self) -> None:
        if not self.secret_key:
            raise RuntimeError("SECRET_KEY environment variable must be set")

        if self.secret_key == "change_me":
            raise RuntimeError("SECRET_KEY must not use the insecure default value")

        if os.getenv("ADMIN_PASSWORD"):
            raise RuntimeError(
                "ADMIN_PASSWORD is no longer supported. Provide a hashed password via"
                " ADMIN_PASSWORD_HASH."
            )

        if not self.admin_password_hash:
            raise RuntimeError("ADMIN_PASSWORD_HASH environment variable must be set")

        # Validate that the hash can be parsed correctly.
        PasswordHash.parse(self.admin_password_hash)


settings = Settings()
