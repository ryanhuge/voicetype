#!/bin/bash
# VoiceType launcher — 動態偵測當前 X session 的 DISPLAY 和 XAUTHORITY
# 避免螢幕熱插拔導致 X server 重啟後 voicetype 連不上

# 找當前活躍的 X 或 Xwayland process
for proc in /proc/*/cmdline; do
  [ -r "$proc" ] || continue
  cmdline=$(tr '\0' ' ' < "$proc" 2>/dev/null)
  if echo "$cmdline" | grep -qE "Xwayland|Xorg"; then
    pid=$(echo "$proc" | grep -oP '/proc/\K[0-9]+')
    # 取出 :N display 編號
    display=$(echo "$cmdline" | grep -oP ':[0-9]+' | head -1)
    # 取出 -auth /path/to/xauth
    auth=$(echo "$cmdline" | grep -oP '\-auth \K\S+')
    if [ -n "$display" ] && [ -n "$auth" ] && [ -f "$auth" ]; then
      export DISPLAY="$display"
      export XAUTHORITY="$auth"
      echo "[VoiceType] Using DISPLAY=$display XAUTHORITY=$auth (X server PID $pid)"
      break
    fi
  fi
done

if [ -z "$DISPLAY" ]; then
  echo "[VoiceType] WARNING: No X server found, using defaults"
  export DISPLAY=":0"
fi

exec /home/ryan/voicetype/.venv/bin/python /home/ryan/voicetype/main.py
