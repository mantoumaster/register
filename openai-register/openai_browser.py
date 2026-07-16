"""Playwright flow for OpenAI signup/login through a Bit Browser profile."""

from __future__ import annotations

import os
import random
import re
from typing import Callable, Iterable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from bitbrowser_client import BitBrowserClient


class OpenAIBrowserError(RuntimeError):
    """OpenAI browser flow failed."""


class OpenAIBrowserFlow:
    def __init__(self, headless: bool | None = None):
        self.headless = (
            str(os.getenv("BIT_BROWSER_HEADLESS", "false")).lower()
            in {"1", "true", "yes", "on"}
            if headless is None else bool(headless)
        )
        self.api_url = os.getenv("BIT_BROWSER_API_URL", "http://127.0.0.1:54346")
        self.browser_name = os.getenv("BIT_BROWSER_NAME", "openai-register")
        self.browser_id = os.getenv("BIT_BROWSER_ID", "")
        self.close_wait = max(5.0, float(os.getenv("BIT_BROWSER_CLOSE_WAIT", "5")))
        self.playwright = None
        self.bitbrowser = None
        self.browser = None
        self.context = None
        self.page = None
        self.started = False

    def start(self):
        self.playwright = sync_playwright().start()
        self.bitbrowser = BitBrowserClient(self.api_url)
        self.bitbrowser.health()
        self.browser_id = self.bitbrowser.get_or_create_browser(
            self.browser_name, self.browser_id
        )
        self.bitbrowser.configure_reusable_browser(self.browser_id, self.browser_name)
        self.bitbrowser.randomize_fingerprint(self.browser_id)
        opened = self.bitbrowser.open_browser(self.browser_id, self.headless)
        self.started = True
        self.browser = self.playwright.chromium.connect_over_cdp(opened.ws)
        if not self.browser.contexts:
            raise OpenAIBrowserError("比特浏览器没有返回可用的浏览器上下文")
        self.context = self.browser.contexts[0]
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(int(os.getenv("BROWSER_TIMEOUT", "30000")))
        return self

    def close(self):
        try:
            if self.page and not self.page.is_closed():
                self.page.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        finally:
            if self.bitbrowser and self.browser_id and self.started:
                try:
                    self.bitbrowser.close_and_clear_browser(self.browser_id, self.close_wait)
                except Exception as exc:
                    print(f"[BitBrowser] 清理窗口失败: {exc}")
            if self.bitbrowser:
                self.bitbrowser.close()
            self.playwright = self.bitbrowser = self.browser = self.context = self.page = None
            self.started = False

    @staticmethod
    def _first_visible(page, selectors: Iterable[str]):
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=3000)
                if locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    def _fill(self, selectors: Iterable[str], value: str, label: str):
        element = self._first_visible(self.page, selectors)
        if not element:
            raise OpenAIBrowserError(f"未找到 {label} 输入框")
        element.fill(value)
        if element.input_value() != value:
            raise OpenAIBrowserError(f"{label} 输入值校验失败")

    def _click(self, selectors: Iterable[str], label: str, required: bool = True) -> bool:
        element = self._first_visible(self.page, selectors)
        if not element:
            if required:
                raise OpenAIBrowserError(f"未找到 {label} 按钮")
            return False
        element.click()
        self.page.wait_for_timeout(500)
        return True

    def _goto(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(800)

    def _fill_otp(self, code: str):
        code = str(code).strip()
        if not re.fullmatch(r"\d{6}", code):
            raise OpenAIBrowserError(f"验证码格式错误: {code!r}")
        inputs = self.page.locator(
            'input[autocomplete="one-time-code"], input[inputmode="numeric"], '
            'input[name*="code" i], input[id*="code" i]'
        )
        visible = []
        for index in range(inputs.count()):
            item = inputs.nth(index)
            try:
                if item.is_visible():
                    visible.append(item)
            except Exception:
                pass
        if not visible:
            raise OpenAIBrowserError("未找到验证码输入框")
        if len(visible) == 1:
            visible[0].fill(code)
        else:
            for item, digit in zip(visible[:6], code):
                item.fill(digit)

    @staticmethod
    def _fetch_code(code_fetcher: Callable, exclude_codes=None):
        try:
            return code_fetcher(timeout_sec=240, poll=4, exclude_codes=exclude_codes or [])
        except TypeError:
            return code_fetcher()

    def _signup(self, email: str, code_fetcher: Callable):
        # This follows the supplied recorder: ChatGPT's login entry point
        # creates an account after email OTP, name and age are submitted.
        self._goto("https://chatgpt.com/")
        self._click(
            ['[data-testid="login-button"]', '[data-testid="login-button"] > div',
             'a:has-text("Log in")', 'button:has-text("Log in")'],
            "登录入口"
        )
        self._fill(
            ['#email', 'input[name="username"]', 'input[type="email"]', 'input[name="email"]'],
            email, "邮箱"
        )
        self._click(
            ['button:has-text("Continue")', 'form > button', 'button[type="submit"]'], "邮箱提交"
        )
        print("[*] 等待 OpenAI 注册验证码...")
        code = self._fetch_code(code_fetcher)
        if not code:
            raise OpenAIBrowserError("未收到注册验证码")
        self._fill_otp(code)
        self._click(
            ['button:has-text("Continue")', 'button[type="submit"]'],
            "验证码提交"
        )
        self._fill(
            ['input[id$="-name"]', 'input[name="name"]', 'input[autocomplete="name"]',
             'input[placeholder*="name" i]'],
            self._random_name(), "姓名"
        )
        self._fill(
            ['input[id$="-age"]', 'input[name="age"]', 'input[aria-label="年龄"]'],
            os.getenv("OPENAI_REGISTER_AGE", "24"), "年龄"
        )
        self._click(
            ['button:has-text("完成帐户创建")', 'button:has-text("Complete account creation")',
             'button[type="submit"]'], "账户信息提交"
        )
        self._click(
            ['dialog button:has-text("Continue")', 'dialog button', 'button:has-text("Continue")'],
            "注册完成确认", required=False
        )
        self._click(
            ['p:has-text("与 ChatGPT 聊天")', 'button:has-text("与 ChatGPT 聊天")',
             '[data-testid="conversation-turn-2"]'],
            "进入 ChatGPT", required=False
        )
        try:
            self.page.locator('#prompt-textarea').wait_for(state="visible", timeout=30000)
        except PlaywrightTimeoutError as exc:
            raise OpenAIBrowserError(
                f"账户创建后未进入 ChatGPT，当前页面: {self.page.url}"
            ) from exc

    @staticmethod
    def _random_name() -> str:
        first = random.choice(("Alex", "Jamie", "Taylor", "Jordan", "Casey"))
        last = random.choice(("Morgan", "Lee", "Miller", "Wilson", "Martin"))
        return f"{first} {last}"

    def run(self, email: str, code_fetcher: Callable):
        if not self.page:
            self.start()
        try:
            print("[步骤2] 通过比特浏览器打开 OpenAI 注册页...")
            self._signup(email, code_fetcher)
            print("[步骤3] ChatGPT 登录成功，注册流程结束")
            return True
        finally:
            self.close()
