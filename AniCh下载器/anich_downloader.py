#!/usr/bin/env python3
"""AniCh 全自动全集下载器 - B站风格UI"""
import os, re, json, base64, time, threading, subprocess, queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import requests
import urllib3
urllib3.disable_warnings()

# ═══════════════════════════════════════
#  颜色常量 - B站蓝白风格
# ═══════════════════════════════════════
C = {
    "bg": "#F5F7FA", "card": "#FFFFFF", "primary": "#00AEEC",
    "primary_dark": "#0091D4", "primary_light": "#E8F4FD",
    "text": "#333333", "text2": "#999999", "border": "#E5E5E5",
    "success": "#67C23A", "warning": "#E6A23C", "danger": "#F56C6C",
}

ANICH_API = "https://anich.sends.eu.org"
ANICH_SITE = "https://anich.emmmm.eu.org"

class AnichDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("AniCh 下载器")
        self.root.geometry("1000x700")
        self.root.configure(bg=C["bg"])

        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        self.download_queue = queue.Queue()
        self.added_ids = set()
        self._downloading = False
        self._cancel = False
        self._current_speed = 0
        self._total_downloaded = 0

        self.build_ui()

    # ═══════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════
    def build_ui(self):
        # 顶部标题
        header = tk.Frame(self.root, bg=C["primary"], height=50)
        header.pack(fill=tk.X)
        tk.Label(header, text="🎬 AniCh 下载器", font=("微软雅黑", 16, "bold"),
                 bg=C["primary"], fg="#FFFFFF").pack(side=tk.LEFT, padx=20, pady=10)

        # 输入区
        card1 = tk.Frame(self.root, bg=C["card"], padx=20, pady=15)
        card1.pack(fill=tk.X, padx=15, pady=(15,5))
        tk.Label(card1, text="🔗 输入番剧链接（每行一个）", font=("微软雅黑", 12, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        tk.Label(card1, text="支持: https://anich.emmmm.eu.org/b/38184/1",
                 font=("微软雅黑", 9), bg=C["card"], fg=C["text2"]).pack(anchor="w", pady=(0,8))

        row = tk.Frame(card1, bg=C["card"])
        row.pack(fill=tk.X)
        self.link_text = tk.Text(row, height=4, font=("Consolas", 10),
                                 bg="#F8F9FA", relief="flat", bd=1,
                                 highlightthickness=1, highlightcolor=C["primary"])
        self.link_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.link_text.insert("1.0", "https://anich.emmmm.eu.org/b/38184/1")

        btn_frame = tk.Frame(row, bg=C["card"])
        btn_frame.pack(side=tk.RIGHT, padx=(10,0))
        self.make_btn(btn_frame, "解析链接", self.parse_all, "primary").pack(pady=(0,5))
        self.make_btn(btn_frame, "清空结果", self.clear_results, "danger").pack(pady=(0,5))
        self.make_btn(btn_frame, "清空输入", lambda: self.link_text.delete("1.0", tk.END), "secondary").pack()

        # 结果表格
        card2 = tk.Frame(self.root, bg=C["card"], padx=20, pady=15)
        card2.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        tk.Label(card2, text="📋 解析结果", font=("微软雅黑", 12, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w", pady=(0,8))

        cols = ("名称", "有资源集", "状态", "进度", "ID")
        self.tree = ttk.Treeview(card2, columns=cols, show="headings", height=8)
        for c, w in [("名称",350),("有资源集",80),("状态",100),("进度",150),("ID",0)]:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center" if c!="名称" else "w")
        self.tree.column("ID", width=0, stretch=False)
        scroll = ttk.Scrollbar(card2, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 控制区
        card3 = tk.Frame(self.root, bg=C["card"], padx=20, pady=15)
        card3.pack(fill=tk.X, padx=15, pady=5)

        ctrl = tk.Frame(card3, bg=C["card"])
        ctrl.pack(fill=tk.X)
        self.make_btn(ctrl, "▶ 全部开始", self.start_download, "success").pack(side=tk.LEFT, padx=(0,10))
        self.make_btn(ctrl, "⏹ 停止", self.stop_download, "danger").pack(side=tk.LEFT, padx=(0,10))

        tk.Label(ctrl, text="  保存目录:", font=("微软雅黑", 10), bg=C["card"]).pack(side=tk.LEFT)
        self.out_dir = tk.StringVar(value=r"G:\测试下载\AniCh")
        tk.Entry(ctrl, textvariable=self.out_dir, width=40, font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=5)
        self.make_btn(ctrl, "浏览", self.choose_dir, "secondary").pack(side=tk.LEFT)

        # 状态栏
        status = tk.Frame(self.root, bg=C["primary_light"], height=35)
        status.pack(fill=tk.X, padx=15, pady=(5,10))
        self.lbl_status = tk.Label(status, text="就绪", font=("微软雅黑", 10),
                                   bg=C["primary_light"], fg=C["primary"])
        self.lbl_status.pack(side=tk.LEFT, padx=15)
        self.lbl_speed = tk.Label(status, text="", font=("微软雅黑", 10),
                                  bg=C["primary_light"], fg=C["text2"])
        self.lbl_speed.pack(side=tk.RIGHT, padx=15)

    def make_btn(self, parent, text, cmd, style="primary"):
        colors = {
            "primary": (C["primary"], C["primary_dark"], "#FFF"),
            "secondary": ("#F0F0F0", "#E0E0E0", C["text"]),
            "danger": (C["danger"], "#E04040", "#FFF"),
            "success": (C["success"], "#5AAA2A", "#FFF"),
        }
        bg, hbg, fg = colors.get(style, colors["primary"])
        btn = tk.Label(parent, text=text, font=("微软雅黑", 10, "bold"),
                       bg=bg, fg=fg, padx=12, pady=6, cursor="hand2")
        btn.pack(side=tk.LEFT, padx=2)
        btn.bind("<Enter>", lambda e: btn.configure(bg=hbg))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        btn.bind("<Button-1>", lambda e: cmd())
        return btn

    def choose_dir(self):
        p = filedialog.askdirectory()
        if p: self.out_dir.set(p)

    def status(self, text):
        self.root.after(0, lambda: self.lbl_status.config(text=text))

    # ═══════════════════════════════════════
    #  AniCh API 解析
    # ═══════════════════════════════════════
    def parse_anich_page(self, url):
        """解析AniCh页面获取bangumi信息"""
        m = re.search(r'/b/(\d+)', url)
        if not m: return None
        bid = m.group(1)
        resp = self.session.get(url, verify=False, timeout=30)
        resp.encoding = "utf-8"
        dm = re.search(r'window\.\$data\s*=\s*(\{.*?\})\s*</script>', resp.text, re.DOTALL)
        if not dm: return None
        try:
            data = json.loads(dm.group(1))
            key = f"bangumi-{bid}"
            if key not in data: return None
            bd = data[key]
            title = bd.get('data',{}).get('title', f'AniCh_{bid}')
            episodes = bd.get('episodes', [])
            eps = [{'sort':ep['sort'], 'title':ep.get('title',''), 'status':ep.get('status',False)} for ep in episodes]
            avail = [e for e in eps if e['status']]
            return {'id':bid, 'name':title, 'eps':eps, 'avail':avail, 'total':len(episodes)}
        except: return None

    def get_video_url(self, bangumi_id, episode):
        """获取视频URL（优先MP4，其次m3u8）"""
        try:
            resp = self.session.get(f"{ANICH_API}/vod/{bangumi_id}/{episode}", verify=False, timeout=30)
            if resp.status_code != 200: return None
            data = json.loads(resp.text)
            raw = bytes(data)
            mp4s, m3u8s = [], []
            for b64 in re.findall(rb'[A-Za-z0-9+/]{20,}={0,2}', raw):
                s = b64.decode('ascii')
                for skip in range(5):
                    c = s[skip:]
                    p = c + '=' * (4 - len(c) % 4) if len(c) % 4 else c
                    try:
                        d = base64.b64decode(p).decode('utf-8', errors='ignore')
                        f = re.sub(r'[^\x00-\x7f]*\d*ps://', 'https://', d)
                        for u in re.finditer(r'https?://[a-zA-Z0-9._:/-]+(?:\.mp4|\.m3u8)[^\s"\'<>]*', f):
                            url = u.group(0)
                            if '.mp4' in url and '.m3u8' not in url: mp4s.append(url)
                            elif '.m3u8' in url: m3u8s.append(url)
                    except: pass
            if mp4s: return ('mp4', mp4s[0])
            if m3u8s: return ('m3u8', m3u8s[0])
            return None
        except: return None

    # ═══════════════════════════════════════
    #  解析 & 下载
    # ═══════════════════════════════════════
    def parse_all(self):
        links = self.link_text.get("1.0", tk.END).strip().split('\n')
        links = [l.strip() for l in links if l.strip()]
        if not links: messagebox.showwarning("提示", "请输入链接"); return
        threading.Thread(target=self._parse_links, args=(links,), daemon=True).start()

    def _parse_links(self, links):
        ok = 0
        for i, link in enumerate(links):
            self.status(f"解析 [{i+1}/{len(links)}]...")
            try:
                info = self.parse_anich_page(link)
                if not info: continue
                if info['id'] in self.added_ids: continue
                self.added_ids.add(info['id'])
                self.download_queue.put(info)
                avail_n = len(info['avail'])
                total_n = info['total']
                self.root.after(0, lambda n=info['name'], a=avail_n, t=total_n, bid=info['id']:
                    self.tree.insert("", tk.END, values=(n, f"{a}/{t}", "待下载", "—", bid)))
                ok += 1
            except: pass
            time.sleep(0.3)
        self.status(f"✅ 解析完成！{ok} 部动漫")

    def start_download(self):
        if self._downloading: return
        if self.download_queue.empty(): messagebox.showinfo("提示", "队列为空，请先解析"); return
        self._downloading = True
        self._cancel = False
        threading.Thread(target=self._download_worker, daemon=True).start()
        threading.Thread(target=self._speed_monitor, daemon=True).start()

    def stop_download(self):
        self._cancel = True
        self._downloading = False

    def _download_worker(self):
        out = self.out_dir.get()
        while not self.download_queue.empty() and not self._cancel:
            try: anime = self.download_queue.get(timeout=1)
            except: break

            # 找到tree item
            item = None
            for it in self.tree.get_children():
                if self.tree.item(it,"values")[4] == anime["id"]:
                    item = it; break
            if not item: continue

            safe = re.sub(r'[<>:"/\\|?*]', '', anime["name"])[:80]
            d = os.path.join(out, safe)
            os.makedirs(d, exist_ok=True)

            # 检查已有集数
            existing = set()
            if os.path.exists(d):
                for f in os.listdir(d):
                    em = re.search(r'第(\d+)集', f)
                    if em: existing.add(em.group(1).zfill(2))

            avail = [ep for ep in anime["avail"] if str(ep['sort']).zfill(2) not in existing]
            if not avail:
                self.root.after(0, lambda i=item: self.tree.set(i, "状态", "✅ 已存在"))
                continue

            self.root.after(0, lambda i=item, n=len(avail): self.tree.set(i, "状态", f"⬇ {n}集"))
            ok = len(existing); fail = 0

            for idx, ep in enumerate(avail):
                if self._cancel: break
                ep_num = str(ep['sort']).zfill(2)
                ep_file = os.path.join(d, f"第{ep_num}集.mp4")
                self.root.after(0, lambda i=item, p=f"{ok+idx+1}/{anime['total']}": self.tree.set(i, "进度", p))
                self.status(f"下载: {anime['name']} 第{ep_num}集")

                for attempt in range(3):
                    if self._cancel: break
                    try:
                        result = self.get_video_url(anime["id"], ep['sort'])
                        if not result: raise Exception("无视频源")
                        vtype, vurl = result

                        if vtype == 'mp4':
                            # MP4直链下载
                            r = self.session.get(vurl, stream=True, verify=False, timeout=1800)
                            if r.status_code != 200: raise Exception(f"HTTP {r.status_code}")
                            with open(ep_file, 'wb') as f:
                                for ch in r.iter_content(1048576):
                                    if self._cancel: break
                                    f.write(ch)
                                    self._total_downloaded += len(ch)
                        else:
                            # m3u8: 优先N_m3u8DL-RE，其次ffmpeg
                            nm3u8 = self._find_nm3u8dl()
                            if nm3u8:
                                cmd = [nm3u8, vurl, "--save-name", f"第{ep_num}集",
                                       "--save-dir", d, "--thread-count", "16",
                                       "--auto-select", "--check-segments-count", "false"]
                                subprocess.run(cmd, capture_output=True, timeout=1800)
                            else:
                                cmd = ["ffmpeg", "-y",
                                       "-headers", f"User-Agent: Mozilla/5.0\r\nReferer: {ANICH_SITE}\r\n",
                                       "-i", vurl, "-c", "copy", "-movflags", "+faststart", ep_file]
                                subprocess.run(cmd, capture_output=True, timeout=1800)

                        if os.path.exists(ep_file) and os.path.getsize(ep_file) > 1024*1024:
                            ok += 1; break
                        else:
                            if os.path.exists(ep_file): os.remove(ep_file)
                            if attempt == 2: fail += 1
                    except Exception as e:
                        if attempt == 2: fail += 1
                        time.sleep(2 * (attempt + 1))

            total_n = anime['total']
            status = "✅ 完成" if fail == 0 else f"⚠️ {ok}/{total_n}"
            self.root.after(0, lambda i=item, s=status, a=ok, t=total_n: (
                self.tree.set(i, "状态", s), self.tree.set(i, "进度", f"{a}/{t}")))

        self._downloading = False
        self.status("✅ 全部完成")

    def _find_nm3u8dl(self):
        """查找N_m3u8DL-RE"""
        paths = [
            r"D:\AniDownloader\N_m3u8DL-RE.exe",
            os.path.join(os.path.dirname(__file__), "N_m3u8DL-RE.exe"),
        ]
        for p in paths:
            if os.path.exists(p): return p
        # 搜索PATH
        import shutil
        return shutil.which("N_m3u8DL-RE") or shutil.which("N_m3u8DL-RE.exe")

    def _speed_monitor(self):
        last = 0
        while self._downloading:
            time.sleep(1)
            speed = self._total_downloaded - last
            last = self._total_downloaded
            if speed > 1024*1024:
                s = f"{speed/1024/1024:.1f} MB/s"
            elif speed > 1024:
                s = f"{speed/1024:.1f} KB/s"
            else:
                s = "0 B/s"
            self.root.after(0, lambda t=s: self.lbl_speed.config(text=t))

    def clear_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        while not self.download_queue.empty():
            try: self.download_queue.get_nowait()
            except: break
        self.added_ids.clear()
        self.status("🗑️ 已清空")


if __name__ == "__main__":
    root = tk.Tk()
    app = AnichDownloader(root)
    root.mainloop()
