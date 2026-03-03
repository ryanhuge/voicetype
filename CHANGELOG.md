# Changelog

All notable changes to VoiceType will be documented in this file.

## [Unreleased] - 2026-03-03

### 🎯 Major Improvements

#### LLM 模型升級到 GPT-4.1
- **從 GPT-4o 升級到 GPT-4.1** - 更強的指令遵循能力
- **解決了 LLM 回答問題的問題** - 現在能完美遵守「只清理文字，不回答問題」的指令
- **性能提升** - GPT-4.1 比 GPT-4o 便宜 20%（$2.00/$8.00 vs $2.50/$10.00 per 1M tokens）
- **上下文容量提升** - 128K tokens 上下文（vs Groq LLM 的 8K-32K）

### ✨ New Features

#### 托盤選單模型選擇器
- **即時切換模型** - 右鍵托盤圖標 → 「模型選擇」
- **支援模型**：
  - GPT-4.1（推薦）
  - GPT-4.1-mini
  - GPT-4o
  - GPT-4o-mini
- **即時生效** - 無需重啟應用程式
- **狀態顯示** - 托盤圖標顯示當前使用的模型

#### 字典擴充
- **從 129 個詞擴充到 160 個詞**
- **新增分類**：
  - AI 模型：GPT-4.1, GPT-4o, GPT-5.2, GPT-5.3, Groq, Ollama
  - AI/ML 概念：LLM, STT, API, prompt, temperature, tokens, context
  - 通訊軟體：Discord, Messenger, WhatsApp, Slack, Teams
  - 郵件客戶端：Outlook, Gmail, Thunderbird
  - 文件編輯：Word, Docs, Notion, Obsidian
  - 開發工具：VSCode, PyCharm
  - 資料庫：PostgreSQL, MongoDB, Redis, FastAPI
  - DevOps：Kubernetes

### 🔧 Optimizations

#### System Prompt 強化
- **更明確的「不回答問題」指令**
- **添加正反範例** - 清楚展示正確和錯誤的輸出
- **強化格式規則** - 更詳細的清理和格式化指導

#### Temperature 優化
- **從預設值調整到 0.1** - 極低溫度確保嚴格遵守指令
- **應用於所有 LLM provider** - OpenAI, Anthropic, Groq, Ollama

### 🐛 Bug Fixes

#### 上下文限制問題
- **問題**：使用 Groq LLM 時，上下文太短（8K-32K tokens）無法處理大量字典詞彙
- **解決**：切換到 OpenAI GPT-4.1（128K tokens）完全解決
- **效果**：現在可以使用數千個字典詞彙而不會超出上下文

#### 托盤選單 Lambda 函數簽名錯誤
- **修正**：MenuItem 回呼函數需要接受 `(icon, item)` 兩個參數
- **影響**：修正後托盤選單的模型選擇功能正常運作

### 📝 Changed Files

- `main.py` - 添加模型選擇器和切換功能
- `core/llm.py` - 調整 temperature 到 0.1
- `config/settings.py` - 更新預設 system prompt
- `config.json` - 升級到 GPT-4.1，擴充字典到 160 個詞

### 💡 Recommendations

- **推薦模型**：GPT-4.1（指令遵循能力最強，性價比高）
- **不推薦**：GPT-4o-mini、GPT-3.5-turbo（無法遵守「不回答問題」的指令）
- **字典擴充**：GPT-4.1 的 128K 上下文可以輕鬆處理數千個詞彙，可以繼續擴充

---

## Previous Versions

### Phase 1 & 2: Focus Loss and Process Hanging Fixes
- Fixed focus loss issue after voice input
- Fixed process hanging on Windows
- Improved focus restoration mechanism
- Added thread safety with locks
- Added timeout protection for AttachThreadInput
- Reordered execution sequence (focus → escape → unhook → inject → rehook)
