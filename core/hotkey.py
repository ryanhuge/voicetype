"""
全域快捷鍵管理模組
監聽 Push-to-Talk 快捷鍵（按住說話，放開處理）

Windows: 使用 keyboard 庫
Linux:   使用 evdev 直接讀取輸入裝置
"""

import sys
import logging
import threading

logger = logging.getLogger("VoiceType.Hotkey")

if sys.platform == "win32":
    # ── Windows 實作 ─────────────────────────────────────────────────────────
    import keyboard

    HOTKEY_MAP = {
        "RightAlt": "right alt",
        "RightCtrl": "right ctrl",
        "F9": "f9",
        "CapsLock": "caps lock",
        "ScrollLock": "scroll lock",
    }

    class HotkeyManager:
        """全域快捷鍵管理器（Windows）"""

        def __init__(self, settings):
            self.settings = settings
            self._on_press = None
            self._on_release = None
            self._running = False
            self._hotkey_name = None
            self._press_hook = None
            self._release_hook = None

        def register(self, on_press, on_release):
            self._on_press = on_press
            self._on_release = on_release
            self._running = True

            cfg = self.settings.get_config()
            hotkey_id = cfg.get("hotkey", "RightAlt")
            key_name = HOTKEY_MAP.get(hotkey_id, "right alt")
            self._hotkey_name = key_name

            self._press_hook = keyboard.on_press_key(key_name, self._handle_press, suppress=True)
            self._release_hook = keyboard.on_release_key(key_name, self._handle_release, suppress=True)
            logger.info("Hotkey registered: %s -> %s", hotkey_id, key_name)

        def _handle_press(self, event):
            if self._running and self._on_press:
                try:
                    self._on_press()
                except Exception as e:
                    logger.error("Hotkey press callback error: %s", e)

        def _handle_release(self, event):
            if self._running and self._on_release:
                try:
                    self._on_release()
                except Exception as e:
                    logger.error("Hotkey release callback error: %s", e)

        def unhook(self):
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
            self._running = False
            self.unhook()
            logger.info("Hotkey listener stopped")

else:
    # ── Linux 實作（evdev）────────────────────────────────────────────────────
    import select
    import evdev
    from evdev import ecodes, InputDevice, list_devices

    HOTKEY_MAP = {
        "RightAlt": ecodes.KEY_RIGHTALT,
        "RightCtrl": ecodes.KEY_RIGHTCTRL,
        "F9": ecodes.KEY_F9,
        "CapsLock": ecodes.KEY_CAPSLOCK,
        "ScrollLock": ecodes.KEY_SCROLLLOCK,
    }

    def _find_keyboard_device() -> InputDevice:
        """掃描 /dev/input 找到主鍵盤裝置"""
        devices = [InputDevice(path) for path in list_devices()]
        keyboards = []
        for dev in devices:
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                keys = caps[ecodes.EV_KEY]
                # 真正的鍵盤會有字母按鍵
                if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                    keyboards.append(dev)

        if not keyboards:
            raise RuntimeError(
                "找不到鍵盤輸入裝置。請確認使用者已加入 input 群組：\n"
                "  sudo usermod -aG input $USER\n"
                "然後登出再登入。"
            )

        # 優先選擇名稱含 "keyboard" 的裝置
        for kb in keyboards:
            if "keyboard" in kb.name.lower():
                return kb
        return keyboards[0]

    class HotkeyManager:
        """全域快捷鍵管理器（Linux / evdev）"""

        def __init__(self, settings):
            self.settings = settings
            self._on_press = None
            self._on_release = None
            self._running = False
            self._thread = None
            self._device = None
            self._target_key = None
            self._stop_event = threading.Event()

        def register(self, on_press, on_release):
            self._on_press = on_press
            self._on_release = on_release
            self._running = True
            self._stop_event.clear()

            cfg = self.settings.get_config()
            hotkey_id = cfg.get("hotkey", "RightAlt")
            self._target_key = HOTKEY_MAP.get(hotkey_id, ecodes.KEY_RIGHTALT)

            # 重用已開啟的裝置，避免重複開啟同一個 /dev/input/event*
            if self._device is None:
                try:
                    self._device = _find_keyboard_device()
                    self._device_name = self._device.name  # 記住裝置名稱供重連用
                except PermissionError:
                    raise PermissionError(
                        "無法存取輸入裝置。請將使用者加入 input 群組：\n"
                        "  sudo usermod -aG input $USER\n"
                        "然後登出再登入。"
                    )

            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            logger.info(
                "Hotkey registered (evdev): %s -> keycode %s [device: %s]",
                hotkey_id, self._target_key, self._device.name,
            )

        def _reconnect_device(self):
            """藍牙鍵盤斷線重連後，等待同名裝置重新出現"""
            old_name = getattr(self, '_device_name', None)
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

            import time as _time
            # 無限等待，直到原本的鍵盤重新出現
            attempt = 0
            while self._running:
                attempt += 1
                try:
                    devices = [InputDevice(path) for path in list_devices()]
                    for dev in devices:
                        if dev.name == old_name:
                            self._device = dev
                            logger.info(
                                "Keyboard reconnected: %s (attempt %d)",
                                dev.name, attempt,
                            )
                            return True
                except (RuntimeError, PermissionError, OSError):
                    pass
                # 每 3 秒掃描一次，不急
                _time.sleep(3)
                if attempt % 20 == 0:  # 每分鐘記錄一次
                    logger.info(
                        "Waiting for keyboard '%s' to reconnect... (attempt %d)",
                        old_name, attempt,
                    )
            return False

        def _listen_loop(self):
            """讀取 evdev 事件，被動監聽，斷線自動重連"""
            while self._running and not self._stop_event.is_set():
                try:
                    r, _, _ = select.select([self._device.fd], [], [], 0.1)
                    if not r:
                        continue
                    for event in self._device.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        if event.code != self._target_key:
                            continue
                        if event.value == 1:  # key down
                            if self._on_press:
                                try:
                                    self._on_press()
                                except Exception as e:
                                    logger.error("Hotkey press error: %s", e)
                        elif event.value == 0:  # key up
                            if self._on_release:
                                try:
                                    self._on_release()
                                except Exception as e:
                                    logger.error("Hotkey release error: %s", e)
                except OSError:
                    if not self._running:
                        break
                    logger.warning("Keyboard disconnected, attempting reconnect...")
                    if not self._reconnect_device():
                        break

        def unhook(self):
            """暫時停止監聽"""
            self._running = False
            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=1)
                self._thread = None

        def stop(self):
            self.unhook()
            if self._device:
                try:
                    self._device.close()
                except Exception:
                    pass
                self._device = None
            logger.info("Hotkey listener stopped")
