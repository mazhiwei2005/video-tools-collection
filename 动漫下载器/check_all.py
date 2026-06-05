import os, subprocess, glob

base = r"C:\Users\Lenovo\Desktop\动漫下载"
ffprobe = r"C:\Program Files\FFmpeg\ffprobe.exe"

print("=== 下载文件检查 ===")
for d in sorted(os.listdir(base)):
    dp = os.path.join(base, d)
    if not os.path.isdir(dp):
        continue
    for f in sorted(os.listdir(dp)):
        if not f.endswith(".mp4"):
            continue
        fp = os.path.join(dp, f)
        sz = os.path.getsize(fp) / 1024 / 1024
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", fp],
                           capture_output=True, encoding="utf-8", errors="replace")
        dur_str = r.stdout.strip()
        try:
            dur = float(dur_str)
            status = "OK" if dur > 30 else f"异常({dur:.1f}s)"
        except:
            dur = 0
            status = "无法读取"
        print(f"  {f}  {sz:.1f}MB  {dur:.1f}秒  [{status}]")
