"""Anonymous outlook.tw mailbox provider for OpenAI verification codes."""

from __future__ import annotations

import re
import time
from urllib.parse import quote

from curl_cffi import requests


class OutlookTwProviderError(RuntimeError):
    """Mailbox creation or polling failed."""


class OutlookTwProvider:
    def __init__(self, base_url: str = "https://outlook.tw", username_length: int = 8,
                 domain_index: int = 0, poll_interval: float = 3.0,
                 request_timeout: float = 30.0, max_wait: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.username_length = max(8, min(30, int(username_length)))
        self.domain_index = max(0, int(domain_index))
        self.poll_interval = max(0.5, float(poll_interval))
        self.request_timeout = max(1.0, float(request_timeout))
        self.max_wait = max(1.0, float(max_wait))
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update({"Accept": "application/json"})
        self.email = ""

    def _get_json(self, path: str, params=None):
        try:
            response = self.session.get(
                f"{self.base_url}{path}", params=params, timeout=self.request_timeout
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestsError, ValueError) as exc:
            raise OutlookTwProviderError(f"outlook.tw 请求失败: {exc}") from exc

    def acquire_email(self) -> str:
        if self.email:
            return self.email
        data = self._get_json(
            "/api/generate",
            params={"length": self.username_length, "domainIndex": self.domain_index},
        )
        email = str(data.get("email") or "").strip()
        if "@" not in email:
            raise OutlookTwProviderError("outlook.tw 未返回有效邮箱地址")
        self.email = email
        print(f"[+] 生成邮箱: {email} (outlook_tw)")
        return email

    @staticmethod
    def _message_text(message) -> str:
        if not isinstance(message, dict):
            return ""
        return "\n".join(str(message.get(key) or "") for key in (
            "subject", "html_content", "content", "text_content", "preview",
            "verification_code", "body", "html",
        ))

    def extract_all_codes(self) -> list[str]:
        if not self.email:
            return []
        codes: list[str] = []
        try:
            messages = self._get_json("/api/emails", params={"mailbox": self.email})
            for message in messages if isinstance(messages, list) else []:
                codes.extend(re.findall(r"(?<!\d)(\d{6})(?!\d)", self._message_text(message)))
                message_id = message.get("id") if isinstance(message, dict) else None
                if message_id is not None:
                    detail = self._get_json(f"/api/email/{quote(str(message_id), safe='')}")
                    codes.extend(re.findall(r"(?<!\d)(\d{6})(?!\d)", self._message_text(detail)))
        except OutlookTwProviderError:
            pass
        return list(dict.fromkeys(codes))

    def wait_for_code(self, timeout_sec: int = 180, poll: float = 3.0,
                      exclude_codes=None) -> str | None:
        excluded = set(exclude_codes or [])
        deadline = time.monotonic() + min(max(1, timeout_sec), self.max_wait)
        interval = max(0.5, float(poll or self.poll_interval))
        while time.monotonic() < deadline:
            for code in self.extract_all_codes():
                if code not in excluded:
                    return code
            time.sleep(interval)
        return None

    def cancel(self) -> None:
        return None

    def close(self) -> None:
        self.session.close()
