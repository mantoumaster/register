import random

from playwright.sync_api import sync_playwright

from bitbrowser_client import BitBrowserClient
from config import (
    BIT_BROWSER_API_URL,
    BIT_BROWSER_CLOSE_WAIT,
    BIT_BROWSER_ID,
    BIT_BROWSER_NAME,
    BROWSER_TIMEOUT,
    HEADLESS,
)
from .base_controller import BaseBrowserController


class BitBrowserController(BaseBrowserController):
    """Run one Outlook flow at a time in a dedicated BitBrowser profile."""

    def __init__(self):
        super().__init__()
        self.playwright = None
        self.bitbrowser = None
        self.browser_id = None
        self.browser_started = False
        self.browser = None
        self.context = None
        self.page = None

    def launch_browser(self):
        self.playwright = sync_playwright().start()
        self.bitbrowser = BitBrowserClient(BIT_BROWSER_API_URL)
        self.bitbrowser.health()
        self.browser_id = self.bitbrowser.get_or_create_browser(
            name=BIT_BROWSER_NAME,
            browser_id=BIT_BROWSER_ID,
            proxy_url=self.proxy,
        )
        self.bitbrowser.configure_reusable_browser(
            self.browser_id,
            name=BIT_BROWSER_NAME,
            proxy_url=self.proxy,
        )
        print(
            f"[Browser] - 复用 Outlook 专用比特浏览器窗口: "
            f"{BIT_BROWSER_NAME} ({self.browser_id})"
        )
        self.bitbrowser.randomize_fingerprint(self.browser_id)

        opened = self.bitbrowser.open_browser(self.browser_id, headless=HEADLESS)
        self.browser_started = True
        self.browser = self.playwright.chromium.connect_over_cdp(opened.ws)
        if not self.browser.contexts:
            raise RuntimeError("比特浏览器没有返回可用的浏览器上下文")
        return self.playwright, self.browser

    def get_thread_page(self):
        if self.browser_started:
            raise RuntimeError("Outlook 专用比特浏览器窗口正在执行其他任务")

        try:
            self.launch_browser()
            self.context = self.browser.contexts[0]
            pages = self.context.pages
            self.page = pages[0] if pages else self.context.new_page()
            for extra_page in pages[1:]:
                extra_page.close()
            self.page.set_default_timeout(BROWSER_TIMEOUT)
            return self.page
        except Exception:
            self.clean_up(type="all_browser")
            raise

    def handle_captcha(self, page):
        frame1 = page.frame_locator('iframe[title="验证质询"]')
        frame2 = frame1.frame_locator('iframe[style*="display: block"]')

        for _ in range(self.max_captcha_retries + 1):
            page.wait_for_timeout(200)
            loc = frame2.locator('[aria-label="可访问性挑战"]')
            box = loc.bounding_box()
            if not box:
                return False
            page.mouse.click(
                box["x"] + box["width"] / 2 + random.randint(-10, 10),
                box["y"] + box["height"] / 2 + random.randint(-10, 10),
            )

            loc2 = frame2.locator('[aria-label="再次按下"]')
            box2 = loc2.bounding_box()
            if not box2:
                return False
            page.mouse.click(
                box2["x"] + box2["width"] / 2 + random.randint(-20, 20),
                box2["y"] + box2["height"] / 2 + random.randint(-13, 13),
            )

            try:
                page.locator(".draw").wait_for(state="detached")
                try:
                    page.locator('[role="status"][aria-label="正在加载..."]').wait_for(
                        timeout=5000
                    )
                    page.wait_for_timeout(8000)
                    if (
                        page.get_by_text("一些异常活动").count()
                        or page.get_by_text(
                            "此站点正在维护，暂时无法使用，请稍后重试。"
                        ).count()
                        > 0
                    ):
                        print(
                            "[Error: Rate limit] - 正常通过验证码，"
                            "但当前IP注册频率过快。"
                        )
                        return False
                    if frame2.locator('[aria-label="可访问性挑战"]').count() > 0:
                        continue
                    break
                except Exception:
                    if page.get_by_text("取消").count() > 0:
                        break
                    frame1.get_by_text("请再试一次").wait_for(timeout=15000)
                    continue
            except Exception:
                if page.get_by_text("取消").count() > 0:
                    break
                return False
        else:
            return False

        return True

    def clean_up(self, page=None, type="all_browser"):
        cleanup_errors = []

        try:
            target_page = page or self.page
            if target_page and not target_page.is_closed():
                target_page.close()
        except Exception as exc:
            cleanup_errors.append(f"关闭页面失败: {exc}")

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as exc:
            cleanup_errors.append(f"断开 Playwright 失败: {exc}")

        if self.bitbrowser and self.browser_id and self.browser_started:
            try:
                self.bitbrowser.close_and_clear_browser(
                    self.browser_id,
                    wait_seconds=BIT_BROWSER_CLOSE_WAIT,
                )
            except Exception as exc:
                cleanup_errors.append(f"清理比特浏览器窗口失败: {exc}")

        if self.bitbrowser:
            self.bitbrowser.close()

        self.playwright = None
        self.bitbrowser = None
        self.browser_id = None
        self.browser_started = False
        self.browser = None
        self.context = None
        self.page = None

        for error in cleanup_errors:
            print(f"[Warning: Browser Cleanup] - {error}")
