# outlook-register

Outlook 自动注册脚本。程序通过比特浏览器 Local API 管理一个独立的 `outlook-register` 窗口，再使用 Playwright CDP 接管窗口完成注册；也可以按需完成 OAuth2 授权并保存 token。

> 选择器经常更新，不保证长期有效，使用前建议先小批量测试。

## 目录结构

- `main.py`：批量注册入口，使用专用比特浏览器窗口串行执行任务
- `get_token.py`：OAuth2 授权与 token 获取逻辑
- `bitbrowser_client.py`：比特浏览器 Local API 封装
- `controllers/bitbrowser_controller.py`：Playwright CDP 控制器
- `config.json`：运行配置
- `.env`：比特浏览器连接与专用窗口配置
- `Results/`：注册结果输出目录

## 环境要求

- Python `>= 3.9`
- 已安装 `uv`
- 已安装、登录并正在运行的比特浏览器
- 比特浏览器中已开启 Local API
- 可用代理，建议使用本地代理池

## 安装

```bash
cd outlook-register
uv sync
```

## 配置

复制比特浏览器配置模板：

```bash
cp .env.example .env
```

确认 `BIT_BROWSER_API_URL` 与比特浏览器系统设置显示的 Local API 地址一致。默认 `BIT_BROWSER_NAME=outlook-register`，因此不会与 `tavily-register` 的窗口共用资料；如果填写 `BIT_BROWSER_ID`，则固定使用该窗口 ID。

主要业务配置在 `config.json`：

- `email_suffix`：邮箱后缀，只支持 `@outlook.com` 或 `@hotmail.com`
- `proxy`：写入比特浏览器专用窗口的代理地址，例如 `http://127.0.0.1:7897`
- `bot_protection_wait`：机器人检测等待时间，单位为秒，可填 `0`
- `max_captcha_retries`：验证码最大重试次数
- `concurrent_flows`：必须为 `1`，同一个比特浏览器窗口不并发复用
- `max_tasks`：最大注册数量

程序按窗口名精确查找；不存在时创建，存在时复用，发现多个同名窗口时停止。每个任务启动前重新生成指纹，任务完成后关闭窗口并清理 Cookie 和缓存，但保留窗口 ID 供下一次使用。

### OAuth2（可选）

默认可以关闭 OAuth2：

```json
"enable_oauth2": false
```

如果需要 OAuth2，把 `enable_oauth2` 改为 `true`，并填写：

- `client_id`：可在 Azure 应用注册中获取
- `redirect_url`：通常类似 `http://localhost:8000`
- `Scopes`：按申请的权限填写

## 运行

```bash
cd outlook-register
uv run python main.py
```

脚本会按 `config.json` 中的 `max_tasks` 串行执行注册，所有任务复用同一个 Outlook 专用窗口。

## 输出

- `Results/unlogged_email.txt`：未启用 OAuth2 时保存成功注册的邮箱和密码
- `Results/logged_email.txt`：启用 OAuth2 时保存成功注册的邮箱和密码
- `Results/outlook_token.txt`：启用 OAuth2 并授权成功后保存 refresh token、access token 和过期时间

## 常见问题

- 无法连接比特浏览器：确认客户端已启动、已登录，并检查 `.env` 中的 `BIT_BROWSER_API_URL`
- 发现多个同名窗口：删除多余的 `outlook-register` 窗口，或在 `.env` 中明确填写 `BIT_BROWSER_ID`
- 提示 IP 质量不佳或注册频率过快：更换代理 IP，单 IP 短时间不宜多次注册
- CDP 连接失败：检查比特浏览器返回的窗口是否已正常打开，并确认 Local API 可用
- 验证码失败：更换代理，或调整 `bot_protection_wait` / `max_captcha_retries`

## 注意

- IP 与成功率高度相关，同一 IP 短时间内不建议多次注册
- 单 IP 完成一轮任务后，短时间内通常不宜高频继续使用
- 使用前先用小任务量测试当前选择器和代理质量

## 资源推荐
- [YesCaptcha](https://cutt.ly/Mywt39r0)（自动验证码识别工具）
- [订阅合租拼车](https://cutt.ly/5ywt8vb4)
- [海外账号、电话卡](https://cutt.ly/dywt86NC)
- [满血CC、GPT中转站](https://cutt.ly/JywJG3G5)(返90%佣金)
- [Telegram 搜索机器人](https://cutt.ly/2yeh3GOE)