"""运行配置，敏感信息通过环境变量传入。"""

import os
from pathlib import Path

from dotenv import load_dotenv


# Shell environment variables take precedence over values in the local .env file.
load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

# Tavily 相关配置
TAVILY_HOME_URL = "https://app.tavily.com/home"

# Output stays beside the script even when main.py is launched from another directory.
API_KEYS_FILE = str(Path(__file__).resolve().with_name("api_keys.txt"))

MAX_EMAIL_WAIT_TIME = int(os.getenv("MAX_EMAIL_WAIT_TIME", "300"))

# 临时邮箱 provider
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "luckmail")

# 浏览器配置
HEADLESS = os.getenv("HEADLESS", "false").lower() in ("1", "true", "yes")
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))
HUMAN_DELAY_MIN = max(0.0, float(os.getenv("HUMAN_DELAY_MIN", "0.8")))
HUMAN_DELAY_MAX = max(HUMAN_DELAY_MIN, float(os.getenv("HUMAN_DELAY_MAX", "2.4")))

# 比特浏览器 Local API 配置
BIT_BROWSER_API_URL = os.getenv("BIT_BROWSER_API_URL", "http://127.0.0.1:54346")
BIT_BROWSER_ID = os.getenv("BIT_BROWSER_ID", "")
BIT_BROWSER_NAME = os.getenv("BIT_BROWSER_NAME", "tavily-register")
BIT_BROWSER_CLOSE_WAIT = max(5.0, float(os.getenv("BIT_BROWSER_CLOSE_WAIT", "5")))

# LuckMail 配置
LUCKMAIL_BASE_URL = os.getenv("LUCKMAIL_BASE_URL", "https://mails.luckyous.com")
LUCKMAIL_API_KEY = os.getenv("LUCKMAIL_API_KEY", "")
LUCKMAIL_API_SECRET = os.getenv("LUCKMAIL_API_SECRET", "")
LUCKMAIL_USE_HMAC = os.getenv("LUCKMAIL_USE_HMAC", "false").lower() in (
    "1",
    "true",
    "yes",
)
LUCKMAIL_PROJECT_CODE = os.getenv("LUCKMAIL_PROJECT_CODE", "grok")
LUCKMAIL_EMAIL_TYPE = os.getenv("LUCKMAIL_EMAIL_TYPE", "ms_graph")
LUCKMAIL_DOMAIN = os.getenv("LUCKMAIL_DOMAIN", "outlook.com")
LUCKMAIL_POLL_INTERVAL = float(os.getenv("LUCKMAIL_POLL_INTERVAL", "3"))

# outlook.tw 匿名临时邮箱配置
OUTLOOK_TW_BASE_URL = os.getenv("OUTLOOK_TW_BASE_URL", "https://outlook.tw").rstrip("/")
OUTLOOK_TW_USERNAME_LENGTH = max(
    8, min(30, int(os.getenv("OUTLOOK_TW_USERNAME_LENGTH", "8")))
)
OUTLOOK_TW_DOMAIN_INDEX = max(0, int(os.getenv("OUTLOOK_TW_DOMAIN_INDEX", "0")))
OUTLOOK_TW_POLL_INTERVAL = float(os.getenv("OUTLOOK_TW_POLL_INTERVAL", "3"))
OUTLOOK_TW_REQUEST_TIMEOUT = float(os.getenv("OUTLOOK_TW_REQUEST_TIMEOUT", "30"))
OUTLOOK_TW_REQUEST_RETRIES = max(1, int(os.getenv("OUTLOOK_TW_REQUEST_RETRIES", "3")))
