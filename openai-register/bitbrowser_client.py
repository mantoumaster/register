"""Bit Browser Local API client used to attach Playwright over CDP."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


class BitBrowserError(RuntimeError):
    """Raised when the Bit Browser Local API returns an error."""


@dataclass
class BitBrowserOpenResult:
    ws: str
    http: str = ""
    driver: str = ""
    pid: Optional[int] = None


class BitBrowserClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        if not base_url:
            raise ValueError("BIT_BROWSER_API_URL 不能为空")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None):
        try:
            response = self.session.post(
                f"{self.base_url}{path}",
                json=payload or {},
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise BitBrowserError(f"调用比特浏览器接口失败 {path}: {exc}") from exc
        if not result.get("success"):
            raise BitBrowserError(
                f"比特浏览器接口返回失败 {path}: {result.get('msg', result)}"
            )
        return result.get("data")

    def health(self) -> bool:
        self._post("/health")
        return True

    def list_browsers(self, name: str = "") -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"page": 0, "pageSize": 100}
        if name:
            payload["name"] = name
        data = self._post("/browser/list", payload) or {}
        browsers = data.get("list", []) if isinstance(data, dict) else []
        if not isinstance(browsers, list):
            raise BitBrowserError("浏览器窗口列表格式异常")
        return browsers

    def create_browser(self, name: str) -> str:
        data = self._post(
            "/browser/update",
            {
                "name": name,
                "workbench": "disable",
                "browserFingerPrint": {},
            },
        ) or {}
        browser_id = data.get("id")
        if not browser_id:
            raise BitBrowserError("创建窗口成功，但响应中缺少窗口 id")
        return str(browser_id)

    def get_or_create_browser(self, name: str, browser_id: str = "") -> str:
        if browser_id:
            return browser_id
        matches = [
            item for item in self.list_browsers(name)
            if str(item.get("name") or "") == name and item.get("id")
        ]
        if len(matches) > 1:
            raise BitBrowserError(f"发现多个同名窗口 {name}")
        return str(matches[0]["id"]) if matches else self.create_browser(name)

    def configure_reusable_browser(self, browser_id: str, name: str) -> None:
        self._post(
            "/browser/update/partial",
            {
                "ids": [browser_id],
                "name": name,
                "workbench": "disable",
                "syncTabs": False,
                "syncCookies": False,
                "syncIndexedDb": False,
                "syncLocalStorage": False,
                "syncAuthorization": False,
                "syncHistory": False,
                "clearCacheFilesBeforeLaunch": True,
                "clearCookiesBeforeLaunch": True,
                "clearHistoriesBeforeLaunch": True,
            },
        )

    def randomize_fingerprint(self, browser_id: str) -> None:
        self._post("/browser/fingerprint/random", {"browserId": browser_id})

    def open_browser(self, browser_id: str, headless: bool = False) -> BitBrowserOpenResult:
        data = self._post(
            "/browser/open",
            {
                "id": browser_id,
                "args": ["--headless"] if headless else [],
                "queue": True,
                "ignoreDefaultUrls": True,
            },
        ) or {}
        ws = data.get("ws")
        if not ws:
            raise BitBrowserError("打开窗口成功，但响应中缺少 Playwright CDP ws 地址")
        return BitBrowserOpenResult(
            ws=ws,
            http=data.get("http", ""),
            driver=data.get("driver", ""),
            pid=data.get("pid"),
        )

    def close_browser(self, browser_id: str) -> None:
        self._post("/browser/close", {"id": browser_id})

    def clear_cookies(self, browser_id: str) -> None:
        self._post("/browser/cookies/clear", {"browserId": browser_id, "saveSynced": True})

    def clear_cache(self, browser_id: str) -> None:
        self._post("/cache/clear", {"ids": [browser_id]})

    def close_and_clear_browser(self, browser_id: str, wait_seconds: float = 5.0) -> None:
        errors = []
        try:
            self.close_browser(browser_id)
        except BitBrowserError as exc:
            errors.append(str(exc))
        time.sleep(max(5.0, wait_seconds))
        for action in (lambda: self.clear_cookies(browser_id), lambda: self.clear_cache(browser_id)):
            try:
                action()
            except BitBrowserError as exc:
                errors.append(str(exc))
        if errors:
            raise BitBrowserError("；".join(errors))

    def close(self) -> None:
        self.session.close()
