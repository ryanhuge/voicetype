# VoiceType

> 按住說話，放開即輸出 — Windows 語音輸入工具

VoiceType 是一個系統級的語音輸入工具。按住快捷鍵說話，放開後自動透過 AI 去除贅字、修正語句、加入標點，然後將文字注入到任何應用程式的游標位置。

---

## 🎉 最新更新 (2026-03-03)

### ✨ 重大改進

- **🚀 升級到 GPT-4.1** - 更強的指令遵循能力，完美解決「AI 回答問題」的問題
- **🎛️ 托盤選單模型切換** - 右鍵托盤圖標即可切換模型，支援 GPT-4.1、GPT-4.1-mini、GPT-4o、GPT-4o-mini
- **📚 字典擴充至 160 個詞** - 新增 AI 模型、開發工具、通訊軟體、資料庫等常用專有名詞
- **🎯 Temperature 優化** - 調整至 0.1，確保嚴格遵守指令
- **📈 上下文容量提升** - 128K tokens（vs Groq 的 8K-32K），可使用數千個字典詞彙

### 💰 性能提升

- **GPT-4.1 比 GPT-4o 便宜 20%** - $2/$8 vs $2.5/$10 per 1M tokens
- **指令遵循能力最強** - 完美執行「只清理文字，不回答問題」
- **即時模型切換** - 無需重啟應用程式

查看完整更新內容：[CHANGELOG.md](CHANGELOG.md)

---

## 功能

- **Push-to-Talk** — 按住 Right Alt 說話，放開自動輸出
- **AI 智能修飾** — 自動去除「嗯」「啊」「那個」等贅字，修正語句結構，加入標點符號
- **中英夾雜處理** — 英文專有名詞自動修正大小寫，中英之間自動加空格
- **自訂字典** — 支援批次匯入專有名詞，同時用於語音辨識與 LLM 修飾
- **全應用程式支援** — Chrome、VS Code、Word、LINE、任何有文字輸入的地方
- **音效提示** — 錄音開始與結束時有聲音回饋
- **隨 Windows 啟動** — 可在設定中開關，開機自動常駐
- **單實例保護** — 防止重複開啟導致鍵盤異常
- **多引擎支援** — STT 和 LLM 皆可自由選擇引擎
- **托盤選單模型切換** — 右鍵托盤圖標即可切換 LLM 模型，無需重啟
- **Web 設定介面** — 在瀏覽器中管理所有設定
- **系統托盤常駐** — 不佔桌面空間，背景安靜運行

## 快速開始

### 使用 EXE（推薦）

1. 從 [Releases](../../releases) 下載 `VoiceType.exe`
2. 雙擊執行
3. 首次啟動會自動開啟設定頁面 → 填入 API Key → 完成

### 從原始碼執行

```bash
pip install -r requirements.txt
python main.py
```

### 取得 API Key

| 服務 | 用途 | 連結 |
|------|------|------|
| **Groq** | 語音辨識（STT） | https://console.groq.com/keys |
| **OpenAI** | 文字修飾（LLM） | https://platform.openai.com/api-keys |

> Groq 提供免費額度，OpenAI GPT-4.1 指令遵循能力最強，兩者搭配為推薦組合。

## 使用方式

1. VoiceType 啟動後常駐在系統托盤（右下角）
2. 在任何 App 中，將游標放在要輸入文字的地方
3. **按住 Right Alt** 開始說話（會聽到提示音）
4. **放開 Right Alt** 等待 1-2 秒
5. 修飾後的文字自動出現在游標位置

```
按住 Right Alt → 錄音
放開 Right Alt → 停止錄音
         ↓
  Groq Whisper 語音辨識
  "嗯那個我想說明天的會議改到呃禮拜三下午兩點"
         ↓
  ChatGPT 智能修飾
  "明天的會議改到禮拜三下午兩點。"
         ↓
  剪貼簿 + Ctrl+V 注入游標位置
```

## 設定

設定方式（擇一）：
- 系統托盤右鍵 →「開啟設定」（Web 介面）
- 手動編輯 `%APPDATA%\voicetype\config.json`

### STT 引擎

| 引擎 | 速度 | 費用 | 說明 |
|------|------|------|------|
| **Groq Whisper** | 極快 | 幾乎免費 | 推薦 |
| OpenAI Whisper | 中等 | ~$0.006/min | 品質穩定 |
| 本地 Whisper | 依硬體 | 免費 | 需安裝 faster-whisper |

### LLM 引擎

| 引擎 | 速度 | 費用 | 說明 |
|------|------|------|------|
| **OpenAI GPT-4.1** | 快 | $2/$8 per 1M tokens | 推薦，指令遵循能力最強 |
| OpenAI GPT-4.1-mini | 快 | ~$6 per 1M tokens | 較便宜但能力稍弱 |
| OpenAI GPT-4o | 快 | $2.5/$10 per 1M tokens | 較舊，將於 2026-02-13 退役 |
| Anthropic Claude | 快 | 較高 | 高品質文字處理 |
| Groq | 極快 | 幾乎免費 | 上下文較短（8K-32K） |
| Ollama | 依硬體 | 免費 | 完全離線 |

### 快捷鍵

預設 `Right Alt`，可在設定中更改為 Right Ctrl、F9、CapsLock 或 ScrollLock。

## 專案結構

```
voicetype/
├── main.py                  # 主程式入口
├── core/
│   ├── recorder.py          # 音訊錄製
│   ├── stt.py               # 語音轉文字
│   ├── llm.py               # LLM 智能修飾
│   ├── injector.py          # 文字注入（剪貼簿 + Ctrl+V）
│   ├── hotkey.py            # 全域快捷鍵
│   ├── sounds.py            # 音效提示
│   └── tray_icons.py        # 系統托盤圖示
├── config/
│   ├── settings.py          # 設定管理
│   └── settings_server.py   # Web 設定伺服器
├── ui/
│   └── settings.html        # 設定頁面
├── assets/
│   └── VoiceType.exe.manifest
├── build.py                 # 打包腳本
├── requirements.txt         # Python 依賴
└── start.bat                # 一鍵啟動
```

## 自行打包

```bash
pip install pyinstaller
python build.py
```

產出 `dist/VoiceType.exe`。

## 系統需求

- Windows 10 / 11
- 麥克風
- 網路連線（使用雲端 STT/LLM 時）

## License

MIT
