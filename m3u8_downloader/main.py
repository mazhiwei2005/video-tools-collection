#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8下载器 — 猫抓风格GUI
功能: 解析m3u8 → 多线程下载TS → ffmpeg合并MP4
支持: master playlist / AES-128加密 / 自定义headers
"""
import re, os, sys, time, json, shutil, hashlib, tempfile, subprocess
import threading, queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urljoin, urlparse

# ===== 配色 =====
BG_DARK = "#1a1a2e"
BG_MAIN = "#f0f2f5"
BG_CARD = "#ffffff"
ACCENT = "#00a1d6"
ACCENT_HOVER = "#0095c8"
ACCENT_LIGHT = "#e3f2fd"
TEXT_PRIMARY = "#1a1a2e"
TEXT_SECONDARY = "#6b7280"
TEXT_DARK = "#ffffff"
BORDER = "#e5e7eb"
GREEN = "#22c55e"
GREEN_HOVER = "#16a34a"
RED = "#ef4444"
ORANGE = "#f59e0b"

def _find_ffmpeg():
    import shutil as sh
    f = sh.which("ffmpeg")
    if f:
        return f
    for p in [r"C:\Program Files\FFmpeg\ffmpeg.exe",
              r"C:\ffmpeg\bin\ffmpeg.exe"]:
        if os.path.exists(p):
            return p
    return "ffmpeg"


class ModernButton(tk.Canvas):
    def __init__(self, parent, text="", bg=ACCENT, fg="#fff", hover=None,
                 width=100, height=32, radius=6, command=None, font_size=10, **kw):
        super().__init__(parent, width=width, height=height,
                         bg=kw.pop("bg_color", parent["bg"]),
                         highlightthickness=0, cursor="hand2", **kw)
        self._bg, self._fg = bg, fg
        self._hover = hover or (ACCENT_HOVER if bg == ACCENT else "#e0e0e0")
        self._text, self._radius, self._cmd, self._font_size = text, radius, command, font_size
        self._draw(bg)
        self.bind("<Enter>", lambda e: self._draw(self._hover))
        self.bind("<Leave>", lambda e: self._draw(self._bg))
        self.bind("<Button-1>", lambda e: self._cmd() if self._cmd else None)

    def _draw(self, color):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        r = self._radius
        self.create_polygon(r,0, w-r,0, w,r, w,h-r, w-r,h, r,h, 0,h-r, 0,r,
                            fill=color, smooth=True)
        self.create_text(w//2, h//2, text=self._text, fill=self._fg,
                         font=("微软雅黑", self._font_size, "bold"))


class M3U8Downloader:
    """M3U8解析+下载引擎"""
    
    def __init__(self, log_fn=None, progress_fn=None):
        self.log = log_fn or print
        self.progress = progress_fn or (lambda *a: None)
        self._cancel = False
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        self.cookie = ""
        self.referer = ""
    
    def cancel(self):
        self._cancel = True
    
    def set_headers(self, referer="", cookie="", ua=""):
        if referer:
            self.headers["Referer"] = referer
            self.referer = referer
        if cookie:
            self.headers["Cookie"] = cookie
            self.cookie = cookie
        if ua:
            self.headers["User-Agent"] = ua
    
    def parse(self, url):
        """解析m3u8, 返回segment列表和密钥信息"""
        import requests as req
        import urllib3
        urllib3.disable_warnings()
        
        s = req.Session()
        s.verify = False
        s.headers.update(self.headers)
        
        self.log(f"获取m3u8...")
        try:
            r = s.get(url, timeout=15)
            r.raise_for_status()
            content = r.text
        except Exception as e:
            self.log(f"获取失败: {e}")
            return None
        
        # master playlist → 选最高码率子流
        if "#EXT-X-STREAM-INF" in content:
            self.log(f"检测到master playlist, 解析子流...")
            streams = []
            lines = content.strip().split("\n")
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF"):
                    bw = re.search(r"BANDWIDTH=(\d+)", line)
                    res = re.search(r"RESOLUTION=(\d+x\d+)", line)
                    bw_val = int(bw.group(1)) if bw else 0
                    res_val = res.group(1) if res else ""
                    if i + 1 < len(lines):
                        sub = lines[i + 1].strip()
                        if not sub.startswith("http"):
                            sub = urljoin(url, sub)
                        streams.append({"url": sub, "bandwidth": bw_val, "resolution": res_val})
            
            if streams:
                streams.sort(key=lambda x: x["bandwidth"], reverse=True)
                self.log(f"  {len(streams)}条子流:")
                for s_item in streams[:5]:
                    self.log(f"    {s_item['resolution']} {s_item['bandwidth']//1000}kbps")
                url = streams[0]["url"]
                self.log(f"  选中: {streams[0]['resolution']} {streams[0]['bandwidth']//1000}kbps")
                # 重新获取子m3u8
                try:
                    r = s.get(url, timeout=15)
                    content = r.text
                except Exception as e:
                    self.log(f"子流获取失败: {e}")
                    return None
        
        # 解析segment
        lines = content.strip().split("\n")
        segments = []
        key_info = None
        duration_total = 0
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 加密密钥
            if line.startswith("#EXT-X-KEY"):
                uri_m = re.search(r'URI="([^"]+)"', line)
                method_m = re.search(r"METHOD=(\w+)", line)
                if uri_m and method_m:
                    key_url = urljoin(url, uri_m.group(1))
                    key_info = {"method": method_m.group(1), "url": key_url}
                    # 获取密钥
                    try:
                        kr = s.get(key_url, timeout=10)
                        key_info["data"] = kr.content
                        self.log(f"  密钥: {key_info['method']} ({len(kr.content)}字节)")
                    except:
                        self.log(f"  密钥获取失败!")
                i += 1
                continue
            
            # segment
            if line.startswith("#EXTINF"):
                dur_m = re.search(r"#EXTINF:([\d.]+)", line)
                dur = float(dur_m.group(1)) if dur_m else 0
                duration_total += dur
                if i + 1 < len(lines):
                    seg_url = lines[i + 1].strip()
                    if not seg_url.startswith("#"):
                        if not seg_url.startswith("http"):
                            seg_url = urljoin(url, seg_url)
                        segments.append({"url": seg_url, "duration": dur, "index": len(segments)})
                i += 2
                continue
            
            i += 1
        
        result = {
            "segments": segments,
            "count": len(segments),
            "duration": duration_total,
            "key": key_info,
            "m3u8_url": url,
        }
        
        self.log(f"解析完成: {len(segments)}个片段, {duration_total:.0f}秒 ({duration_total/60:.1f}分钟)")
        return result
    
    def download(self, info, output_path, threads=8):
        """多线程下载 + ffmpeg合并"""
        import requests as req
        import urllib3
        urllib3.disable_warnings()
        
        segments = info["segments"]
        key = info["key"]
        total = len(segments)
        
        if total == 0:
            self.log("没有片段可下载")
            return False
        
        # 创建临时目录
        tmp_dir = tempfile.mkdtemp(prefix="m3u8_dl_")
        self.log(f"下载目录: {tmp_dir}")
        self.log(f"线程数: {threads}")
        
        self._cancel = False
        downloaded = [0]  # 用list以便在闭包中修改
        failed = [0]
        lock = threading.Lock()
        
        def download_seg(seg):
            if self._cancel:
                return
            idx = seg["index"]
            url = seg["url"]
            out_file = os.path.join(tmp_dir, f"{idx:06d}.ts")
            
            for retry in range(3):
                try:
                    s = req.Session()
                    s.verify = False
                    s.headers.update(self.headers)
                    r = s.get(url, timeout=30)
                    r.raise_for_status()
                    data = r.content
                    
                    # AES-128解密
                    if key and key.get("data") and key.get("method") == "AES-128":
                        try:
                            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                            from cryptography.hazmat.backends import default_backend
                            iv = key.get("iv") or (idx.to_bytes(16, 'big'))
                            cipher = Cipher(algorithms.AES(key["data"]), modes.CBC(iv),
                                          backend=default_backend())
                            decryptor = cipher.decryptor()
                            data = decryptor.update(data) + decryptor.finalize()
                            # 去PKCS7 padding
                            pad_len = data[-1]
                            if pad_len <= 16:
                                data = data[:-pad_len]
                        except ImportError:
                            pass  # 没有cryptography库就跳过解密
                    
                    with open(out_file, "wb") as f:
                        f.write(data)
                    
                    with lock:
                        downloaded[0] += 1
                        self.progress(downloaded[0], total)
                        pct = downloaded[0] / total * 100
                        if downloaded[0] % max(1, total // 20) == 0 or downloaded[0] == total:
                            self.log(f"  下载 {downloaded[0]}/{total} ({pct:.0f}%)")
                    return
                except Exception as e:
                    if retry < 2:
                        time.sleep(1)
                    else:
                        with lock:
                            failed[0] += 1
                            downloaded[0] += 1
                        self.log(f"  ✗ 片段{idx}失败: {str(e)[:50]}")
        
        # 多线程下载
        self.log(f"开始下载 {total} 个片段...")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = [pool.submit(download_seg, seg) for seg in segments]
            for f in futures:
                if self._cancel:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                f.result()
        
        elapsed = time.time() - start_time
        self.log(f"下载完成: {elapsed:.1f}秒, 成功{total - failed[0]}, 失败{failed[0]}")
        
        if self._cancel:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return False
        
        if failed[0] > total * 0.1:  # 超过10%失败
            self.log(f"警告: {failed[0]}个片段失败, 视频可能不完整")
        
        # 合并
        self.log(f"ffmpeg合并中...")
        concat_file = os.path.join(tmp_dir, "concat.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for i in range(total):
                ts_path = os.path.join(tmp_dir, f"{i:06d}.ts")
                if os.path.exists(ts_path) and os.path.getsize(ts_path) > 0:
                    # 用正斜杠避免Windows路径问题
                    f.write(f"file '{ts_path.replace(chr(92), '/')}'\n")
        
        ffmpeg = _find_ffmpeg()
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file.replace("\\", "/"),
            "-c", "copy",
            "-movflags", "+faststart",
            "-hide_banner", "-loglevel", "warning",
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=600,
                                    encoding="utf-8", errors="replace")
            if result.returncode != 0:
                self.log(f"ffmpeg失败: {result.stderr[:200]}")
                # 尝试重编码
                self.log(f"尝试重编码...")
                cmd2 = [
                    ffmpeg, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file.replace("\\", "/"),
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    "-hide_banner", "-loglevel", "warning",
                    output_path
                ]
                result = subprocess.run(cmd2, capture_output=True, timeout=1200,
                                        encoding="utf-8", errors="replace")
                if result.returncode != 0:
                    self.log(f"重编码也失败: {result.stderr[:200]}")
                    return False
        except subprocess.TimeoutExpired:
            self.log(f"ffmpeg超时")
            return False
        
        # 清理
        shutil.rmtree(tmp_dir, ignore_errors=True)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            sz = os.path.getsize(output_path)
            self.log(f"完成! {sz/1024/1024:.1f}MB → {output_path}")
            return True
        
        self.log(f"输出文件异常")
        return False


# 需要导入
from concurrent.futures import ThreadPoolExecutor


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("M3U8下载器 — 猫抓风格")
        self.root.geometry("880x620")
        self.root.minsize(750, 520)
        self.root.configure(bg=BG_MAIN)
        
        self.downloader = M3U8Downloader(log_fn=self._log, progress_fn=self._progress)
        self.m3u8_info = None
        self._downloading = False
        self.msg_queue = queue.Queue()
        
        self._build_ui()
        self._poll_queue()
    
    def _build_ui(self):
        # ===== 侧边栏 =====
        sidebar = tk.Frame(self.root, bg=BG_DARK, width=170)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        
        tk.Label(sidebar, text="🎬 M3U8下载器", bg=BG_DARK, fg=TEXT_DARK,
                 font=("微软雅黑", 13, "bold")).pack(pady=(20, 5), padx=12, anchor="w")
        tk.Label(sidebar, text="解析 · 下载 · 合并", bg=BG_DARK, fg="#888",
                 font=("微软雅黑", 8)).pack(padx=12, anchor="w", pady=(0, 15))
        
        tk.Frame(sidebar, bg="#333", height=1).pack(fill=tk.X, padx=12, pady=5)
        
        # 步骤
        self.step_labels = []
        for txt in ["1. 输入链接", "2. 解析信息", "3. 开始下载", "4. 合并完成"]:
            lbl = tk.Label(sidebar, text=txt, bg=BG_DARK, fg="#666",
                           font=("微软雅黑", 10), anchor="w", padx=12)
            lbl.pack(fill=tk.X, pady=2)
            self.step_labels.append(lbl)
        self._highlight_step(0)
        
        # 信息面板
        tk.Frame(sidebar, bg="#333", height=1).pack(fill=tk.X, padx=12, pady=8)
        
        self.info_labels = {}
        for key, label in [("segments", "片段数:"), ("duration", "时长:"), ("size", "预估大小:"), ("speed", "下载速度:")]:
            f = tk.Frame(sidebar, bg=BG_DARK)
            f.pack(fill=tk.X, padx=12, pady=1)
            tk.Label(f, text=label, bg=BG_DARK, fg="#888", font=("微软雅黑", 8), anchor="w").pack(side=tk.LEFT)
            v = tk.Label(f, text="--", bg=BG_DARK, fg=TEXT_DARK, font=("微软雅黑", 8, "bold"), anchor="e")
            v.pack(side=tk.RIGHT)
            self.info_labels[key] = v
        
        # 底部
        tk.Frame(sidebar, bg="#333", height=1).pack(fill=tk.X, padx=12, pady=5, side=tk.BOTTOM)
        self.sidebar_status = tk.Label(sidebar, text="就绪", bg=BG_DARK, fg="#666",
                                        font=("微软雅黑", 8), padx=12, anchor="w")
        self.sidebar_status.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        # ===== 主内容区 =====
        main = tk.Frame(self.root, bg=BG_MAIN)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 顶栏
        top = tk.Frame(main, bg=BG_CARD, height=48)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="M3U8 视频下载", bg=BG_CARD, fg=TEXT_PRIMARY,
                 font=("微软雅黑", 13, "bold")).pack(side=tk.LEFT, padx=16, pady=8)
        
        # 输入区
        input_frame = tk.Frame(main, bg=BG_MAIN)
        input_frame.pack(fill=tk.X, padx=16, pady=(10, 4))
        
        tk.Label(input_frame, text="M3U8链接:", bg=BG_MAIN, fg=TEXT_PRIMARY,
                 font=("微软雅黑", 9)).pack(anchor="w")
        
        url_row = tk.Frame(input_frame, bg=BG_MAIN)
        url_row.pack(fill=tk.X, pady=(2, 0))
        
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(url_row, textvariable=self.url_var, font=("Consolas", 9),
                                   relief=tk.SOLID, borderwidth=1)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.url_entry.bind("<Return>", lambda e: self._parse())
        
        ModernButton(url_row, text="解析", bg=ACCENT, width=60, height=30,
                     command=self._parse).pack(side=tk.LEFT, padx=(6, 0))
        
        # Headers区
        hdr_frame = tk.Frame(main, bg=BG_MAIN)
        hdr_frame.pack(fill=tk.X, padx=16, pady=(0, 4))
        
        hdr_row1 = tk.Frame(hdr_frame, bg=BG_MAIN)
        hdr_row1.pack(fill=tk.X, pady=1)
        tk.Label(hdr_row1, text="Referer:", bg=BG_MAIN, fg=TEXT_SECONDARY, font=("微软雅黑", 8)).pack(side=tk.LEFT)
        self.referer_var = tk.StringVar()
        tk.Entry(hdr_row1, textvariable=self.referer_var, font=("微软雅黑", 8), width=40).pack(side=tk.LEFT, padx=4)
        tk.Label(hdr_row1, text="Cookie:", bg=BG_MAIN, fg=TEXT_SECONDARY, font=("微软雅黑", 8)).pack(side=tk.LEFT, padx=(8, 0))
        self.cookie_var = tk.StringVar()
        tk.Entry(hdr_row1, textvariable=self.cookie_var, font=("微软雅黑", 8), width=30).pack(side=tk.LEFT, padx=4)
        
        # 按钮栏
        btn_frame = tk.Frame(main, bg=BG_MAIN)
        btn_frame.pack(fill=tk.X, padx=16, pady=(4, 4))
        
        self.btn_download = ModernButton(btn_frame, text="⬇ 开始下载", bg=GREEN,
                                          hover=GREEN_HOVER, width=100, height=34,
                                          command=self._download)
        self.btn_download.pack(side=tk.LEFT, padx=(0, 8))
        
        self.btn_stop = ModernButton(btn_frame, text="⏹ 停止", bg=RED,
                                      hover="#dc2626", width=70, height=34,
                                      command=self._stop)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))
        
        # 输出路径
        out_row = tk.Frame(btn_frame, bg=BG_MAIN)
        out_row.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(out_row, text="保存到:", bg=BG_MAIN, fg=TEXT_SECONDARY, font=("微软雅黑", 8)).pack(side=tk.LEFT)
        self.out_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        tk.Entry(out_row, textvariable=self.out_var, font=("微软雅黑", 8)).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ModernButton(out_row, text="📁", bg=BG_CARD, fg=TEXT_PRIMARY, hover="#e0e0e0",
                     width=30, height=28, command=self._browse_out, font_size=9).pack(side=tk.LEFT)
        
        # 线程数
        tk.Label(btn_frame, text="线程:", bg=BG_MAIN, fg=TEXT_SECONDARY, font=("微软雅黑", 8)).pack(side=tk.LEFT, padx=(8, 2))
        self.thread_var = tk.StringVar(value="8")
        ttk.Combobox(btn_frame, textvariable=self.thread_var, values=["4", "8", "16", "32"],
                      width=3, state="readonly").pack(side=tk.LEFT)
        
        # 进度条
        progress_frame = tk.Frame(main, bg=BG_MAIN)
        progress_frame.pack(fill=tk.X, padx=16, pady=(0, 4))
        
        self.progress_var = tk.DoubleVar(value=0)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("green.Horizontal.TProgressbar", troughcolor="#e5e7eb",
                         background=GREEN, thickness=16)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                             maximum=100, style="green.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X)
        
        self.progress_label = tk.Label(progress_frame, text="0%", bg=BG_MAIN, fg=TEXT_SECONDARY,
                                        font=("微软雅黑", 8))
        self.progress_label.pack(anchor="e")
        
        # 日志
        log_card = tk.Frame(main, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        log_card.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        
        tk.Label(log_card, text="📋 日志", bg=BG_CARD, fg=TEXT_PRIMARY,
                 font=("微软雅黑", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
        
        log_frame = tk.Frame(log_card, bg=BG_CARD)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 6))
        
        self.log_text = tk.Text(log_frame, font=("Consolas", 9), bg="#fafafa",
                                 relief=tk.FLAT, wrap=tk.WORD, state=tk.DISABLED)
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _highlight_step(self, idx):
        for i, lbl in enumerate(self.step_labels):
            if i == idx:
                lbl.configure(fg=ACCENT, font=("微软雅黑", 10, "bold"))
            elif i < idx:
                lbl.configure(fg=GREEN, font=("微软雅黑", 10))
            else:
                lbl.configure(fg="#666", font=("微软雅黑", 10))
    
    def _log(self, msg):
        self.msg_queue.put(("log", msg))
    
    def _progress(self, current, total):
        pct = current / total * 100 if total > 0 else 0
        self.msg_queue.put(("progress", pct))
    
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "log":
                    self.log_text.configure(state=tk.NORMAL)
                    self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg[1]}\n")
                    self.log_text.see(tk.END)
                    self.log_text.configure(state=tk.DISABLED)
                elif msg[0] == "progress":
                    self.progress_var.set(msg[1])
                    self.progress_label.configure(text=f"{msg[1]:.0f}%")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)
    
    def _browse_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get())
        if d:
            self.out_var.set(d)
    
    def _parse(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入M3U8链接")
            return
        
        self._highlight_step(1)
        self.downloader.set_headers(
            referer=self.referer_var.get().strip(),
            cookie=self.cookie_var.get().strip()
        )
        
        threading.Thread(target=self._parse_worker, args=(url,), daemon=True).start()
    
    def _parse_worker(self, url):
        self.m3u8_info = self.downloader.parse(url)
        if self.m3u8_info:
            info = self.m3u8_info
            self.msg_queue.put(("info", ("segments", f"{info['count']}个")))
            dur = info["duration"]
            self.msg_queue.put(("info", ("duration", f"{dur/60:.1f}分钟")))
            # 预估大小 (假设2Mbps)
            est_mb = dur * 250 / 1024  # 2Mbps ≈ 250KB/s
            self.msg_queue.put(("info", ("size", f"~{est_mb:.0f}MB")))
            self._highlight_step(2)
            self.sidebar_status.configure(text="解析完成, 可以下载")
        else:
            self._log("解析失败!")
    
    def _download(self):
        if not self.m3u8_info:
            messagebox.showwarning("提示", "请先解析M3U8链接")
            return
        
        if self._downloading:
            return
        
        # 生成输出文件名
        url = self.url_var.get().strip()
        parsed = urlparse(url)
        path_parts = parsed.path.rstrip("/").split("/")
        default_name = path_parts[-2] if len(path_parts) >= 2 else "video"
        default_name = re.sub(r'[<>:"/\\|?*]', '_', default_name)
        
        out_dir = self.out_var.get().strip()
        output_path = os.path.join(out_dir, f"{default_name}.mp4")
        
        # 如果文件已存在, 加序号
        if os.path.exists(output_path):
            base, ext = os.path.splitext(output_path)
            for n in range(1, 100):
                output_path = f"{base}_{n}{ext}"
                if not os.path.exists(output_path):
                    break
        
        self._downloading = True
        self._highlight_step(3)
        self.progress_var.set(0)
        self.downloader.set_headers(
            referer=self.referer_var.get().strip(),
            cookie=self.cookie_var.get().strip()
        )
        
        threads = int(self.thread_var.get())
        threading.Thread(target=self._download_worker, args=(output_path, threads), daemon=True).start()
    
    def _download_worker(self, output_path, threads):
        start = time.time()
        ok = self.downloader.download(self.m3u8_info, output_path, threads=threads)
        elapsed = time.time() - start
        
        if ok:
            sz = os.path.getsize(output_path) / 1024 / 1024
            self.msg_queue.put(("info", ("speed", f"{sz/elapsed:.1f}MB/s")))
            self.msg_queue.put(("log", f"✅ 完成! {sz:.1f}MB, 耗时{elapsed:.0f}秒"))
            self.msg_queue.put(("progress", 100))
            self._highlight_step(4)
        else:
            self.msg_queue.put(("log", "❌ 下载失败"))
        
        self._downloading = False
    
    def _stop(self):
        self.downloader.cancel()
        self._log("用户停止")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
