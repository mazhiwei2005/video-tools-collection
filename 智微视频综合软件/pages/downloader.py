#!/usr/bin/env python3
"""稀饭动漫下载模块 v2.0 - 动态高级版"""
import os, re, json, time, math, tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading, queue
import requests, urllib3
urllib3.disable_warnings()

SITE = "https://anime.xifanacg.com"

# ── 动画卡片 ──
class AnimatedCard(tk.Frame):
    """悬浮发光 + 上浮效果的卡片"""
    def __init__(self, parent, colors, **kw):
        super().__init__(parent, bg=colors["card"], **kw)
        self.C = colors
        self._shadow = tk.Frame(parent, bg="#E0E4E8", height=2)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def pack(self, **kw):
        super().pack(**kw)

    def _on_enter(self, e):
        self.configure(bg=self.C["card_hover"])
        for child in self.winfo_children():
            try: child.configure(bg=self.C["card_hover"])
            except: pass

    def _on_leave(self, e):
        self.configure(bg=self.C["card"])
        for child in self.winfo_children():
            try: child.configure(bg=self.C["card"])
            except: pass


class DownloaderPage:
    def __init__(self, parent, colors):
        self.C = colors
        self.frame = tk.Frame(parent, bg=colors["bg"])
        self.session = None
        self._downloading = False
        self._cancel = False
        self.download_queue = queue.Queue()
        self.added_anime = set()
        self.stats = {"success": 0, "failed": 0, "downloaded_eps": 0, "failed_eps": 0}
        self._task_widgets = {}  # vod_id -> widget refs
        self._empty_visible = True
        self._build_ui()
        self._init_session()
        self._animate_empty()

    def show(self): pass
    def hide(self): pass

    # ── 通用组件 ──
    def _btn(self, parent, text, cmd, style="primary", w=120, h=42):
        from main import GlowButton
        btn = GlowButton(parent, text=text, command=cmd, style=style, width=w, height=h)
        return btn

    def _build_ui(self):
        # 滚动Canvas
        self.canvas = tk.Canvas(self.frame, bg=self.C["bg"], highlightthickness=0)
        self.sb = ttk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
        self.sf = tk.Frame(self.canvas, bg=self.C["bg"])
        self.sf.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.sf, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0, pady=0)
        self.sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind_all("<MouseWheel>",
            lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        PAD = 20
        # ── 输入卡片 ──
        card = AnimatedCard(self.sf, self.C)
        card.pack(fill=tk.X, padx=PAD, pady=(PAD, 12))
        self._input_card = card

        hdr = tk.Frame(card, bg=self.C["card"])
        hdr.pack(fill=tk.X, padx=20, pady=(16, 10))
        tk.Label(hdr, text="🔗 输入动漫链接", font=("微软雅黑", 13, "bold"),
                 bg=self.C["card"], fg=self.C["text"]).pack(side=tk.LEFT)
        tk.Label(hdr, text="每行一个 · 支持批量", font=("微软雅黑", 9),
                 bg=self.C["card"], fg=self.C["text3"]).pack(side=tk.RIGHT)

        row = tk.Frame(card, bg=self.C["card"])
        row.pack(fill=tk.X, padx=20, pady=(0, 14))

        # 输入框（带聚焦光效）
        self.link_text = tk.Text(row, height=4, font=("Consolas", 11),
                                 bg="#F6F8FA", fg=self.C["text"],
                                 relief="flat", bd=0, insertbackground=self.C["primary"],
                                 highlightthickness=2, highlightcolor=self.C["primary"],
                                 highlightbackground=self.C["border"])
        self.link_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.link_text.insert("1.0", "https://anime.xifanacg.com/bangumi/3235.html")

        bf = tk.Frame(row, bg=self.C["card"])
        bf.pack(side=tk.RIGHT, padx=(12, 0))
        self._btn(bf, "🚀 开始解析", self.parse_all, "primary", 130, 42).pack(pady=(0, 6))
        self._btn(bf, "🗑 删除选中", self.delete_selected, "danger", 130, 36).pack(pady=(0, 6))
        self._btn(bf, "📋 粘贴", self.paste_links, "secondary", 130, 36).pack(pady=(0, 6))
        self._btn(bf, "✖ 清空", self.clear_links, "secondary", 130, 36).pack()

        # ── 空状态占位（无任务时显示） ──
        self._empty_frame = tk.Frame(self.sf, bg=self.C["bg"], height=200)
        self._empty_frame.pack(fill=tk.X, padx=PAD, pady=30)
        self._empty_frame.pack_propagate(False)

        ef_inner = tk.Frame(self._empty_frame, bg=self.C["bg"])
        ef_inner.pack(expand=True)

        self._empty_icon = tk.Label(ef_inner, text="📡", font=("微软雅黑", 48),
                                    bg=self.C["bg"], fg=self.C["primary"])
        self._empty_icon.pack()
        tk.Label(ef_inner, text="拖入链接开始下载",
                 font=("微软雅黑", 14), bg=self.C["bg"], fg=self.C["text2"]).pack(pady=(8, 4))
        tk.Label(ef_inner, text="支持稀饭动漫批量链接 · 自动解析 · 智能补齐",
                 font=("微软雅黑", 10), bg=self.C["bg"], fg=self.C["text3"]).pack()

        # ── 任务列表（初始隐藏） ──
        self._list_card = AnimatedCard(self.sf, self.C)
        # 不pack，等有任务时显示

        lc_hdr = tk.Frame(self._list_card, bg=self.C["card"])
        lc_hdr.pack(fill=tk.X, padx=20, pady=(16, 8))
        tk.Label(lc_hdr, text="📋 下载任务", font=("微软雅黑", 13, "bold"),
                 bg=self.C["card"], fg=self.C["text"]).pack(side=tk.LEFT)
        self.lbl_task_count = tk.Label(lc_hdr, text="0 个任务",
                                       font=("微软雅黑", 9), bg=self.C["card"], fg=self.C["text3"])
        self.lbl_task_count.pack(side=tk.RIGHT)

        # Treeview
        style = ttk.Style()
        style.configure("DL.Treeview", rowheight=38, font=("微软雅黑", 10),
                        background="#FFF", fieldbackground="#FFF", borderwidth=0)
        style.configure("DL.Treeview.Heading", font=("微软雅黑", 10, "bold"),
                        background="#F6F8FA", relief="flat")
        style.map("DL.Treeview", background=[("selected", self.C["primary_light"])])

        cols = ("名称", "集数", "状态", "进度", "速度")
        self.tree = ttk.Treeview(self._list_card, columns=cols, show="headings",
                                 height=8, style="DL.Treeview")
        for c, w in zip(cols, [350, 70, 100, 180, 100]):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center" if c != "名称" else "w")

        tree_frame = tk.Frame(self._list_card, bg=self.C["card"])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 14))
        self.tree.pack(in_=tree_frame, side=tk.LEFT, fill=tk.BOTH, expand=True)
        tsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 输出设置卡片 ──
        card = AnimatedCard(self.sf, self.C)
        card.pack(fill=tk.X, padx=PAD, pady=(0, 12))

        tk.Label(card, text="💾 输出设置", font=("微软雅黑", 13, "bold"),
                 bg=self.C["card"], fg=self.C["text"]).pack(anchor="w", padx=20, pady=(16, 8))

        r1 = tk.Frame(card, bg=self.C["card"])
        r1.pack(fill=tk.X, padx=20, pady=(0, 8))
        tk.Label(r1, text="保存目录", font=("微软雅黑", 10),
                 bg=self.C["card"], fg=self.C["text2"]).pack(side=tk.LEFT)
        self.out_dir = tk.StringVar(value=r"G:\测试下载")
        dir_entry = tk.Entry(r1, textvariable=self.out_dir, font=("微软雅黑", 10),
                             relief="flat", bg="#F6F8FA", highlightthickness=1,
                             highlightcolor=self.C["primary"], highlightbackground=self.C["border"])
        dir_entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        self._btn(r1, "浏览", self.choose_dir, "secondary", 80, 32).pack(side=tk.LEFT)

        r2 = tk.Frame(card, bg=self.C["card"])
        r2.pack(fill=tk.X, padx=20, pady=(0, 16))
        tk.Label(r2, text="同时下载", font=("微软雅黑", 10),
                 bg=self.C["card"], fg=self.C["text2"]).pack(side=tk.LEFT)
        self.thread_count = tk.IntVar(value=3)
        tk.Spinbox(r2, from_=1, to=10, textvariable=self.thread_count, width=4,
                   font=("微软雅黑", 10), relief="flat", bg="#F6F8FA").pack(side=tk.LEFT, padx=10)
        tk.Label(r2, text="个任务", font=("微软雅黑", 10),
                 bg=self.C["card"], fg=self.C["text2"]).pack(side=tk.LEFT)

        # ── 控制卡片 ──
        card = AnimatedCard(self.sf, self.C)
        card.pack(fill=tk.X, padx=PAD, pady=(0, 12))

        tk.Label(card, text="🎮 下载控制", font=("微软雅黑", 13, "bold"),
                 bg=self.C["card"], fg=self.C["text"]).pack(anchor="w", padx=20, pady=(16, 8))

        bf = tk.Frame(card, bg=self.C["card"])
        bf.pack(fill=tk.X, padx=20, pady=(0, 10))
        self._btn(bf, "▶ 全部开始", self.start_download, "success", 140, 44).pack(side=tk.LEFT, padx=(0, 10))
        self._btn(bf, "⏹ 全部停止", self.stop_download, "danger", 140, 44).pack(side=tk.LEFT)

        # 速度 + 统计
        sf = tk.Frame(card, bg=self.C["card"])
        sf.pack(fill=tk.X, padx=20, pady=(0, 6))
        self.lbl_speed = tk.Label(sf, text="⬇ 0 MB/s", font=("Consolas", 14, "bold"),
                                  bg=self.C["card"], fg=self.C["primary"])
        self.lbl_speed.pack(side=tk.LEFT)

        self.lbl_stats = tk.Label(sf, text="动漫: 0  已下载: 0  失败: 0",
                                  font=("微软雅黑", 10), bg=self.C["card"], fg=self.C["text2"])
        self.lbl_stats.pack(side=tk.RIGHT)

        # 全局进度条
        from main import GlowProgress
        self.global_progress = GlowProgress(card, width=600, height=20)
        self.global_progress.pack(fill=tk.X, padx=20, pady=(4, 4))

        # 状态栏
        self.lbl_status = tk.Label(card, text="就绪 · 粘贴链接后点击开始解析",
                                   font=("微软雅黑", 10), bg=self.C["primary_light"],
                                   fg=self.C["primary"], padx=14, pady=8)
        self.lbl_status.pack(fill=tk.X, padx=20, pady=(4, 16))

    # ── 空状态动画 ──
    def _animate_empty(self):
        """空状态图标浮动动画"""
        if not self._empty_visible: return
        t = time.time()
        y_offset = int(6 * math.sin(t * 1.5))
        self._empty_icon.configure(pady=y_offset + 10)
        self.frame.after(80, self._animate_empty)

    def _show_list(self):
        if self._empty_visible:
            self._empty_visible = False
            self._empty_frame.pack_forget()
            self._list_card.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 12))

    # ── 逻辑（与v1相同，略加增强） ──
    def _init_session(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        try: self.session.get(SITE, verify=False, timeout=10)
        except: pass

    def choose_dir(self):
        p = filedialog.askdirectory()
        if p: self.out_dir.set(p)

    def clear_links(self):
        self.link_text.delete("1.0", tk.END)

    def delete_selected(self):
        try:
            self.link_text.delete(self.link_text.index("sel.first"), self.link_text.index("sel.last"))
        except tk.TclError:
            try:
                ln = self.link_text.index("insert").split(".")[0]
                self.link_text.delete(f"{ln}.0", f"{ln}.end+1c")
            except: pass

    def paste_links(self):
        try:
            t = self.frame.clipboard_get()
            self.link_text.insert(tk.END, t + "\n")
        except: pass

    def parse_all(self):
        links = [l.strip() for l in self.link_text.get("1.0", tk.END).strip().split('\n') if l.strip()]
        if not links:
            messagebox.showwarning("提示", "请输入至少一个链接"); return
        threading.Thread(target=self._parse_links, args=(links,), daemon=True).start()

    def _parse_links(self, links):
        total = len(links)
        success = skipped = 0
        for i, link in enumerate(links):
            self._update_status(f"🔍 正在解析 [{i+1}/{total}]...")
            try:
                m = re.search(r'/watch/(\d+)/', link) or re.search(r'/bangumi/(\d+)', link)
                if not m: continue
                vod_id = m.group(1)
                if vod_id in self.added_anime:
                    skipped += 1; continue

                resp = self.session.get(f"{SITE}/bangumi/{vod_id}.html", verify=False, timeout=30)
                resp.encoding = "utf-8"
                tm = re.search(r'<title>(.*?)</title>', resp.text)
                if not tm: continue
                full_title = tm.group(1).strip()
                anime_name = re.split(r'_\w+', full_title)[0].strip()
                anime_name = re.split(r'\s*[-|]\s*稀饭动漫', anime_name)[0].strip()

                all_eps = re.findall(r'/watch/(\d+)/(\d+)/(\d+)\.html', resp.text)
                if not all_eps: continue
                first_line = [(v, s, n) for v, s, n in all_eps if s == "1"]
                if not first_line:
                    ms = min(int(s) for _, s, _ in all_eps)
                    first_line = [(v, s, n) for v, s, n in all_eps if int(s) == ms]
                eps = sorted(set(first_line), key=lambda x: int(x[2]))

                info = {"id": vod_id, "name": anime_name, "eps": eps, "total": len(eps)}
                self.download_queue.put(info)
                self.added_anime.add(vod_id)

                self.frame.after(0, lambda n=anime_name, t=len(eps): self._add_task_row(n, t))
                success += 1
            except: pass
            time.sleep(0.5)

        self._update_status(f"✅ 解析完成！成功 {success}/{total}，跳过 {skipped} 重复")
        self.frame.after(0, self._update_stats)

    def _add_task_row(self, name, total):
        """添加任务行（带动画）"""
        self._show_list()
        iid = self.tree.insert("", tk.END, values=(name, total, "⏳ 待下载", "—", "—"))
        self.lbl_task_count.config(text=f"{self.tree.get_children().__len__()} 个任务")

    def start_download(self):
        if self._downloading: return
        if self.download_queue.empty():
            messagebox.showinfo("提示", "队列为空，请先解析链接"); return
        self._downloading = True
        self._cancel = False
        self.stats = {"success": 0, "failed": 0, "downloaded_eps": 0, "failed_eps": 0}
        threading.Thread(target=self._download_worker, daemon=True).start()

    def stop_download(self):
        self._cancel = True
        self._downloading = False

    def _download_worker(self):
        out_dir = self.out_dir.get()
        while not self.download_queue.empty() and not self._cancel:
            try: anime = self.download_queue.get(timeout=1)
            except: break

            item = None
            for it in self.tree.get_children():
                if self.tree.item(it, "values")[0] == anime["name"]:
                    item = it; break
            if not item: continue

            name, eps = anime["name"], anime["eps"]
            safe = re.sub(r'[<>:"/\\|?*]', '', name)[:80]
            anime_dir = os.path.join(out_dir, safe)

            existing = set()
            if os.path.exists(anime_dir):
                for f in os.listdir(anime_dir):
                    if f.endswith('.mp4'):
                        em = re.search(r'第(\d+)集', f)
                        if em: existing.add(em.group(1))

            to_dl = [(v, s, n) for v, s, n in eps if n.zfill(2) not in existing]
            if not to_dl:
                self.frame.after(0, lambda i=item: self.tree.set(i, "状态", "✅ 已存在"))
                self.stats["success"] += 1
                continue

            self.frame.after(0, lambda i=item, m=len(to_dl): self.tree.set(i, "状态", f"⬇ 补{m}集"))
            os.makedirs(anime_dir, exist_ok=True)
            ok, fail = len(existing), 0

            for idx, (v, s, n) in enumerate(to_dl):
                if self._cancel: break
                ep = n.zfill(2)
                ep_file = os.path.join(anime_dir, f"第{ep}集.mp4")
                prog = f"{ok+idx+1}/{len(eps)}"
                self.frame.after(0, lambda i=item, p=prog: self.tree.set(i, "进度", p))

                try:
                    t0 = time.time()
                    resp = self.session.get(f"{SITE}/watch/{v}/{s}/{n}.html", verify=False, timeout=30)
                    pm = re.search(r'player_aaaa=(\{.*?\})</script>', resp.text)
                    if not pm: fail += 1; continue
                    pd = json.loads(pm.group(1).replace('\\/', '/'))
                    url = pd.get('url', '')
                    if not url: fail += 1; continue

                    r1 = self.session.get(url, allow_redirects=False, verify=False, timeout=15)
                    real = r1.headers.get('Location', url) if r1.status_code == 302 else url
                    r2 = self.session.get(real, stream=True, verify=False, timeout=1800)

                    if r2.status_code == 200:
                        downloaded = 0
                        with open(ep_file, 'wb') as f:
                            for chunk in r2.iter_content(8192):
                                if self._cancel: break
                                f.write(chunk)
                                downloaded += len(chunk)
                                # 更新速度
                                elapsed = time.time() - t0
                                if elapsed > 0:
                                    speed = downloaded / elapsed / 1024 / 1024
                                    self.frame.after(0, lambda sp=f"{speed:.1f} MB/s",
                                        i=item: self.tree.set(i, "速度", sp))

                        if os.path.getsize(ep_file) > 1024*1024:
                            ok += 1; self.stats["downloaded_eps"] += 1
                        else:
                            os.remove(ep_file); fail += 1; self.stats["failed_eps"] += 1
                    else:
                        fail += 1; self.stats["failed_eps"] += 1
                except:
                    fail += 1; self.stats["failed_eps"] += 1
                time.sleep(0.3)

            status = "✅ 完成" if fail == 0 else (f"⚠️ {ok}/{len(eps)}" if ok > 0 else "❌ 失败")
            self.stats["success" if ok > 0 else "failed"] += 1
            self.frame.after(0, lambda i=item, s=status, a=ok, t=len(eps): (
                self.tree.set(i, "状态", s), self.tree.set(i, "进度", f"{a}/{t}"),
                self.tree.set(i, "速度", "—")))
            self.frame.after(0, self._update_stats)

        self._downloading = False
        self._update_status("✅ 下载完成！可继续添加新链接")

    def _update_stats(self):
        s = self.stats
        self.lbl_stats.config(text=f"动漫: {s['success']+s['failed']}  已下载: {s['success']}  失败: {s['failed']}")

    def _update_status(self, text):
        self.frame.after(0, lambda: self.lbl_status.config(text=text))
