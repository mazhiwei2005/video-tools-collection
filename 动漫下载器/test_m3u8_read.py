"""测试: ffmpeg能不能读clean.m3u8"""
import tempfile, os, subprocess

ffmpeg = r"C:\Program Files\FFmpeg\ffmpeg.exe"

# 模拟clean.m3u8内容
lines = [
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    "#EXT-X-TARGETDURATION:10",
    "#EXT-X-MEDIA-SEQUENCE:0",
    "#EXTINF:10.416667,",
    "https://m3u8.cyz.app/kuais/c1d54490cb989c7b20a270138b573bb9/v_92b18d4dfd6a47d9b0f561ecd2592bd3/index0.ts?statis=0",
    "#EXTINF:1.208333,",
    "https://m3u8.cyz.app/kuais/946f36b4fdaa1d97d3b865892d378d9a/v_92b18d4dfd6a47d9b0f561ecd2592bd3/index6.ts?statis=5",
]

# 方法1: 写到temp目录
tmp = tempfile.mkdtemp(prefix="ani_test_")
m3u8_path = os.path.join(tmp, "test.m3u8")
with open(m3u8_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"文件: {m3u8_path}")
print(f"存在: {os.path.exists(m3u8_path)}")
print(f"大小: {os.path.getsize(m3u8_path)}")
with open(m3u8_path, "r") as f:
    print(f"内容:\n{f.read()}")

# 方法2: 用subprocess列表
output = os.path.join(tmp, "out.mp4")
cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", m3u8_path, "-c", "copy", output]
r = subprocess.run(cmd, capture_output=True, timeout=30, encoding="utf-8", errors="replace")
print(f"\n方法1(列表): returncode={r.returncode}")
if r.stderr:
    print(f"  stderr: {r.stderr[-200:]}")

# 方法3: 用shell=True
cmd_str = f'"{ffmpeg}" -y -f concat -safe 0 -i "{m3u8_path}" -c copy "{output}"'
r2 = subprocess.run(cmd_str, shell=True, capture_output=True, timeout=30, encoding="utf-8", errors="replace")
print(f"\n方法2(shell): returncode={r2.returncode}")
if r2.stderr:
    print(f"  stderr: {r2.stderr[-200:]}")

# 方法4: 不用-f concat, 直接-i
cmd3 = [ffmpeg, "-y", "-i", m3u8_path, "-c", "copy", output]
r3 = subprocess.run(cmd3, capture_output=True, timeout=30, encoding="utf-8", errors="replace")
print(f"\n方法3(直接-i): returncode={r3.returncode}")
if r3.stderr:
    print(f"  stderr: {r3.stderr[-200:]}")

import shutil
shutil.rmtree(tmp, ignore_errors=True)
