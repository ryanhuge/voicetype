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
        self._target_hwnd = None

    def polish(self, raw_text: str, target_hwnd=None) -> str:
        """將 STT 原始文字修飾為乾淨的輸出"""
        cfg = self.settings.get_config()
        provider = cfg.get("llmProvider", "openai")

        # 儲存目標視窗供 _detect_context 使用
        self._target_hwnd = target_hwnd

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
            # 使用快取的 hwnd，避免再次呼叫 GetForegroundWindow（此時焦點可能已改變）
            hwnd = getattr(self, '_target_hwnd', None)
            if not hwnd:
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

    # ── OpenAI 相容介面的參數相容處理 ────────────────────────────────────────

    # 每個 (模型, 推理強度) 第一次呼叫時協商出可用的參數組合，之後直接沿用；
    # 否則不支援 reasoning_effort 的模型每次口述都要白花一趟往返。
    _param_cache = {}

    @classmethod
    def _chat_with_fallback(cls, client, model, messages, effort):
        """呼叫 OpenAI 相容的 chat completions，自動吸收各模型的參數差異。

        gpt-5 以後的模型不接受 max_tokens，必須改用 max_completion_tokens；
        而指定 reasoning_effort 時又不可同時送出 temperature。各家模型支援的
        參數子集並不一致，被拒絕的參數會自動拿掉重送，避免換個模型就讓整個
        語意修正失效。
        """
        from openai import BadRequestError

        key = (model, effort)
        if key in cls._param_cache:
            send_reasoning, send_temperature, legacy_tokens = cls._param_cache[key]
        else:
            send_reasoning = bool(effort) and effort != "unspecified"
            send_temperature = not send_reasoning
            legacy_tokens = False

        while True:
            kwargs = {"model": model, "messages": messages}
            kwargs["max_tokens" if legacy_tokens else "max_completion_tokens"] = 4096
            if send_reasoning:
                kwargs["reasoning_effort"] = effort
            if send_temperature:
                kwargs["temperature"] = 0.1   # 極低溫度：嚴格遵守指令

            try:
                response = client.chat.completions.create(**kwargs)
                cls._param_cache[key] = (send_reasoning, send_temperature, legacy_tokens)
                return response
            except BadRequestError as exc:
                detail = str(exc)
                if "reasoning_effort" in detail and send_reasoning:
                    send_reasoning, send_temperature = False, True
                elif "temperature" in detail and send_temperature:
                    send_temperature = False
                elif "max_completion_tokens" in detail and not legacy_tokens:
                    legacy_tokens = True
                else:
                    raise

    # ── OpenAI ChatGPT ───────────────────────────────────────────────────────

    def _polish_openai(self, raw_text: str, cfg: dict) -> str:
        from openai import OpenAI

        api_key = self.settings.get_api_key("openai")
        if not api_key:
            raise ValueError("OpenAI API Key 未設定")

        client = OpenAI(api_key=api_key)
        model = cfg.get("llmModel", "gpt-5.4-nano")
        effort = cfg.get("llmReasoningEffort", "low")
        system_prompt = self._get_system_prompt(cfg)

        response = self._chat_with_fallback(
            client,
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            effort,
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
        model = cfg.get("llmModel", "openai/gpt-oss-20b")
        system_prompt = self._get_system_prompt(cfg)

        # Groq 端多數模型不吃 reasoning_effort，直接不送，免得每次呼叫都多一趟往返
        response = self._chat_with_fallback(
            client,
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            None,
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
                "options": {"temperature": 0.1},  # 極低溫度：嚴格遵守指令
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"].strip()
