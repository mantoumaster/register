import json
import time

from get_token import get_access_token
from utils import random_email, generate_strong_password
from config import BIT_BROWSER_NAME, CONFIG_PATH, RESULTS_DIR
from controllers.bitbrowser_controller import BitBrowserController


def process_single_flow(controller):
    page = None

    try:
        page = controller.get_thread_page()

        email = random_email()
        password = generate_strong_password()

        # 调用 controller 特定的注册方法
        result = controller.outlook_register(page, email, password)

        if result and not controller.enable_oauth2:
            return True
        elif not result:
            return False

        token_result = get_access_token(page, email)
        if token_result[0]:
            refresh_token, access_token, expire_at = token_result
            token_file = RESULTS_DIR / "outlook_token.txt"
            with token_file.open("a", encoding="utf-8") as f2:
                f2.write(
                    f"{email}{controller.email_suffix}---{password}---"
                    f"{refresh_token}---{access_token}---{expire_at}\n"
                )
            print(f"[Success: TokenAuth] - {email}{controller.email_suffix}")
            return True
        else:
            return False

    except Exception as e:
        print(e)
        return False

    finally:
        controller.clean_up(page, "done_browser")


def run_flows(controller, max_tasks=100):
    succeeded_tasks = 0
    failed_tasks = 0

    for task_number in range(1, max_tasks + 1):
        print(f"\n[Task] - 开始 {task_number}/{max_tasks}")
        if process_single_flow(controller):
            succeeded_tasks += 1
        else:
            failed_tasks += 1
        if task_number < max_tasks:
            time.sleep(0.5)

    print(f"\n[Result] - 共: {max_tasks}, 成功 {succeeded_tasks}, 失败 {failed_tasks}")


if __name__ == "__main__":
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    max_tasks = data["max_tasks"]
    concurrent_flows = data["concurrent_flows"]
    if concurrent_flows != 1:
        raise ValueError(
            "单个比特浏览器窗口只支持串行执行，请将 concurrent_flows 设为 1"
        )

    print(f"[Browser] - Outlook 专用比特浏览器窗口: {BIT_BROWSER_NAME}")
    selected_controller = BitBrowserController()

    try:
        run_flows(selected_controller, max_tasks)
    finally:
        selected_controller.clean_up(type="all_browser")
