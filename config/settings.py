"""
設定管理模組
讀寫 config.json，管理 API Key 和所有應用設定
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("VoiceType.Settings")

# 有效值定義
VALID_STT_PROVIDERS = {"groq", "openai", "local"}
VALID_LLM_PROVIDERS = {"openai", "anthropic", "groq", "ollama"}
VALID_HOTKEYS = {"RightAlt", "RightCtrl", "F9", "CapsLock", "ScrollLock"}
VALID_LANGUAGES = {"auto", "zh-TW", "zh-CN", "en", "ja"}

# 預設設定
DEFAULT_CONFIG = {
    "sttProvider": "groq",
    "llmProvider": "openai",
    "sttModel": "whisper-large-v3-turbo",
    "llmModel": "gpt-4o-mini",
    "apiKeys": {
        "groq": "",
        "openai": "",
        "anthropic": "",
        "ollama": "http://localhost:11434",
    },
    "hotkey": "RightAlt",
    "language": "auto",
    "outputMode": "clipboard",
    "autoStart": True,
    "removeFiller": True,
    "autoFormat": True,
    "contextAware": True,
    "dictionary": [],
    "systemPrompt": (
        "你是語音轉文字的編輯器。你的工作是清理口述文字的贅字和標點，僅此而已。\n\n"
        "=== 絕對禁止 ===\n"
        "- 禁止回答問題\n"
        "- 禁止提供建議\n"
        "- 禁止擴充內容\n"
        "- 禁止改變句型（問句必須保持問句，陳述必須保持陳述）\n\n"
        "=== 你的唯一工作 ===\n"
        "1. 移除口頭禪（嗯、啊、那個、就是說、然後）\n"
        "2. 加標點符號\n"
        "3. 修正明顯的語音辨識錯誤\n"
        "4. 輸出清理後的原文\n\n"
        "=== 範例 ===\n"
        "輸入：「那個呃我想問一下怎麼用那個 API」\n"
        "正確輸出：「我想問一下怎麼用那個 API？」\n"
        "錯誤輸出：「要使用 API，你可以...」❌（這是在回答，禁止）\n\n"
        "輸入：「嗯我覺得這個設計不太好」\n"
        "正確輸出：「我覺得這個設計不太好。」\n"
        "錯誤輸出：「建議可以改成...」❌（這是在提供建議，禁止）\n\n"
        "=== 格式規則 ===\n"
        "- 中文用繁體，不可用簡體\n"
        "- 英文單字前後加空格（例：使用 Python 開發）\n"
        "- 專有名詞大小寫正確（GitHub、API、iPhone）\n"
        "- 修正拼音化錯誤（「皮爾森」→ Python）\n\n"
        "記住：你只是清理文字，不是回答問題。用戶說什麼，你就輸出清理後的「什麼」。"
    ),
}

# 匯出預設系統提示詞，供 llm.py 等模組使用
DEFAULT_SYSTEM_PROMPT = DEFAULT_CONFIG["systemPrompt"]


class Settings:
    """設定管理器"""

    def __init__(self, config_dir: Path | None = None):
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Windows: %APPDATA%/voicetype
            # 其他: ~/.config/voicetype
            if os.name == "nt":
                base = os.environ.get("APPDATA", os.path.expanduser("~"))
            else:
                base = os.path.expanduser("~/.config")
            self.config_dir = Path(base) / "voicetype"

        self.config_path = self.config_dir / "config.json"
        self._config: dict = {}

    def load(self) -> dict:
        """載入設定檔，不存在則建立預設設定"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)

                # 合併預設值（確保新增欄位有預設值）
                self._config = {**DEFAULT_CONFIG, **saved}

                # 合併 apiKeys（避免缺少的 key）
                default_keys = DEFAULT_CONFIG.get("apiKeys", {})
                saved_keys = saved.get("apiKeys", {})
                self._config["apiKeys"] = {**default_keys, **saved_keys}

                logger.info("設定已載入: %s", self.config_path)
            except Exception as e:
                logger.error("設定檔讀取失敗: %s，使用預設值", e)
                self._config = DEFAULT_CONFIG.copy()
        else:
            logger.info("設定檔不存在，建立預設設定...")
            self._config = DEFAULT_CONFIG.copy()
            self.save()

        return self._config

    def save(self):
        """儲存設定到檔案"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)
        logger.info("設定已儲存: %s", self.config_path)

    def get_config(self) -> dict:
        """取得當前設定（若未載入則自動載入）"""
        if not self._config:
            self.load()
        return self._config

    def update(self, key: str, value):
        """更新單一設定值"""
        self._config[key] = value
        self.save()

    def update_all(self, new_config: dict):
        """批次更新設定"""
        self._config.update(new_config)
        self.save()

    def get_api_key(self, provider: str) -> str:
        """取得指定引擎的 API Key"""
        cfg = self.get_config()
        return cfg.get("apiKeys", {}).get(provider, "")

    def set_api_key(self, provider: str, key: str):
        """設定 API Key"""
        cfg = self.get_config()
        if "apiKeys" not in cfg:
            cfg["apiKeys"] = {}
        cfg["apiKeys"][provider] = key
        self.save()

    def validate(self) -> list[str]:
        """驗證設定值，回傳警告訊息列表"""
        warnings = []
        cfg = self._config
        if cfg.get("sttProvider") not in VALID_STT_PROVIDERS:
            warnings.append(f"Invalid STT provider: {cfg.get('sttProvider')}")
        if cfg.get("llmProvider") not in VALID_LLM_PROVIDERS:
            warnings.append(f"Invalid LLM provider: {cfg.get('llmProvider')}")
        if cfg.get("hotkey") not in VALID_HOTKEYS:
            warnings.append(f"Invalid hotkey: {cfg.get('hotkey')}")
        if cfg.get("language") not in VALID_LANGUAGES:
            warnings.append(f"Invalid language: {cfg.get('language')}")
        return warnings
