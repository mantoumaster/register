# Tavily API Key 自动化获取工具

使用比特浏览器管理浏览器指纹环境，通过 Playwright CDP 接管窗口，并使用可配置的临时邮箱 provider 分配注册邮箱、轮询验证邮件。

## 环境要求

- Python 3.10-3.12
- [uv](https://docs.astral.sh/uv/)
- 已安装、登录并正在运行的比特浏览器
- 比特浏览器中已开启 Local API
- 使用 LuckMail 时需要可用的 API Key 和接码项目；使用 outlook.tw 时无需邮箱凭据

## 安装

```bash
cd tavily-register
uv sync
```

## 配置

复制配置模板并填写真实值：

```bash
cp .env.example .env
```

必须确认：

- `BIT_BROWSER_API_URL`（必须与比特浏览器“系统设置”显示的本地接口 URL 完全一致，端口可能不同）
- `BIT_BROWSER_NAME`：固定复用的窗口名称，默认 `tavily-register`
- `EMAIL_PROVIDER`：`luckmail` 或 `outlook_tw`

`EMAIL_PROVIDER=outlook_tw` 使用 outlook.tw 的匿名 HTTP API，无需 API key。默认生成 8 位用户名的 `@outlook.tw` 邮箱，可通过 `OUTLOOK_TW_USERNAME_LENGTH`、`OUTLOOK_TW_DOMAIN_INDEX` 和 `OUTLOOK_TW_POLL_INTERVAL` 调整。

`EMAIL_PROVIDER=luckmail` 时必须填写 `LUCKMAIL_API_KEY`。LuckMail 默认使用 `https://mails.luckyous.com`。由于平台没有 Tavily 项目类型，默认使用 `grok` 项目类型，并采用 `ms_graph` / `outlook.com`。程序会自动加载项目目录下的 `.env`，已在 shell 中设置的同名环境变量优先级更高。其它可选配置及说明见 `.env.example`。

浏览器导航、点击、输入和按键前默认随机等待 `0.8-2.4` 秒，以降低固定节奏。可通过 `HUMAN_DELAY_MIN` 和 `HUMAN_DELAY_MAX` 调整；两者都设为 `0` 可关闭。

每个账户会独立生成一个 14 位随机密码，保证同时包含大写字母、小写字母、数字和特殊字符。密码只在本轮注册及验证后的登录流程中使用，不会写入日志。

程序只保留一个比特浏览器窗口。`BIT_BROWSER_ID` 为空时，会按 `BIT_BROWSER_NAME` 精确查找；没有时创建，存在时复用，发现多个同名窗口则停止并报错。每轮启动前重新生成指纹；任务结束后关闭窗口，等待至少 5 秒，再清除本地及同步 Cookie 和全部窗口缓存。窗口本身不会删除，下一轮继续使用相同 ID。


## 运行

```bash
uv run python main.py
```

程序直接进入完整自动化流程，只需选择前台/后台浏览器模式和本轮注册数量。任务结束后会输出每个账户的执行结果、成功数、失败数、成功率和总耗时，然后直接退出。

## 工作流程

1. 按固定名称查找或首次创建唯一的比特浏览器窗口。
2. 关闭浏览器数据同步，重新生成本轮指纹并调用 `/browser/open`。
3. Playwright 使用 `connect_over_cdp()` 接管比特浏览器窗口。
4. 配置的临时邮箱 provider 生成或分配邮箱并注册 Tavily。
5. provider 轮询验证邮件，从邮件 HTML 中提取 Tavily 验证链接。
6. 在同一个比特浏览器页面中完成验证、登录和 API Key 获取。
7. 保存 key 后关闭窗口，清除 Cookie 和缓存，但保留窗口 ID 供下一轮复用。

## 项目结构

```text
tavily-register/
├── bitbrowser_client.py              # 比特浏览器 Local API 封装
├── mail_provider.py                   # 临时邮箱 provider 工厂
├── luckmail_provider.py               # LuckMail 订单和验证链接封装
├── outlook_tw_provider.py             # outlook.tw 匿名邮箱 API 封装
├── LuckMailSdk-Python/                # LuckMail SDK
├── tavily_automation.py               # 注册、验证、登录和 Key 获取流程
├── email_checker.py                   # Tavily 验证后登录和 API Key 页面操作
├── main.py                            # 命令行入口
├── config.py                          # 环境变量和非敏感配置
├── utils.py                           # 验证链接、Key 提取和等待工具
├── tests/                             # 集成边界与流程单元测试
├── pyproject.toml                     # uv 项目和依赖配置
└── uv.lock                            # 锁定依赖版本
```

## 输出

最后一步会点击页面上的复制 key 按钮，并将成功结果追加保存到 `api_keys.txt`：

```text
tvly-xxxxxxxxxxxxxxxx
tvly-yyyyyyyyyyyyyyyy
```

## 常见问题

### 无法连接比特浏览器

- 确认比特浏览器客户端已启动并登录。
- 在比特浏览器系统设置中确认 Local API 地址。
- 确认 `BIT_BROWSER_API_URL` 与客户端显示的地址一致。

### LuckMail 创建订单失败

- 检查 `LUCKMAIL_BASE_URL` 和 `LUCKMAIL_API_KEY`。
- 检查账户余额。
- 使用项目列表接口确认 `LUCKMAIL_PROJECT_CODE`。

### outlook.tw 邮箱生成或收信失败

- 确认 `OUTLOOK_TW_BASE_URL=https://outlook.tw`。
- 访问 `https://outlook.tw/api/domains`，确认服务可用。
- 适当增加 `MAX_EMAIL_WAIT_TIME`，避免邮件投递延迟导致超时。

### 收到邮件但没有验证链接

邮件 provider 需要返回完整邮件正文。程序会优先匹配 Tavily 的 `auth.tavily.com/u/email-verification` 链接。

## 资源推荐
- [YesCaptcha](https://cutt.ly/Mywt39r0)（自动验证码识别工具）
- [订阅合租拼车](https://cutt.ly/5ywt8vb4)
- [海外账号、电话卡](https://cutt.ly/dywt86NC)
- [满血CC、GPT中转站](https://cutt.ly/JywJG3G5)(返90%佣金)
- [Telegram 搜索机器人](https://cutt.ly/2yeh3GOE)

## 免责声明

本工具仅用于学习和研究。使用时请遵守 Tavily、比特浏览器、LuckMail、outlook.tw 及相关服务的条款。

## 许可证

MIT License
