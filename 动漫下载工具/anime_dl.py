#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动漫下载工具 - 支持番茶屋等网站
自动提取m3u8链接并下载
"""
import os, sys, json, time, re, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess

C = {
    "bg": "#F6F8FA", "card": "#FFFFFF", "primary": "#00A1D6",
    "text": "#222", "text2": "#666", "text3": "#999",
    "success": "#67C23A", "danger": "#F56C6C",
}

class AnimeDownloader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("动漫下载工具")
        self.root.geometry("700x550")
        self.root.configure(bg=C["bg"])
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self.root, bg=C["primary"], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="📺 动漫下载工具", font=("微软雅黑", 14, "bold"),
                 bg=C["primary"], fg="white").pack(side=tk.LEFT, padx=16)

        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # URL输入区
        url_card = tk.Frame(main, bg=C["card"], padx=12, pady=10)
        url_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(url_card, text="🔗 视频链接", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        fr = tk.Frame(url_card, bg=C["card"])
        fr.pack(fill=tk.X, pady=6)
        self.url_var = tk.StringVar()
        tk.Entry(fr, textvariable=self.url_var, font=("Consolas", 10), width=60,
                 bg="#F6F8FA", relief="flat").pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(fr, text="粘贴", font=("微软雅黑", 9), bg="#E5E7EB", fg=C["text"],
                  relief="flat", padx=8, cursor="hand2",
                  command=lambda: self.url_var.set(self.root.clipboard_get())).pack(side=tk.LEFT, padx=6)

        # 支持格式说明
        tk.Label(url_card, text="支持: m3u8链接 | 番茶屋网页链接 | 直链mp4",
                 font=("微软雅黑", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w")

        # 下载目录
        dir_card = tk.Frame(main, bg=C["card"], padx=12, pady=10)
        dir_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(dir_card, text="📁 保存目录", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        dr = tk.Frame(dir_card, bg=C["card"])
        dr.pack(fill=tk.X, pady=6)
        self.dir_var = tk.StringVar(value=r"C:\Users\Lenovo\Desktop")
        tk.Entry(dr, textvariable=self.dir_var, font=("Consolas", 10), width=55,
                 bg="#F6F8FA", relief="flat").pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(dr, text="选择", font=("微软雅黑", 9), bg="#E5E7EB", fg=C["text"],
                  relief="flat", padx=8, cursor="hand2",
                  command=lambda: self.dir_var.set(filedialog.askdirectory())).pack(side=tk.LEFT, padx=6)

        # 文件名
        fn = tk.Frame(dir_card, bg=C["card"])
        fn.pack(fill=tk.X, pady=4)
        tk.Label(fn, text="文件名:", font=("微软雅黑", 10), bg=C["card"]).pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value="")
        tk.Entry(fn, textvariable=self.name_var, font=("微软雅黑", 10), width=40,
                 bg="#F6F8FA", relief="flat").pack(side=tk.LEFT, padx=8)
        tk.Label(fn, text="(留空自动识别)", font=("微软雅黑", 9), bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)

        # 按钮区
        br = tk.Frame(main, bg=C["card"], padx=12, pady=10)
        br.pack(fill=tk.X, pady=(0, 10))
        self.btn_dl = tk.Button(br, text="🚀 开始下载", font=("微软雅黑", 12, "bold"),
                                bg=C["success"], fg="white", relief="flat",
                                padx=20, pady=8, cursor="hand2", command=self._start_download)
        self.btn_dl.pack(side=tk.LEFT)
        self.btn_stop = tk.Button(br, text="⏹ 停止", font=("微软雅黑", 11),
                                  bg=C["danger"], fg="white", relief="flat",
                                  padx=14, pady=8, cursor="hand2", state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=10)
        self.lbl_status = tk.Label(br, text="", font=("微软雅黑", 10),
                                   bg=C["card"], fg=C["primary"])
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # 日志
        log_card = tk.Frame(main, bg=C["card"], padx=12, pady=10)
        log_card.pack(fill=tk.BOTH, expand=True)
        tk.Label(log_card, text="📝 日志", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        self.log_text = tk.Text(log_card, height=8, font=("Consolas", 9),
                                bg="#1E1E1E", fg="#D4D4D4", relief="flat", wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=4)
        scroll = tk.Scrollbar(self.log_text, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.root.after(0, lambda: (
            self.log_text.insert(tk.END, line),
            self.log_text.see(tk.END)
        ))

    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入视频链接")
            return
        self.btn_dl.config(state="disabled")
        self.btn_stop.config(state="normal")
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url):
        try:
            save_dir = self.dir_var.get().strip()
            if not save_dir:
                save_dir = r"C:\Users\Lenovo\Desktop"
            os.makedirs(save_dir, exist_ok=True)

            # 判断URL类型
            if ".m3u8" in url:
                # 直接是m3u8链接
                m3u8_url = url
                self._log(f"✅ 检测到m3u8链接")
            elif "fanchawu" in url or "vodplay" in url:
                # 番茶屋网页链接，需要提取m3u8
                self._log("🔍 正在从网页提取m3u8链接...")
                m3u8_url = self._extract_m3u8_from_page(url)
                if not m3u8_url:
                    self._log("❌ 无法提取m3u8链接，请手动复制m3u8地址")
                    self.root.after(0, lambda: (
                        self.btn_dl.config(state="normal"),
                        self.btn_stop.config(state="disabled")))
                    return
            elif ".mp4" in url:
                # 直链mp4
                m3u8_url = url
                self._log("✅ 检测到mp4直链")
            else:
                # 尝试作为网页提取
                self._log("🔍 尝试从网页提取视频链接...")
                m3u8_url = self._extract_m3u8_from_page(url)
                if not m3u8_url:
                    self._log("❌ 无法提取视频链接")
                    self.root.after(0, lambda: (
                        self.btn_dl.config(state="normal"),
                        self.btn_stop.config(state="disabled")))
                    return

            # 确定文件名
            name = self.name_var.get().strip()
            if not name:
                if ".m3u8" in m3u8_url:
                    # 从URL提取名称
                    name = m3u8_url.split("/")[-2] if m3u8_url.count("/") > 3 else "anime"
                else:
                    name = "anime"
            if not name.endswith(".mp4"):
                name += ".mp4"

            save_path = os.path.join(save_dir, name)
            self._log(f"📁 保存到: {save_path}")
            self._log(f"🔗 视频源: {m3u8_url[:80]}...")

            # 用ffmpeg下载
            self._log("⬇️ 开始下载...")
            cmd = [
                "ffmpeg", "-i", m3u8_url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-y", save_path
            ]
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )

            # 读取输出
            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    text = line.decode('utf-8', errors='ignore').strip()
                    if 'time=' in text:
                        # 提取进度
                        match = re.search(r'time=(\d+:\d+:\d+)', text)
                        if match:
                            self.root.after(0, lambda t=match.group(1): self.lbl_status.config(text=f"下载中: {t}"))
                    elif 'error' in text.lower():
                        self._log(f"⚠️ {text}")

            if process.returncode == 0:
                size = os.path.getsize(save_path) / 1048576
                self._log(f"✅ 下载完成! {name} ({size:.1f}MB)")
                self.root.after(0, lambda: self.lbl_status.config(text="✅ 下载完成"))
            else:
                self._log(f"❌ 下载失败 (返回码: {process.returncode})")

        except Exception as e:
            self._log(f"❌ 错误: {e}")
        finally:
            self.root.after(0, lambda: (
                self.btn_dl.config(state="normal"),
                self.btn_stop.config(state="disabled")))

    def _extract_m3u8_from_page(self, url):
        """从网页提取m3u8链接"""
        try:
            import requests
            from bs4 import BeautifulSoup

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.google.com/',
            }
            r = requests.get(url, headers=headers, timeout=15)
            r.encoding = r.apparent_encoding
            html = r.text

            # 方法1: 直接正则搜索m3u8
            m3u8_urls = re.findall(r'https?://[^\s"\\'\']+\.m3u8[^\s"\\'\']*', html)
            if m3u8_urls:
                self._log(f"✅ 找到 {len(m3u8_urls)} 个m3u8链接")
                return m3u8_urls[0]

            # 方法2: 搜索iframe
            soup = BeautifulSoup(html, 'html.parser')
            iframes = soup.find_all('iframe')
            for iframe in iframes:
                src = iframe.get('src', '')
                if src and ('player' in src or 'video' in src):
                    self._log(f"🔍 发现播放器iframe: {src[:60]}...")
                    # 递归获取iframe内容
                    r2 = requests.get(src, headers=headers, timeout=15)
                    m3u8_in_frame = re.findall(r'https?://[^\s"\\'\']+\.m3u8[^\s"\\'\']*', r2.text)
                    if m3u8_in_frame:
                        return m3u8_in_frame[0]

            # 方法3: 搜索script中的m3u8
            scripts = soup.find_all('script')
            for s in scripts:
                text = s.string or ''
                m3u8_in_script = re.findall(r'https?://[^\s"\\'\']+\.m3u8[^\s"\\'\']*', text)
                if m3u8_in_script:
                    return m3u8_in_script[0]

            return None
        except Exception as e:
            self._log(f"⚠️ 提取失败: {e}")
            return None

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AnimeDownloader()
    app.run()
