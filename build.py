"""
VoiceType 打包腳本
將整個專案打包成單一可執行檔

用法：
  python build.py

產出：
  Windows: dist/VoiceType.exe
  Linux:   dist/VoiceType

需求：
  pip install pyinstaller
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def check_pyinstaller():
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[INFO] PyInstaller not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[OK] PyInstaller installed")


def build():
    print("=" * 50)
    print("  VoiceType Build Tool")
    print(f"  Platform: {sys.platform}")
    print("=" * 50)

    check_pyinstaller()

    # 清理舊的打包檔案
    for d in [DIST, BUILD]:
        if d.exists():
            shutil.rmtree(d)
            print(f"[CLEAN] {d}")

    if sys.platform == "win32":
        cmd = _build_cmd_windows()
        output_name = "VoiceType.exe"
    else:
        cmd = _build_cmd_linux()
        output_name = "VoiceType"

    print(f"\n[BUILD] Starting...\n")

    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        exe_path = DIST / output_name
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n{'=' * 50}")
            print(f"  [OK] Build successful!")
            print(f"  Output: {exe_path}")
            print(f"  Size: {size_mb:.1f} MB")
            print(f"{'=' * 50}")
            if sys.platform == "win32":
                print(f"\n  Double-click VoiceType.exe to start")
            else:
                print(f"\n  Run: ./dist/VoiceType")
            print(f"  First run will auto-open settings page")
        else:
            print("[ERROR] Build seemed to succeed but output not found")
    else:
        print(f"\n[ERROR] Build failed (exit code: {result.returncode})")
        print("   Check error messages above")


def _build_cmd_windows():
    """Windows PyInstaller 打包指令"""
    icon_path = ROOT / "assets" / "icon.ico"
    if not icon_path.exists():
        create_default_icon_ico(icon_path)

    return [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name=VoiceType",
        f"--icon={icon_path}",
        f"--add-data=ui/settings.html{os.pathsep}ui",
        "--hidden-import=pystray._win32",
        "--hidden-import=PIL.Image",
        "--hidden-import=sounddevice",
        "--hidden-import=numpy",
        "--hidden-import=httpx",
        "--hidden-import=httpx._transports",
        "--hidden-import=httpx._transports.default",
        "--hidden-import=httpcore",
        "--hidden-import=httpcore._backends",
        "--hidden-import=httpcore._backends.sync",
        "--hidden-import=h11",
        "--hidden-import=certifi",
        "--hidden-import=pyperclip",
        "--hidden-import=pyautogui",
        "--hidden-import=keyboard",
        "--hidden-import=keyboard._winkeyboard",
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=torch",
        "--exclude-module=tensorflow",
        "--exclude-module=cv2",
        "--exclude-module=opencv-python",
        "--exclude-module=IPython",
        "--exclude-module=jedi",
        "--exclude-module=pygments",
        "--exclude-module=pytest",
        "--exclude-module=yapf",
        "--exclude-module=parso",
        "--exclude-module=sqlite3",
        "--exclude-module=websockets",
        f"--manifest={ROOT / 'assets' / 'VoiceType.exe.manifest'}",
        "main.py",
    ]


def _build_cmd_linux():
    """Linux PyInstaller 打包指令"""
    icon_path = ROOT / "assets" / "icon.png"
    if not icon_path.exists():
        create_default_icon_png(icon_path)

    return [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name=VoiceType",
        f"--add-data=ui/settings.html{os.pathsep}ui",
        "--hidden-import=pystray._xorg",
        "--hidden-import=PIL.Image",
        "--hidden-import=sounddevice",
        "--hidden-import=numpy",
        "--hidden-import=httpx",
        "--hidden-import=httpx._transports",
        "--hidden-import=httpx._transports.default",
        "--hidden-import=httpcore",
        "--hidden-import=httpcore._backends",
        "--hidden-import=httpcore._backends.sync",
        "--hidden-import=h11",
        "--hidden-import=certifi",
        "--hidden-import=evdev",
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=torch",
        "--exclude-module=tensorflow",
        "--exclude-module=cv2",
        "--exclude-module=opencv-python",
        "--exclude-module=IPython",
        "--exclude-module=jedi",
        "--exclude-module=pygments",
        "--exclude-module=pytest",
        "--exclude-module=yapf",
        "--exclude-module=parso",
        "--exclude-module=sqlite3",
        "--exclude-module=websockets",
        "main.py",
    ]


def create_default_icon_ico(icon_path: Path):
    """用 Pillow 建立 Windows ICO 圖示"""
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        images = []

        for size in sizes:
            img = Image.new("RGBA", size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            w, h = size
            pad = w // 10

            # 橙色圓形背景
            draw.ellipse([pad, pad, w - pad, h - pad], fill=(249, 115, 22, 255))

            # 白色麥克風
            mic_w = w // 5
            mic_h = h // 3
            cx, cy = w // 2, h // 2 - h // 10
            draw.rounded_rectangle(
                [cx - mic_w, cy - mic_h, cx + mic_w, cy + mic_h // 2],
                radius=mic_w,
                fill=(255, 255, 255, 255),
            )
            # 底座
            stand_w = w // 10
            draw.rectangle(
                [cx - stand_w, cy + mic_h // 2, cx + stand_w, cy + mic_h],
                fill=(255, 255, 255, 255),
            )
            draw.line(
                [cx - mic_w, cy + mic_h, cx + mic_w, cy + mic_h],
                fill=(255, 255, 255, 255),
                width=max(1, w // 20),
            )
            images.append(img)

        images[0].save(
            str(icon_path), format="ICO",
            sizes=[(s[0], s[1]) for s in sizes],
            append_images=images[1:],
        )
        print(f"[OK] Default icon created: {icon_path}")
    except ImportError:
        print("[WARN] Pillow not installed, skipping icon creation")


def create_default_icon_png(icon_path: Path):
    """用 Pillow 建立 Linux PNG 圖示"""
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        w = h = size
        pad = w // 10

        # 橙色圓形背景
        draw.ellipse([pad, pad, w - pad, h - pad], fill=(249, 115, 22, 255))

        # 白色麥克風
        mic_w = w // 5
        mic_h = h // 3
        cx, cy = w // 2, h // 2 - h // 10
        draw.rounded_rectangle(
            [cx - mic_w, cy - mic_h, cx + mic_w, cy + mic_h // 2],
            radius=mic_w,
            fill=(255, 255, 255, 255),
        )
        stand_w = w // 10
        draw.rectangle(
            [cx - stand_w, cy + mic_h // 2, cx + stand_w, cy + mic_h],
            fill=(255, 255, 255, 255),
        )
        draw.line(
            [cx - mic_w, cy + mic_h, cx + mic_w, cy + mic_h],
            fill=(255, 255, 255, 255),
            width=max(1, w // 20),
        )

        img.save(str(icon_path), format="PNG")
        print(f"[OK] Default icon created: {icon_path}")
    except ImportError:
        print("[WARN] Pillow not installed, skipping icon creation")


if __name__ == "__main__":
    build()
