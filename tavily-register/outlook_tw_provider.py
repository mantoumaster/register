"""outlook.tw anonymous temporary email provider."""

from __future__ import annotations

import time
from urllib.parse import quote

from curl_cffi import requests

from config import (
    MAX_EMAIL_WAIT_TIME,
    OUTLOOK_TW_BASE_URL,
    OUTLOOK_TW_DOMAIN_INDEX,
    OUTLOOK_TW_POLL_INTERVAL,
    OUTLOOK_TW_REQUEST_RETRIES,
    OUTLOOK_TW_REQUEST_TIMEOUT,
    OUTLOOK_TW_USERNAME_LENGTH,
)
from utils import extract_verification_link


class OutlookTwProviderError(RuntimeError):
    """outlook.tw mailbox creation or polling failed."""


class OutlookTwProvider:
    def __init__(self, session=None):
        self._owns_session = session is None
        self.session = session or self._create_session()
        self.email = None
        self.expires_at = None
        self.completed = False

    @staticmethod
    def _create_session():
        # Let curl-cffi keep its internally consistent TLS and browser headers.
        session = requests.Session(impersonate="chrome")
        session.headers.update({"Accept": "application/json"})
        return session

    def _reset_session(self):
        if not self._owns_session:
            return
        self.session.close()
        self.session = self._create_session()

    def _get_json(self, path, *, params=None):
        last_error = None
        for attempt in range(1, OUTLOOK_TW_REQUEST_RETRIES + 1):
            try:
                response = self.session.get(
                    f"{OUTLOOK_TW_BASE_URL}{path}",
                    params=params,
                    timeout=OUTLOOK_TW_REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()
            except (requests.RequestsError, ValueError) as exc:
                last_error = exc
                if attempt < OUTLOOK_TW_REQUEST_RETRIES:
                    self._reset_session()
                    time.sleep(min(float(attempt), 2.0))

        raise OutlookTwProviderError(
            f"outlook.tw 请求失败，已重试 {OUTLOOK_TW_REQUEST_RETRIES} 次: {last_error}"
        ) from last_error

    def acquire_email(self) -> str:
        if self.email:
            return self.email

        data = self._get_json(
            "/api/generate",
            params={
                "length": OUTLOOK_TW_USERNAME_LENGTH,
                "domainIndex": OUTLOOK_TW_DOMAIN_INDEX,
            },
        )
        email = str(data.get("email") or "").strip()
        if "@" not in email:
            raise OutlookTwProviderError("outlook.tw 未返回有效邮箱地址")

        self.email = email
        self.expires_at = data.get("expires")
        return email

    def wait_for_verification_link(self) -> str:
        if not self.email:
            raise OutlookTwProviderError("尚未生成 outlook.tw 邮箱")

        deadline = time.monotonic() + MAX_EMAIL_WAIT_TIME
        last_error = None
        while time.monotonic() < deadline:
            try:
                messages = self._get_json(
                    "/api/emails",
                    params={"mailbox": self.email},
                )
                if not isinstance(messages, list):
                    raise OutlookTwProviderError("outlook.tw 邮件列表格式异常")

                for message in messages:
                    link = self._extract_link_from_message(message)
                    if link:
                        self.completed = True
                        return link

                    message_id = message.get("id")
                    if message_id is None:
                        continue
                    detail = self._get_json(
                        f"/api/email/{quote(str(message_id), safe='')}"
                    )
                    link = self._extract_link_from_message(detail)
                    if link:
                        self.completed = True
                        return link
                last_error = None
            except (requests.RequestsError, ValueError, OutlookTwProviderError) as exc:
                last_error = exc

            time.sleep(OUTLOOK_TW_POLL_INTERVAL)

        suffix = f": {last_error}" if last_error else ""
        raise OutlookTwProviderError(f"等待 outlook.tw 的 Tavily 验证邮件超时{suffix}")

    @staticmethod
    def _extract_link_from_message(message) -> str | None:
        if not isinstance(message, dict):
            return None
        content = "\n".join(
            str(message.get(field) or "")
            for field in (
                "subject",
                "html_content",
                "content",
                "text_content",
                "preview",
                "verification_code",
            )
        )
        return extract_verification_link(content)

    def cancel(self) -> None:
        # Anonymous outlook.tw mailboxes expire automatically.
        return None

    def close(self) -> None:
        self.session.close()
