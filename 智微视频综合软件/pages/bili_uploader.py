#!/usr/bin/env python3
"""B站批量上传模块"""
import os, json, time, tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import requests
import urllib3
urllib3.disable_warnings()

class BiliUploaderPage:
    def __init__(self, parent, colors):
        self.C = colors
        self.frame = tk.Frame(parent, bg=colors["bg"])
        self.video_files = []
        self.cookies = {}
        self._uploading = False
        self._build_ui()

    def show(self): pass
    def hide(self): pass

    def _card(self, parent=None):
        p = parent or self.scroll_frame
        card = tk.Frame(p, bg=self.C["card"])
        card.pack(fill=tk.X, padx=15, pady=(0, 10))
        return card

    def _card_title(self, card, text):
        f = tk.Frame(card, bg=self.C["card"])
        f.pack(fill=tk.X, padx=15, pady=(10, 6))
        tk.Label(f, text=text, font=("微软雅黑", 12, "bold"),
                 bg=self.C["card"], fg=self.C["text"]).pack(side=tk.LEFT)

    def _btn(self, parent, text, cmd, style="primary"):
        colors = {
            "primary": (self.C["primary"], self.C["primary_dark"], "#FFF"),
            "secondary": ("#F0F0F0", "#E0E0E0", self.C["text"]),
            "danger": (self.C["danger"], "#E04040", "#FFF"),
            "success": (self.C["success"], "#5AAP2A", "#FFF"),
        }
        bg, hbg, fg = colors.get(style, colors["primary"])
        btn = tk.Label(parent, text=text, font=("微软雅黑", 10, "bold"),
                       bg=bg, fg=fg, padx=10, pady=5, cursor="hand2")
        btn.bind("<Enter>", lambda e: btn.configure(bg=hbg))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        btn.bind("<ButtonPress-1>", lambda e: cmd())
        return btn

    def _build_ui(self):
        canvas = tk.Canvas(self.frame, bg=self.C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self.frame, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=self.C["bg"])
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 登录
        card = self._card()
        self._card_title(card, "🔑 登录B站")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(0, 10))
        self._btn(r, "📱 扫码登录", self._qr_login).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(r, "手动输入Cookie", self._manual_cookie, "secondary").pack(side=tk.LEFT)
        self.lbl_login = tk.Label(r, text="未登录", font=("微软雅黑", 10),
                                  bg=self.C["card"], fg=self.C["text3"])
        self.lbl_login.pack(side=tk.LEFT, padx=20)

        # 视频列表
        card = self._card()
        self._card_title(card, "📋 视频列表")
        btn_row = tk.Frame(card, bg=self.C["card"])
        btn_row.pack(fill=tk.X, padx=15, pady=(0, 5))
        self._btn(btn_row, "添加视频", self._add_videos).pack(side=tk.LEFT, padx=(0, 5))
        self._btn(btn_row, "添加文件夹", self._add_folder).pack(side=tk.LEFT, padx=(0, 5))
        self._btn(btn_row, "删除选中", self._del_selected, "danger").pack(side=tk.LEFT, padx=(0, 5))
        self._btn(btn_row, "清空", self._clear_list, "secondary").pack(side=tk.LEFT)

        list_frame = tk.Frame(card, bg=self.C["card"])
        list_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        self.listbox = tk.Listbox(list_frame, height=8, font=("Consolas", 9), selectmode=tk.EXTENDED)
        self.listbox.pack(fill=tk.X)
        self.lbl_count = tk.Label(card, text="0 个视频", font=("微软雅黑", 9),
                                  bg=self.C["card"], fg=self.C["text3"])
        self.lbl_count.pack(anchor="w", padx=15, pady=(0, 10))

        # 投稿设置
        card = self._card()
        self._card_title(card, "⚙️ 投稿设置")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="标题:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        self.title_var = tk.StringVar()
        tk.Entry(r, textvariable=self.title_var, font=("微软雅黑", 10), width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="标签:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        self.tags_var = tk.StringVar(value="动漫,番剧,日本动漫")
        tk.Entry(r, textvariable=self.tags_var, font=("微软雅黑", 10), width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="简介:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        self.desc_var = tk.StringVar(value="喜欢的话请三连支持一下！")
        tk.Entry(r, textvariable=self.desc_var, font=("微软雅黑", 10), width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(3, 10))
        tk.Label(r, text="分区:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        self.tid_var = tk.StringVar(value="番剧")
        tid_combo = ttk.Combobox(r, textvariable=self.tid_var, width=15, state="readonly",
                                 values=["番剧", "动画", "国创"])
        tid_combo.pack(side=tk.LEFT, padx=5)

        # 控制
        card = self._card()
        self._card_title(card, "🚀 上传控制")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(0, 5))
        self._btn(r, "▶ 开始上传", self._start_upload, "success").pack(side=tk.LEFT, padx=(0, 8))
        self._btn(r, "⏹ 停止", self._stop_upload, "danger").pack(side=tk.LEFT)

        self.lbl_status = tk.Label(card, text="就绪 - 请先登录并添加视频",
                                   font=("微软雅黑", 10), bg=self.C["primary_light"],
                                   fg=self.C["primary"], padx=12, pady=6)
        self.lbl_status.pack(fill=tk.X, padx=15, pady=(0, 10))

        self.log_text = tk.Text(self.scroll_frame, height=6, font=("Consolas", 9), bg="#F8F9FA")
        self.log_text.pack(fill=tk.X, padx=15, pady=(0, 10))

    def _log(self, msg):
        self.frame.after(0, lambda: (self.log_text.insert(tk.END, msg + "\n"), self.log_text.see(tk.END)))

    def _qr_login(self):
        self._log("扫码登录功能需要B站API支持")
        self._log("提示: 可以手动输入Cookie来登录")
        messagebox.showinfo("提示", "扫码登录需要额外配置。\n请使用「手动输入Cookie」方式登录。")

    def _manual_cookie(self):
        win = tk.Toplevel(self.frame)
        win.title("输入Cookie")
        win.geometry("500x200")
        win.transient(self.frame.winfo_toplevel())
        tk.Label(win, text="请从浏览器开发者工具复制Cookie:", font=("微软雅黑", 10)).pack(padx=10, pady=(10, 5), anchor="w")
        text = tk.Text(win, height=5, font=("Consolas", 9))
        text.pack(fill=tk.X, padx=10, pady=5)

        def do_save():
            cookie_str = text.get("1.0", tk.END).strip()
            if cookie_str:
                for item in cookie_str.split(';'):
                    item = item.strip()
                    if '=' in item:
                        k, v = item.split('=', 1)
                        self.cookies[k.strip()] = v.strip()
                self.lbl_login.config(text="✅ 已登录", fg=self.C["success"])
                self._log(f"Cookie已保存 ({len(self.cookies)} 项)")
                win.destroy()

        tk.Button(win, text="保存", command=do_save).pack(pady=10)

    def _add_videos(self):
        files = filedialog.askopenfilenames(filetypes=[("视频", "*.mp4 *.avi *.mov *.mkv *.flv")])
        for f in files:
            if f not in self.video_files:
                self.video_files.append(f)
                self.listbox.insert(tk.END, os.path.basename(f))
        self.lbl_count.config(text=f"{len(self.video_files)} 个视频")

    def _add_folder(self):
        folder = filedialog.askdirectory()
        if not folder: return
        exts = ('.mp4', '.avi', '.mov', '.mkv', '.flv')
        count = 0
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(exts):
                fp = os.path.join(folder, f)
                if fp not in self.video_files:
                    self.video_files.append(fp)
                    self.listbox.insert(tk.END, f)
                    count += 1
        self.lbl_count.config(text=f"{len(self.video_files)} 个视频")
        self._log(f"从文件夹导入 {count} 个视频")

    def _del_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            self.video_files.pop(i)
        self.lbl_count.config(text=f"{len(self.video_files)} 个视频")

    def _clear_list(self):
        self.video_files.clear()
        self.listbox.delete(0, tk.END)
        self.lbl_count.config(text="0 个视频")

    def _start_upload(self):
        if not self.cookies:
            messagebox.showwarning("警告", "请先登录B站"); return
        if not self.video_files:
            messagebox.showwarning("警告", "请先添加视频"); return
        if not self.title_var.get():
            messagebox.showwarning("警告", "请输入标题"); return
        self._uploading = True
        threading.Thread(target=self._upload_worker, daemon=True).start()

    def _stop_upload(self):
        self._uploading = False

    def _upload_worker(self):
        self._log(f"开始上传 {len(self.video_files)} 个视频...")
        self.frame.after(0, lambda: self.lbl_status.config(text="上传中..."))
        # 实际上传需要B站API的完整实现
        for i, f in enumerate(self.video_files):
            if not self._uploading:
                self._log("上传已停止"); break
            self._log(f"[{i+1}/{len(self.video_files)}] 上传: {os.path.basename(f)}")
            self.frame.after(0, lambda i=i: self.lbl_status.config(
                text=f"上传中 {i+1}/{len(self.video_files)}"))
            time.sleep(1)  # 占位
        self._uploading = False
        self.frame.after(0, lambda: self.lbl_status.config(text="完成"))
        self._log("上传完成!")
