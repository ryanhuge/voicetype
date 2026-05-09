"""
音效模組
錄音開始/結束時播放提示音
使用 sounddevice + numpy 生成正弦波音調（跨平台）
"""

import logging
import threading

import numpy as np
import sounddevice as sd

logger = logging.getLogger("VoiceType.Sounds")

SAMPLE_RATE = 44100


def _beep(freq: int, duration_ms: int):
    """在背景執行緒播放正弦波音調"""
    try:
        n_samples = int(SAMPLE_RATE * duration_ms / 1000)
        t = np.linspace(0, duration_ms / 1000, n_samples, endpoint=False)
        wave = (np.sin(2 * np.pi * freq * t) * 0.3).astype(np.float32)
        # 淡入淡出避免喀嚓聲
        fade = min(int(SAMPLE_RATE * 0.01), len(wave) // 4)
        if fade > 0:
            wave[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            wave[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        sd.play(wave, samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception as e:
        logger.debug("Beep failed: %s", e)


def play_start():
    """錄音開始：柔和上升音 (500Hz, 120ms)"""
    threading.Thread(target=_beep, args=(500, 120), daemon=True).start()


def play_stop():
    """錄音結束：柔和下降音 (350Hz, 120ms)"""
    threading.Thread(target=_beep, args=(350, 120), daemon=True).start()
