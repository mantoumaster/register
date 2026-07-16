#!/usr/bin/env python3
"""Tavily browser registration and API key automation."""

import time

from playwright.sync_api import sync_playwright

from bitbrowser_client import BitBrowserClient
from config import (
    BIT_BROWSER_API_URL,
    BIT_BROWSER_CLOSE_WAIT,
    BIT_BROWSER_ID,
    BIT_BROWSER_NAME,
    BROWSER_TIMEOUT,
    HEADLESS,
    TAVILY_HOME_URL,
)
from mail_provider import create_mail_provider
from utils import generate_password, human_delay, mask_api_key, save_api_key


class TavilyAutomation:
    def __init__(self, mail_provider=None):
        self.playwright = None
        self.bitbrowser = None
        self.browser_id = None
        self.browser_started = False
        self.browser = None
        self.context = None
        self.page = None
        self.email = None
        self.password = generate_password()
        self.mail_provider = mail_provider or create_mail_provider()
        self.owns_mail_provider = mail_provider is None

        # Registration and login selectors, ordered from stable to fallback.
        self.selectors = {
            "signup_button": {
                "primary": [
                    'a[href*="/u/signup/identifier"]',  # Auth0动态注册链接
                    'a:has-text("Sign up")',  # 最稳定：基于文本内容
                    'a[href*="signup"]',  # 稳定：基于URL特征
                ],
                "fallback": [
                    'p:has-text("Don\'t have an account?") a',  # 基于父元素上下文
                    'a[class*="c7c2d7b15"]',  # 基于部分class（如果稳定）
                ],
            },
            "email_input": {
                "primary": [
                    "input#email",  # 最稳定：基于ID
                    'input[name="email"]',  # 最稳定：基于name
                    'input[type="text"][autocomplete="email"]',  # 稳定：组合属性
                ],
                "fallback": [
                    'form._form-signup-id input[type="text"]',  # 基于表单上下文
                    'label:has-text("Email address") + div input',  # 基于标签关联
                ],
            },
            "continue_button": {
                "primary": [
                    'button[name="action"][type="submit"]',  # 最稳定：精确属性组合
                    'button[type="submit"]:has-text("Continue")',  # 稳定：类型+文本
                ],
                "fallback": [
                    'form._form-signup-id button[type="submit"]',  # 基于表单上下文
                    "button._button-signup-id",  # 基于特定class
                ],
            },
            "password_input": {
                "primary": [
                    "input#password",  # 最稳定：基于ID
                    'input[name="password"]',  # 最稳定：基于name
                    'input[type="password"][autocomplete="new-password"]',  # 稳定：组合属性
                ],
                "fallback": [
                    'input[type="password"]',  # 基于类型
                    'label:has-text("Password") + div input',  # 基于标签关联
                ],
            },
            "submit_button": {
                "primary": [
                    'button[name="action"][type="submit"]',  # 复用continue按钮逻辑
                    'button[type="submit"]:has-text("Continue")',
                ],
                "fallback": [
                    'button[type="submit"]',
                    'input[type="submit"]',
                ],
            },
        }

    def log(self, message, level="INFO"):
        """Write a timestamped progress message."""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def start_browser(self, headless=None):
        """通过比特浏览器 Local API 启动窗口并使用 CDP 接管。"""
        self.playwright = sync_playwright().start()
        headless_mode = headless if headless is not None else HEADLESS

        self.bitbrowser = BitBrowserClient(BIT_BROWSER_API_URL)
        self.bitbrowser.health()
        self.browser_id = self.bitbrowser.get_or_create_browser(
            name=BIT_BROWSER_NAME,
            browser_id=BIT_BROWSER_ID,
        )
        self.bitbrowser.configure_reusable_browser(
            self.browser_id,
            name=BIT_BROWSER_NAME,
        )
        self.log(f"♻️ 复用比特浏览器窗口: {BIT_BROWSER_NAME} ({self.browser_id})")
        self.bitbrowser.randomize_fingerprint(self.browser_id)
        self.log("🎭 已为本轮重新生成浏览器指纹")

        opened = self.bitbrowser.open_browser(self.browser_id, headless=headless_mode)
        self.browser_started = True
        self.browser = self.playwright.chromium.connect_over_cdp(opened.ws)
        if not self.browser.contexts:
            raise RuntimeError("比特浏览器没有返回可用的浏览器上下文")
        self.context = self.browser.contexts[0]
        self.page = (
            self.context.pages[0] if self.context.pages else self.context.new_page()
        )
        self.page.set_default_timeout(BROWSER_TIMEOUT)

    def close_browser(self):
        """断开 Playwright，并通过 Local API 关闭比特浏览器窗口。"""
        try:
            if self.page and not self.page.is_closed():
                self.page.close()
                self.page = None
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
        except Exception as e:
            self.log(f"⚠️ 浏览器关闭时出现错误（可忽略）: {e}", "DEBUG")
        finally:
            if self.bitbrowser and self.browser_id:
                try:
                    if self.browser_started:
                        self.log("🧹 关闭窗口并清空 Cookie、缓存和本地数据...")
                        self.bitbrowser.close_and_clear_browser(
                            self.browser_id,
                            wait_seconds=BIT_BROWSER_CLOSE_WAIT,
                        )
                        self.browser_started = False
                        self.log("✅ 窗口数据已清空，窗口 ID 保留供下一轮复用")
                except Exception as e:
                    self.log(f"⚠️ 比特浏览器窗口清理失败: {e}", "DEBUG")
                finally:
                    self.bitbrowser.close()
            if self.owns_mail_provider:
                self.mail_provider.close()

    def wait_for_element(self, element_config, timeout=30000):
        """Wait for an element using primary selectors before fallbacks."""
        primary_selectors = element_config["primary"]
        fallback_selectors = element_config["fallback"]

        # 首先尝试主要选择器
        for selector in primary_selectors:
            try:
                self.log(f"🔍 尝试主要选择器: {selector}")
                element = self.page.wait_for_selector(
                    selector, timeout=timeout // len(primary_selectors)
                )
                if element:
                    self.log(f"✅ 找到元素: {selector}")
                    return element, selector
            except Exception:
                self.log(f"❌ 主要选择器失败: {selector}")
                continue

        # 如果主要选择器都失败，尝试备用选择器
        self.log("⚠️ 主要选择器都失败，尝试备用选择器...")
        for selector in fallback_selectors:
            try:
                self.log(f"🔍 尝试备用选择器: {selector}")
                element = self.page.wait_for_selector(
                    selector, timeout=timeout // len(fallback_selectors)
                )
                if element:
                    self.log(f"✅ 找到元素（备用）: {selector}")
                    return element, selector
            except Exception:
                self.log(f"❌ 备用选择器失败: {selector}")
                continue

        return None, None

    def click_element(self, element_name, retries=3):
        """Click a configured element with bounded retries."""
        element_config = self.selectors.get(element_name)
        if not element_config:
            self.log(f"❌ 未找到元素配置: {element_name}")
            return False

        for attempt in range(retries):
            self.log(f"🔄 尝试点击 {element_name} (第 {attempt + 1}/{retries} 次)")

            element, selector = self.wait_for_element(element_config)

            if element:
                try:
                    # 确保元素可见和稳定
                    element.wait_for_element_state("visible", timeout=5000)
                    element.wait_for_element_state("stable", timeout=5000)

                    # 点击元素
                    human_delay(f"点击 {element_name}")
                    element.click()
                    self.log(f"✅ 成功点击 {element_name}")

                    # 后续步骤会等待明确的目标URL或元素，不使用networkidle。
                    self.page.wait_for_timeout(500)
                    return True

                except Exception as e:
                    self.log(f"❌ 点击失败: {e}")

            # 不刷新页面，避免已成功的点击被重复提交或丢失当前表单状态。
            if attempt < retries - 1:
                self.log("🔄 等待页面稳定后重试...")
                self.page.wait_for_timeout(1000)

        self.log(f"❌ 最终未能点击 {element_name}")
        return False

    def fill_element(self, element_name, text, retries=3):
        """Fill a configured input with bounded retries."""
        element_config = self.selectors.get(element_name)
        if not element_config:
            self.log(f"❌ 未找到元素配置: {element_name}")
            return False

        for attempt in range(retries):
            self.log(f"🔄 尝试填写 {element_name} (第 {attempt + 1}/{retries} 次)")

            element, selector = self.wait_for_element(element_config)

            if element:
                try:
                    # 确保元素可见和可编辑
                    element.wait_for_element_state("visible", timeout=5000)
                    element.wait_for_element_state("editable", timeout=5000)

                    # 清空并填写
                    human_delay(f"填写 {element_name}")
                    element.fill("")  # 先清空
                    element.fill(text)

                    # 增加1秒延迟确保填写稳定
                    time.sleep(1)

                    # 验证填写结果
                    filled_value = element.input_value()
                    if filled_value == text:
                        self.log(f"✅ 成功填写 {element_name}: {text}")
                        return True
                    else:
                        self.log(
                            f"⚠️ 填写验证失败: 期望 '{text}', 实际 '{filled_value}'"
                        )

                except Exception as e:
                    self.log(f"❌ 填写失败: {e}")

            # 不刷新页面，密码页等多步骤表单刷新后可能回到上一步。
            if attempt < retries - 1:
                self.log("🔄 等待输入框稳定后重试...")
                self.page.wait_for_timeout(1000)

        self.log(f"❌ 最终未能填写 {element_name}")
        return False

    def navigate_to_signup(self):
        """导航到注册页面"""
        try:
            self.log("🌐 正在访问Tavily主页...")
            human_delay("打开 Tavily 主页")
            self.page.goto(
                TAVILY_HOME_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # 某些会话可能已经停留在Auth0注册页面。
            if "/u/signup/" in self.page.url:
                self.page.locator("input#email").wait_for(
                    state="visible", timeout=30000
                )
                self.log("✅ 当前已经位于注册页面")
                return True

            # Follow the dynamic Auth0 sign-up link.
            if self.click_element("signup_button"):
                self.page.wait_for_url(
                    "**/u/signup/**",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                self.page.locator("input#email").wait_for(
                    state="visible", timeout=30000
                )
                self.log("✅ 成功导航到注册页面")
                return True

            # Auth0注册链接包含动态state，不能使用固定URL作为后备。
            self.log("❌ 未找到可用的Sign Up链接")
            return False

        except Exception as e:
            self.log(f"❌ 导航到注册页面失败: {e}")
            return False

    def fill_registration_form(self):
        """填写注册表单"""
        try:
            # 先从配置的临时邮箱 provider 获取注册邮箱。
            self.email = self.mail_provider.acquire_email()
            self.log(f"📧 临时邮箱 provider 分配的注册邮箱: {self.email}")

            # Fill the allocated email address.
            if not self.fill_element("email_input", self.email):
                return False

            # Continue to the password step.
            if not self.click_element("continue_button"):
                return False

            self.log("✅ 注册表单填写完成")
            return True

        except Exception as e:
            self.log(f"❌ 填写注册表单失败: {e}")
            return False

    def fill_password(self):
        """填写密码"""
        try:
            self.log("🔐 正在填写密码...")

            # Reuse this account's generated password for registration and login.
            if not self.fill_element("password_input", self.password):
                return False

            # Submit the registration form.
            if not self.click_element("submit_button"):
                return False

            self.log("✅ 密码填写完成")
            return True

        except Exception as e:
            self.log(f"❌ 填写密码失败: {e}")
            return False

    def run_registration(self):
        """Run the browser registration flow."""
        try:
            self.log("🚀 开始注册流程...")

            if not self.navigate_to_signup():
                raise Exception("导航到注册页面失败")

            if not self.fill_registration_form():
                raise Exception("填写注册表单失败")

            if not self.fill_password():
                raise Exception("填写密码失败")

            self.log("🎉 注册流程完成!")
            return True

        except Exception as e:
            self.log(f"❌ 注册流程失败: {e}")
            return False

    def run_complete_automation(self):
        """Run registration, email verification, login, and key retrieval."""
        try:
            self.log("🚀 开始完整自动化流程...")

            # 步骤1: 注册账户
            self.log("📋 步骤1: 注册账户...")
            if not self.run_registration():
                raise Exception("注册流程失败")

            # 步骤2: 邮件验证和登录
            self.log("📋 步骤2: 邮件验证和登录...")
            api_key = self.handle_email_verification_and_login()

            if api_key:
                self.log("🎉 完整自动化流程成功完成!")
                self.log(f"📧 注册邮箱: {self.email}")
                self.log(f"🔑 API Key: {mask_api_key(api_key)}")

                # 保存API key
                save_api_key(api_key)
                return api_key
            else:
                raise Exception("邮件验证或API key获取失败")

        except Exception as e:
            self.log(f"❌ 完整自动化流程失败: {e}")
            try:
                self.mail_provider.cancel()
            except Exception as cancel_error:
                self.log(f"⚠️ 清理临时邮箱失败: {cancel_error}", "DEBUG")
            return None

    def handle_email_verification_and_login(self):
        """处理邮件验证和登录，返回API key"""
        try:
            # 导入邮件检查器
            from email_checker import EmailChecker

            self.log("📧 等待临时邮箱接收 Tavily 验证邮件...")
            account_helper = EmailChecker()

            # 复用当前浏览器与页面，不关闭（避免二次登录）
            account_helper.attach_to(self.page)

            verification_link = self.mail_provider.wait_for_verification_link()

            self.log(f"✅ 找到验证链接: {verification_link}")

            # 访问验证链接
            self.log("🔗 访问验证链接...")
            result = account_helper.navigate_to_verification_link(verification_link)

            if result == "login_required":
                self.log("🔑 需要登录Tavily账户...")
                if not account_helper.login_to_tavily(self.email, self.password):
                    raise Exception("Tavily登录失败")
                self.log("✅ Tavily登录成功!")

            # 获取API key
            self.log("🔑 获取API key...")
            api_key = account_helper.get_api_key_from_tavily()

            if api_key:
                self.log(f"🎉 成功获取 API key: {mask_api_key(api_key)}")
                return api_key
            raise Exception("未能获取API key")

        except Exception as e:
            self.log(f"❌ 邮件验证和登录失败: {e}")
            return None
