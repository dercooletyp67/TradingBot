import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

OANDA_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

if OANDA_ENV == "live":
    raise RuntimeError(
        "OANDA_ENV is set to 'live'. This project is built for paper/demo "
        "trading only and refuses to run against a live real-money account."
    )

OANDA_HOST = OANDA_HOSTS[OANDA_ENV]

ROOT_DIR = Path(__file__).parent

# Overridable so a cloud instance (e.g. GitHub Actions) can use its own state
# files, kept separate from a local desktop instance's -- otherwise two
# instances writing the same SQLite file from different machines would
# stomp on each other.
DB_PATH = ROOT_DIR / os.getenv("TRADINGBOT_DB_PATH", "storage/tradingbot.db")
LEARN_DIR = ROOT_DIR / os.getenv("TRADINGBOT_LEARN_DIR", "learn")
