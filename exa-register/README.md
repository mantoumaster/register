# exa-register

Exa 自动注册脚本，走邮箱验证码，登录 dashboard 抓取完整 API Key 并写入 `exa_apikeys.txt`（一行一个 key）。

## 环境要求
- Python 3.10+
- Chrome/Chromium 可用（Camoufox/patchright 依赖）
- `pip install -r requirements.txt`

## 安装
```bash
cd exa-register
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 配置（.env 或环境变量）
- 邮箱提供方：`EMAIL_PROVIDER` = `auto` | `cloudflare` | `duckmail` | `gptmail` | `tempmail`
- Cloudflare 自建邮件 API：`EMAIL_API_URL`, `EMAIL_API_TOKEN`, `EMAIL_DOMAIN` / `EMAIL_DOMAINS`
- DuckMail：`DUCKMAIL_API_URL` (默认 https://api.duckmail.sbs), `DUCKMAIL_API_KEY`, `DUCKMAIL_DOMAIN` / `DUCKMAIL_DOMAINS`
- GPTMail：无需额外配置
- TempMail.lol：无需额外配置
- `auto`：优先 TempMail.lol，失败自动回退 GPTMail
- 运行参数：
  - `DEFAULT_COUNT` (默认 5)、`DEFAULT_CONCURRENCY` (默认 2)、`DEFAULT_DELAY` (默认 10)
  - `REGISTER_HEADLESS` (默认 true) — 设为 false 可前台可视化
  - `EMAIL_CODE_TIMEOUT` (默认 90s)，`API_KEY_TIMEOUT` (默认 20s)

## 使用
直接跑主入口，自动生成邮箱与密码并注册：
```bash
cd exa-register
source venv/bin/activate
python3 exa_core.py
```

## 输出
- 成功的 API Key 追加写入 `exa_apikeys.txt`，每行一个 key。
- 控制台会打印邮箱、标记密码（EMAIL_OTP_ONLY）和 key 供核对。

## 工作流摘要
1) 创建一次性邮箱（按 `EMAIL_PROVIDER`）
2) 打开 Exa 登录页，填邮箱 -> 收验证码 -> 登录
3) 进入 dashboard，优先调用 `/api/get-api-keys`，兜底页面提取
4) 调用 Exa API 校验 key 可用后写入 `exa_apikeys.txt`

## 常见问题
- 一直拿不到验证码：检查邮箱 API 配置、域名是否可用，或加长 `EMAIL_CODE_TIMEOUT`
- 浏览器前台闪退：把 `REGISTER_HEADLESS=false` 并确保本机有 Chrome
- 没写入 key：看日志是否校验失败，或 dashboard 没渲染完整 key
