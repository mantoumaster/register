import unittest
from unittest.mock import patch

from bitbrowser_client import BitBrowserClient, proxy_fields_from_url


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


class BitBrowserClientTests(unittest.TestCase):
    def test_parses_authenticated_proxy(self):
        fields = proxy_fields_from_url("http://user:p%40ss@127.0.0.1:10808")

        self.assertEqual(fields["proxyType"], "http")
        self.assertEqual(fields["host"], "127.0.0.1")
        self.assertEqual(fields["port"], "10808")
        self.assertEqual(fields["proxyUserName"], "user")
        self.assertEqual(fields["proxyPassword"], "p@ss")

    def test_uses_a_separate_exact_named_profile(self):
        client = BitBrowserClient("http://127.0.0.1:54346")
        client.session = FakeSession(
            [
                {"success": True, "data": {"list": []}},
                {"success": True, "data": {"id": "outlook-browser"}},
            ]
        )

        browser_id = client.get_or_create_browser(
            "outlook-register", proxy_url="http://127.0.0.1:10808"
        )

        self.assertEqual(browser_id, "outlook-browser")
        self.assertEqual(client.session.calls[0][1]["name"], "outlook-register")
        self.assertEqual(client.session.calls[1][1]["name"], "outlook-register")
        self.assertEqual(client.session.calls[1][1]["host"], "127.0.0.1")

    @patch("bitbrowser_client.time.sleep", return_value=None)
    def test_closes_and_clears_reusable_profile(self, sleep):
        client = BitBrowserClient("http://127.0.0.1:54346")
        client.session = FakeSession(
            [
                {"success": True, "data": None},
                {"success": True, "data": None},
                {"success": True, "data": None},
            ]
        )

        client.close_and_clear_browser("outlook-browser", wait_seconds=5)

        self.assertTrue(client.session.calls[0][0].endswith("/browser/close"))
        self.assertTrue(client.session.calls[1][0].endswith("/browser/cookies/clear"))
        self.assertTrue(client.session.calls[2][0].endswith("/cache/clear"))
        sleep.assert_called_once_with(5.0)


if __name__ == "__main__":
    unittest.main()
