"""
VoiceType - 類 Typeless 語音輸入工具
主程式：系統托盤常駐 + 快捷鍵監聽 + 語音處理管線

使用方式：
  1. 設定 config/config.json 中的 API Key
  2. python main.py
  3. 按住 Right Alt 說話，放開即輸出
"""

import ctypes
# 在 import sounddevice 之前初始化 COM 為 STA 模式
# 避免 PortAudio 將 COM 初始化為 MTA，導致 SendInput 無法被 Chrome 接收
ctypes.windll.ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED

# ── 單實例鎖 ─────────────────────────────────────────────────────────────────
# 使用 Windows Named Mutex 確保只有一個 VoiceType 在執行
_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\VoiceType_SingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    ctypes.windll.user32.MessageBoxW(
        None, "VoiceType 已在執行中。\n請檢查系統托盤。", "VoiceType", 0x40
    )
    raise SystemExit(0)

import atexit
import threading
import os
import sys
import time
import logging

from core.recorder import AudioRecorder
from core.stt import SpeechToText
from core.llm import LLMProcessor
from core.injector import TextInjector
from core.hotkey import HotkeyManager
from core.tray_icons import create_tray_icon
from core.sounds import play_start, play_stop
from config.settings import Settings

# ── 常數 ─────────────────────────────────────────────────────────────────────
MIN_RECORDING_SECONDS = 0.3
INJECT_DELAY_SECONDS = 0.3
ERROR_DISPLAY_SECONDS = 3

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("VoiceType")


class VoiceType:
    """主應用程式類別"""

    def __init__(self):
        self.settings = Settings()
        self.recorder = AudioRecorder()
        self.stt = SpeechToText(self.settings)
        self.llm = LLMProcessor(self.settings)
        self.injector = TextInjector(self.settings)
        self.hotkey = HotkeyManager(self.settings)
        self.is_recording = False
        self.processing = False
        self.tray_icon = None
        self._target_hwnd = None

    # ── 快捷鍵回呼 ───────────────────────────────────────────────────────────

    def on_hotkey_press(self):
        """快捷鍵按下：開始錄音"""
        if self.is_recording or self.processing:
            return
        # 記住目前的前景視窗（使用者正在操作的視窗）
        self._target_hwnd = ctypes.windll.user32.GetForegroundWindow()
        self.is_recording = True
        play_start()
        self.recorder.start()
        logger.info("Recording started...")
        self._update_tray("錄音中...", "recording")

    def on_hotkey_release(self):
        """快捷鍵釋放：停止錄音 → STT → LLM → 注入"""
        if not self.is_recording:
            return
        self.is_recording = False
        self.processing = True
        play_stop()

        # 立即按 Escape 取消瀏覽器的 Alt 選單激活（suppress=False 時 Alt 會穿透）
        try:
            import pyautogui
            pyautogui.press("escape")
        except Exception:
            pass

        audio_data = self.recorder.stop()
        logger.info("Recording stopped (%.1f sec), processing...", len(audio_data) / 16000)
        self._update_tray("處理中...", "processing")

        # 背景執行緒處理，避免阻塞快捷鍵
        threading.Thread(target=self._process_audio, args=(audio_data,), daemon=True).start()

    # ── 語音處理管線 ─────────────────────────────────────────────────────────

    def _process_audio(self, audio_data):
        """STT → LLM → 文字注入"""
        # 背景執行緒也需要初始化 COM 為 STA（httpx 可能會改變 COM 模式）
        ctypes.windll.ole32.CoInitializeEx(None, 2)
        try:
            # 太短的錄音直接跳過
            duration = len(audio_data) / 16000
            if duration < MIN_RECORDING_SECONDS:
                logger.warning("Recording too short (%.1fs), skipped", duration)
                self._reset_status()
                return

            # 步驟 1：語音轉文字
            t0 = time.time()
            raw_text = self.stt.transcribe(audio_data)
            stt_time = time.time() - t0

            if not raw_text or not raw_text.strip():
                logger.warning("No text recognized")
                self._reset_status()
                return

            logger.info("Raw text (%.1fs): %s", stt_time, raw_text)

            # 步驟 2：LLM 智能修飾
            t1 = time.time()
            polished = self.llm.polish(raw_text)
            llm_time = time.time() - t1
            logger.info("Polished (%.1fs): %s", llm_time, polished)

            # 步驟 3：暫停 keyboard hook → 恢復前景視窗 → 注入 → 重新註冊
            self.hotkey.unhook()
            time.sleep(INJECT_DELAY_SECONDS)

            # 恢復使用者原本操作的視窗到前景
            if self._target_hwnd:
                try:
                    ctypes.windll.user32.SetForegroundWindow(self._target_hwnd)
                    time.sleep(0.05)
                except Exception:
                    pass

            self.injector.inject(polished)

            # 重新註冊快捷鍵
            self.hotkey.register(
                on_press=self.on_hotkey_press,
                on_release=self.on_hotkey_release,
            )

            total = time.time() - t0
            logger.info("Done! Total %.1fs (STT %.1fs + LLM %.1fs)", total, stt_time, llm_time)

        except Exception as e:
            logger.error("Processing failed: %s", e, exc_info=True)
            self._update_tray("錯誤", "error")
            time.sleep(ERROR_DISPLAY_SECONDS)

        finally:
            # 確保快捷鍵一定會重新註冊，否則 VoiceType 會停止回應
            if not self.hotkey._press_hook:
                try:
                    self.hotkey.register(
                        on_press=self.on_hotkey_press,
                        on_release=self.on_hotkey_release,
                    )
                    logger.info("Hotkey re-registered after error recovery")
                except Exception as e2:
                    logger.error("Failed to re-register hotkey: %s", e2)
            self._reset_status()

    # ── 輔助方法 ─────────────────────────────────────────────────────────────

    def _update_tray(self, status_text: str, state: str = "idle"):
        """更新系統列圖標外觀與提示文字"""
        if self.tray_icon:
            self.tray_icon.title = f"VoiceType - {status_text}"
            try:
                self.tray_icon.icon = create_tray_icon(state)
            except Exception:
                pass  # 圖標更新非關鍵功能

    def _reset_status(self):
        self.processing = False
        self._update_tray("就緒", "idle")

    def _create_tray_icon(self):
        """建立系統托盤圖示"""
        try:
            import pystray

            img = create_tray_icon("idle")

            menu = pystray.Menu(
                pystray.MenuItem("VoiceType v0.1.0", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("開啟設定", self._open_settings),
                pystray.MenuItem("設定檔位置", self._open_config_dir),
                pystray.MenuItem("重新載入設定", self._reload_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("結束", self._quit),
            )

            self.tray_icon = pystray.Icon("VoiceType", img, "VoiceType - 就緒", menu)
            return self.tray_icon

        except ImportError:
            logger.warning("pystray not installed, tray icon disabled")
            return None

    def _open_settings(self, icon=None, item=None):
        """開啟後臺設定頁面"""
        try:
            from config.settings_server import start_settings_server
            start_settings_server(self.settings, port=18923)
            logger.info("Settings page opened")
        except Exception as e:
            logger.error("Failed to open settings: %s", e)

    def _open_config_dir(self, icon=None, item=None):
        config_dir = self.settings.config_dir
        if sys.platform == "win32":
            os.startfile(str(config_dir))

    def _reload_settings(self, icon=None, item=None):
        """重新載入設定"""
        self.settings.load()
        self.stt = SpeechToText(self.settings)
        self.llm = LLMProcessor(self.settings)
        self.injector = TextInjector(self.settings)
        # 重新註冊快捷鍵
        self.hotkey.stop()
        self.hotkey = HotkeyManager(self.settings)
        self.hotkey.register(
            on_press=self.on_hotkey_press,
            on_release=self.on_hotkey_release,
        )
        logger.info("Settings reloaded")

    def _quit(self, icon=None, item=None):
        logger.info("Shutting down VoiceType...")
        self.hotkey.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        sys.exit(0)

    # ── 啟動 ─────────────────────────────────────────────────────────────────

    def _cleanup(self):
        """確保程式退出時釋放所有鍵盤 hook，防止鍵盤卡住"""
        try:
            self.hotkey.stop()
            import keyboard
            keyboard.unhook_all()
            logger.info("Keyboard hooks cleaned up")
        except Exception:
            pass

    def run(self):
        cfg = self.settings.load()
        hotkey = cfg.get("hotkey", "RightAlt")

        logger.info("=" * 55)
        logger.info("  VoiceType v0.1.0")
        logger.info("  Hotkey: %s (hold to speak)", hotkey)
        logger.info("  STT:    %s / %s", cfg.get("sttProvider"), cfg.get("sttModel"))
        logger.info("  LLM:    %s / %s", cfg.get("llmProvider"), cfg.get("llmModel"))
        logger.info("=" * 55)

        # 註冊 atexit 確保任何情況退出都會釋放鍵盤 hook
        atexit.register(self._cleanup)

        # 同步開機啟動設定
        from config.settings_server import sync_autostart
        sync_autostart(cfg.get("autoStart", True))

        # 檢查 API Key
        self._check_api_keys(cfg)

        # 註冊快捷鍵
        self.hotkey.register(
            on_press=self.on_hotkey_press,
            on_release=self.on_hotkey_release,
        )
        logger.info("Hotkey registered: %s", hotkey)

        # 啟動系統托盤（在背景執行緒，避免主執行緒訊息迴圈阻擋鍵盤模擬）
        tray = self._create_tray_icon()
        if tray:
            tray_thread = threading.Thread(target=tray.run, daemon=True)
            tray_thread.start()

        logger.info("VoiceType started! Hold %s to speak", hotkey)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self._quit()

    def _check_api_keys(self, cfg):
        """啟動時檢查必要的 API Key，如為空則自動開啟設定頁面"""
        keys = cfg.get("apiKeys", {})
        stt_provider = cfg.get("sttProvider", "groq")
        llm_provider = cfg.get("llmProvider", "openai")

        missing = []
        if stt_provider in ("groq", "openai") and not keys.get(stt_provider):
            missing.append(f"STT ({stt_provider})")
        if llm_provider in ("openai", "anthropic", "groq") and not keys.get(llm_provider):
            missing.append(f"LLM ({llm_provider})")

        if missing:
            for m in missing:
                logger.warning("%s API Key 尚未設定", m)
            logger.info("首次啟動偵測：自動開啟設定頁面...")
            self._open_settings()


if __name__ == "__main__":
    app = VoiceType()
    app.run()
