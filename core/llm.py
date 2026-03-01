"""
LLM 智能修飾模組
將 STT 原始文字送給 LLM 進行去贅字、修正、格式化
支援 OpenAI ChatGPT、Anthropic Claude、Groq、Ollama
"""

import logging

from config.settings import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger("VoiceType.LLM")


class LLMProcessor:
    """LLM 文字修飾引擎"""

    def __init__(self, settings):
        self.settings = settings

    def polish(self, raw_text: str) -> str:
        """將 STT 原始文字修飾為乾淨的輸出"""
        cfg = self.settings.get_config()
        provider = cfg.get("llmProvider", "openai")

        # 如果文字很短且乾淨，可以跳過 LLM
        if len(raw_text.strip()) < 3:
            return raw_text.strip()

        try:
            if provider == "openai":
                return self._polish_openai(raw_text, cfg)
            elif provider == "anthropic":
                return self._polish_anthropic(raw_text, cfg)
            elif provider == "groq":
                return self._polish_groq(raw_text, cfg)
            elif provider == "ollama":
                return self._polish_ollama(raw_text, cfg)
            else:
                logger.warning("未知 LLM 引擎 %s，直接輸出原文", provider)
                return raw_text.strip()
        except Exception as e:
            logger.error("LLM 修飾失敗: %s，回退為原文", e)
            return raw_text.strip()

    def _get_system_prompt(self, cfg: dict) -> str:
        """取得系統提示詞（含語境資訊與自訂字典）"""
        base_prompt = cfg.get("systemPrompt", DEFAULT_SYSTEM_PROMPT)

        # 自訂字典：讓 LLM 知道這些專有名詞的正確寫法
        dictionary = cfg.get("dictionary", [])
        if dictionary:
            words = "、".join(dictionary)
            base_prompt += (
                f"\n\n自訂字典（請確保這些詞彙使用正確的拼寫和大小寫）：\n{words}"
            )

        # 語境適應：偵測當前 App
        if cfg.get("contextAware", True):
            context = self._detect_context()
            if context:
                base_prompt += f"\n\n當前語境：{context}"

        return base_prompt

    def _detect_context(self) -> str:
        """偵測當前使用的 App 來調整語氣"""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).lower()

            if any(k in title for k in ["outlook", "gmail", "mail", "thunderbird"]):
                return "用戶正在撰寫郵件，語氣應正式專業"
            elif any(k in title for k in ["discord", "line", "messenger", "telegram", "whatsapp"]):
                return "用戶正在聊天，語氣可以輕鬆口語"
            elif any(k in title for k in ["slack", "teams"]):
                return "用戶在工作通訊軟體，語氣應簡潔專業"
            elif any(k in title for k in ["word", "docs", "notion", "obsidian"]):
                return "用戶在撰寫文件，語氣應清晰有條理"
            elif any(k in title for k in ["code", "vscode", "visual studio", "pycharm"]):
                return "用戶在寫程式，可能是在寫註解或文件，語氣應技術性簡潔"
        except Exception:
            pass
        return ""

    # ── OpenAI ChatGPT ───────────────────────────────────────────────────────

    def _polish_openai(self, raw_text: str, cfg: dict) -> str:
        from openai import OpenAI

        api_key = self.settings.get_api_key("openai")
        if not api_key:
            raise ValueError("OpenAI API Key 未設定")

        client = OpenAI(api_key=api_key)
        model = cfg.get("llmModel", "gpt-4o-mini")
        system_prompt = self._get_system_prompt(cfg)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            temperature=0.3,  # 低溫度：忠於原意
            max_tokens=2048,
        )

        return response.choices[0].message.content.strip()

    # ── Anthropic Claude ─────────────────────────────────────────────────────

    def _polish_anthropic(self, raw_text: str, cfg: dict) -> str:
        import anthropic

        api_key = self.settings.get_api_key("anthropic")
        if not api_key:
            raise ValueError("Anthropic API Key 未設定")

        client = anthropic.Anthropic(api_key=api_key)
        model = cfg.get("llmModel", "claude-haiku-4-5-20251001")
        system_prompt = self._get_system_prompt(cfg)

        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {"role": "user", "content": raw_text},
            ],
        )

        return response.content[0].text.strip()

    # ── Groq（OpenAI 相容）───────────────────────────────────────────────────

    def _polish_groq(self, raw_text: str, cfg: dict) -> str:
        from openai import OpenAI

        api_key = self.settings.get_api_key("groq")
        if not api_key:
            raise ValueError("Groq API Key 未設定")

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        model = cfg.get("llmModel", "llama-3.3-70b-versatile")
        system_prompt = self._get_system_prompt(cfg)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            temperature=0.3,
            max_tokens=2048,
        )

        return response.choices[0].message.content.strip()

    # ── Ollama 本地 ──────────────────────────────────────────────────────────

    def _polish_ollama(self, raw_text: str, cfg: dict) -> str:
        import requests

        endpoint = self.settings.get_api_key("ollama") or "http://localhost:11434"
        model = cfg.get("llmModel", "qwen3:8b")
        system_prompt = self._get_system_prompt(cfg)

        response = requests.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_text},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"].strip()
