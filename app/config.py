from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

@dataclass
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin")
    secret_key: str = os.getenv("SECRET_KEY", "change_me")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./quest_bot.db")
    group_chat_id: int = int(os.getenv("GROUP_CHAT_ID", "0"))

settings = Settings()
