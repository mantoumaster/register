#!/usr/bin/env python3
"""
Tavily 邮箱验证、登录与 API key 页面操作。
"""

import shutil
import subprocess

from config import BROWSER_TIMEOUT
from utils import extract_api_key, human_delay, mask_api_key, wait_with_message


class EmailChecker:
    def __init__(self):
        self.page = None

    def attach_to(self, page):
        """Reuse an existing Playwright page."""
        self.page = page
        self.page.set_default_timeout(BROWSER_TIMEOUT)

    @staticmethod
    def _human_click(element, action, **kwargs):
        human_delay(action)
        element.click(**kwargs)

    @staticmethod
    def _human_fill(element, value, action):
        human_delay(action)
        element.fill(value)

    def _human_goto(self, url, action):
        human_delay(action)
        self.page.goto(url)

    def _human_press(self, target, key, action):
        human_delay(action)
        target.press(key)

    def navigate_to_verification_link(self, verification_link):
        """导航到验证链接并处理弹窗"""
        try:
            print(f"🔗 正在访问验证链接: {verification_link}")

            # 设置页面事件监听
            def handle_popup(dialog):
                try:
                    print(f"🔔 检测到弹窗: {dialog.message}")
                    if (
                        "第三方网站跳转提醒" in dialog.message
                        or "即将离开" in dialog.message
                        or "继续前往" in dialog.message
                    ):
                        print("✅ 确认跳转到验证页面")
                        human_delay("确认跳转到验证页面")
                        dialog.accept()
                    else:
                        print("❌ 取消弹窗")
                        human_delay("关闭浏览器提示框")
                        dialog.dismiss()
                except Exception as e:
                    print(f"⚠️ 处理弹窗失败: {e}")
                    try:
                        dialog.dismiss()
                    except Exception:
                        pass

            # 监听弹窗
            self.page.on("dialog", handle_popup)

            # 访问验证链接
            self._human_goto(verification_link, "打开邮箱验证链接")
            wait_with_message(5, "等待验证页面加载")

            # 检查是否成功跳转到验证页面
            current_url = self.page.url
            if "tavily.com" in current_url:
                print(f"✅ 成功跳转到Tavily页面: {current_url}")

                # 检查是否是登录页面
                if "login" in current_url.lower():
                    print("🔑 检测到Tavily登录页面，需要进行登录")
                    return "login_required"
                else:
                    print("✅ 邮箱验证可能已完成")
                    return True
            else:
                print(f"⚠️ 当前页面: {current_url}")
                print("可能需要手动处理验证")
                return False

        except Exception as e:
            print(f"❌ 访问验证链接失败: {e}")
            return False

    def login_to_tavily(self, email, password):
        """登录到Tavily账户（支持分步登录）"""
        try:
            print(f"🔑 开始登录Tavily账户: {email}")

            # 等待登录页面加载
            wait_with_message(3, "等待登录页面加载")

            # 步骤1: 输入邮箱
            if not self._input_email_step(email):
                return False

            # 步骤2: 点击继续按钮（如果存在）
            if not self._click_continue_if_exists():
                print("⚠️ 未找到继续按钮，可能是单页登录")

            # 步骤3: 输入密码
            if not self._input_password_step(password):
                return False

            # 步骤4: 提交登录
            if not self._submit_login():
                return False

            # 步骤5: 验证登录结果
            return self._verify_login_success()

        except Exception as e:
            print(f"❌ 登录Tavily失败: {e}")
            return False

    def _input_email_step(self, email):
        """输入邮箱步骤"""
        email_selectors = [
            'input[name="username"]',  # Tavily使用username字段
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="email"]',
            'input[placeholder*="Email"]',
            "#email",
            "#username",
            ".email-input",
        ]

        email_input = None
        for selector in email_selectors:
            try:
                email_input = self.page.wait_for_selector(selector, timeout=5000)
                if email_input:
                    print(f"✅ 找到邮箱输入框: {selector}")
                    break
            except Exception:
                continue

        if not email_input:
            print("❌ 未找到邮箱输入框")
            return False

        # 输入邮箱
        self._human_fill(email_input, email, "输入登录邮箱")
        print(f"✅ 已输入邮箱: {email}")
        wait_with_message(1, "等待输入完成")
        return True

    def _click_continue_if_exists(self):
        """点击继续按钮（如果存在）"""
        continue_selectors = [
            'button[type="submit"]:has-text("Continue")',
            'button:has-text("Continue")',
            'button:has-text("Next")',
            'button[name="action"][type="submit"]',
            'button[type="submit"]',
        ]

        for selector in continue_selectors:
            try:
                continue_button = self.page.wait_for_selector(selector, timeout=3000)
                if continue_button:
                    print(f"✅ 找到继续按钮: {selector}")
                    self._human_click(continue_button, "点击登录继续按钮")
                    wait_with_message(3, "等待页面跳转")
                    return True
            except Exception:
                continue

        return False

    def _input_password_step(self, password):
        """输入密码步骤"""
        # 等待密码页面加载
        wait_with_message(2, "等待密码页面加载")

        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="password"]',
            'input[placeholder*="Password"]',
            "#password",
            ".password-input",
        ]

        password_input = None
        for selector in password_selectors:
            try:
                password_input = self.page.wait_for_selector(selector, timeout=5000)
                if password_input:
                    print(f"✅ 找到密码输入框: {selector}")
                    break
            except Exception:
                continue

        if not password_input:
            print("❌ 未找到密码输入框")
            return False

        # 输入密码
        self._human_fill(password_input, password, "输入登录密码")
        print("✅ 已输入密码")
        wait_with_message(1, "等待输入完成")
        return True

    def _submit_login(self):
        """提交登录"""
        login_selectors = [
            'button[type="submit"]:has-text("Continue")',
            'button[type="submit"]:has-text("Log in")',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button[name="action"][type="submit"]',
            'button[type="submit"]',
            'input[type="submit"]',
            ".login-btn",
            ".submit-btn",
        ]

        login_button = None
        for selector in login_selectors:
            try:
                login_button = self.page.wait_for_selector(selector, timeout=5000)
                if login_button:
                    print(f"✅ 找到登录按钮: {selector}")
                    break
            except Exception:
                continue

        if login_button:
            print("🔑 正在点击登录按钮...")
            self._human_click(login_button, "提交 Tavily 登录")
        else:
            print("⚠️ 未找到登录按钮，尝试按Enter键...")
            # 尝试在密码框按Enter
            password_inputs = self.page.query_selector_all('input[type="password"]')
            if password_inputs:
                self._human_press(password_inputs[0], "Enter", "按 Enter 提交登录")
            else:
                return False

        # 等待登录完成
        wait_with_message(5, "等待登录完成")
        return True

    def _verify_login_success(self):
        """验证登录是否成功"""
        current_url = self.page.url
        print(f"📋 登录后页面: {current_url}")

        # 检查是否成功登录
        if any(
            keyword in current_url.lower()
            for keyword in ["dashboard", "home", "app", "console"]
        ):
            print("✅ 登录成功!")
            return True
        elif "login" in current_url.lower():
            print("❌ 登录失败，仍在登录页面")
            return False
        else:
            print("✅ 登录可能成功，已跳转到新页面")
            return True

    def get_api_key_from_tavily(self):
        """点击 Tavily 的复制按钮，并从剪贴板获取 API key。"""
        try:
            print("🔑 开始复制 API key...")

            # 等待页面完全加载
            wait_with_message(2, "等待页面加载")

            current_url = self.page.url
            print(f"📋 当前页面: {current_url}")

            # 如果不在home页面，先导航到home页面
            if "app.tavily.com/home" not in current_url:
                home_url = "https://app.tavily.com/home"
                print(f"🏠 导航到home页面: {home_url}")
                self._human_goto(home_url, "打开 Tavily 首页")
                wait_with_message(2, "等待home页面加载")

            self.close_verification_success_popup()
            self.close_cookie_consent_if_present()

            api_key = self._click_copy_key_button()
            if api_key:
                return api_key

            # 某些页面只有显示完整 key 后，复制按钮才会可用。
            print("👁️ 首次复制失败，尝试显示完整 API key 后重试...")
            if self.reveal_api_key():
                api_key = self._click_copy_key_button()
                if api_key:
                    return api_key

            # 剪贴板权限受限时，保留页面读取作为最后兜底。
            api_key = self.find_api_key_on_page()
            if api_key and "*" not in api_key:
                print("⚠️ 剪贴板不可读，已从页面提取 API key")
                return api_key

            print("❌ 未能通过复制按钮获取 API key")
            return None

        except Exception as e:
            print(f"❌ 获取API key失败: {e}")
            return None

    def _click_copy_key_button(self):
        """按稳定属性和图标特征查找复制按钮，点击后读取 key。"""
        selectors = [
            'button:has-text("Copy key")',
            'button:has-text("Copy API key")',
            'button:has-text("复制 key")',
            'button[aria-label*="copy" i]',
            'button[title*="copy" i]',
            'button[data-testid*="copy" i]',
            "button.hover\\:text-\\[\\#66dd44\\]",
            'button:has(svg rect[x="9"][y="9"])',
            'button:has(svg path[d*="M5 15H4"])',
            "button.chakra-button.css-1nit5dt",
        ]

        print("🔍 查找复制 key 按钮...")
        for selector in selectors:
            try:
                buttons = self.page.query_selector_all(selector)
            except Exception:
                continue

            for button in buttons:
                try:
                    if not button.is_visible():
                        continue
                    human_delay("滚动到复制 key 按钮")
                    button.scroll_into_view_if_needed()
                    self._human_click(button, "复制 Tavily API key")
                    wait_with_message(1, "等待复制完成")

                    api_key = self._read_clipboard_api_key()
                    if api_key:
                        print(f"✅ 已通过复制按钮获取 API key: {mask_api_key(api_key)}")
                        return api_key

                    # 点击已经完成，仅在浏览器禁止读取剪贴板时读取按钮邻近文本。
                    parent_text = button.evaluate(
                        "el => el.parentElement ? el.parentElement.innerText : ''"
                    )
                    api_key = extract_api_key(parent_text)
                    if api_key:
                        print(
                            f"✅ 复制完成，并从按钮附近确认 API key: {mask_api_key(api_key)}"
                        )
                        return api_key
                except Exception as exc:
                    print(f"⚠️ 处理复制按钮失败: {exc}")

        return None

    def close_verification_success_popup(self):
        """关闭邮箱验证完成后出现的 Tavily 订阅弹窗。"""
        print('🔍 检查 "Stay updated about Tavily!" 弹窗...')

        # 录制脚本中的 id 后缀（如 :ri:）会动态变化，只匹配稳定前缀。
        primary_selector = '[id^="chakra-modal--body-"] button:has-text("Continue")'
        try:
            button = self.page.wait_for_selector(
                primary_selector,
                state="visible",
                timeout=8000,
            )
            if button:
                self._human_click(button, "点击 Continue 关闭 Tavily 弹窗")
                wait_with_message(1, "等待弹窗关闭")
                print("✅ 已通过 Continue 关闭 Tavily 验证成功弹窗")
                return True
        except Exception:
            pass

        fallback_selectors = [
            '[role="dialog"]:has-text("Stay updated about Tavily!") '
            'button:has-text("Continue")',
            '[id^="chakra-modal--body-"] button',
        ]
        for selector in fallback_selectors:
            try:
                buttons = self.page.query_selector_all(selector)
            except Exception:
                continue

            for button in buttons:
                try:
                    if not button.is_visible():
                        continue
                    self._human_click(button, "点击 Continue 关闭 Tavily 弹窗")
                    wait_with_message(1, "等待弹窗关闭")
                    print("✅ 已关闭 Tavily 验证成功弹窗")
                    return True
                except Exception as exc:
                    print(f"⚠️ 关闭验证成功弹窗失败: {exc}")

        print("ℹ️ 当前没有需要关闭的验证成功弹窗")
        return False

    def close_cookie_consent_if_present(self):
        """可选关闭右下角的 OneTrust Cookie 弹窗。"""
        print("🍪 检查 Cookie 弹窗...")
        primary_selector = "#onetrust-accept-btn-handler"
        try:
            button = self.page.wait_for_selector(
                primary_selector,
                state="visible",
                timeout=3000,
            )
            if button:
                self._human_click(button, "接受 Cookie 并关闭提示")
                wait_with_message(1, "等待 Cookie 弹窗关闭")
                print("✅ 已关闭 Cookie 弹窗")
                return True
        except Exception:
            pass

        fallback_selector = '#onetrust-banner-sdk button:has-text("Accept All Cookies")'
        try:
            buttons = self.page.query_selector_all(fallback_selector)
            for button in buttons:
                if not button.is_visible():
                    continue
                self._human_click(button, "接受 Cookie 并关闭提示")
                wait_with_message(1, "等待 Cookie 弹窗关闭")
                print("✅ 已关闭 Cookie 弹窗")
                return True
        except Exception as exc:
            print(f"⚠️ 关闭 Cookie 弹窗失败: {exc}")

        print("ℹ️ 当前没有 Cookie 弹窗")
        return False

    def _read_clipboard_api_key(self):
        """优先读取浏览器剪贴板，失败后读取操作系统剪贴板。"""
        try:
            self.page.bring_to_front()
            try:
                self.page.context.grant_permissions(
                    ["clipboard-read", "clipboard-write"],
                    origin="https://app.tavily.com",
                )
            except Exception:
                pass
            clipboard_text = self.page.evaluate(
                "async () => await navigator.clipboard.readText()"
            )
            api_key = extract_api_key(clipboard_text)
            if api_key:
                return api_key
        except Exception:
            pass

        commands = []
        if shutil.which("pbpaste"):
            commands.append(["pbpaste"])
        if shutil.which("wl-paste"):
            commands.append(["wl-paste", "--no-newline"])
        if shutil.which("xclip"):
            commands.append(["xclip", "-selection", "clipboard", "-o"])
        if shutil.which("powershell"):
            commands.append(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])

        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                api_key = extract_api_key(result.stdout)
                if api_key:
                    return api_key
            except Exception:
                continue

        return None

    def reveal_api_key(self):
        """Reveal the key using selectors tied to the key control."""
        selectors = [
            'button[aria-label*="show" i]',
            'button[aria-label*="reveal" i]',
            'button[data-testid*="reveal" i]',
            'button:has(svg path[d*="M12 6.5"])',
            "button.chakra-button.css-1a1nl3a",
        ]

        print("👁️ 尝试显示完整 API key...")
        for selector in selectors:
            try:
                buttons = self.page.query_selector_all(selector)
            except Exception:
                continue

            for button in buttons:
                try:
                    if not button.is_visible():
                        continue
                    human_delay("滚动到显示 API key 按钮")
                    button.scroll_into_view_if_needed()
                    self._human_click(button, "显示完整 API key")
                    wait_with_message(1, "等待 API key 显示")
                    return True
                except Exception as exc:
                    print(f"⚠️ 显示 API key 失败: {exc}")

        return False

    def find_api_key_on_page(self):
        """在当前页面查找API key"""
        try:
            # 查找包含API key的元素
            api_key_selectors = [
                'input[value*="tvly-"]',
                'code:has-text("tvly-")',
                'span:has-text("tvly-")',
                'div:has-text("tvly-")',
                ".api-key",
                '[data-testid*="api"]',
                "input[readonly]",
                ".token",
                ".key-value",
            ]

            for selector in api_key_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        # 尝试从value属性获取
                        value = element.get_attribute("value") or ""
                        api_key = extract_api_key(value)
                        if api_key:
                            print(
                                f"✅ 从 input value 中找到 API key: {mask_api_key(api_key)}"
                            )
                            return api_key

                        # 尝试从文本内容获取
                        api_key = extract_api_key(element.inner_text())
                        if api_key:
                            print(f"✅ 从文本中找到 API key: {mask_api_key(api_key)}")
                            return api_key
                except Exception:
                    continue

            # 如果没找到，尝试从页面所有文本中搜索
            api_key = extract_api_key(self.page.inner_text("body"))
            if api_key:
                print(f"✅ 从页面文本中找到 API key: {mask_api_key(api_key)}")
                return api_key

            return None

        except Exception as e:
            print(f"❌ 在页面中查找API key失败: {e}")
            return None
