"""
VoiceType - 類 Typeless 語音輸入工具
主程式：系統托盤常駐 + 快捷鍵監聽 + 語音處理管線

使用方式：
  1. 設定 config/config.json 中的 API Key
  2. python main.py
  3. 按住 Right Alt 說話，放開即輸出
"""

import sys
import subprocess

# Windows: 在 import sounddevice 之前初始化 COM 為 STA 模式
# 避免 PortAudio 將 COM 初始化為 MTA，導致 SendInput 無法被 Chrome 接收
if sys.platform == "win32":
    import ctypes
    ctypes.windll.ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED

import signal
import threading
import os
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
        self._target_window = None

    # ── 跨平台視窗管理 ───────────────────────────────────────────────────────

    def _get_active_window(self):
        """取得當前前景視窗 ID"""
        if sys.platform == "win32":
            import ctypes
            return ctypes.windll.user32.GetForegroundWindow()
        else:
            try:
                result = subprocess.run(
                    ["xdotool", "getactivewindow"],
                    capture_output=True, text=True, timeout=2,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            return None

    def _restore_window(self, window_id):
        """恢復指定視窗到前景"""
        if window_id is None:
            return
        if sys.platform == "win32":
            import ctypes
            try:
                ctypes.windll.user32.SetForegroundWindow(window_id)
            except Exception:
                pass
        else:
            try:
                subprocess.run(
                    ["xdotool", "windowactivate", str(window_id)],
                    capture_output=True, timeout=2,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    # ── 快捷鍵回呼 ───────────────────────────────────────────────────────────

    def on_hotkey_press(self):
        """快捷鍵按下：開始錄音"""
        if self.is_recording or self.processing:
            return
        # 記住前景視窗，處理完成後恢復焦點再注入
        self._target_window = self._get_active_window()
        self.is_recording = True
        play_start()
        self.recorder.start()
        logger.info("Recording started...")
        self._update_tray("Recording...", "recording")

    def on_hotkey_release(self):
        """快捷鍵釋放：停止錄音 → STT → LLM → 注入"""
        if not self.is_recording:
            return
        self.is_recording = False
        self.processing = True
        play_stop()
        audio_data = self.recorder.stop()
        logger.info("Recording stopped (%.1f sec), processing...", len(audio_data) / 16000)
        self._update_tray("Processing...", "processing")

        # 背景執行緒處理，避免阻塞快捷鍵
        threading.Thread(target=self._process_audio, args=(audio_data,), daemon=True).start()

    # ── 語音處理管線 ─────────────────────────────────────────────────────────

    def _process_audio(self, audio_data):
        """STT → LLM → 文字注入"""
        # Windows 背景執行緒也需要初始化 COM 為 STA
        if sys.platform == "win32":
            import ctypes
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

            # 步驟 3：恢復焦點 → 注入文字
            if sys.platform == "win32":
                # Windows：需要暫停 keyboard hook 才能模擬按鍵
                self.hotkey.unhook()
                time.sleep(INJECT_DELAY_SECONDS)
                self._restore_window(self._target_window)
                time.sleep(0.05)
                self.injector.inject(polished)
                self.hotkey.register(
                    on_press=self.on_hotkey_press,
                    on_release=self.on_hotkey_release,
                )
            else:
                # Linux：傳入目標視窗，injector 內部恢復焦點 + Escape + 貼上
                self.injector.inject(polished, target_window=self._target_window)

            total = time.time() - t0
            logger.info("Done! Total %.1fs (STT %.1fs + LLM %.1fs)", total, stt_time, llm_time)

        except Exception as e:
            logger.error("Processing failed: %s", e, exc_info=True)
            self._update_tray("Error", "error")
            time.sleep(ERROR_DISPLAY_SECONDS)

        finally:
            self._reset_status()

    # ── 輔助方法 ─────────────────────────────────────────────────────────────

    def _update_tray(self, status_text: str, state: str = "idle"):
        """更新系統列圖標外觀與提示文字"""
        if self.tray_icon:
            # pystray X11 後端的 WM_NAME 只支援 Latin-1，中文會報錯
            try:
                self.tray_icon.title = f"VoiceType - {status_text}"
            except UnicodeEncodeError:
                self.tray_icon.title = "VoiceType"
            try:
                self.tray_icon.icon = create_tray_icon(state)
            except Exception:
                pass  # 圖標更新非關鍵功能

    def _reset_status(self):
        self.processing = False
        self._update_tray("Ready", "idle")

    def _create_tray_icon(self):
        """建立系統托盤圖示"""
        try:
            import pystray

            img = create_tray_icon("idle")

            menu = pystray.Menu(
                pystray.MenuItem("VoiceType v0.1.0", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Settings", self._open_settings),
                pystray.MenuItem("Config folder", self._open_config_dir),
                pystray.MenuItem("Reload", self._reload_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            )

            self.tray_icon = pystray.Icon("VoiceType", img, "VoiceType - Ready", menu)
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
        else:
            try:
                subprocess.Popen(["xdg-open", str(config_dir)])
            except FileNotFoundError:
                logger.error("xdg-open not found, cannot open config directory")

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

    def run(self):
        cfg = self.settings.load()
        hotkey = cfg.get("hotkey", "RightAlt")

        logger.info("=" * 55)
        logger.info("  VoiceType v0.1.0")
        logger.info("  Platform: %s", sys.platform)
        logger.info("  Hotkey: %s (hold to speak)", hotkey)
        logger.info("  STT:    %s / %s", cfg.get("sttProvider"), cfg.get("sttModel"))
        logger.info("  LLM:    %s / %s", cfg.get("llmProvider"), cfg.get("llmModel"))
        logger.info("=" * 55)

        # 同步開機啟動設定
        from config.settings_server import sync_autostart
        sync_autostart(cfg.get("autoStart", True))

        # 檢查 API Key
        self._check_api_keys(cfg)

        # 預先建立 UInput 虛擬鍵盤，讓 X11 有時間註冊裝置
        self.injector.warmup()

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

        # 處理 SIGHUP / SIGTERM，確保被 kill 或 shell 關閉時正常退出
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda *_: self._quit())

        logger.info("VoiceType started! Hold %s to speak", hotkey)
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
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
