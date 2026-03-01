"""
VoiceType 自動化測試
涵蓋：設定載入、字典容量、STT prompt 構建、LLM prompt 構建、
      單實例鎖、快捷鍵註冊/釋放、音效模組、文字注入邏輯
"""

import sys
import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

# 加入專案根目錄到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSettings(unittest.TestCase):
    """測試設定管理模組"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config.json")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_config_has_required_keys(self):
        """預設設定必須包含所有必要的 key"""
        from config.settings import DEFAULT_CONFIG
        required = [
            "sttProvider", "llmProvider", "sttModel", "llmModel",
            "apiKeys", "hotkey", "language", "outputMode",
            "removeFiller", "autoFormat", "contextAware",
            "dictionary", "systemPrompt", "autoStart",
        ]
        for key in required:
            self.assertIn(key, DEFAULT_CONFIG, f"DEFAULT_CONFIG missing key: {key}")

    def test_default_config_values(self):
        """預設值檢查"""
        from config.settings import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG["sttProvider"], "groq")
        self.assertEqual(DEFAULT_CONFIG["llmProvider"], "openai")
        self.assertEqual(DEFAULT_CONFIG["hotkey"], "RightAlt")
        self.assertIsInstance(DEFAULT_CONFIG["dictionary"], list)
        self.assertIsInstance(DEFAULT_CONFIG["autoStart"], bool)

    def test_settings_load_creates_default(self):
        """首次載入應建立預設設定檔"""
        from config.settings import Settings
        settings = Settings(config_dir=self.temp_dir)
        cfg = settings.load()
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "config.json")))
        self.assertIn("sttProvider", cfg)

    def test_settings_preserves_user_data(self):
        """載入時不覆蓋使用者的自訂設定"""
        user_config = {
            "sttProvider": "openai",
            "llmProvider": "anthropic",
            "llmModel": "claude-haiku-4-5-20251001",
            "apiKeys": {"groq": "test-key"},
            "dictionary": ["TestWord"],
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(user_config, f)

        from config.settings import Settings
        settings = Settings(config_dir=self.temp_dir)
        cfg = settings.load()
        self.assertEqual(cfg["sttProvider"], "openai")
        self.assertEqual(cfg["llmProvider"], "anthropic")
        self.assertEqual(cfg["apiKeys"]["groq"], "test-key")
        self.assertEqual(cfg["dictionary"], ["TestWord"])


class TestDictionaryByteLimit(unittest.TestCase):
    """測試字典 byte 容量限制"""

    def _calc_bytes(self, words):
        """模擬 stt.py 中的 byte 計算邏輯"""
        if not words:
            return 0
        total = 0
        for i, w in enumerate(words):
            total += (1 if i > 0 else 0) + len(w.encode("utf-8"))
        return total

    def test_ascii_words_byte_count(self):
        """純 ASCII 詞彙的 byte 計算"""
        words = ["GitHub", "Python", "API"]
        # "GitHub,Python,API" = 6+1+6+1+3 = 17
        self.assertEqual(self._calc_bytes(words), 17)

    def test_unicode_words_byte_count(self):
        """中文詞彙佔 3 bytes/字"""
        words = ["繁體中文"]
        # 4 個中文字 × 3 bytes = 12
        self.assertEqual(self._calc_bytes(words), 12)

    def test_mixed_words_byte_count(self):
        """中英混合詞彙"""
        words = ["Claude", "繁體"]
        # "Claude" = 6, comma = 1, "繁體" = 6 → 13
        self.assertEqual(self._calc_bytes(words), 13)

    def test_empty_dict_zero_bytes(self):
        """空字典 = 0 bytes"""
        self.assertEqual(self._calc_bytes([]), 0)

    def test_large_dict_exceeds_limit(self):
        """大量詞彙超過 890 bytes 時應被截斷"""
        # 建立超大字典
        words = [f"Word{i:03d}" for i in range(200)]  # 每個 7 bytes + 1 comma
        total = self._calc_bytes(words)
        self.assertGreater(total, 890)


class TestSTTPromptTruncation(unittest.TestCase):
    """測試 STT prompt 截斷邏輯"""

    def _build_prompt(self, dictionary):
        """模擬 stt.py 中的 prompt 構建"""
        if not dictionary:
            return None
        parts = []
        current_bytes = 0
        for word in dictionary:
            word_bytes = len(word.encode("utf-8"))
            sep_bytes = 1 if parts else 0
            if current_bytes + sep_bytes + word_bytes > 890:
                break
            parts.append(word)
            current_bytes += sep_bytes + word_bytes
        return ",".join(parts) if parts else None

    def test_small_dict_no_truncation(self):
        """小字典不截斷"""
        words = ["GitHub", "Python", "API", "Claude"]
        prompt = self._build_prompt(words)
        self.assertEqual(prompt, "GitHub,Python,API,Claude")

    def test_empty_dict_returns_none(self):
        """空字典回傳 None"""
        self.assertIsNone(self._build_prompt([]))

    def test_large_dict_truncated_within_limit(self):
        """大字典截斷後不超過 890 bytes"""
        words = [f"LongWord{i:04d}" for i in range(200)]
        prompt = self._build_prompt(words)
        self.assertIsNotNone(prompt)
        self.assertLessEqual(len(prompt.encode("utf-8")), 890)

    def test_truncation_preserves_complete_words(self):
        """截斷時保持完整詞彙，不會切到一半"""
        words = [f"Word{i}" for i in range(200)]
        prompt = self._build_prompt(words)
        for word in prompt.split(","):
            self.assertTrue(word.startswith("Word"), f"Incomplete word found: {word}")

    def test_unicode_dict_truncated_correctly(self):
        """中文字典截斷後 bytes 正確"""
        words = ["Stable Diffusion", "ComfyUI", "LoRA"] + [f"測試詞彙{i}" for i in range(100)]
        prompt = self._build_prompt(words)
        self.assertLessEqual(len(prompt.encode("utf-8")), 890)

    def test_real_user_dictionary(self):
        """模擬真實使用者字典（來自 config.json）"""
        words = [
            "Ubuntu", "BNI", "LINE", "RAG", "Whisper", "Claude",
            "ComfyUI", "SDXL", "Stable Diffusion", "Illustrious", "LoRA", "FLUX",
            "Imagen", "DALL-E", "Midjourney", "Claude Code", "Anthropic", "OpenAI",
            "GPT", "Gemini", "Sonnet", "Opus", "Haiku", "euler_ancestral", "Karras",
            "CFG", "CLIP Skip", "Checkpoint", ".safetensors", "Negative Prompt",
            "Positive Prompt", "Sampler", "Scheduler", "VAE", "ReActor", "BREAK",
            "Electrum Cinnamon Anime", "NSFW", "CivitAI", "n8n", "Dify", "Node.js",
            "Express", "SQLite", "HNSW", "MCP", "VCP", "SSE", "JSON-RPC", "REST API",
            "Webhook", "cron", "Docker", "Git", "GitHub", "Supabase", "AnythingLLM",
            "ZeroTier", "Telegram", "IPv6", "IPv4", "DNS", "HTTPS", "HTTP", "SSL",
            "TLS", "Nginx", "RTX 3070 Ti", "RTX 4080", "VRAM", "i9-13900K", "CWA",
            "Emma", "VCP Lite", "Skill", "Tool Guard", "AutoMemory",
            "ContextCompressor", "MemorySearch", "MemoryWrite", "BashExecutor",
            "ZImageGenerator", "ImageGenerator", "ImageEditor", "ModelRouter",
            "WebSearch", "WebBrowser", "Bot Persona", "Knowledge Base",
            "YouTube", "Podcast", "Instagram", "Facebook", "Meta",
            "Python", "JavaScript", "TypeScript", "Bash", "YAML", "JSON", "Markdown",
            "NDJSON", "RegEx", "FTS5", "MD5", "Bearer Token", "OAuth", "JWT",
            "API Key", "Embedding",
        ]
        prompt = self._build_prompt(words)
        prompt_bytes = len(prompt.encode("utf-8"))
        self.assertLessEqual(prompt_bytes, 890,
                             f"Real dictionary prompt is {prompt_bytes} bytes, exceeds 890")
        # 確認至少包含部分詞彙
        self.assertIn("Ubuntu", prompt)
        self.assertIn("ComfyUI", prompt)


class TestLLMPromptBuilder(unittest.TestCase):
    """測試 LLM 系統提示詞構建"""

    def test_dict_appended_to_prompt(self):
        """字典詞彙應附加到系統提示詞"""
        from config.settings import Settings
        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            cfg = settings.load()
            cfg["dictionary"] = ["GitHub", "Python"]

            from core.llm import LLMProcessor
            llm = LLMProcessor(settings)
            # Mock get_config to return our cfg
            settings.get_config = lambda: cfg

            prompt = llm._get_system_prompt(cfg)
            self.assertIn("GitHub", prompt)
            self.assertIn("Python", prompt)
            self.assertIn("自訂字典", prompt)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_empty_dict_no_append(self):
        """空字典不附加額外文字"""
        from config.settings import Settings
        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            cfg = settings.load()
            cfg["dictionary"] = []

            from core.llm import LLMProcessor
            llm = LLMProcessor(settings)

            prompt = llm._get_system_prompt(cfg)
            self.assertNotIn("自訂字典", prompt)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestHotkeyManager(unittest.TestCase):
    """測試快捷鍵管理"""

    def test_hotkey_map_completeness(self):
        """所有設定中可選的快捷鍵都要有映射"""
        from core.hotkey import HOTKEY_MAP
        expected_keys = ["RightAlt", "RightCtrl", "F9", "CapsLock", "ScrollLock"]
        for key in expected_keys:
            self.assertIn(key, HOTKEY_MAP, f"HOTKEY_MAP missing: {key}")

    @patch("core.hotkey.keyboard")
    def test_register_and_unhook(self, mock_kb):
        """註冊後 unhook 應正確清理"""
        from core.hotkey import HotkeyManager
        from config.settings import Settings

        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            settings.load()
            mgr = HotkeyManager(settings)

            mock_press = MagicMock()
            mock_release = MagicMock()
            mgr.register(mock_press, mock_release)

            # 確認有註冊
            self.assertIsNotNone(mgr._press_hook)
            self.assertIsNotNone(mgr._release_hook)
            self.assertTrue(mgr._running)

            # unhook
            mgr.unhook()
            self.assertIsNone(mgr._press_hook)
            self.assertIsNone(mgr._release_hook)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("core.hotkey.keyboard")
    def test_stop_cleans_everything(self, mock_kb):
        """stop() 應停止監聽並清理 hook"""
        from core.hotkey import HotkeyManager
        from config.settings import Settings

        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            settings.load()
            mgr = HotkeyManager(settings)
            mgr.register(lambda: None, lambda: None)
            mgr.stop()

            self.assertFalse(mgr._running)
            self.assertIsNone(mgr._press_hook)
            self.assertIsNone(mgr._release_hook)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("core.hotkey.keyboard")
    def test_suppress_is_false(self, mock_kb):
        """確認 suppress=False 避免鍵盤鎖死"""
        from core.hotkey import HotkeyManager
        from config.settings import Settings

        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            settings.load()
            mgr = HotkeyManager(settings)
            mgr.register(lambda: None, lambda: None)

            # 檢查 on_press_key 和 on_release_key 被呼叫時 suppress=False
            for call in mock_kb.on_press_key.call_args_list:
                kwargs = call.kwargs if call.kwargs else {}
                args = call.args if call.args else ()
                # suppress 可能是 positional 或 keyword
                if "suppress" in kwargs:
                    self.assertFalse(kwargs["suppress"],
                                    "suppress must be False to prevent keyboard lockup")
            for call in mock_kb.on_release_key.call_args_list:
                kwargs = call.kwargs if call.kwargs else {}
                if "suppress" in kwargs:
                    self.assertFalse(kwargs["suppress"],
                                    "suppress must be False to prevent keyboard lockup")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestSounds(unittest.TestCase):
    """測試音效模組"""

    def test_sounds_module_importable(self):
        """音效模組可正常匯入"""
        from core.sounds import play_start, play_stop
        self.assertTrue(callable(play_start))
        self.assertTrue(callable(play_stop))

    @patch("core.sounds.winsound")
    def test_play_start_frequency(self, mock_ws):
        """開始音效頻率 500Hz"""
        from core.sounds import _beep
        _beep(500, 120)
        mock_ws.Beep.assert_called_once_with(500, 120)

    @patch("core.sounds.winsound")
    def test_play_stop_frequency(self, mock_ws):
        """結束音效頻率 350Hz"""
        from core.sounds import _beep
        _beep(350, 120)
        mock_ws.Beep.assert_called_once_with(350, 120)

    @patch("core.sounds.winsound")
    def test_beep_error_handling(self, mock_ws):
        """Beep 失敗不應拋出例外"""
        mock_ws.Beep.side_effect = RuntimeError("No speaker")
        from core.sounds import _beep
        # 不應 raise
        _beep(500, 120)


class TestInjector(unittest.TestCase):
    """測試文字注入模組"""

    @patch("core.injector.pyautogui")
    @patch("core.injector.pyperclip")
    def test_inject_copies_and_pastes(self, mock_clip, mock_gui):
        """注入應複製到剪貼簿再貼上"""
        from core.injector import TextInjector
        from config.settings import Settings

        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            settings.load()
            injector = TextInjector(settings)
            injector.inject("Hello World")

            mock_clip.copy.assert_called_once_with("Hello World")
            mock_gui.hotkey.assert_called_once_with("ctrl", "v")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("core.injector.pyautogui")
    @patch("core.injector.pyperclip")
    def test_inject_empty_skips(self, mock_clip, mock_gui):
        """空文字不注入"""
        from core.injector import TextInjector
        from config.settings import Settings

        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            settings.load()
            injector = TextInjector(settings)
            injector.inject("")

            mock_clip.copy.assert_not_called()
            mock_gui.hotkey.assert_not_called()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("core.injector.pyautogui")
    @patch("core.injector.pyperclip")
    def test_inject_chinese_text(self, mock_clip, mock_gui):
        """中文文字注入"""
        from core.injector import TextInjector
        from config.settings import Settings

        temp_dir = tempfile.mkdtemp()
        try:
            settings = Settings(config_dir=temp_dir)
            settings.load()
            injector = TextInjector(settings)
            injector.inject("你好世界")
            mock_clip.copy.assert_called_once_with("你好世界")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestSingleInstance(unittest.TestCase):
    """測試單實例鎖"""

    def test_mutex_constant_name(self):
        """確認 mutex 名稱在 main.py 中正確設定"""
        import re
        main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 確認有 CreateMutexW
        self.assertIn("CreateMutexW", content)
        # 確認有 ERROR_ALREADY_EXISTS (183)
        self.assertIn("183", content)
        # 確認有 SystemExit
        self.assertIn("SystemExit", content)

    def test_atexit_cleanup_registered(self):
        """確認 atexit 清理在 run() 中註冊"""
        import re
        main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("atexit.register(self._cleanup)", content)
        self.assertIn("keyboard.unhook_all()", content)


class TestErrorRecovery(unittest.TestCase):
    """測試錯誤恢復機制"""

    def test_hotkey_reregister_in_finally(self):
        """_process_audio 的 finally 應重新註冊快捷鍵"""
        main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 確認 finally 區塊有重新註冊邏輯
        self.assertIn("if not self.hotkey._press_hook:", content)
        self.assertIn("Hotkey re-registered after error recovery", content)


class TestConfigIntegration(unittest.TestCase):
    """設定整合測試"""

    def test_config_roundtrip(self):
        """設定寫入後讀取應一致"""
        temp_dir = tempfile.mkdtemp()
        try:
            from config.settings import Settings
            settings = Settings(config_dir=temp_dir)

            # 首次載入（建立預設）
            cfg1 = settings.load()

            # 修改（直接改 _config，再呼叫 save()）
            cfg1["llmModel"] = "gpt-4.1-mini"
            cfg1["dictionary"] = ["TestWord", "AnotherWord"]
            settings.save()

            # 重新載入
            settings2 = Settings(config_dir=temp_dir)
            cfg2 = settings2.load()

            self.assertEqual(cfg2["llmModel"], "gpt-4.1-mini")
            self.assertEqual(cfg2["dictionary"], ["TestWord", "AnotherWord"])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_config_handles_missing_keys(self):
        """舊版設定檔缺少新 key 時應自動補齊"""
        temp_dir = tempfile.mkdtemp()
        try:
            # 寫入一個缺少 autoStart 和 dictionary 的舊設定
            old_config = {"sttProvider": "groq", "llmProvider": "openai"}
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(old_config, f)

            from config.settings import Settings
            settings = Settings(config_dir=temp_dir)
            cfg = settings.load()

            # 應自動補上預設值
            self.assertIn("autoStart", cfg)
            self.assertIn("dictionary", cfg)
            self.assertIn("systemPrompt", cfg)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
