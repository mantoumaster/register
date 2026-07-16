#!/usr/bin/env python3
"""Tavily API key automation entry point."""

import time

from config import API_KEYS_FILE, BIT_BROWSER_NAME, EMAIL_PROVIDER
from tavily_automation import TavilyAutomation
from utils import mask_api_key


def get_run_config():
    """Read the only two interactive settings required for a run."""
    print("🚀 Tavily API Key 自动化")
    print("=" * 60)
    print(f"📧 邮箱 provider: {EMAIL_PROVIDER}")
    print(f"♻️ 比特浏览器窗口: {BIT_BROWSER_NAME}")

    print("\n🖥️ 浏览器模式:")
    print("1. 前台模式（可观察过程）")
    print("2. 后台模式")
    while True:
        browser_choice = input("选择浏览器模式 (1/2): ").strip()
        if browser_choice in {"1", "2"}:
            headless = browser_choice == "2"
            break
        print("❌ 请输入 1 或 2")

    while True:
        try:
            count = int(input("\n📊 注册账户数量 (1-10): "))
            if 1 <= count <= 10:
                return headless, count
            print("❌ 请输入 1-10 之间的数字")
        except ValueError:
            print("❌ 请输入有效数字")


def run_automation():
    """Run one batch, print its result, and exit."""
    headless, count = get_run_config()
    batch_started = time.monotonic()
    results = []

    print("\n🤖 开始自动化执行")
    print(f"  浏览器: {'后台' if headless else '前台'}模式")
    print(f"  任务数: {count}")

    for index in range(1, count + 1):
        print(f"\n{'=' * 60}")
        print(f"🔄 执行第 {index}/{count} 个账户")
        print(f"{'=' * 60}")

        account_started = time.monotonic()
        automation = None
        api_key = None
        error = None
        email = None

        try:
            automation = TavilyAutomation()
            automation.start_browser(headless=headless)
            api_key = automation.run_complete_automation()
            email = automation.email
            if not api_key:
                error = "未获取到 API key"
        except Exception as exc:
            error = str(exc)
            print(f"❌ 第 {index} 个账户执行出错: {exc}")
        finally:
            if automation:
                try:
                    automation.close_browser()
                except Exception as close_error:
                    cleanup_error = f"资源清理失败: {close_error}"
                    print(f"⚠️ {cleanup_error}")
                    error = f"{error}; {cleanup_error}" if error else cleanup_error

        elapsed = time.monotonic() - account_started
        success = bool(api_key) and error is None
        results.append(
            {
                "index": index,
                "success": success,
                "email": email,
                "elapsed": elapsed,
                "error": error,
            }
        )

        if success:
            print(f"✅ 第 {index} 个账户成功，耗时 {elapsed:.1f} 秒")
            print(f"📧 邮箱: {email}")
            print(f"🔑 API Key: {mask_api_key(api_key)} (已保存到文件)")
        else:
            print(f"❌ 第 {index} 个账户失败，耗时 {elapsed:.1f} 秒")
            print(f"   原因: {error or '未知错误'}")

    total_elapsed = time.monotonic() - batch_started
    success_count = sum(1 for result in results if result["success"])
    failure_count = count - success_count

    print(f"\n{'=' * 60}")
    print("📋 本轮执行结果")
    for result in results:
        marker = "✅" if result["success"] else "❌"
        detail = result["email"] or result["error"] or "未知结果"
        print(f"{marker} #{result['index']} {detail} ({result['elapsed']:.1f} 秒)")
    print("-" * 60)
    print(f"任务总数: {count}")
    print(f"成功: {success_count}")
    print(f"失败: {failure_count}")
    print(f"成功率: {success_count / count * 100:.1f}%")
    print(f"总耗时: {total_elapsed:.1f} 秒")
    print(f"API Key 文件: {API_KEYS_FILE}")
    print("任务执行完毕，程序结束。")
    print("=" * 60)


def main():
    run_automation()


if __name__ == "__main__":
    main()
