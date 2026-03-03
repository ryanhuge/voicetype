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
        self._state_lock = threading.RLock()  # 執行緒安全狀態鎖
        self.is_recording = False
        self.processing = False
        self.tray_icon = None
        self._target_hwnd = None
        self._target_thread_id = None

    # ── 快捷鍵回呼 ───────────────────────────────────────────────────────────

    def on_hotkey_press(self):
        """快捷鍵按下：開始錄音"""
        with self._state_lock:
            if self.is_recording or self.processing:
                return
            self.is_recording = True
        # 記住目前的前景視窗（使用者正在操作的視窗）
        self._target_hwnd = ctypes.windll.user32.GetForegroundWindow()
        # 取得該視窗的執行緒 ID，用於 AttachThreadInput
        self._target_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(self._target_hwnd, None)
        play_start()
        self.recorder.start()
        logger.info("Recording started (target hwnd: 0x%x)...", self._target_hwnd)
        self._update_tray("錄音中...", "recording")

    def on_hotkey_release(self):
        """快捷鍵釋放：停止錄音 → STT → LLM → 注入"""
        with self._state_lock:
            if not self.is_recording:
                return
            self.is_recording = False
            self.processing = True
        play_stop()

        audio_data = self.recorder.stop()
        logger.info("Recording stopped (%.1f sec), processing...", len(audio_data) / 16000)
        self._update_tray("處理中...", "processing")

        # 使用帶超時的背景執行緒
        thread = threading.Thread(
            target=self._process_audio_with_watchdog,
            args=(audio_data,),
            daemon=True
        )
        thread.start()

    # ── 語音處理管線 ─────────────────────────────────────────────────────────

    def _process_audio_with_watchdog(self, audio_data):
        """包裝器，帶超時保護"""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._process_audio, audio_data)
            try:
                future.result(timeout=30.0)  # 30 秒最大限制
            except concurrent.futures.TimeoutError:
                logger.error("Processing timeout after 30s - forcing hook recovery")
                self._emergency_hook_recovery()
            except Exception as e:
                logger.error("Processing error: %s", e, exc_info=True)
                self._emergency_hook_recovery()

    def _emergency_hook_recovery(self):
        """緊急 hook 恢復"""
        logger.warning("Emergency hook recovery triggered")
        with self._state_lock:
            self.processing = False
            self.is_recording = False

        try:
            # 停止並重新註冊
            self.hotkey.stop()
            time.sleep(0.1)
            self.hotkey.register(
                on_press=self.on_hotkey_press,
                on_release=self.on_hotkey_release,
            )
            logger.info("Hook forcibly recovered")
        except Exception as e:
            logger.error("Hook recovery failed: %s", e)

        self._update_tray("就緒", "idle")

    def _process_audio(self, audio_data):
        """STT → LLM → 焦點恢復 → unhook → 注入 → rehook"""
        # 背景執行緒也需要初始化 COM 為 STA
        ctypes.windll.ole32.CoInitializeEx(None, 2)
        hook_unhooked = False

        try:
            # 檢查錄音長度
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
            polished = self.llm.polish(raw_text, target_hwnd=self._target_hwnd)
            llm_time = time.time() - t1
            logger.info("Polished (%.1fs): %s", llm_time, polished)

            # ==========================================
            # 關鍵修復：恢復焦點 BEFORE unhook
            # ==========================================

            # 步驟 3：恢復焦點（此時 hook 仍然活躍）
            if self._target_hwnd:
                focus_success = self._restore_focus(self._target_hwnd)
                if not focus_success:
                    logger.warning("Focus restoration failed, but continuing with injection")
                time.sleep(0.05)  # 讓焦點穩定

            # 步驟 4：發送 Escape 鍵（取消 Alt 選單，現在發送到正確視窗）
            try:
                import pyautogui
                pyautogui.press("escape")
                time.sleep(0.02)
            except Exception as e:
                logger.warning("Failed to send escape: %s", e)

            # 步驟 5：暫時 unhook（僅在注入期間）
            self.hotkey.unhook()
            hook_unhooked = True
            time.sleep(0.05)  # 短暫暫停

            # 步驟 6：注入文字
            self.injector.inject(polished)

            # 步驟 7：立即重新註冊 hook
            self.hotkey.register(
                on_press=self.on_hotkey_press,
                on_release=self.on_hotkey_release,
            )
            hook_unhooked = False

            total = time.time() - t0
            logger.info("Done! Total %.1fs (STT %.1fs + LLM %.1fs)", total, stt_time, llm_time)

        except Exception as e:
            logger.error("Processing failed: %s", e, exc_info=True)
            self._update_tray("錯誤", "error")
            time.sleep(ERROR_DISPLAY_SECONDS)

        finally:
            # 確保 hook 一定會重新註冊
            if hook_unhooked or not self.hotkey._press_hook:
                try:
                    self.hotkey.register(
                        on_press=self.on_hotkey_press,
                        on_release=self.on_hotkey_release,
                    )
                    logger.info("Hotkey re-registered in finally block")
                except Exception as e2:
                    logger.error("Failed to re-register hotkey in finally: %s", e2)

            self._reset_status()

    # ── 輔助方法 ─────────────────────────────────────────────────────────────

    def _update_tray(self, status_text: str, state: str = "idle"):
        """更新系統列圖標外觀與提示文字"""
        if self.tray_icon:
            # 在就緒狀態顯示當前模型
            if status_text == "就緒" and state == "idle":
                model = self._get_current_model()
                self.tray_icon.title = f"VoiceType - {status_text} ({model})"
            else:
                self.tray_icon.title = f"VoiceType - {status_text}"
            try:
                self.tray_icon.icon = create_tray_icon(state)
            except Exception:
                pass  # 圖標更新非關鍵功能

    def _reset_status(self):
        with self._state_lock:
            self.processing = False
        self._update_tray("就緒", "idle")

    def _is_thread_alive(self, thread_id):
        """檢查執行緒 ID 是否仍然有效"""
        if not thread_id:
            return False

        # 開啟執行緒控制碼
        THREAD_QUERY_INFORMATION = 0x0040
        h_thread = ctypes.windll.kernel32.OpenThread(
            THREAD_QUERY_INFORMATION, False, thread_id
        )
        if not h_thread:
            return False

        # 檢查退出碼
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeThread(h_thread, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(h_thread)

        STILL_ACTIVE = 259
        return exit_code.value == STILL_ACTIVE

    def _attach_thread_input_safe(self, thread_from, thread_to, attach=True, timeout=1.0):
        """AttachThreadInput with timeout protection"""
        import concurrent.futures

        def do_attach():
            return ctypes.windll.user32.AttachThreadInput(thread_from, thread_to, attach)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(do_attach)
            try:
                result = future.result(timeout=timeout)
                return result
            except concurrent.futures.TimeoutError:
                logger.error("AttachThreadInput timeout after %.1fs", timeout)
                return False
            except Exception as e:
                logger.error("AttachThreadInput failed: %s", e)
                return False

    def _restore_focus(self, hwnd):
        """使用簡化的焦點恢復（避免死鎖）"""
        try:
            user32 = ctypes.windll.user32

            # 驗證視窗仍然存在
            if not user32.IsWindow(hwnd):
                logger.warning("Target window no longer exists")
                return False

            # 方法 1：簡單 SetForegroundWindow（適用於 90% 情況）
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)

            # 驗證成功
            current_fg = user32.GetForegroundWindow()
            if current_fg == hwnd:
                logger.info("Focus restored successfully (simple method)")
                return True

            # 方法 2：進階恢復（使用 AttachThreadInput 作為後備）
            logger.info("Simple focus restoration failed, trying advanced method")

            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            target_thread = self._target_thread_id

            # 驗證執行緒存活
            if not target_thread or not self._is_thread_alive(target_thread):
                logger.warning("Target thread invalid or dead, cannot use AttachThreadInput")
                return False

            if target_thread == current_thread:
                logger.info("Same thread, no AttachThreadInput needed")
                return False

            # 使用有超時保護的 AttachThreadInput
            attached = self._attach_thread_input_safe(current_thread, target_thread, True, timeout=1.0)
            if not attached:
                return False

            try:
                # 如果被最小化，恢復
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    time.sleep(0.02)

                # 設置前景
                user32.SetForegroundWindow(hwnd)
                time.sleep(0.05)

            finally:
                # 確保 detach
                self._attach_thread_input_safe(current_thread, target_thread, False, timeout=0.5)

            # 最終驗證
            current_fg = user32.GetForegroundWindow()
            success = (current_fg == hwnd)
            if success:
                logger.info("Focus restored successfully (advanced method)")
            else:
                logger.warning("Focus restoration failed (current: 0x%x, target: 0x%x)",
                             current_fg, hwnd)

            return success

        except Exception as e:
            logger.error("Failed to restore focus: %s", e, exc_info=True)
            return False

    def _create_tray_icon(self):
        """建立系統托盤圖示"""
        try:
            import pystray

            img = create_tray_icon("idle")

            # 建立模型選擇子選單
            model_menu = pystray.Menu(
                pystray.MenuItem(
                    "gpt-4.1 (推薦)",
                    lambda icon, item: self._switch_model("gpt-4.1"),
                    checked=lambda item: self._get_current_model() == "gpt-4.1",
                    radio=True,
                ),
                pystray.MenuItem(
                    "gpt-4.1-mini",
                    lambda icon, item: self._switch_model("gpt-4.1-mini"),
                    checked=lambda item: self._get_current_model() == "gpt-4.1-mini",
                    radio=True,
                ),
                pystray.MenuItem(
                    "gpt-4o",
                    lambda icon, item: self._switch_model("gpt-4o"),
                    checked=lambda item: self._get_current_model() == "gpt-4o",
                    radio=True,
                ),
                pystray.MenuItem(
                    "gpt-4o-mini",
                    lambda icon, item: self._switch_model("gpt-4o-mini"),
                    checked=lambda item: self._get_current_model() == "gpt-4o-mini",
                    radio=True,
                ),
            )

            menu = pystray.Menu(
                pystray.MenuItem("VoiceType v0.1.0", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("模型選擇", model_menu),
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

    def _get_current_model(self):
        """取得當前使用的模型"""
        cfg = self.settings.get_config()
        return cfg.get("llmModel", "gpt-4.1")

    def _switch_model(self, model_name: str):
        """切換 LLM 模型"""
        try:
            logger.info("Switching model to: %s", model_name)
            self.settings.update("llmModel", model_name)
            # 重新建立 LLM 處理器
            self.llm = LLMProcessor(self.settings)
            # 更新托盤提示文字
            if self.tray_icon:
                cfg = self.settings.get_config()
                tooltip = f"VoiceType - 就緒 ({model_name})"
                self.tray_icon.title = tooltip
            logger.info("Model switched to: %s", model_name)
        except Exception as e:
            logger.error("Failed to switch model: %s", e)

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
