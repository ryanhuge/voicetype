"""
全域快捷鍵管理模組
監聽 Push-to-Talk 快捷鍵（按住說話，放開處理）
"""

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
        self._press_hook = None
        self._release_hook = None

    def register(self, on_press, on_release):
        """
        註冊 Push-to-Talk 快捷鍵

        Args:
            on_press: 按下時的回呼函式
            on_release: 釋放時的回呼函式
        """
        self._on_press = on_press
        self._on_release = on_release
        self._running = True

        cfg = self.settings.get_config()
        hotkey_id = cfg.get("hotkey", "RightAlt")
        key_name = HOTKEY_MAP.get(hotkey_id, "right alt")
        self._hotkey_name = key_name

        # 註冊按下和釋放事件，不使用 suppress 避免鍵盤鎖死
        self._press_hook = keyboard.on_press_key(key_name, self._handle_press, suppress=False)
        self._release_hook = keyboard.on_release_key(key_name, self._handle_release, suppress=False)

        logger.info("Hotkey registered: %s -> %s", hotkey_id, key_name)

    def _handle_press(self, event):
        """處理按下事件"""
        if self._running and self._on_press:
            try:
                self._on_press()
            except Exception as e:
                logger.error("Hotkey press callback error: %s", e)

    def _handle_release(self, event):
        """處理釋放事件"""
        if self._running and self._on_release:
            try:
                self._on_release()
            except Exception as e:
                logger.error("Hotkey release callback error: %s", e)

    def unhook(self):
        """移除此管理器註冊的 hook（不影響其他程式的 hook）"""
        if self._press_hook:
            try:
                keyboard.unhook(self._press_hook)
            except Exception:
                pass
            self._press_hook = None
        if self._release_hook:
            try:
                keyboard.unhook(self._release_hook)
            except Exception:
                pass
            self._release_hook = None

    def stop(self):
        """停止快捷鍵監聽"""
        self._running = False
        self.unhook()
        logger.info("Hotkey listener stopped")
