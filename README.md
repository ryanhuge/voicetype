# VoiceType

> 按住說話，放開即輸出 — 跨平台語音輸入工具

VoiceType 是一個系統級的語音輸入工具，支援 **Windows** 和 **Ubuntu Linux**。按住快捷鍵說話，放開後自動透過 AI 去除贅字、修正語句、加入標點，然後將文字注入到任何應用程式的游標位置。

## 功能

- **Push-to-Talk** — 按住 Right Alt 說話，放開自動輸出
- **AI 智能修飾** — 自動去除「嗯」「啊」「那個」等贅字，修正語句結構，加入標點符號
- **中英夾雜處理** — 英文專有名詞自動修正大小寫，中英之間自動加空格
- **全應用程式支援** — 瀏覽器、IDE、終端機、任何有文字輸入的地方
- **音效提示** — 錄音開始與結束時有聲音回饋
- **多引擎支援** — STT 和 LLM 皆可自由選擇引擎
- **Web 設定介面** — 在瀏覽器中管理所有設定
- **系統托盤常駐** — 不佔桌面空間，背景安靜運行
- **開機自動啟動** — Windows 和 Linux 皆支援

## 快速開始

### Windows

#### 使用 EXE（推薦）

1. 從 [Releases](../../releases) 下載 `VoiceType.exe`
2. 雙擊執行
3. 首次啟動會自動開啟設定頁面 → 填入 API Key → 完成

#### 從原始碼執行

```bash
pip install -r requirements.txt
python main.py
```

### Ubuntu Linux

#### 安裝系統依賴

```bash
# 音訊驅動
sudo apt install libportaudio2

# 文字注入工具
sudo apt install xdotool xsel

# evdev 權限（需登出再登入生效）
sudo usermod -aG input $USER
```

#### 安裝 Python 依賴並執行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

#### IBus 輸入法設定（使用中文輸入法時）

如果你使用 IBus + 注音/Chewing，需移除 Right Alt 的 IBus 觸發鍵以避免衝突：

```bash
gsettings set org.freedesktop.ibus.general.hotkey trigger "[]"
```

#### IDE 設定（VSCode / Antigravity）

如果 Right Alt 會觸發 IDE 的選單列，在 IDE 設定中加入：

```json
{
    "window.enableMenuBarMnemonics": false,
    "window.titleBarStyle": "native"
}
```

### 取得 API Key

| 服務 | 用途 | 連結 |
|------|------|------|
| **Groq** | 語音辨識（STT） | https://console.groq.com/keys |
| **OpenAI** | 文字修飾（LLM） | https://platform.openai.com/api-keys |

> Groq 提供免費額度，OpenAI gpt-4o-mini 費用極低，兩者搭配為推薦組合。

## 使用方式

1. VoiceType 啟動後常駐在系統托盤
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
  注入游標位置
```

## 設定

設定方式（擇一）：
- 系統托盤右鍵 →「開啟設定」（Web 介面）
- 手動編輯設定檔：
  - Windows: `%APPDATA%\voicetype\config.json`
  - Linux: `~/.config/voicetype/config.json`

### STT 引擎

| 引擎 | 速度 | 費用 | 說明 |
|------|------|------|------|
| **Groq Whisper** | 極快 | 幾乎免費 | 推薦 |
| OpenAI Whisper | 中等 | ~$0.006/min | 品質穩定 |
| 本地 Whisper | 依硬體 | 免費 | 需安裝 faster-whisper |

### LLM 引擎

| 引擎 | 速度 | 費用 | 說明 |
|------|------|------|------|
| **OpenAI gpt-4o-mini** | 快 | 極低 | 推薦 |
| Anthropic Claude | 快 | 低 | 高品質文字處理 |
| Groq | 極快 | 幾乎免費 | 開源模型 |
| Ollama | 依硬體 | 免費 | 完全離線 |

### 快捷鍵

預設 `Right Alt`，可在設定中更改為 Right Ctrl、F9、CapsLock 或 ScrollLock。

## 跨平台實作

| 功能 | Windows | Linux |
|------|---------|-------|
| 快捷鍵監聽 | `keyboard` 庫 | `evdev` 讀取 `/dev/input` |
| 文字注入 | `pyperclip` + `pyautogui` Ctrl+V | `xsel` 剪貼簿 + `xdotool` Ctrl+V |
| 終端機貼上 | Ctrl+V | 自動偵測終端機，改用 Ctrl+Shift+V |
| 音效 | `winsound` 正弦波 | `sounddevice` + `numpy` 正弦波 |
| 開機自啟 | 登錄檔 `Run` | `~/.config/autostart/*.desktop` |
| 系統托盤 | pystray (Win32) | pystray (Xorg) |

## 專案結構

```
voicetype/
├── main.py                  # 主程式入口
├── core/
│   ├── recorder.py          # 音訊錄製（sounddevice）
│   ├── stt.py               # 語音轉文字（Groq/OpenAI/本地）
│   ├── llm.py               # LLM 智能修飾
│   ├── injector.py          # 文字注入（跨平台）
│   ├── hotkey.py            # 全域快捷鍵（跨平台）
│   ├── sounds.py            # 音效提示（跨平台）
│   └── tray_icons.py        # 系統托盤圖示
├── config/
│   ├── settings.py          # 設定管理
│   └── settings_server.py   # Web 設定伺服器 + 自動啟動
├── ui/
│   └── settings.html        # 設定頁面
├── assets/
│   └── VoiceType.exe.manifest
├── build.py                 # 打包腳本（Windows/Linux）
├── requirements.txt         # Python 依賴（含平台標記）
└── start.bat                # Windows 一鍵啟動
```

## 自行打包

```bash
pip install pyinstaller
python build.py
```

- Windows 產出：`dist/VoiceType.exe`
- Linux 產出：`dist/VoiceType`

## 系統需求

- **Windows** 10 / 11
- **Ubuntu** 22.04+（X11 桌面環境）
- 麥克風
- 網路連線（使用雲端 STT/LLM 時）

## License

MIT
