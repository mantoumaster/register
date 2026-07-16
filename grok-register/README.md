# Grok (x.ai) 注册机使用教程

## 环境准备

1. 安装依赖并创建环境（Python 3.10+）：

```bash
cd grok-register
uv sync
```

2. 准备输出目录：

```bash
mkdir -p keys
```

3. 复制配置模板：

```bash
cp .env.example .env
```

4. 按需编辑 `.env`，然后直接运行脚本即可；脚本启动时会自动加载当前目录下的 `.env`。

基础必填项：

```env
YESCAPTCHA_KEY="你的_yescaptcha_key"
```

如果要使用 `luckmail`，一般只需要补这些：

```env
EMAIL_PROVIDER="luckmail"
LUCKMAIL_API_KEY="你的_luckmail_api_key"
```

`LUCKMAIL_BASE_URL` 已内置为 `https://mails.luckyous.com`，通常不用额外设置；只有你使用别的 LuckMail 站点时，才需要自行覆盖。

其余可选项也都可以放进 `.env` 里自定义，比如：

```env
THREADS="1"
LUCKMAIL_API_SECRET=""
LUCKMAIL_USE_HMAC="false"
LUCKMAIL_PROJECT_CODE="grok"
LUCKMAIL_EMAIL_TYPE="ms_graph"
LUCKMAIL_DOMAIN="outlook.com"
```

5. 如需代理，可自行使用系统环境变量，或按需修改代码中的代理配置。

## 运行示例

使用 `.env` 里的默认配置直接运行：

```bash
cd grok-register
uv run python grok.py
```

显式使用 `luckmail`：

```bash
cd grok-register
uv run python grok.py --email-provider luckmail
```

也可以直接指定线程数：

```bash
uv run python grok.py --email-provider luckmail --threads 8
```

## 参数说明

- `--email-provider`：邮箱提供商，可选 `gptmail` / `luckmail`。默认读取 `.env` 中的 `EMAIL_PROVIDER`，未设置时为 `gptmail`。
- `--threads`：并发线程数。CLI 参数优先；未传时会读取 `.env` 中的 `THREADS`；再没有就交互输入，默认 1。
- `YESCAPTCHA_KEY`：YesCaptcha 的 API Key，必填。
- `LUCKMAIL_BASE_URL`：LuckMail 平台地址，默认内置为 `https://mails.luckyous.com`；只有使用别的 LuckMail 站点时才需要设置。
- `LUCKMAIL_API_KEY`：LuckMail API Key，使用 `luckmail` 时必填。
- `LUCKMAIL_API_SECRET` / `LUCKMAIL_USE_HMAC`：LuckMail 可选 HMAC 鉴权配置。
- `LUCKMAIL_PROJECT_CODE` / `LUCKMAIL_EMAIL_TYPE` / `LUCKMAIL_DOMAIN`：LuckMail 购买邮箱参数，默认分别为 `grok` / `ms_graph` / `outlook.com`。

## 输出位置

成功后输出：

- `keys/grok.txt`：SSO token 列表
- `keys/accounts.txt`：`email:password:SSO`

## 注意

- 必须有 YesCaptcha 余额并配置 `YESCAPTCHA_KEY`。
- 若初始化提示“未找到 Action ID”，请更换代理或重试。
- `luckmail` 走的是**购买邮箱 + token 轮询邮件**的模式，不是一次性接码订单。
- 使用 `luckmail` 前需要先注册 LuckMail 网站并获取 API Key。
- LuckMail 的邮箱购买会产生消费，不是免费邮箱。

## 资源推荐
- [YesCaptcha](https://cutt.ly/Mywt39r0)（自动验证码识别工具）
- [订阅合租拼车](https://cutt.ly/5ywt8vb4)
- [海外账号、电话卡](https://cutt.ly/dywt86NC)
- [满血CC、GPT中转站](https://cutt.ly/JywJG3G5)(返90%佣金)
- [Telegram 搜索机器人](https://cutt.ly/2yeh3GOE)