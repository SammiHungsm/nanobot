# 🚀 財報分析 Chatbot - LiteParse + Nanobot

> **第一步 ✅ 已完成：所有依賴已包含喺 Docker 容器入面，無需用戶手動安裝！**

一個基於 MCP 協議嘅高準確度財報分析 Chatbot，結合 Nanobot Agent 同 LiteParse PDF 解析工具。

---

## 🎯 一分鐘快速開始

> [!IMPORTANT]
> **Security note:** Due to `litellm` supply chain poisoning, **please check your Python environment ASAP** and refer to this [advisory](https://github.com/HKUDS/nanobot/discussions/2445) for details. We have fully removed the `litellm` dependency in [this commit](https://github.com/HKUDS/nanobot/commit/3dfdab7).

- **2026-03-21** 🔒 Replace `litellm` with native `openai` + `anthropic` SDKs. Please see [commit](https://github.com/HKUDS/nanobot/commit/3dfdab7).
- **2026-03-20** 🧙 Interactive setup wizard — pick your provider, model autocomplete, and you're good to go.
- **2026-03-19** 💬 Telegram gets more resilient under load; Feishu now renders code blocks properly.
- **2026-03-18** 📷 Telegram can now send media via URL. Cron schedules show human-readable details.
- **2026-03-17** ✨ Feishu formatting glow-up, Slack reacts when done, custom endpoints support extra headers, and image handling is more reliable.
- **2026-03-16** 🚀 Released **v0.1.4.post5** — a refinement-focused release with stronger reliability and channel support, and a more dependable day-to-day experience. Please see [release notes](https://github.com/HKUDS/nanobot/releases/tag/v0.1.4.post5) for details.
- **2026-03-15** 🧩 DingTalk rich media, smarter built-in skills, and cleaner model compatibility.
- **2026-03-14** 💬 Channel plugins, Feishu replies, and steadier MCP, QQ, and media handling.
- **2026-03-13** 🌐 Multi-provider web search, LangSmith, and broader reliability improvements.
- **2026-03-12** 🚀 VolcEngine support, Telegram reply context, `/restart`, and sturdier memory.
- **2026-03-11** 🔌 WeCom, Ollama, cleaner discovery, and safer tool behavior.
- **2026-03-10** 🧠 Token-based memory, shared retries, and cleaner gateway and Telegram behavior.
- **2026-03-09** 💬 Slack thread polish and better Feishu audio compatibility.
- **2026-03-08** 🚀 Released **v0.1.4.post4** — a reliability-packed release with safer defaults, better multi-instance support, sturdier MCP, and major channel and provider improvements. Please see [release notes](https://github.com/HKUDS/nanobot/releases/tag/v0.1.4.post4) for details.
- **2026-03-07** 🚀 Azure OpenAI provider, WhatsApp media, QQ group chats, and more Telegram/Feishu polish.
- **2026-03-06** 🪄 Lighter providers, smarter media handling, and sturdier memory and CLI compatibility.

**方法 1: 雙擊啟動**
```
雙擊 start.bat
```

**方法 2: PowerShell**
```powershell
.\start.ps1
```

**方法 3: Docker Compose**
```bash
docker-compose up -d
```

### 訪問服務

- **Web UI:** http://localhost:8080
- **API:** http://localhost:18790

### 停止服務

```bash
docker-compose down
```

**就係咁簡單！** 🎉

```bash
uv tool install nanobot-ai
```

**Install from PyPI** (stable)

```bash
pip install nanobot-ai
```

### Update to latest version

**PyPI / pip**

```bash
pip install -U nanobot-ai
nanobot --version
```

**uv**

```bash
uv tool upgrade nanobot-ai
nanobot --version
```

**Using WhatsApp?** Rebuild the local bridge after upgrading:

```bash
rm -rf ~/.nanobot/bridge
nanobot channels login whatsapp
```

## 🚀 Quick Start

> [!TIP]
> Set your API key in `~/.nanobot/config.json`.
> Get API keys: [OpenRouter](https://openrouter.ai/keys) (Global)
>
> For other LLM providers, please see the [Providers](#providers) section.
>
> For web search capability setup, please see [Web Search](#web-search).

**1. Initialize**

```bash
nanobot onboard
```

Use `nanobot onboard --wizard` if you want the interactive setup wizard.

**2. Configure** (`~/.nanobot/config.json`)

Configure these **two parts** in your config (other options have defaults).

*Set your API key* (e.g. OpenRouter, recommended for global users):
```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  }
}
```

*Set your model* (optionally pin a provider — defaults to auto-detection):
```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "provider": "openrouter"
    }
  }
}
```

**3. Chat**

```bash
nanobot agent
```

That's it! You have a working AI assistant in 2 minutes.

## 💬 Chat Apps

Connect nanobot to your favorite chat platform. Want to build your own? See the [Channel Plugin Guide](./docs/CHANNEL_PLUGIN_GUIDE.md).

| Channel | What you need |
|---------|---------------|
| **Telegram** | Bot token from @BotFather |
| **Discord** | Bot token + Message Content intent |
| **WhatsApp** | QR code scan (`nanobot channels login whatsapp`) |
| **WeChat (Weixin)** | QR code scan (`nanobot channels login weixin`) |
| **Feishu** | App ID + App Secret |
| **DingTalk** | App Key + App Secret |
| **Slack** | Bot token + App-Level token |
| **Matrix** | Homeserver URL + Access token |
| **Email** | IMAP/SMTP credentials |
| **QQ** | App ID + App Secret |
| **Wecom** | Bot ID + Bot Secret |
| **Mochat** | Claw token (auto-setup available) |

<details>
<summary><b>Telegram</b> (Recommended)</summary>

**1. Create a bot**
- Open Telegram, search `@BotFather`
- Send `/newbot`, follow prompts
- Copy the token

**2. Configure**

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

> You can find your **User ID** in Telegram settings. It is shown as `@yourUserId`.
> Copy this value **without the `@` symbol** and paste it into the config file.


**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Mochat (Claw IM)</b></summary>

Uses **Socket.IO WebSocket** by default, with HTTP polling fallback.

**1. Ask nanobot to set up Mochat for you**

Simply send this message to nanobot (replace `xxx@xxx` with your real email):

```
Read https://raw.githubusercontent.com/HKUDS/MoChat/refs/heads/main/skills/nanobot/skill.md and register on MoChat. My Email account is xxx@xxx Bind me as your owner and DM me on MoChat.
```

nanobot will automatically register, configure `~/.nanobot/config.json`, and connect to Mochat.

**2. Restart gateway**

```bash
nanobot gateway
```

That's it — nanobot handles the rest!

<br>

<details>
<summary>Manual configuration (advanced)</summary>

If you prefer to configure manually, add the following to `~/.nanobot/config.json`:

> Keep `claw_token` private. It should only be sent in `X-Claw-Token` header to your Mochat API endpoint.

```json
{
  "channels": {
    "mochat": {
      "enabled": true,
      "base_url": "https://mochat.io",
      "socket_url": "https://mochat.io",
      "socket_path": "/socket.io",
      "claw_token": "claw_xxx",
      "agent_user_id": "6982abcdef",
      "sessions": ["*"],
      "panels": ["*"],
      "reply_delay_mode": "non-mention",
      "reply_delay_ms": 120000
    }
  }
}
```



</details>

</details>

<details>
<summary><b>Discord</b></summary>

**1. Create a bot**
- Go to https://discord.com/developers/applications
- Create an application → Bot → Add Bot
- Copy the bot token

**2. Enable intents**
- In the Bot settings, enable **MESSAGE CONTENT INTENT**
- (Optional) Enable **SERVER MEMBERS INTENT** if you plan to use allow lists based on member data

**3. Get your User ID**
- Discord Settings → Advanced → enable **Developer Mode**
- Right-click your avatar → **Copy User ID**

**4. Configure**

```json
{
  "channels": {
    "discord": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"],
      "groupPolicy": "mention"
    }
  }
}
```

> `groupPolicy` controls how the bot responds in group channels:
> - `"mention"` (default) — Only respond when @mentioned
> - `"open"` — Respond to all messages
> DMs always respond when the sender is in `allowFrom`.
> - If you set group policy to open create new threads as private threads and then @ the bot into it. Otherwise the thread itself and the channel in which you spawned it will spawn a bot session.

**5. Invite the bot**
- OAuth2 → URL Generator
- Scopes: `bot`
- Bot Permissions: `Send Messages`, `Read Message History`
- Open the generated invite URL and add the bot to your server

## 📋 系統架構

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Nanobot   │ ───→ │  MCP Server      │ ───→ │  LiteParse CLI  │
│   (Agent)   │ HTTP │  (Node.js + HTTP) │ CLI  │  (PDF Parser)   │
└─────────────┘      └──────────────────┘      └──────────────────┘
                              │
                              ↓
                     ┌─────────────────┐
                     │ Data Cleaner    │
                     │ (Python)        │
                     └─────────────────┘
```

---

## 🐳 Docker 容器包含咩？

### `liteparse-mcp` 容器

**4. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>WhatsApp</b></summary>

Requires **Node.js ≥18**.

**1. Link device**

```bash
nanobot channels login whatsapp
# Scan QR with WhatsApp → Settings → Linked Devices
```

**2. Configure**

```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "allowFrom": ["+1234567890"]
    }
  }
}
```

**3. Run** (two terminals)

```bash
# Terminal 1
nanobot channels login whatsapp

# Terminal 2
nanobot gateway
```

> WhatsApp bridge updates are not applied automatically for existing installations.
> After upgrading nanobot, rebuild the local bridge with:
> `rm -rf ~/.nanobot/bridge && nanobot channels login whatsapp`

</details>

<details>
<summary><b>Feishu (飞书)</b></summary>

Uses **WebSocket** long connection — no public IP required.

**1. Create a Feishu bot**
- Visit [Feishu Open Platform](https://open.feishu.cn/app)
- Create a new app → Enable **Bot** capability
- **Permissions**: Add `im:message` (send messages) and `im:message.p2p_msg:readonly` (receive messages)
- **Events**: Add `im.message.receive_v1` (receive messages)
  - Select **Long Connection** mode (requires running nanobot first to establish connection)
- Get **App ID** and **App Secret** from "Credentials & Basic Info"
- Publish the app

**2. Configure**

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "cli_xxx",
      "appSecret": "xxx",
      "encryptKey": "",
      "verificationToken": "",
      "allowFrom": ["ou_YOUR_OPEN_ID"],
      "groupPolicy": "mention"
    }
  }
}
```

> `encryptKey` and `verificationToken` are optional for Long Connection mode.
> `allowFrom`: Add your open_id (find it in nanobot logs when you message the bot). Use `["*"]` to allow all users.
> `groupPolicy`: `"mention"` (default — respond only when @mentioned), `"open"` (respond to all group messages). Private chats always respond.

**3. Run**

```bash
nanobot gateway
```

> [!TIP]
> Feishu uses WebSocket to receive messages — no webhook or public IP needed!

</details>

<details>
<summary><b>QQ (QQ单聊)</b></summary>

Uses **botpy SDK** with WebSocket — no public IP required. Currently supports **private messages only**.

**1. Register & create bot**
- Visit [QQ Open Platform](https://q.qq.com) → Register as a developer (personal or enterprise)
- Create a new bot application
- Go to **开发设置 (Developer Settings)** → copy **AppID** and **AppSecret**

**2. Set up sandbox for testing**
- In the bot management console, find **沙箱配置 (Sandbox Config)**
- Under **在消息列表配置**, click **添加成员** and add your own QQ number
- Once added, scan the bot's QR code with mobile QQ → open the bot profile → tap "发消息" to start chatting

**3. Configure**

> - `allowFrom`: Add your openid (find it in nanobot logs when you message the bot). Use `["*"]` for public access.
> - `msgFormat`: Optional. Use `"plain"` (default) for maximum compatibility with legacy QQ clients, or `"markdown"` for richer formatting on newer clients.
> - For production: submit a review in the bot console and publish. See [QQ Bot Docs](https://bot.q.qq.com/wiki/) for the full publishing flow.

```json
{
  "channels": {
    "qq": {
      "enabled": true,
      "appId": "YOUR_APP_ID",
      "secret": "YOUR_APP_SECRET",
      "allowFrom": ["YOUR_OPENID"],
      "msgFormat": "plain"
    }
  }
}
```

**4. Run**

```bash
nanobot gateway
```

Now send a message to the bot from QQ — it should respond!

</details>

<details>
<summary><b>DingTalk (钉钉)</b></summary>

Uses **Stream Mode** — no public IP required.

**1. Create a DingTalk bot**
- Visit [DingTalk Open Platform](https://open-dev.dingtalk.com/)
- Create a new app -> Add **Robot** capability
- **Configuration**:
  - Toggle **Stream Mode** ON
- **Permissions**: Add necessary permissions for sending messages
- Get **AppKey** (Client ID) and **AppSecret** (Client Secret) from "Credentials"
- Publish the app

**2. Configure**

```json
{
  "channels": {
    "dingtalk": {
      "enabled": true,
      "clientId": "YOUR_APP_KEY",
      "clientSecret": "YOUR_APP_SECRET",
      "allowFrom": ["YOUR_STAFF_ID"]
    }
  }
}
```

> `allowFrom`: Add your staff ID. Use `["*"]` to allow all users.

**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Slack</b></summary>

Uses **Socket Mode** — no public URL required.

**1. Create a Slack app**
- Go to [Slack API](https://api.slack.com/apps) → **Create New App** → "From scratch"
- Pick a name and select your workspace

**2. Configure the app**
- **Socket Mode**: Toggle ON → Generate an **App-Level Token** with `connections:write` scope → copy it (`xapp-...`)
- **OAuth & Permissions**: Add bot scopes: `chat:write`, `reactions:write`, `app_mentions:read`
- **Event Subscriptions**: Toggle ON → Subscribe to bot events: `message.im`, `message.channels`, `app_mention` → Save Changes
- **App Home**: Scroll to **Show Tabs** → Enable **Messages Tab** → Check **"Allow users to send Slash commands and messages from the messages tab"**
- **Install App**: Click **Install to Workspace** → Authorize → copy the **Bot Token** (`xoxb-...`)

**3. Configure nanobot**

```json
{
  "channels": {
    "slack": {
      "enabled": true,
      "botToken": "xoxb-...",
      "appToken": "xapp-...",
      "allowFrom": ["YOUR_SLACK_USER_ID"],
      "groupPolicy": "mention"
    }
  }
}
```

**4. Run**

```bash
nanobot gateway
```

DM the bot directly or @mention it in a channel — it should respond!

> [!TIP]
> - `groupPolicy`: `"mention"` (default — respond only when @mentioned), `"open"` (respond to all channel messages), or `"allowlist"` (restrict to specific channels).
> - DM policy defaults to open. Set `"dm": {"enabled": false}` to disable DMs.

</details>

<details>
<summary><b>Email</b></summary>

Give nanobot its own email account. It polls **IMAP** for incoming mail and replies via **SMTP** — like a personal email assistant.

**1. Get credentials (Gmail example)**
- Create a dedicated Gmail account for your bot (e.g. `my-nanobot@gmail.com`)
- Enable 2-Step Verification → Create an [App Password](https://myaccount.google.com/apppasswords)
- Use this app password for both IMAP and SMTP

**2. Configure**

> - `consentGranted` must be `true` to allow mailbox access. This is a safety gate — set `false` to fully disable.
> - `allowFrom`: Add your email address. Use `["*"]` to accept emails from anyone.
> - `smtpUseTls` and `smtpUseSsl` default to `true` / `false` respectively, which is correct for Gmail (port 587 + STARTTLS). No need to set them explicitly.
> - Set `"autoReplyEnabled": false` if you only want to read/analyze emails without sending automatic replies.

```json
{
  "channels": {
    "email": {
      "enabled": true,
      "consentGranted": true,
      "imapHost": "imap.gmail.com",
      "imapPort": 993,
      "imapUsername": "my-nanobot@gmail.com",
      "imapPassword": "your-app-password",
      "smtpHost": "smtp.gmail.com",
      "smtpPort": 587,
      "smtpUsername": "my-nanobot@gmail.com",
      "smtpPassword": "your-app-password",
      "fromAddress": "my-nanobot@gmail.com",
      "allowFrom": ["your-real-email@gmail.com"]
    }
  }
}
```


**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>WeChat (微信 / Weixin)</b></summary>

Uses **HTTP long-poll** with QR-code login via the ilinkai personal WeChat API. No local WeChat desktop client is required.

> Weixin support is available from source checkout, but is not included in the current PyPI release yet.

**1. Install from source**

```bash
git clone https://github.com/HKUDS/nanobot.git
cd nanobot
pip install -e ".[weixin]"
```

**2. Configure**

```json
{
  "channels": {
    "weixin": {
      "enabled": true,
      "allowFrom": ["YOUR_WECHAT_USER_ID"]
    }
  }
}
```

> - `allowFrom`: Add the sender ID you see in nanobot logs for your WeChat account. Use `["*"]` to allow all users.
> - `token`: Optional. If omitted, log in interactively and nanobot will save the token for you.
> - `routeTag`: Optional. When your upstream Weixin deployment requires request routing, nanobot will send it as the `SKRouteTag` header.
> - `stateDir`: Optional. Defaults to nanobot's runtime directory for Weixin state.
> - `pollTimeout`: Optional long-poll timeout in seconds.

**3. Login**

```bash
nanobot channels login weixin
```

Use `--force` to re-authenticate and ignore any saved token:

```bash
nanobot channels login weixin --force
```

**4. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Wecom (企业微信)</b></summary>

> Here we use [wecom-aibot-sdk-python](https://github.com/chengyongru/wecom_aibot_sdk) (community Python version of the official [@wecom/aibot-node-sdk](https://www.npmjs.com/package/@wecom/aibot-node-sdk)).
>
> Uses **WebSocket** long connection — no public IP required.

**1. Install the optional dependency**

```bash
pip install nanobot-ai[wecom]
```

**2. Create a WeCom AI Bot**

Go to the WeCom admin console → Intelligent Robot → Create Robot → select **API mode** with **long connection**. Copy the Bot ID and Secret.

**3. Configure**

```json
{
  "channels": {
    "wecom": {
      "enabled": true,
      "botId": "your_bot_id",
      "secret": "your_bot_secret",
      "allowFrom": ["your_id"]
    }
  }
}
```

**4. Run**

```bash
nanobot gateway
```

</details>

### `nanobot-gateway` 容器

- Python 3.11
- Nanobot Agent 框架
- MCP Client

**所有依賴已自動安裝，無需用戶手動配置！**

---

## 💡 使用範例

### 場景：分析 SFC 年報

1. **上傳 PDF**
   將 PDF 放入 `data/pdfs/` 目錄

> [!TIP]
> - **Groq** provides free voice transcription via Whisper. If configured, Telegram voice messages will be automatically transcribed.
> - **MiniMax Coding Plan**: Exclusive discount links for the nanobot community: [Overseas](https://platform.minimax.io/subscribe/coding-plan?code=9txpdXw04g&source=link) · [Mainland China](https://platform.minimaxi.com/subscribe/token-plan?code=GILTJpMTqZ&source=link)
> - **MiniMax (Mainland China)**: If your API key is from MiniMax's mainland China platform (minimaxi.com), set `"apiBase": "https://api.minimaxi.com/v1"` in your minimax provider config.
> - **VolcEngine / BytePlus Coding Plan**: Use dedicated providers `volcengineCodingPlan` or `byteplusCodingPlan` instead of the pay-per-use `volcengine` / `byteplus` providers.
> - **Zhipu Coding Plan**: If you're on Zhipu's coding plan, set `"apiBase": "https://open.bigmodel.cn/api/coding/paas/v4"` in your zhipu provider config.
> - **Alibaba Cloud BaiLian**: If you're using Alibaba Cloud BaiLian's OpenAI-compatible endpoint, set `"apiBase": "https://dashscope.aliyuncs.com/compatible-mode/v1"` in your dashscope provider config.
> - **Step Fun (Mainland China)**: If your API key is from Step Fun's mainland China platform (stepfun.com), set `"apiBase": "https://api.stepfun.com/v1"` in your stepfun provider config.
> - **Step Fun Step Plan**: Exclusive discount links for the nanobot community: [Overseas](https://platform.stepfun.ai/step-plan) · [Mainland China](https://platform.stepfun.com/step-plan)

| Provider | Purpose | Get API Key |
|----------|---------|-------------|
| `custom` | Any OpenAI-compatible endpoint | — |
| `openrouter` | LLM (recommended, access to all models) | [openrouter.ai](https://openrouter.ai) |
| `volcengine` | LLM (VolcEngine, pay-per-use) | [Coding Plan](https://www.volcengine.com/activity/codingplan?utm_campaign=nanobot&utm_content=nanobot&utm_medium=devrel&utm_source=OWO&utm_term=nanobot) · [volcengine.com](https://www.volcengine.com) |
| `byteplus` | LLM (VolcEngine international, pay-per-use) | [Coding Plan](https://www.byteplus.com/en/activity/codingplan?utm_campaign=nanobot&utm_content=nanobot&utm_medium=devrel&utm_source=OWO&utm_term=nanobot) · [byteplus.com](https://www.byteplus.com) |
| `anthropic` | LLM (Claude direct) | [console.anthropic.com](https://console.anthropic.com) |
| `azure_openai` | LLM (Azure OpenAI) | [portal.azure.com](https://portal.azure.com) |
| `openai` | LLM (GPT direct) | [platform.openai.com](https://platform.openai.com) |
| `deepseek` | LLM (DeepSeek direct) | [platform.deepseek.com](https://platform.deepseek.com) |
| `groq` | LLM + **Voice transcription** (Whisper) | [console.groq.com](https://console.groq.com) |
| `minimax` | LLM (MiniMax direct) | [platform.minimaxi.com](https://platform.minimaxi.com) |
| `gemini` | LLM (Gemini direct) | [aistudio.google.com](https://aistudio.google.com) |
| `aihubmix` | LLM (API gateway, access to all models) | [aihubmix.com](https://aihubmix.com) |
| `siliconflow` | LLM (SiliconFlow/硅基流动) | [siliconflow.cn](https://siliconflow.cn) |
| `dashscope` | LLM (Qwen) | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com) |
| `moonshot` | LLM (Moonshot/Kimi) | [platform.moonshot.cn](https://platform.moonshot.cn) |
| `zhipu` | LLM (Zhipu GLM) | [open.bigmodel.cn](https://open.bigmodel.cn) |
| `ollama` | LLM (local, Ollama) | — |
| `mistral` | LLM | [docs.mistral.ai](https://docs.mistral.ai/) |
| `stepfun` | LLM (Step Fun/阶跃星辰) | [platform.stepfun.com](https://platform.stepfun.com) |
| `ovms` | LLM (local, OpenVINO Model Server) | [docs.openvino.ai](https://docs.openvino.ai/2026/model-server/ovms_docs_llm_quickstart.html) |
| `vllm` | LLM (local, any OpenAI-compatible server) | — |
| `openai_codex` | LLM (Codex, OAuth) | `nanobot provider login openai-codex` |
| `github_copilot` | LLM (GitHub Copilot, OAuth) | `nanobot provider login github-copilot` |

<details>
<summary><b>OpenAI Codex (OAuth)</b></summary>

Codex uses OAuth instead of API keys. Requires a ChatGPT Plus or Pro account.
No `providers.openaiCodex` block is needed in `config.json`; `nanobot provider login` stores the OAuth session outside config.

**1. Login:**
```bash
nanobot provider login openai-codex
```

**2. Set model** (merge into `~/.nanobot/config.json`):
```json
{
  "agents": {
    "defaults": {
      "model": "openai-codex/gpt-5.1-codex"
    }
  }
}
```

**3. Chat:**
```bash
nanobot agent -m "Hello!"

# Target a specific workspace/config locally
nanobot agent -c ~/.nanobot-telegram/config.json -m "Hello!"

# One-off workspace override on top of that config
nanobot agent -c ~/.nanobot-telegram/config.json -w /tmp/nanobot-telegram-test -m "Hello!"
```

> Docker users: use `docker run -it` for interactive OAuth login.

</details>


<details>
<summary><b>GitHub Copilot (OAuth)</b></summary>

GitHub Copilot uses OAuth instead of API keys. Requires a [GitHub account with a plan](https://github.com/features/copilot/plans) configured.
No `providers.githubCopilot` block is needed in `config.json`; `nanobot provider login` stores the OAuth session outside config.

**1. Login:**
```bash
nanobot provider login github-copilot
```

**2. Set model** (merge into `~/.nanobot/config.json`):
```json
{
  "agents": {
    "defaults": {
      "model": "github-copilot/gpt-4.1"
    }
  }
}
```

**3. Chat:**
```bash
nanobot agent -m "Hello!"

# Target a specific workspace/config locally
nanobot agent -c ~/.nanobot-telegram/config.json -m "Hello!"

# One-off workspace override on top of that config
nanobot agent -c ~/.nanobot-telegram/config.json -w /tmp/nanobot-telegram-test -m "Hello!"
```

> Docker users: use `docker run -it` for interactive OAuth login.

</details>

<details>
<summary><b>Custom Provider (Any OpenAI-compatible API)</b></summary>

Connects directly to any OpenAI-compatible endpoint — LM Studio, llama.cpp, Together AI, Fireworks, Azure OpenAI, or any self-hosted server. Model name is passed as-is.

```json
{
  "providers": {
    "custom": {
      "apiKey": "your-api-key",
      "apiBase": "https://api.your-provider.com/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "your-model-name"
    }
  }
}
```

> For local servers that don't require a key, set `apiKey` to any non-empty string (e.g. `"no-key"`).

</details>

<details>
<summary><b>Ollama (local)</b></summary>

Run a local model with Ollama, then add to config:

**1. Start Ollama** (example):
```bash
ollama run llama3.2
```

**2. Add to config** (partial — merge into `~/.nanobot/config.json`):
```json
{
  "providers": {
    "ollama": {
      "apiBase": "http://localhost:11434"
    }
  },
  "agents": {
    "defaults": {
      "provider": "ollama",
      "model": "llama3.2"
    }
  }
}
```

> `provider: "auto"` also works when `providers.ollama.apiBase` is configured, but setting `"provider": "ollama"` is the clearest option.

</details>

<details>
<summary><b>OpenVINO Model Server (local / OpenAI-compatible)</b></summary>

Run LLMs locally on Intel GPUs using [OpenVINO Model Server](https://docs.openvino.ai/2026/model-server/ovms_docs_llm_quickstart.html). OVMS exposes an OpenAI-compatible API at `/v3`.

> Requires Docker and an Intel GPU with driver access (`/dev/dri`).

**1. Pull the model** (example):

```bash
mkdir -p ov/models && cd ov

docker run -d \
  --rm \
  --user $(id -u):$(id -g) \
  -v $(pwd)/models:/models \
  openvino/model_server:latest-gpu \
  --pull \
  --model_name openai/gpt-oss-20b \
  --model_repository_path /models \
  --source_model OpenVINO/gpt-oss-20b-int4-ov \
  --task text_generation \
  --tool_parser gptoss \
  --reasoning_parser gptoss \
  --enable_prefix_caching true \
  --target_device GPU
```

> This downloads the model weights. Wait for the container to finish before proceeding.

**2. Start the server** (example):

```bash
docker run -d \
  --rm \
  --name ovms \
  --user $(id -u):$(id -g) \
  -p 8000:8000 \
  -v $(pwd)/models:/models \
  --device /dev/dri \
  --group-add=$(stat -c "%g" /dev/dri/render* | head -n 1) \
  openvino/model_server:latest-gpu \
  --rest_port 8000 \
  --model_name openai/gpt-oss-20b \
  --model_repository_path /models \
  --source_model OpenVINO/gpt-oss-20b-int4-ov \
  --task text_generation \
  --tool_parser gptoss \
  --reasoning_parser gptoss \
  --enable_prefix_caching true \
  --target_device GPU
```

**3. Add to config** (partial — merge into `~/.nanobot/config.json`):

```json
{
  "providers": {
    "ovms": {
      "apiBase": "http://localhost:8000/v3"
    }
  },
  "agents": {
    "defaults": {
      "provider": "ovms",
      "model": "openai/gpt-oss-20b"
    }
  }
}
```

> OVMS is a local server — no API key required. Supports tool calling (`--tool_parser gptoss`), reasoning (`--reasoning_parser gptoss`), and streaming.
> See the [official OVMS docs](https://docs.openvino.ai/2026/model-server/ovms_docs_llm_quickstart.html) for more details.
</details>

<details>
<summary><b>vLLM (local / OpenAI-compatible)</b></summary>

Run your own model with vLLM or any OpenAI-compatible server, then add to config:

**1. Start the server** (example):
```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000
```

**2. Add to config** (partial — merge into `~/.nanobot/config.json`):

*Provider (key can be any non-empty string for local):*
```json
{
  "providers": {
    "vllm": {
      "apiKey": "dummy",
      "apiBase": "http://localhost:8000/v1"
    }
  }
}
```

*Model:*
```json
{
  "agents": {
    "defaults": {
      "model": "meta-llama/Llama-3.1-8B-Instruct"
    }
  }
}
```

</details>

<details>
<summary><b>Adding a New Provider (Developer Guide)</b></summary>

nanobot uses a **Provider Registry** (`nanobot/providers/registry.py`) as the single source of truth.
Adding a new provider only takes **2 steps** — no if-elif chains to touch.

**Step 1.** Add a `ProviderSpec` entry to `PROVIDERS` in `nanobot/providers/registry.py`:

```python
ProviderSpec(
    name="myprovider",                   # config field name
    keywords=("myprovider", "mymodel"),  # model-name keywords for auto-matching
    env_key="MYPROVIDER_API_KEY",        # env var name
    display_name="My Provider",          # shown in `nanobot status`
    default_api_base="https://api.myprovider.com/v1",  # OpenAI-compatible endpoint
)
```

**Step 2.** Add a field to `ProvidersConfig` in `nanobot/config/schema.py`:

```python
class ProvidersConfig(BaseModel):
    ...
    myprovider: ProviderConfig = ProviderConfig()
```

That's it! Environment variables, model routing, config matching, and `nanobot status` display will all work automatically.

**Common `ProviderSpec` options:**

| Field | Description | Example |
|-------|-------------|---------|
| `default_api_base` | OpenAI-compatible base URL | `"https://api.deepseek.com"` |
| `env_extras` | Additional env vars to set | `(("ZHIPUAI_API_KEY", "{api_key}"),)` |
| `model_overrides` | Per-model parameter overrides | `(("kimi-k2.5", {"temperature": 1.0}),)` |
| `is_gateway` | Can route any model (like OpenRouter) | `True` |
| `detect_by_key_prefix` | Detect gateway by API key prefix | `"sk-or-"` |
| `detect_by_base_keyword` | Detect gateway by API base URL | `"openrouter"` |
| `strip_model_prefix` | Strip provider prefix before sending to gateway | `True` (for AiHubMix) |

</details>

### Channel Settings

Global settings that apply to all channels. Configure under the `channels` section in `~/.nanobot/config.json`:

```json
{
  "channels": {
    "sendProgress": true,
    "sendToolHints": false,
    "sendMaxRetries": 3,
    "telegram": { ... }
  }
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `sendProgress` | `true` | Stream agent's text progress to the channel |
| `sendToolHints` | `false` | Stream tool-call hints (e.g. `read_file("…")`) |
| `sendMaxRetries` | `3` | Max delivery attempts per outbound message, including the initial send (0-10 configured, minimum 1 actual attempt) |

#### Retry Behavior

When a channel send operation raises an error, nanobot retries with exponential backoff:

- **Attempt 1**: Initial send
- **Attempts 2-4**: Retry delays are 1s, 2s, 4s
- **Attempts 5+**: Retry delay caps at 4s
- **Transient failures** (network hiccups, temporary API limits): Retry usually succeeds
- **Permanent failures** (invalid token, channel banned): All retries fail

> [!NOTE]
> When a channel is completely unavailable, there's no way to notify the user since we cannot reach them through that channel. Monitor logs for "Failed to send to {channel} after N attempts" to detect persistent delivery failures.

### Web Search

> [!TIP]
> Use `proxy` in `tools.web` to route all web requests (search + fetch) through a proxy:
> ```json
> { "tools": { "web": { "proxy": "http://127.0.0.1:7890" } } }
> ```

nanobot supports multiple web search providers. Configure in `~/.nanobot/config.json` under `tools.web.search`.

| Provider | Config fields | Env var fallback | Free |
|----------|--------------|------------------|------|
| `brave` (default) | `apiKey` | `BRAVE_API_KEY` | No |
| `tavily` | `apiKey` | `TAVILY_API_KEY` | No |
| `jina` | `apiKey` | `JINA_API_KEY` | Free tier (10M tokens) |
| `searxng` | `baseUrl` | `SEARXNG_BASE_URL` | Yes (self-hosted) |
| `duckduckgo` | — | — | Yes |

When credentials are missing, nanobot automatically falls back to DuckDuckGo.

**Brave** (default):
```json
{
  "tools": {
    "web": {
      "search": {
        "provider": "brave",
        "apiKey": "BSA..."
      }
    }
  }
}
```

**Tavily:**
```json
{
  "tools": {
    "web": {
      "search": {
        "provider": "tavily",
        "apiKey": "tvly-..."
      }
    }
  }
}
```

**Jina** (free tier with 10M tokens):
```json
{
  "tools": {
    "web": {
      "search": {
        "provider": "jina",
        "apiKey": "jina_..."
      }
    }
  }
}
```

**SearXNG** (self-hosted, no API key needed):
```json
{
  "tools": {
    "web": {
      "search": {
        "provider": "searxng",
        "baseUrl": "https://searx.example"
      }
    }
  }
}
```

**DuckDuckGo** (zero config):
```json
{
  "tools": {
    "web": {
      "search": {
        "provider": "duckduckgo"
      }
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `provider` | string | `"brave"` | Search backend: `brave`, `tavily`, `jina`, `searxng`, `duckduckgo` |
| `apiKey` | string | `""` | API key for Brave or Tavily |
| `baseUrl` | string | `""` | Base URL for SearXNG |
| `maxResults` | integer | `5` | Results per search (1–10) |

### MCP (Model Context Protocol)

> [!TIP]
> The config format is compatible with Claude Desktop / Cursor. You can copy MCP server configs directly from any MCP server's README.

nanobot supports [MCP](https://modelcontextprotocol.io/) — connect external tool servers and use them as native agent tools.

Add MCP servers to your `config.json`:

```json
{
  "tools": {
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
      },
      "my-remote-mcp": {
        "url": "https://example.com/mcp/",
        "headers": {
          "Authorization": "Bearer xxxxx"
        }
      }
    }
  }
}
```

Two transport modes are supported:

| Mode | Config | Example |
|------|--------|---------|
| **Stdio** | `command` + `args` | Local process via `npx` / `uvx` |
| **HTTP** | `url` + `headers` (optional) | Remote endpoint (`https://mcp.example.com/sse`) |

Use `toolTimeout` to override the default 30s per-call timeout for slow servers:

```json
{
  "tools": {
    "mcpServers": {
      "my-slow-server": {
        "url": "https://example.com/mcp/",
        "toolTimeout": 120
      }
    }
  }
}
```

Use `enabledTools` to register only a subset of tools from an MCP server:

```json
{
  "tools": {
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
        "enabledTools": ["read_file", "mcp_filesystem_write_file"]
      }
    }
  }
}
```

`enabledTools` accepts either the raw MCP tool name (for example `read_file`) or the wrapped nanobot tool name (for example `mcp_filesystem_write_file`).

- Omit `enabledTools`, or set it to `["*"]`, to register all tools.
- Set `enabledTools` to `[]` to register no tools from that server.
- Set `enabledTools` to a non-empty list of names to register only that subset.

MCP tools are automatically discovered and registered on startup. The LLM can use them alongside built-in tools — no extra configuration needed.




### Security

> [!TIP]
> For production deployments, set `"restrictToWorkspace": true` in your config to sandbox the agent.
> In `v0.1.4.post3` and earlier, an empty `allowFrom` allowed all senders. Since `v0.1.4.post4`, empty `allowFrom` denies all access by default. To allow all senders, set `"allowFrom": ["*"]`.

| Option | Default | Description |
|--------|---------|-------------|
| `tools.restrictToWorkspace` | `false` | When `true`, restricts **all** agent tools (shell, file read/write/edit, list) to the workspace directory. Prevents path traversal and out-of-scope access. |
| `tools.exec.enable` | `true` | When `false`, the shell `exec` tool is not registered at all. Use this to completely disable shell command execution. |
| `tools.exec.pathAppend` | `""` | Extra directories to append to `PATH` when running shell commands (e.g. `/usr/sbin` for `ufw`). |
| `channels.*.allowFrom` | `[]` (deny all) | Whitelist of user IDs. Empty denies all; use `["*"]` to allow everyone. |


### Timezone

Time is context. Context should be precise.

By default, nanobot uses `UTC` for runtime time context. If you want the agent to think in your local time, set `agents.defaults.timezone` to a valid [IANA timezone name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones):

```json
{
  "agents": {
    "defaults": {
      "timezone": "Asia/Shanghai"
    }
  }
}
```

This affects runtime time strings shown to the model, such as runtime context and heartbeat prompts. It also becomes the default timezone for cron schedules when a cron expression omits `tz`, and for one-shot `at` times when the ISO datetime has no explicit offset.

Common examples: `UTC`, `America/New_York`, `America/Los_Angeles`, `Europe/London`, `Europe/Berlin`, `Asia/Tokyo`, `Asia/Shanghai`, `Asia/Singapore`, `Australia/Sydney`.

> Need another timezone? Browse the full [IANA Time Zone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).

## 🧩 Multiple Instances

Run multiple nanobot instances simultaneously with separate configs and runtime data. Use `--config` as the main entrypoint. Optionally pass `--workspace` during `onboard` when you want to initialize or update the saved workspace for a specific instance.

### Quick Start

If you want each instance to have its own dedicated workspace from the start, pass both `--config` and `--workspace` during onboarding.

**Initialize instances:**

```bash
# Create separate instance configs and workspaces
nanobot onboard --config ~/.nanobot-telegram/config.json --workspace ~/.nanobot-telegram/workspace
nanobot onboard --config ~/.nanobot-discord/config.json --workspace ~/.nanobot-discord/workspace
nanobot onboard --config ~/.nanobot-feishu/config.json --workspace ~/.nanobot-feishu/workspace
```

**Configure each instance:**

Edit `~/.nanobot-telegram/config.json`, `~/.nanobot-discord/config.json`, etc. with different channel settings. The workspace you passed during `onboard` is saved into each config as that instance's default workspace.

**Run instances:**

```bash
# Instance A - Telegram bot
nanobot gateway --config ~/.nanobot-telegram/config.json

# Instance B - Discord bot  
nanobot gateway --config ~/.nanobot-discord/config.json

# Instance C - Feishu bot with custom port
nanobot gateway --config ~/.nanobot-feishu/config.json --port 18792
```

### Path Resolution

When using `--config`, nanobot derives its runtime data directory from the config file location. The workspace still comes from `agents.defaults.workspace` unless you override it with `--workspace`.

To open a CLI session against one of these instances locally:

```bash
nanobot agent -c ~/.nanobot-telegram/config.json -m "Hello from Telegram instance"
nanobot agent -c ~/.nanobot-discord/config.json -m "Hello from Discord instance"

# Optional one-off workspace override
nanobot agent -c ~/.nanobot-telegram/config.json -w /tmp/nanobot-telegram-test
```

> `nanobot agent` starts a local CLI agent using the selected workspace/config. It does not attach to or proxy through an already running `nanobot gateway` process.

| Component | Resolved From | Example |
|-----------|---------------|---------|
| **Config** | `--config` path | `~/.nanobot-A/config.json` |
| **Workspace** | `--workspace` or config | `~/.nanobot-A/workspace/` |
| **Cron Jobs** | config directory | `~/.nanobot-A/cron/` |
| **Media / runtime state** | config directory | `~/.nanobot-A/media/` |

### How It Works

- `--config` selects which config file to load
- By default, the workspace comes from `agents.defaults.workspace` in that config
- If you pass `--workspace`, it overrides the workspace from the config file

### Minimal Setup

1. Copy your base config into a new instance directory.
2. Set a different `agents.defaults.workspace` for that instance.
3. Start the instance with `--config`.

Example config:

```json
{
  "agents": {
    "defaults": {
      "workspace": "~/.nanobot-telegram/workspace",
      "model": "anthropic/claude-sonnet-4-6"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_TELEGRAM_BOT_TOKEN"
    }
  },
  "gateway": {
    "port": 18790
  }
}
```

Start separate instances:

```bash
nanobot gateway --config ~/.nanobot-telegram/config.json
nanobot gateway --config ~/.nanobot-discord/config.json
```

Override workspace for one-off runs when needed:

```bash
nanobot gateway --config ~/.nanobot-telegram/config.json --workspace /tmp/nanobot-telegram-test
```

### Common Use Cases

- Run separate bots for Telegram, Discord, Feishu, and other platforms
- Keep testing and production instances isolated
- Use different models or providers for different teams
- Serve multiple tenants with separate configs and runtime data

### Notes

- Each instance must use a different port if they run at the same time
- Use a different workspace per instance if you want isolated memory, sessions, and skills
- `--workspace` overrides the workspace defined in the config file
- Cron jobs and runtime media/state are derived from the config directory

## 💻 CLI Reference

| Command | Description |
|---------|-------------|
| `nanobot onboard` | Initialize config & workspace at `~/.nanobot/` |
| `nanobot onboard --wizard` | Launch the interactive onboarding wizard |
| `nanobot onboard -c <config> -w <workspace>` | Initialize or refresh a specific instance config and workspace |
| `nanobot agent -m "..."` | Chat with the agent |
| `nanobot agent -w <workspace>` | Chat against a specific workspace |
| `nanobot agent -w <workspace> -c <config>` | Chat against a specific workspace/config |
| `nanobot agent` | Interactive chat mode |
| `nanobot agent --no-markdown` | Show plain-text replies |
| `nanobot agent --logs` | Show runtime logs during chat |
| `nanobot gateway` | Start the gateway |
| `nanobot status` | Show status |
| `nanobot provider login openai-codex` | OAuth login for providers |
| `nanobot channels login <channel>` | Authenticate a channel interactively |
| `nanobot channels status` | Show channel status |

Interactive mode exits: `exit`, `quit`, `/exit`, `/quit`, `:q`, or `Ctrl+D`.

<details>
<summary><b>Heartbeat (Periodic Tasks)</b></summary>

The gateway wakes up every 30 minutes and checks `HEARTBEAT.md` in your workspace (`~/.nanobot/workspace/HEARTBEAT.md`). If the file has tasks, the agent executes them and delivers results to your most recently active chat channel.

**Setup:** edit `~/.nanobot/workspace/HEARTBEAT.md` (created automatically by `nanobot onboard`):

```markdown
## Periodic Tasks

- [ ] Check weather forecast and send a summary
- [ ] Scan inbox for urgent emails
```

The agent can also manage this file itself — ask it to "add a periodic task" and it will update `HEARTBEAT.md` for you.

> **Note:** The gateway must be running (`nanobot gateway`) and you must have chatted with the bot at least once so it knows which channel to deliver to.

</details>

## 🐳 Docker

> [!TIP]
> The `-v ~/.nanobot:/root/.nanobot` flag mounts your local config directory into the container, so your config and workspace persist across container restarts.

### Docker Compose

```bash
docker compose run --rm nanobot-cli onboard   # first-time setup
vim ~/.nanobot/config.json                     # add API keys
docker compose up -d nanobot-gateway           # start gateway
```

```bash
docker compose run --rm nanobot-cli agent -m "Hello!"   # run CLI
docker compose logs -f nanobot-gateway                   # view logs
docker compose down                                      # stop
```

### Docker

```bash
# Build the image
docker build -t nanobot .

# Initialize config (first time only)
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot onboard

# Edit config on host to add API keys
vim ~/.nanobot/config.json

# Run gateway (connects to enabled channels, e.g. Telegram/Discord/Mochat)
docker run -v ~/.nanobot:/root/.nanobot -p 18790:18790 nanobot gateway

# Or run a single command
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot agent -m "Hello!"
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot status
```

## 🐧 Linux Service

Run the gateway as a systemd user service so it starts automatically and restarts on failure.

**1. Find the nanobot binary path:**

```bash
which nanobot   # e.g. /home/user/.local/bin/nanobot
```

**2. Create the service file** at `~/.config/systemd/user/nanobot-gateway.service` (replace `ExecStart` path if needed):

```ini
[Unit]
Description=Nanobot Gateway
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/nanobot gateway
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=%h

[Install]
WantedBy=default.target
```

**3. Enable and start:**

```bash
systemctl --user daemon-reload
systemctl --user enable --now nanobot-gateway
```

**Common operations:**

```bash
systemctl --user status nanobot-gateway        # check status
systemctl --user restart nanobot-gateway       # restart after config changes
journalctl --user -u nanobot-gateway -f        # follow logs
```

4. **結果**
   Agent 返回結構化分析結果

---

## 📁 目錄結構

```
nanobot/
├── start.bat              # Windows 一鍵啟動
├── start.ps1              # PowerShell 一鍵啟動
├── docker-compose.yml     # Docker 配置
├── config/                # 配置文件
├── data/pdfs/             # PDF 文件目錄
├── liteparse-mcp-server/  # MCP 服務
│   ├── index.js           # MCP Server
│   ├── liteparse_data_cleaner.py  # 數據清洗
│   └── Dockerfile
├── nanobot/               # Nanobot 主程式
│   └── agent/tools/liteparse.py   # LiteParse 工具
└── tests/                 # 測試套件
```

---

## 📚 文檔

| 文檔 | 說明 |
|------|------|
| [`FIRST_STEP_COMPLETE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/FIRST_STEP_COMPLETE.md) | **第一步完成報告** |
| [`QUICKSTART_MCP.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/QUICKSTART_MCP.md) | 快速開始指南 |
| [`liteparse-mcp-server/README_DOCKER.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/liteparse-mcp-server/README_DOCKER.md) | Docker 部署指南 |
| [`README_LITEPARSE_INTEGRATED.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/README_LITEPARSE_INTEGRATED.md) | 集成說明 |

---

## 🧪 測試

### 端到端測試

```bash
py test_end_to_end.py
```

### Docker 測試

```bash
docker-compose ps
docker-compose logs -f
```

---

## 🔧 常見命令

```bash
# 啟動服務
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止服務
docker-compose down

# 重建容器
docker-compose build --no-cache

# 進入容器調試
docker-compose exec liteparse-mcp sh
```

---

## ❓ 常見問題

### Q: 需要手動安裝依賴嗎？

**A:** 唔需要！所有依賴已包含喺 Docker 容器入面。

### Q: Docker 容器佔用幾多資源？

**A:** 最多 1.5GB RAM, 1.5 CPU（實際使用更少）

### Q: 點樣上傳 PDF 文件？

**A:** 將 PDF 放入 `data/pdfs/` 目錄，容器會自動掛載。

### Q: 遇到問題點算？

**A:** 查看 [`FIRST_STEP_COMPLETE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/FIRST_STEP_COMPLETE.md) 嘅常見問題章節。

---

## 🎯 下一步

**第一步 ✅ 已完成** - Docker 化部署，零手動安裝

**下一步：** 第二步（數據清洗與 Prompt 設計）

1. 優化數據清洗邏輯
2. 設計 System Prompt
3. 測試真實場景

---

## 📞 需要幫助？

查看完整文檔：[`FIRST_STEP_COMPLETE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/FIRST_STEP_COMPLETE.md)

---

**記住：所有依賴已包含喺 Docker 容器入面，你只需要運行 `docker-compose up -d`！** 🚀
