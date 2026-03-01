"""
語音轉文字模組 (Speech-to-Text)
支援 Groq Whisper、OpenAI Whisper、本地 Whisper
"""

import io
import logging
import numpy as np
from core.recorder import audio_to_wav_bytes

logger = logging.getLogger("VoiceType.STT")

# Whisper 使用 ISO 639-1 語言碼
LANGUAGE_MAP = {"zh-TW": "zh", "zh-CN": "zh", "en": "en", "ja": "ja"}


class SpeechToText:
    """語音轉文字引擎"""

    def __init__(self, settings):
        self.settings = settings

    def transcribe(self, audio: np.ndarray) -> str:
        """將音訊轉為文字"""
        cfg = self.settings.get_config()
        provider = cfg.get("sttProvider", "groq")
        model = cfg.get("sttModel", "whisper-large-v3-turbo")
        language = cfg.get("language", "auto")
        dictionary = cfg.get("dictionary", [])

        # 組合自訂詞彙作為 Whisper prompt（Groq 限制 896 bytes）
        whisper_prompt = None
        if dictionary:
            # 用逗號分隔（1 byte）而非「、」（3 bytes）節省空間
            parts = []
            current_bytes = 0
            for word in dictionary:
                word_bytes = len(word.encode("utf-8"))
                sep_bytes = 1 if parts else 0  # 逗號 1 byte
                if current_bytes + sep_bytes + word_bytes > 890:
                    logger.warning("Dictionary prompt truncated at %d bytes (limit 896)", current_bytes)
                    break
                parts.append(word)
                current_bytes += sep_bytes + word_bytes
            whisper_prompt = ",".join(parts) if parts else None

        if provider == "groq":
            return self._transcribe_groq(audio, model, language, whisper_prompt)
        elif provider == "openai":
            return self._transcribe_openai(audio, model, language, whisper_prompt)
        elif provider == "local":
            return self._transcribe_local(audio, model, language)
        else:
            raise ValueError(f"不支援的 STT 引擎: {provider}")

    # ── Groq Whisper ─────────────────────────────────────────────────────────

    def _transcribe_groq(self, audio, model, language, prompt):
        """使用 Groq API 進行語音辨識（OpenAI 相容介面）"""
        from openai import OpenAI

        api_key = self.settings.get_api_key("groq")
        if not api_key:
            raise ValueError("Groq API Key 未設定")

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        wav_bytes = audio_to_wav_bytes(audio)
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "recording.wav"

        kwargs = {
            "model": model,
            "file": audio_file,
            "response_format": "text",
        }
        if language and language != "auto":
            # Whisper 使用 ISO 639-1 語言碼
            kwargs["language"] = LANGUAGE_MAP.get(language, language)
        if prompt:
            kwargs["prompt"] = prompt

        result = client.audio.transcriptions.create(**kwargs)
        return result.strip() if isinstance(result, str) else result.text.strip()

    # ── OpenAI Whisper ───────────────────────────────────────────────────────

    def _transcribe_openai(self, audio, model, language, prompt):
        """使用 OpenAI Whisper API"""
        from openai import OpenAI

        api_key = self.settings.get_api_key("openai")
        if not api_key:
            raise ValueError("OpenAI API Key 未設定")

        client = OpenAI(api_key=api_key)

        wav_bytes = audio_to_wav_bytes(audio)
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "recording.wav"

        kwargs = {
            "model": model,
            "file": audio_file,
            "response_format": "text",
        }
        if language and language != "auto":
            kwargs["language"] = LANGUAGE_MAP.get(language, language)
        if prompt:
            kwargs["prompt"] = prompt

        result = client.audio.transcriptions.create(**kwargs)
        return result.strip() if isinstance(result, str) else result.text.strip()

    # ── 本地 Whisper ─────────────────────────────────────────────────────────

    def _transcribe_local(self, audio, model, language):
        """使用本地 faster-whisper 模型"""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "本地 Whisper 需要安裝 faster-whisper：\n"
                "pip install faster-whisper --break-system-packages"
            )

        # 快取模型實例
        if not hasattr(self, "_local_model") or self._local_model_name != model:
            logger.info("載入本地 Whisper 模型: %s ...", model)
            self._local_model = WhisperModel(model, device="auto", compute_type="auto")
            self._local_model_name = model

        # faster-whisper 需要 float32 音訊
        audio_f32 = audio.astype(np.float32) / 32768.0

        kwargs = {"beam_size": 5}
        if language and language != "auto":
            kwargs["language"] = LANGUAGE_MAP.get(language, language)

        segments, info = self._local_model.transcribe(audio_f32, **kwargs)
        text = " ".join(seg.text for seg in segments)
        return text.strip()
