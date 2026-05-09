"""
文字注入模組
將修飾後的文字注入到當前游標位置

Windows: 剪貼簿 + Ctrl+V（pyperclip + pyautogui）
Linux:   剪貼簿(xsel) + xdotool 模擬貼上（XTEST 擴充）
         - 一般應用：Ctrl+V
         - 終端模擬器：Ctrl+Shift+V
"""

import sys
import time
import logging
import subprocess

logger = logging.getLogger("VoiceType.Injector")

CLIPBOARD_SETTLE_SECONDS = 0.15

# 終端模擬器的 WM_CLASS 關鍵字（這些應用需要 Ctrl+Shift+V 貼上）
_TERMINAL_KEYWORDS = {
    "terminal", "konsole", "kitty", "alacritty", "tilix",
    "terminator", "xterm", "urxvt", "rxvt", "sakura",
    "guake", "tilda", "yakuake", "st-256color", "foot",
    "wezterm",
}


class TextInjector:
    """文字注入引擎"""

    def __init__(self, settings):
        self.settings = settings

    def warmup(self):
        """預熱（Linux 目前使用 xdotool，無需預建裝置）"""
        pass

    def inject(self, text: str, **kwargs):
        """將文字注入到當前游標位置"""
        if not text:
            return

        try:
            if sys.platform == "win32":
                self._inject_windows(text)
            else:
                self._inject_linux(text, **kwargs)
            logger.info("Injected %d characters", len(text))
        except Exception as e:
            logger.error("Text injection failed: %s", e)
            raise

    def _inject_windows(self, text: str):
        """Windows：剪貼簿 + Ctrl+V"""
        import pyperclip
        import pyautogui
        pyperclip.copy(text)
        time.sleep(CLIPBOARD_SETTLE_SECONDS)
        pyautogui.hotkey("ctrl", "v")

    def _get_focused_wm_class(self) -> str:
        """取得當前焦點視窗的 WM_CLASS"""
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode != 0:
                return ""
            wid = result.stdout.strip()
            result = subprocess.run(
                ["xprop", "-id", wid, "WM_CLASS"],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _is_terminal(self, wm_class: str) -> bool:
        """檢查 WM_CLASS 是否為終端模擬器"""
        wm_lower = wm_class.lower()
        return any(kw in wm_lower for kw in _TERMINAL_KEYWORDS)

    def _get_ibus_engine(self) -> str:
        """取得當前 IBus 引擎名稱"""
        try:
            r = subprocess.run(["ibus", "engine"], capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return ""

    def _inject_linux(self, text: str, target_window=None):
        """Linux：xsel 設定剪貼簿 + xdotool 模擬貼上"""
        # 步驟 1：設定剪貼簿（xsel 不會 fork 殘留行程）
        subprocess.run(
            ["xsel", "--clipboard", "--input"],
            input=text.encode("utf-8"),
            timeout=5,
        )
        time.sleep(CLIPBOARD_SETTLE_SECONDS)

        # 步驟 2：恢復焦點視窗
        if target_window:
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", str(target_window)],
                capture_output=True, timeout=3,
            )
            time.sleep(0.05)

        # 步驟 3：暫時切換 IBus 為直接輸入，避免中文輸入法攔截 Ctrl+V
        ibus_engine = self._get_ibus_engine()
        if ibus_engine and ibus_engine != "xkb:us::eng":
            try:
                subprocess.run(["ibus", "engine", "xkb:us::eng"], timeout=2)
                time.sleep(0.05)
            except Exception:
                ibus_engine = ""  # ibus 不可用，略過還原步驟

        # 步驟 4：偵測焦點視窗類型，選擇貼上快捷鍵
        wm_class = self._get_focused_wm_class()
        is_term = self._is_terminal(wm_class)
        paste_keys = "ctrl+shift+v" if is_term else "ctrl+v"
        logger.info("Focused: %s | keys: %s", wm_class, paste_keys)

        # 步驟 5：xdotool 模擬貼上
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", paste_keys],
            timeout=5,
        )

        # 步驟 6：還原 IBus 引擎
        if ibus_engine and ibus_engine != "xkb:us::eng":
            try:
                subprocess.run(["ibus", "engine", ibus_engine], timeout=2)
            except Exception:
                pass
