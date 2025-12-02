import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).parent.parent.parent
APP_DIR = ROOT_DIR / "app"

# ======= Application variables ======= #
APP_ENV = os.getenv("APP_ENV", "development")
APP_NAME = os.getenv("APP_NAME", "FastAPI Project")
SECRET_KEY = os.getenv("SECRET_KEY", "abcde-12345")

# ======= Logger variables ======= #
LOGGER_LEVEL = os.getenv("LOGGER_LEVEL", "INFO")
LOGGER_MIDDLEWARE = os.getenv("LOGGER_MIDDLEWARE", "True").lower() == "true"
LOGGER_MIDDLEWARE_SHOW_HEADERS = (
    os.getenv("LOGGER_MIDDLEWARE_SHOW_HEADERS", "False").lower() == "true"
)
LOGGER_EXCEPTIONS = os.getenv("LOGGER_EXCEPTIONS", "True").lower() == "true"


# ======= Database variables ======= #
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "username")
DB_PASS = os.getenv("DB_PASS", "password")
DB_NAME = os.getenv("DB_NAME", "database")
DB_PORT = int(os.getenv("DB_PORT", 3306))
