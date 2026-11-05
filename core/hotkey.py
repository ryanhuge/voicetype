"""
全域快捷鍵管理模組
監聽 Push-to-Talk 快捷鍵（按住說話，放開處理）
"""

from concurrent.futures import ThreadPoolExecutor
import logging
import keyboard

logger = logging.getLogger("VoiceType.Hotkey")

# 快捷鍵名稱映射到 keyboard 模組的鍵名
HOTKEY_MAP = {
    "RightAlt": "right alt",
    "RightCtrl": "right ctrl",
    "F9": "f9",
    "CapsLock": "caps lock",
    "ScrollLock": "scroll lock",
}


class HotkeyManager:
    """全域快捷鍵管理器"""

    def __init__(self, settings):
        self.settings = settings
        self._on_press = None
        self._on_release = None
        self._running = False
        self._hotkey_name = None
        self._hook = None
        self._pressed = False
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="VoiceTypeHotkey")

    def register(self, on_press, on_release):
        """
        註冊 Push-to-Talk 快捷鍵

        Args:
            on_press: 按下時的回呼函式
            on_release: 釋放時的回呼函式
        """
        self.unhook()
        self._on_press = on_press
        self._on_release = on_release
        self._running = True

        cfg = self.settings.get_config()
        hotkey_id = cfg.get("hotkey", "RightAlt")
        key_name = HOTKEY_MAP.get(hotkey_id, "right alt")
        self._hotkey_name = key_name

        # 鍵盤回呼只攔截按鍵，錄音啟停在背景依序執行。
        self._hook = keyboard.hook_key(key_name, self._handle_event, suppress=True)

        logger.info("Hotkey registered: %s -> %s", hotkey_id, key_name)

    def _handle_event(self, event):
        if not self._running:
            return True

        pressed = event.event_type == keyboard.KEY_DOWN
        if pressed != self._pressed:
            self._pressed = pressed
            callback = self._on_press if pressed else self._on_release
            self._worker.submit(self._dispatch, callback)
        return False

    def _dispatch(self, callback):
        if self._running and callback:
            try:
                callback()
            except Exception:
                logger.exception("Hotkey callback failed")

    def unhook(self):
        """移除語音快捷鍵的監聽。"""
        if self._hook:
            keyboard.unhook(self._hook)
            self._hook = None
        self._pressed = False

    def stop(self):
        """停止快捷鍵監聽"""
        self._running = False
        self.unhook()
        logger.info("Hotkey listener stopped")
