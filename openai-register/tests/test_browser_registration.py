import unittest
from unittest.mock import patch

import openai_register
from outlook_tw_provider import OutlookTwProvider


class OutlookTwProviderTests(unittest.TestCase):
    def test_extracts_openai_code_from_message_and_detail(self):
        provider = OutlookTwProvider(max_wait=1)
        provider.email = "test@outlook.tw"

        def fake_get(path, params=None):
            if path == "/api/emails":
                return [{"id": "message-1", "subject": "Your code is 123456"}]
            return {"html_content": "<p>Verification code: 654321</p>"}

        provider._get_json = fake_get
        self.assertEqual(provider.extract_all_codes(), ["123456", "654321"])


class BrowserDispatchTests(unittest.TestCase):
    def test_run_uses_browser_flow(self):
        fake_bundle = (
            "test@outlook.tw",
            lambda **kwargs: "123456",
            "outlook_tw",
        )

        with patch.object(
            openai_register, "get_email_and_code_fetcher", return_value=fake_bundle
        ), patch.object(openai_register, "OpenAIBrowserFlow") as flow_class:
            flow_class.return_value.run.return_value = True
            result = openai_register.run(mail_provider="outlook_tw")

        self.assertEqual(result, "test@outlook.tw")
        flow_class.return_value.run.assert_called_once()
        self.assertEqual(
            flow_class.return_value.run.call_args.kwargs["email"],
            "test@outlook.tw",
        )


if __name__ == "__main__":
    unittest.main()
