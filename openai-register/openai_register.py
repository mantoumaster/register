import json
import os
import re
import time
import random
import argparse
from datetime import datetime
from typing import Any, Dict, Optional, List
import urllib.parse

from curl_cffi import requests
from outlook_tw_provider import OutlookTwProvider
from openai_browser import OpenAIBrowserFlow

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

LUCKMAIL_BASE_URL = str(os.getenv("LUCKMAIL_BASE_URL") or "https://mails.luckyous.com").strip().rstrip("/")
LUCKMAIL_API_KEY = str(os.getenv("LUCKMAIL_API_KEY") or "").strip()
LUCKMAIL_API_SECRET = str(os.getenv("LUCKMAIL_API_SECRET") or "").strip()
LUCKMAIL_USE_HMAC = str(os.getenv("LUCKMAIL_USE_HMAC") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
LUCKMAIL_PROJECT_CODE = str(os.getenv("LUCKMAIL_PROJECT_CODE") or "openai").strip()
LUCKMAIL_EMAIL_TYPE = str(os.getenv("LUCKMAIL_EMAIL_TYPE") or "ms_graph").strip()
LUCKMAIL_DOMAIN = str(os.getenv("LUCKMAIL_DOMAIN") or "outlook.com").strip()
LUCKMAIL_ORDER_TIMEOUT = int(str(os.getenv("LUCKMAIL_ORDER_TIMEOUT") or "180").strip() or "180")
LUCKMAIL_POLL_INTERVAL = float(str(os.getenv("LUCKMAIL_POLL_INTERVAL") or "6").strip() or "6")

OUTLOOK_TW_BASE_URL = str(os.getenv("OUTLOOK_TW_BASE_URL") or "https://outlook.tw").strip().rstrip("/")
OUTLOOK_TW_USERNAME_LENGTH = max(8, min(30, int(os.getenv("OUTLOOK_TW_USERNAME_LENGTH", "8"))))
OUTLOOK_TW_DOMAIN_INDEX = max(0, int(os.getenv("OUTLOOK_TW_DOMAIN_INDEX", "0")))
OUTLOOK_TW_POLL_INTERVAL = float(os.getenv("OUTLOOK_TW_POLL_INTERVAL", "3"))
OUTLOOK_TW_REQUEST_TIMEOUT = float(os.getenv("OUTLOOK_TW_REQUEST_TIMEOUT", "30"))
OUTLOOK_TW_MAX_WAIT = float(os.getenv("OUTLOOK_TW_MAX_WAIT", "300"))

try:
    from luckmail import LuckMailClient
    from luckmail.exceptions import LuckMailError
except Exception:
    LuckMailClient = None
    class LuckMailError(Exception):
        pass

# ========== 临时邮箱提供商：GPTMail + TempMail.lol + LuckMail ==========

class GPTMailClient:
    def __init__(self):
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://mail.chatgpt.org.uk/",
        })
        self.base_url = "https://mail.chatgpt.org.uk"

    def _init_browser_session(self):
        try:
            resp = self.session.get(self.base_url, timeout=15)
            gm_sid = self.session.cookies.get("gm_sid")
            if gm_sid:
                self.session.headers.update({"Cookie": f"gm_sid={gm_sid}"})
            token_match = re.search(r'(eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)', resp.text)
            if token_match:
                self.session.headers.update({"x-inbox-token": token_match.group(1)})
        except Exception:
            pass

    def generate_email(self) -> str:
        self._init_browser_session()
        resp = self.session.get(f"{self.base_url}/api/generate-email", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            email = data["data"]["email"]
            self.session.headers.update({"x-inbox-token": data["auth"]["token"]})
            print(f"[+] 生成邮箱: {email} (GPTMail)")
            print("[*] 自动轮询已启动（GPTMail 会话已准备）")
            return email
        raise RuntimeError(f"GPTMail 生成失败: {resp.status_code}")

    def list_emails(self, email: str) -> List[Dict[str, Any]]:
        encoded_email = urllib.parse.quote(email)
        resp = self.session.get(f"{self.base_url}/api/emails?email={encoded_email}", timeout=15)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("emails", [])
        return []


class Message:
    def __init__(self, data: dict):
        self.from_addr = data.get("from", "")
        self.subject = data.get("subject", "")
        self.body = data.get("body", "") or ""
        self.html_body = data.get("html", "") or ""


class EMail:
    def __init__(self):
        self.s = requests.Session(impersonate="chrome")
        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        r = self.s.post("https://api.tempmail.lol/v2/inbox/create", json={}, timeout=15)
        r.raise_for_status()
        data = r.json()
        self.address = data["address"]
        self.token = data["token"]
        print(f"[+] 生成邮箱: {self.address} (TempMail.lol)")
        print("[*] 自动轮询已启动（token 已保存）")

    def _get_messages(self) -> List[Dict[str, Any]]:
        r = self.s.get(f"https://api.tempmail.lol/v2/inbox?token={self.token}", timeout=15)
        r.raise_for_status()
        return r.json().get("emails", [])


class LuckMailInbox:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str = "",
        use_hmac: bool = False,
        project_code: str = "openai",
        email_type: str = "ms_graph",
        domain: str = "outlook.com",
        timeout: int = 180,
        poll_interval: float = 6.0,
    ):
        if LuckMailClient is None:
            raise RuntimeError("LuckMail SDK 不可用，请确认内置 luckmail 包可导入")
        if not base_url:
            raise RuntimeError("缺少 LUCKMAIL_BASE_URL")
        if not api_key:
            raise RuntimeError("缺少 LUCKMAIL_API_KEY")
        self.project_code = project_code or "openai"
        self.email_type = email_type or "ms_graph"
        self.domain = domain or "outlook.com"
        self.timeout = max(30, int(timeout or 180))
        self.poll_interval = max(1.0, float(poll_interval or 6.0))
        self.client = LuckMailClient(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret or None,
            use_hmac=bool(use_hmac),
            timeout=30.0,
        )
        self.purchase = None
        self.address = ""
        self.token = ""
        self._seen_message_ids: set[str] = set()

    def create_outlook_inbox(self) -> str:
        try:
            result = self.client.user.purchase_emails(
                project_code=self.project_code,
                quantity=1,
                email_type=self.email_type,
                domain=self.domain,
            )
        except LuckMailError as e:
            raise RuntimeError(f"LuckMail 购买邮箱失败: {e}") from e
        except Exception as e:
            raise RuntimeError(f"LuckMail 初始化失败: {e}") from e

        if not isinstance(result, dict):
            preview = repr(result)
            if isinstance(result, (bytes, bytearray)):
                preview = bytes(result[:200]).decode("utf-8", errors="replace")
            raise RuntimeError(f"LuckMail 购买邮箱失败：接口返回异常类型 {type(result).__name__}: {preview[:200]}")

        purchases_raw = result.get("purchases") or []
        if not isinstance(purchases_raw, list):
            raise RuntimeError(f"LuckMail 购买邮箱失败：purchases 字段类型异常: {type(purchases_raw).__name__}")

        purchases = list(purchases_raw)
        if not purchases:
            raise RuntimeError("LuckMail 购买邮箱失败：未返回 purchases")

        first_purchase = purchases[0]
        if not isinstance(first_purchase, dict):
            raise RuntimeError(f"LuckMail 购买邮箱失败：purchase 项类型异常: {type(first_purchase).__name__}")

        self.purchase = first_purchase
        self.address = str(self.purchase.get("email_address") or "").strip()
        self.token = str(self.purchase.get("token") or "").strip()
        if not self.address or not self.token:
            raise RuntimeError("LuckMail 购买邮箱失败：缺少 email_address 或 token")

        print(f"[+] 购买邮箱: {self.address} (LuckMail)")
        print("[*] 自动轮询已启动（LuckMail 已购邮箱 token 已保存）")
        return self.address

    def _poll_once(self):
        if not self.token:
            raise RuntimeError("LuckMail token 未初始化")
        try:
            return self.client.user.get_token_code(self.token)
        except LuckMailError as e:
            raise RuntimeError(f"LuckMail 查询验证码失败: {e}") from e

    def _extract_codes_from_token_result(self, result: Any) -> List[str]:
        body = " ".join([
            str(getattr(result, "verification_code", "") or ""),
            json.dumps(getattr(result, "mail", None) or {}, ensure_ascii=False),
        ])
        return re.findall(r"(?<!\d)(\d{6})(?!\d)", body)

    def _list_token_mails(self):
        if not self.token:
            raise RuntimeError("LuckMail token 未初始化")
        try:
            return self.client.user.get_token_mails(self.token)
        except LuckMailError as e:
            raise RuntimeError(f"LuckMail 获取邮件列表失败: {e}") from e

    def _get_token_mail_detail(self, message_id: str):
        if not self.token:
            raise RuntimeError("LuckMail token 未初始化")
        try:
            return self.client.user.get_token_mail_detail(self.token, message_id)
        except LuckMailError as e:
            raise RuntimeError(f"LuckMail 获取邮件详情失败: {e}") from e

    def _extract_all_codes(self) -> List[str]:
        results: List[str] = []
        try:
            token_result = self._poll_once()
            results.extend(self._extract_codes_from_token_result(token_result))
        except Exception:
            pass
        try:
            mail_list = self._list_token_mails()
            for mail in list(getattr(mail_list, "mails", []) or []):
                message_id = str(getattr(mail, "message_id", "") or "").strip()
                body = " ".join([
                    str(getattr(mail, "subject", "") or ""),
                    str(getattr(mail, "body", "") or ""),
                    str(getattr(mail, "html_body", "") or ""),
                ])
                results.extend(re.findall(r"(?<!\\d)(\\d{6})(?!\\d)", body))
                if message_id:
                    try:
                        detail = self._get_token_mail_detail(message_id)
                        body2 = " ".join([
                            str(getattr(detail, "subject", "") or ""),
                            str(getattr(detail, "body_text", "") or ""),
                            str(getattr(detail, "body_html", "") or ""),
                            str(getattr(detail, "verification_code", "") or ""),
                        ])
                        results.extend(re.findall(r"(?<!\d)(\d{6})(?!\d)", body2))
                    except Exception:
                        pass
        except Exception:
            pass
        return results

    def fetch_code(self, timeout_sec: int = 180, poll: float = 6.0, exclude_codes: Optional[List[str]] = None) -> str | None:
        exclude = set(exclude_codes or [])
        timeout_sec = max(30, int(timeout_sec or self.timeout))
        poll = max(1.0, float(poll or self.poll_interval))
        start = time.monotonic()
        attempt = 0
        while time.monotonic() - start < timeout_sec:
            attempt += 1
            try:
                token_result = self._poll_once()
                has_new_mail = bool(getattr(token_result, "has_new_mail", False))
                codes = self._extract_codes_from_token_result(token_result)
                print(f"[otp][luckmail] 轮询 #{attempt}, has_new_mail={has_new_mail}, token_code={getattr(token_result, 'verification_code', None)}, 目标: {self.address}")
                for code in codes:
                    if code and code not in exclude:
                        return code

                mail_list = self._list_token_mails()
                mails = list(getattr(mail_list, "mails", []) or [])
                print(f"[otp][luckmail] 邮件列表数量: {len(mails)}")
                for mail in mails:
                    message_id = str(getattr(mail, "message_id", "") or "").strip()
                    body = " ".join([
                        str(getattr(mail, "subject", "") or ""),
                        str(getattr(mail, "body", "") or ""),
                        str(getattr(mail, "html_body", "") or ""),
                    ])
                    for code in re.findall(r"(?<!\\d)(\\d{6})(?!\\d)", body):
                        if code and code not in exclude:
                            if message_id:
                                self._seen_message_ids.add(message_id)
                            return code
                    if message_id:
                        try:
                            detail = self._get_token_mail_detail(message_id)
                            detail_code = str(getattr(detail, "verification_code", "") or "").strip()
                            print(f"[otp][luckmail] 检查邮件详情: message_id={message_id}, detail_code={detail_code!r}, subject={getattr(detail, 'subject', '')!r}")
                            body2 = " ".join([
                                str(getattr(detail, "subject", "") or ""),
                                str(getattr(detail, "body_text", "") or ""),
                                str(getattr(detail, "body_html", "") or ""),
                                detail_code,
                            ])
                            if detail_code and detail_code not in exclude:
                                self._seen_message_ids.add(message_id)
                                return detail_code
                            for code in re.findall(r"(?<!\d)(\d{6})(?!\d)", body2):
                                if code and code not in exclude:
                                    self._seen_message_ids.add(message_id)
                                    return code
                        except Exception as e:
                            print(f"[otp][luckmail] 获取邮件详情异常: {e}")
            except Exception as e:
                print(f"[otp][luckmail] 轮询异常: {e}")
            time.sleep(poll)
        return None


def get_email_and_code_fetcher(
    provider: str = "auto",
    luckmail_base_url: str = "",
    luckmail_api_key: str = "",
    luckmail_api_secret: str = "",
    luckmail_use_hmac: bool = False,
    luckmail_project_code: str = "",
    luckmail_email_type: str = "",
    luckmail_domain: str = "",
    luckmail_order_timeout: int = 180,
    luckmail_poll_interval: float = 6.0,
    outlook_tw_base_url: str = "",
    outlook_tw_username_length: int = OUTLOOK_TW_USERNAME_LENGTH,
    outlook_tw_domain_index: int = OUTLOOK_TW_DOMAIN_INDEX,
    outlook_tw_poll_interval: float = OUTLOOK_TW_POLL_INTERVAL,
    outlook_tw_request_timeout: float = OUTLOOK_TW_REQUEST_TIMEOUT,
    outlook_tw_max_wait: float = OUTLOOK_TW_MAX_WAIT,
):
    provider = (provider or "auto").strip().lower()
    if provider in {"outlooktw", "outlook-tw"}:
        provider = "outlook_tw"
    if provider not in {"auto", "gptmail", "tempmail", "luckmail", "outlook_tw"}:
        raise ValueError(f"不支持的邮箱提供商: {provider}")

    def _build_tempmail_bundle():
        inbox = EMail()
        email = inbox.address

        def fetch_code(timeout_sec: int = 180, poll: float = 6.0, exclude_codes: Optional[List[str]] = None) -> str | None:
            exclude = set(exclude_codes or [])
            start = time.monotonic()
            attempt = 0
            while time.monotonic() - start < timeout_sec:
                attempt += 1
                try:
                    msgs = inbox._get_messages()
                    print(f"[otp][tempmail] 轮询 #{attempt}, 收到 {len(msgs)} 封邮件, 目标: {email}")
                    for msg_data in msgs:
                        msg = Message(msg_data)
                        body = msg.body or msg.html_body or msg.subject or ""
                        for code in re.findall(r"\b(\d{6})\b", body):
                            if code not in exclude:
                                return code
                except Exception:
                    pass
                time.sleep(poll)
            return None

        return email, fetch_code, "tempmail"

    def _build_gptmail_bundle():
        client = GPTMailClient()
        email = client.generate_email()

        def fetch_code(timeout_sec: int = 180, poll: float = 6.0, exclude_codes: Optional[List[str]] = None) -> str | None:
            exclude = set(exclude_codes or [])
            start = time.monotonic()
            attempt = 0
            while time.monotonic() - start < timeout_sec:
                attempt += 1
                try:
                    summaries = client.list_emails(email)
                    print(f"[otp][gptmail] 轮询 #{attempt}, 收到 {len(summaries)} 封邮件, 目标: {email}")
                    for s in summaries:
                        body = " ".join([
                            str(s.get("subject", "") or ""),
                            str(s.get("text", "") or ""),
                            str(s.get("body", "") or ""),
                            str(s.get("html", "") or ""),
                            json.dumps(s, ensure_ascii=False),
                        ])
                        for code in re.findall(r"(?<!\d)(\d{6})(?!\d)", body):
                            if code not in exclude:
                                return code
                except Exception:
                    pass
                time.sleep(poll)
            return None

        return email, fetch_code, "gptmail"

    def _build_luckmail_bundle():
        inbox = LuckMailInbox(
            base_url=(luckmail_base_url or LUCKMAIL_BASE_URL),
            api_key=(luckmail_api_key or LUCKMAIL_API_KEY),
            api_secret=(luckmail_api_secret or LUCKMAIL_API_SECRET),
            use_hmac=bool(luckmail_use_hmac or LUCKMAIL_USE_HMAC),
            project_code=(luckmail_project_code or LUCKMAIL_PROJECT_CODE),
            email_type=(luckmail_email_type or LUCKMAIL_EMAIL_TYPE),
            domain=(luckmail_domain or LUCKMAIL_DOMAIN),
            timeout=(luckmail_order_timeout or LUCKMAIL_ORDER_TIMEOUT),
            poll_interval=(luckmail_poll_interval or LUCKMAIL_POLL_INTERVAL),
        )
        email = inbox.create_outlook_inbox()
        def fetch_code(timeout_sec: int = 180, poll: float = 6.0, exclude_codes: Optional[List[str]] = None) -> str | None:
            return inbox.fetch_code(timeout_sec=timeout_sec, poll=poll, exclude_codes=exclude_codes)

        return email, fetch_code, "luckmail"

    def _build_outlook_tw_bundle():
        inbox = OutlookTwProvider(
            base_url=(outlook_tw_base_url or OUTLOOK_TW_BASE_URL),
            username_length=outlook_tw_username_length,
            domain_index=outlook_tw_domain_index,
            poll_interval=outlook_tw_poll_interval,
            request_timeout=outlook_tw_request_timeout,
            max_wait=outlook_tw_max_wait,
        )
        email = inbox.acquire_email()

        def fetch_code(timeout_sec: int = 180, poll: float = 6.0, exclude_codes=None):
            return inbox.wait_for_code(timeout_sec=timeout_sec, poll=poll, exclude_codes=exclude_codes)

        return email, fetch_code, "outlook_tw"

    if provider == "tempmail":
        return _build_tempmail_bundle()
    if provider == "gptmail":
        return _build_gptmail_bundle()
    if provider == "luckmail":
        return _build_luckmail_bundle()
    if provider == "outlook_tw":
        return _build_outlook_tw_bundle()

    try:
        return _build_luckmail_bundle()
    except Exception as e:
        print(f"[邮箱] LuckMail 初始化失败，回退 TempMail.lol: {e}")
    try:
        return _build_tempmail_bundle()
    except Exception as e:
        print(f"[邮箱] TempMail.lol 初始化失败，回退 GPTMail: {e}")
        return _build_gptmail_bundle()

# ========== 主注册流程 (恢复详细日志与异常捕获) ==========

def run(
    mail_provider: str = "auto",
    luckmail_base_url: str = "",
    luckmail_api_key: str = "",
    luckmail_api_secret: str = "",
    luckmail_use_hmac: bool = False,
    luckmail_project_code: str = "",
    luckmail_email_type: str = "",
    luckmail_domain: str = "",
    luckmail_order_timeout: int = 180,
    luckmail_poll_interval: float = 6.0,
    outlook_tw_base_url: str = "",
    outlook_tw_username_length: int = OUTLOOK_TW_USERNAME_LENGTH,
    outlook_tw_domain_index: int = OUTLOOK_TW_DOMAIN_INDEX,
    outlook_tw_poll_interval: float = OUTLOOK_TW_POLL_INTERVAL,
    outlook_tw_request_timeout: float = OUTLOOK_TW_REQUEST_TIMEOUT,
    outlook_tw_max_wait: float = OUTLOOK_TW_MAX_WAIT,
):
    print(f"\n{'='*20} 开启注册流程 {'='*20}")
    try:
        print(f"[步骤1] 正在初始化临时邮箱（provider={mail_provider}）...")
        email, code_fetcher, actual_mail_provider = get_email_and_code_fetcher(
            provider=mail_provider,
            luckmail_base_url=luckmail_base_url,
            luckmail_api_key=luckmail_api_key,
            luckmail_api_secret=luckmail_api_secret,
            luckmail_use_hmac=luckmail_use_hmac,
            luckmail_project_code=luckmail_project_code,
            luckmail_email_type=luckmail_email_type,
            luckmail_domain=luckmail_domain,
            luckmail_order_timeout=luckmail_order_timeout,
            luckmail_poll_interval=luckmail_poll_interval,
            outlook_tw_base_url=outlook_tw_base_url,
            outlook_tw_username_length=outlook_tw_username_length,
            outlook_tw_domain_index=outlook_tw_domain_index,
            outlook_tw_poll_interval=outlook_tw_poll_interval,
            outlook_tw_request_timeout=outlook_tw_request_timeout,
            outlook_tw_max_wait=outlook_tw_max_wait,
        )
        print(f"[*] 当前邮箱提供商: {actual_mail_provider}")
        if not email:
            print("[失败] 未能获取邮箱")
            return None
        print(f"[成功] 邮箱: {email} | 注册方式: 邮箱验证码（不使用密码）")

        # Registration is intentionally driven only by the recorded browser flow.
        browser_flow = OpenAIBrowserFlow()
        if not browser_flow.run(email=email, code_fetcher=code_fetcher):
            return None
        return email
    except Exception as e:
        print(f"[致命错误] 流程崩溃: {e}")
        return None

# ========== Main 保持原版完整结构与输出格式 ==========

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mail-provider", choices=["auto", "gptmail", "tempmail", "luckmail", "outlook_tw"], default="auto", help="临时邮箱提供商：auto/luckmail/gptmail/tempmail/outlook_tw")
    parser.add_argument("--once", action="store_true", help="只运行一次")
    parser.add_argument("--sleep-min", type=int, default=5, help="最小间隔(秒)")
    parser.add_argument("--sleep-max", type=int, default=30, help="最大间隔(秒)")
    parser.add_argument("--luckmail-base-url", default=os.getenv("LUCKMAIL_BASE_URL"), help="LuckMail 平台地址")
    parser.add_argument("--luckmail-api-key", default=os.getenv("LUCKMAIL_API_KEY"), help="LuckMail API Key")
    parser.add_argument("--luckmail-api-secret", default=os.getenv("LUCKMAIL_API_SECRET"), help="LuckMail API Secret（可选）")
    parser.add_argument("--luckmail-use-hmac", action="store_true", help="LuckMail 使用 HMAC 鉴权")
    parser.add_argument("--luckmail-project-code", default=os.getenv("LUCKMAIL_PROJECT_CODE", "openai"), help="LuckMail 项目编码")
    parser.add_argument("--luckmail-email-type", default=os.getenv("LUCKMAIL_EMAIL_TYPE", "ms_graph"), help="LuckMail 邮箱类型")
    parser.add_argument("--luckmail-domain", default=os.getenv("LUCKMAIL_DOMAIN", "outlook.com"), help="LuckMail 指定邮箱域名")
    parser.add_argument("--luckmail-order-timeout", type=int, default=int(os.getenv("LUCKMAIL_ORDER_TIMEOUT", "180")), help="LuckMail 接码等待超时(秒)")
    parser.add_argument("--luckmail-poll-interval", type=float, default=float(os.getenv("LUCKMAIL_POLL_INTERVAL", "6")), help="LuckMail 轮询间隔(秒)")
    parser.add_argument("--outlook-tw-base-url", default=os.getenv("OUTLOOK_TW_BASE_URL", "https://outlook.tw"), help="outlook.tw 地址")
    parser.add_argument("--outlook-tw-username-length", type=int, default=int(os.getenv("OUTLOOK_TW_USERNAME_LENGTH", "8")), help="outlook.tw 用户名长度")
    parser.add_argument("--outlook-tw-domain-index", type=int, default=int(os.getenv("OUTLOOK_TW_DOMAIN_INDEX", "0")), help="outlook.tw 域名索引")
    parser.add_argument("--outlook-tw-poll-interval", type=float, default=float(os.getenv("OUTLOOK_TW_POLL_INTERVAL", "3")), help="outlook.tw 轮询间隔")
    parser.add_argument("--outlook-tw-request-timeout", type=float, default=float(os.getenv("OUTLOOK_TW_REQUEST_TIMEOUT", "30")), help="outlook.tw 请求超时")
    parser.add_argument("--outlook-tw-max-wait", type=float, default=float(os.getenv("OUTLOOK_TW_MAX_WAIT", "300")), help="outlook.tw 最大接码等待时间")

    args = parser.parse_args()

    count = 0
    while True:
        count += 1
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> 流程 #{count} <<<")

        res = run(
            args.mail_provider,
            luckmail_base_url=args.luckmail_base_url,
            luckmail_api_key=args.luckmail_api_key,
            luckmail_api_secret=args.luckmail_api_secret,
            luckmail_use_hmac=args.luckmail_use_hmac,
            luckmail_project_code=args.luckmail_project_code,
            luckmail_email_type=args.luckmail_email_type,
            luckmail_domain=args.luckmail_domain,
            luckmail_order_timeout=args.luckmail_order_timeout,
            luckmail_poll_interval=args.luckmail_poll_interval,
            outlook_tw_base_url=args.outlook_tw_base_url,
            outlook_tw_username_length=args.outlook_tw_username_length,
            outlook_tw_domain_index=args.outlook_tw_domain_index,
            outlook_tw_poll_interval=args.outlook_tw_poll_interval,
            outlook_tw_request_timeout=args.outlook_tw_request_timeout,
            outlook_tw_max_wait=args.outlook_tw_max_wait,
        )
        if res:
            print(f"[🎉] 注册并登录成功: {res}")

        else:
            print("[-] 本次注册流程未能完成。")

        if args.once:
            break

        if not res:
            wait_time = random.randint(args.sleep_min, args.sleep_max)
            print(f"[*] 随机休息 {wait_time} 秒...")
            time.sleep(wait_time)

if __name__ == "__main__":
    main()
