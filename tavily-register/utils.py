"""Shared helpers for Tavily automation."""

import html
import random
import re
import secrets
import string
import time

from config import API_KEYS_FILE, HUMAN_DELAY_MAX, HUMAN_DELAY_MIN


PASSWORD_LENGTH = 14
PASSWORD_SPECIAL_CHARS = "!@#$%^&*"


def extract_api_key(value):
    """从剪贴板或页面文本中提取完整的 Tavily API key。"""
    match = re.search(r"tvly-[A-Za-z0-9_-]+", str(value or ""))
    return match.group(0) if match else None


def mask_api_key(value):
    """Return a short identifier suitable for logs instead of the full key."""
    api_key = extract_api_key(value)
    if not api_key:
        return "<invalid>"
    if len(api_key) <= 8:
        return "tvly-****"
    return f"{api_key[:5]}...{api_key[-4:]}"


def generate_password(length=PASSWORD_LENGTH):
    """Generate a password containing lower, upper, digit, and special characters."""
    if length < 4:
        raise ValueError("密码长度不能少于 4 位")

    character_groups = (
        string.ascii_lowercase,
        string.ascii_uppercase,
        string.digits,
        PASSWORD_SPECIAL_CHARS,
    )
    characters = [secrets.choice(group) for group in character_groups]
    alphabet = "".join(character_groups)
    characters.extend(secrets.choice(alphabet) for _ in range(length - len(characters)))
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def extract_verification_link(*values):
    """Extract a verification URL from decoded email fields."""
    patterns = (
        r"https://auth\.tavily\.com/u/email-verification\?ticket=[^\s<>'\"]+",
        r"https?://[^\s<>'\"]+(?:verify|verification|confirm)[^\s<>'\"]*",
    )
    for value in values:
        content = html.unescape(str(value or ""))
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(0).rstrip(".,;)")
    return None


def save_api_key(api_key):
    """将 API key 保存为纯文本，每行一个，并避免重复写入。"""
    normalized_key = extract_api_key(api_key)
    if not normalized_key:
        raise ValueError("无效的 Tavily API key")

    try:
        with open(API_KEYS_FILE, "r", encoding="utf-8") as file_obj:
            saved_keys = {line.strip() for line in file_obj if line.strip()}
    except FileNotFoundError:
        saved_keys = set()

    if normalized_key in saved_keys:
        print(f"ℹ️ API Key 已存在于 {API_KEYS_FILE}，跳过重复写入")
        return normalized_key

    with open(API_KEYS_FILE, "a", encoding="utf-8") as file_obj:
        file_obj.write(f"{normalized_key}\n")

    print(f"✅ API Key 已保存到 {API_KEYS_FILE}")
    return normalized_key


def wait_with_message(seconds, message="等待中"):
    """带消息的等待函数"""
    print(f"⏳ {message}，等待 {seconds} 秒...")
    time.sleep(seconds)


def human_delay(action="下一步操作", minimum=None, maximum=None):
    """在 UI 操作前加入可配置的随机停顿。"""
    lower = HUMAN_DELAY_MIN if minimum is None else max(0.0, float(minimum))
    upper = HUMAN_DELAY_MAX if maximum is None else max(lower, float(maximum))
    delay = random.uniform(lower, upper)
    if delay <= 0:
        return 0.0
    print(f"⏳ 模拟真人停顿 {delay:.2f} 秒：{action}")
    time.sleep(delay)
    return delay
