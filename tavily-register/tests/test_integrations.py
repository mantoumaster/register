import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bitbrowser_client import BitBrowserClient, BitBrowserError
from utils import extract_verification_link


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.headers = {}

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse(next(self.responses))

    def close(self):
        return None


class FakeOutlookTwSession:
    def __init__(self):
        self.headers = {}
        self.calls = []
        self.closed = False

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if url.endswith("/api/generate"):
            return FakeResponse(
                {
                    "email": "testbox@outlook.tw",
                    "expires": 123456789,
                    "anonymous": True,
                }
            )
        if url.endswith("/api/emails"):
            return FakeResponse([{"id": 42, "subject": "Verify your email"}])
        if url.endswith("/api/email/42"):
            return FakeResponse(
                {
                    "id": 42,
                    "html_content": (
                        '<a href="https://auth.tavily.com/u/email-verification?'
                        'ticket=outlook-tw-test">Verify</a>'
                    ),
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    def close(self):
        self.closed = True


class BitBrowserClientTests(unittest.TestCase):
    def test_create_and_open_browser(self):
        client = BitBrowserClient("http://127.0.0.1:54345")
        client.session = FakeSession(
            [
                {"success": True, "data": {"id": "browser-1"}},
                {
                    "success": True,
                    "data": {"ws": "ws://127.0.0.1/devtools/browser/1"},
                },
            ]
        )

        browser_id = client.create_browser("tavily-test")
        opened = client.open_browser(browser_id, headless=True)

        self.assertEqual(browser_id, "browser-1")
        self.assertEqual(opened.ws, "ws://127.0.0.1/devtools/browser/1")
        self.assertEqual(client.session.calls[1][1]["args"], ["--headless"])
        self.assertTrue(client.session.calls[1][1]["queue"])

    def test_reuses_exact_named_browser(self):
        client = BitBrowserClient("http://127.0.0.1:54345")
        client.session = FakeSession(
            [
                {
                    "success": True,
                    "data": {
                        "list": [
                            {"id": "browser-other", "name": "tavily-register-old"},
                            {"id": "browser-reused", "name": "tavily-register"},
                        ]
                    },
                }
            ]
        )

        browser_id = client.get_or_create_browser("tavily-register")

        self.assertEqual(browser_id, "browser-reused")
        self.assertTrue(client.session.calls[0][0].endswith("/browser/list"))
        self.assertEqual(client.session.calls[0][1]["name"], "tavily-register")

    def test_rejects_duplicate_exact_named_browsers(self):
        client = BitBrowserClient("http://127.0.0.1:54345")
        client.session = FakeSession(
            [
                {
                    "success": True,
                    "data": {
                        "list": [
                            {"id": "browser-1", "name": "tavily-register"},
                            {"id": "browser-2", "name": "tavily-register"},
                        ]
                    },
                }
            ]
        )

        with self.assertRaisesRegex(BitBrowserError, "多个同名窗口"):
            client.get_or_create_browser("tavily-register")

    @patch("bitbrowser_client.time.sleep", return_value=None)
    def test_configures_randomizes_and_clears_reusable_browser(self, sleep):
        client = BitBrowserClient("http://127.0.0.1:54345")
        client.session = FakeSession(
            [
                {"success": True, "data": None},
                {"success": True, "data": {"canvas": "randomized"}},
                {"success": True, "data": None},
                {"success": True, "data": None},
                {"success": True, "data": None},
            ]
        )

        client.configure_reusable_browser("browser-1", "tavily-register")
        client.randomize_fingerprint("browser-1")
        client.close_and_clear_browser("browser-1", wait_seconds=5)

        calls = client.session.calls
        self.assertTrue(calls[0][0].endswith("/browser/update/partial"))
        self.assertFalse(calls[0][1]["syncCookies"])
        self.assertTrue(calls[0][1]["clearCacheFilesBeforeLaunch"])
        self.assertTrue(calls[1][0].endswith("/browser/fingerprint/random"))
        self.assertTrue(calls[2][0].endswith("/browser/close"))
        self.assertTrue(calls[3][0].endswith("/browser/cookies/clear"))
        self.assertTrue(calls[3][1]["saveSynced"])
        self.assertTrue(calls[4][0].endswith("/cache/clear"))
        sleep.assert_called_once_with(5.0)


class VerificationLinkTests(unittest.TestCase):
    def test_extracts_tavily_link_from_html(self):
        body = (
            '<a href="https://auth.tavily.com/u/email-verification?ticket=abc123&amp;x=1">'
            "Verify</a>"
        )
        link = extract_verification_link(body)
        self.assertEqual(
            link,
            "https://auth.tavily.com/u/email-verification?ticket=abc123&x=1",
        )

    def test_falls_back_to_url_in_verification_code(self):
        link = extract_verification_link(
            None,
            "https://example.com/confirm?id=42",
        )
        self.assertEqual(link, "https://example.com/confirm?id=42")


class OutlookTwProviderTests(unittest.TestCase):
    def test_generates_mailbox_and_extracts_verification_link(self):
        from outlook_tw_provider import OutlookTwProvider

        session = FakeOutlookTwSession()
        provider = OutlookTwProvider(session=session)

        self.assertNotIn("User-Agent", session.headers)
        self.assertEqual(provider.acquire_email(), "testbox@outlook.tw")
        self.assertEqual(
            provider.wait_for_verification_link(),
            "https://auth.tavily.com/u/email-verification?ticket=outlook-tw-test",
        )
        self.assertEqual(
            session.calls[0][1],
            {"length": 8, "domainIndex": 0},
        )
        self.assertEqual(
            session.calls[1][1],
            {"mailbox": "testbox@outlook.tw"},
        )
        self.assertTrue(provider.completed)

        provider.close()
        self.assertTrue(session.closed)

    @patch("mail_provider.OutlookTwProvider")
    @patch("mail_provider.EMAIL_PROVIDER", "outlook_tw")
    def test_factory_selects_outlook_tw(self, provider_class):
        from mail_provider import create_mail_provider

        create_mail_provider()
        provider_class.assert_called_once_with()


class ApiKeyOutputTests(unittest.TestCase):
    def test_saves_one_key_per_line_without_duplicates(self):
        from utils import save_api_key

        with TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "api_keys.txt"
            with patch("utils.API_KEYS_FILE", str(output_file)):
                save_api_key("tvly-first_key")
                save_api_key("copied value: tvly-second-key")
                save_api_key("tvly-first_key")

            self.assertEqual(
                output_file.read_text(encoding="utf-8"),
                "tvly-first_key\ntvly-second-key\n",
            )

    def test_rejects_text_without_tavily_key(self):
        from utils import save_api_key

        with TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "api_keys.txt"
            with patch("utils.API_KEYS_FILE", str(output_file)):
                with self.assertRaises(ValueError):
                    save_api_key("not-a-key")

            self.assertFalse(output_file.exists())

    def test_masks_api_key_for_logs(self):
        from utils import mask_api_key

        self.assertEqual(mask_api_key("tvly-1234567890"), "tvly-...7890")
        self.assertEqual(mask_api_key("not-a-key"), "<invalid>")


class FakePage:
    def __init__(self):
        self.closed = False
        self.timeout = None

    def set_default_timeout(self, timeout):
        self.timeout = timeout

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]


class FakeConnectedBrowser:
    def __init__(self):
        self.contexts = [FakeContext()]


class FakeChromium:
    def __init__(self):
        self.ws = None

    def connect_over_cdp(self, ws):
        self.ws = ws
        return FakeConnectedBrowser()


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakePlaywrightStarter:
    def __init__(self):
        self.instance = FakePlaywright()

    def start(self):
        return self.instance


class FakeBitBrowser:
    def __init__(self, _url):
        self.events = []

    def health(self):
        return True

    def get_or_create_browser(self, name, browser_id=""):
        self.events.append(("get_or_create", name, browser_id))
        return "browser-reused"

    def configure_reusable_browser(self, browser_id, name):
        self.events.append(("configure", browser_id, name))

    def randomize_fingerprint(self, browser_id):
        self.events.append(("randomize", browser_id))

    def open_browser(self, browser_id, headless=False):
        self.events.append(("open", browser_id, headless))
        return type("Opened", (), {"ws": "ws://bitbrowser"})()

    def close_and_clear_browser(self, browser_id, wait_seconds=5):
        self.events.append(("close_and_clear", browser_id, wait_seconds))

    def close(self):
        return None


class FakeMailProvider:
    def close(self):
        return None

    def cancel(self):
        return None


class FakeClickableElement:
    def __init__(self):
        self.click_count = 0

    def wait_for_element_state(self, _state, timeout):
        return timeout

    def click(self):
        self.click_count += 1


class FakeClickPage:
    def __init__(self):
        self.waits = []

    def wait_for_timeout(self, timeout):
        self.waits.append(timeout)


class FakeCopyButton:
    def __init__(self):
        self.click_count = 0

    def is_visible(self):
        return True

    def scroll_into_view_if_needed(self):
        return None

    def click(self):
        self.click_count += 1

    def evaluate(self, _script):
        return ""


class FakeCopyPage:
    def __init__(self, button):
        self.button = button
        self.selectors = []

    def query_selector_all(self, selector):
        self.selectors.append(selector)
        if selector == 'button:has-text("Copy key")':
            return [self.button]
        return []


class FakeVerificationHomePage:
    def __init__(self, close_button, cookie_button=None):
        self.url = "https://app.tavily.com/home?email_verified=1"
        self.close_button = close_button
        self.cookie_button = cookie_button
        self.waited_selectors = []

    def wait_for_selector(self, selector, **kwargs):
        self.waited_selectors.append((selector, kwargs))
        if selector == '[id^="chakra-modal--body-"] button:has-text("Continue")':
            return self.close_button
        if selector == "#onetrust-accept-btn-handler":
            return self.cookie_button
        return None

    def query_selector_all(self, selector):
        return []


class FakeLocator:
    def __init__(self):
        self.wait_calls = []

    def wait_for(self, **kwargs):
        self.wait_calls.append(kwargs)


class FakeNavigationPage:
    def __init__(self):
        self.url = "https://auth.tavily.com/u/login/identifier?state=test"
        self.goto_calls = []
        self.wait_url_calls = []
        self.email_locator = FakeLocator()

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))

    def wait_for_url(self, url, **kwargs):
        self.wait_url_calls.append((url, kwargs))
        self.url = "https://auth.tavily.com/u/signup/identifier?state=test"

    def locator(self, selector):
        assert selector == "input#email"
        return self.email_locator


class AutomationLifecycleTests(unittest.TestCase):
    @patch("tavily_automation.BitBrowserClient", FakeBitBrowser)
    @patch("tavily_automation.sync_playwright", FakePlaywrightStarter)
    def test_automation_reuses_randomizes_and_clears_browser(self):
        from tavily_automation import TavilyAutomation

        automation = TavilyAutomation(mail_provider=FakeMailProvider())
        automation.start_browser(headless=True)
        bitbrowser = automation.bitbrowser

        self.assertEqual(automation.browser_id, "browser-reused")
        self.assertEqual(automation.playwright.chromium.ws, "ws://bitbrowser")
        automation.close_browser()
        self.assertEqual(
            bitbrowser.events,
            [
                ("get_or_create", "tavily-register", ""),
                ("configure", "browser-reused", "tavily-register"),
                ("randomize", "browser-reused"),
                ("open", "browser-reused", True),
                ("close_and_clear", "browser-reused", 5.0),
            ],
        )

    @patch("tavily_automation.human_delay", return_value=0)
    def test_click_does_not_reload_or_click_twice(self, _delay):
        from tavily_automation import TavilyAutomation

        automation = TavilyAutomation(mail_provider=FakeMailProvider())
        element = FakeClickableElement()
        page = FakeClickPage()
        automation.page = page
        automation.wait_for_element = lambda _config: (element, "selector")

        self.assertTrue(automation.click_element("continue_button", retries=3))
        self.assertEqual(element.click_count, 1)
        self.assertEqual(page.waits, [500])

    @patch("tavily_automation.human_delay", return_value=0)
    def test_navigation_waits_for_signup_url_and_email_input(self, _delay):
        from tavily_automation import TavilyAutomation

        automation = TavilyAutomation(mail_provider=FakeMailProvider())
        page = FakeNavigationPage()
        automation.page = page
        automation.click_element = lambda _name: True

        self.assertTrue(automation.navigate_to_signup())
        self.assertEqual(page.goto_calls[0][1]["wait_until"], "domcontentloaded")
        self.assertEqual(page.wait_url_calls[0][0], "**/u/signup/**")
        self.assertEqual(
            page.email_locator.wait_calls,
            [{"state": "visible", "timeout": 30000}],
        )


class ApiKeyCopyTests(unittest.TestCase):
    @patch("email_checker.human_delay", return_value=0)
    @patch("email_checker.wait_with_message", return_value=None)
    def test_clicks_copy_button_before_returning_key(self, _wait, _delay):
        from email_checker import EmailChecker

        button = FakeCopyButton()
        checker = EmailChecker()
        checker.page = FakeCopyPage(button)
        checker._read_clipboard_api_key = lambda: "tvly-copied-key"

        self.assertEqual(checker._click_copy_key_button(), "tvly-copied-key")
        self.assertEqual(button.click_count, 1)

    @patch("email_checker.human_delay", return_value=0)
    @patch("email_checker.wait_with_message", return_value=None)
    def test_closes_overlays_before_copying_key(self, _wait, _delay):
        from email_checker import EmailChecker

        close_button = FakeCopyButton()
        cookie_button = FakeCopyButton()
        checker = EmailChecker()
        checker.page = FakeVerificationHomePage(close_button, cookie_button)

        overlay_click_counts = []

        def copy_key():
            overlay_click_counts.append(
                (close_button.click_count, cookie_button.click_count)
            )
            return "tvly-after-popup-close"

        checker._click_copy_key_button = copy_key

        self.assertEqual(
            checker.get_api_key_from_tavily(),
            "tvly-after-popup-close",
        )
        self.assertEqual(overlay_click_counts, [(1, 1)])
        self.assertEqual(
            checker.page.waited_selectors,
            [
                (
                    '[id^="chakra-modal--body-"] button:has-text("Continue")',
                    {"state": "visible", "timeout": 8000},
                ),
                (
                    "#onetrust-accept-btn-handler",
                    {"state": "visible", "timeout": 3000},
                ),
            ],
        )

    @patch("email_checker.human_delay", return_value=0)
    @patch("email_checker.wait_with_message", return_value=None)
    def test_copies_key_when_cookie_popup_is_absent(self, _wait, _delay):
        from email_checker import EmailChecker

        close_button = FakeCopyButton()
        checker = EmailChecker()
        checker.page = FakeVerificationHomePage(close_button)
        checker._click_copy_key_button = lambda: "tvly-without-cookie-popup"

        self.assertEqual(
            checker.get_api_key_from_tavily(),
            "tvly-without-cookie-popup",
        )
        self.assertEqual(close_button.click_count, 1)


class HumanDelayTests(unittest.TestCase):
    @patch("utils.time.sleep")
    @patch("utils.random.uniform", return_value=1.37)
    def test_human_delay_uses_random_duration(self, random_uniform, sleep):
        from utils import human_delay

        self.assertEqual(human_delay("测试点击", minimum=0.5, maximum=2.0), 1.37)
        random_uniform.assert_called_once_with(0.5, 2.0)
        sleep.assert_called_once_with(1.37)


class PasswordGenerationTests(unittest.TestCase):
    def test_generates_unique_passwords_with_required_character_groups(self):
        from utils import PASSWORD_LENGTH, PASSWORD_SPECIAL_CHARS, generate_password

        passwords = {generate_password() for _ in range(20)}

        self.assertEqual(len(passwords), 20)
        for password in passwords:
            self.assertEqual(len(password), PASSWORD_LENGTH)
            self.assertTrue(any(character.islower() for character in password))
            self.assertTrue(any(character.isupper() for character in password))
            self.assertTrue(any(character.isdigit() for character in password))
            self.assertTrue(
                any(character in PASSWORD_SPECIAL_CHARS for character in password)
            )

    def test_rejects_passwords_shorter_than_required_groups(self):
        from utils import generate_password

        with self.assertRaisesRegex(ValueError, "不能少于 4 位"):
            generate_password(length=3)


if __name__ == "__main__":
    unittest.main()
