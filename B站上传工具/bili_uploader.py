#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站视频自动上传工具 - 纯requests版（不依赖aiohttp）
"""
import os, sys, json, time, hashlib, math, threading, io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests

# ═══════ 颜色主题（B站蓝白风格） ═══════
C = {
    "bg": "#F6F8FA", "card": "#FFFFFF", "primary": "#00A1D6",
    "primary_dark": "#0088CC", "text": "#222", "text2": "#666",
    "text3": "#999", "border": "#E5E9F0", "success": "#67C23A",
    "danger": "#F56C6C", "warning": "#E6A23C",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class BiliUploader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("B站视频上传工具")
        self.root.geometry("750x700")
        self.root.minsize(650, 600)
        self.root.configure(bg=C["bg"])

        # 数据
        self.cookie = None  # {SESSDATA, bili_jct, DedeUserID}
        self.upload_groups = []
        self._uploading = False
        self._cancel = False

        # 配置路径
        self._config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bili_upload_config.json")

        self._build_ui()
        self._load_config()
        self._auto_login()

    def _build_ui(self):
        header = tk.Frame(self.root, bg=C["primary"], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="📺 B站视频上传工具", font=("微软雅黑", 14, "bold"),
                 bg=C["primary"], fg="white").pack(side=tk.LEFT, padx=16)
        self.lbl_status = tk.Label(header, text="未登录", font=("微软雅黑", 10),
                                   bg=C["primary"], fg="#B3E5FC")
        self.lbl_status.pack(side=tk.RIGHT, padx=16)

        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # ── 登录区 ──
        login_card = tk.Frame(main, bg=C["card"], padx=12, pady=8)
        login_card.pack(fill=tk.X, pady=(0, 8))
        tk.Label(login_card, text="🔑 登录", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        lr = tk.Frame(login_card, bg=C["card"])
        lr.pack(fill=tk.X, pady=4)
        tk.Button(lr, text="📱 扫码登录", font=("微软雅黑", 9),
                  bg=C["primary"], fg="white", relief="flat", padx=10, cursor="hand2",
                  command=self._qr_login).pack(side=tk.LEFT)
        tk.Button(lr, text="📋 手动粘贴Cookie", font=("微软雅黑", 9),
                  bg="#E5E7EB", fg=C["text"], relief="flat", padx=10, cursor="hand2",
                  command=self._login_cookie).pack(side=tk.LEFT, padx=8)
        tk.Button(lr, text="✅ 测试登录", font=("微软雅黑", 9),
                  bg="#E5E7EB", fg=C["text"], relief="flat", padx=10, cursor="hand2",
                  command=self._test_login).pack(side=tk.LEFT, padx=8)

        # ── 上传列表区 ──
        list_card = tk.Frame(main, bg=C["card"], padx=12, pady=8)
        list_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        tk.Label(list_card, text="📋 上传列表", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")

        columns = ("name", "files", "title", "tid")
        self.tree = ttk.Treeview(list_card, columns=columns, show="headings", height=8)
        self.tree.heading("name", text="名称")
        self.tree.heading("files", text="文件数")
        self.tree.heading("title", text="标题")
        self.tree.heading("tid", text="分区")
        self.tree.column("name", width=120)
        self.tree.column("files", width=60, anchor="center")
        self.tree.column("title", width=300)
        self.tree.column("tid", width=80, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True, pady=4)

        bl = tk.Frame(list_card, bg=C["card"])
        bl.pack(fill=tk.X, pady=4)
        for txt, cmd in [("添加文件夹(分P)", self._add_folder),
                         ("添加单个视频", self._add_single),
                         ("编辑选中", self._edit_item),
                         ("移除选中", self._remove_item),
                         ("清空列表", self._clear_list)]:
            tk.Button(bl, text=txt, font=("微软雅黑", 9), bg="#E5E7EB", fg=C["text"],
                      relief="flat", padx=8, cursor="hand2", command=cmd).pack(side=tk.LEFT, padx=(0, 6))

        # ── 底部操作区 ──
        bot = tk.Frame(main, bg=C["card"], padx=12, pady=8)
        bot.pack(fill=tk.X)
        self.btn_upload = tk.Button(bot, text="🚀 开始上传", font=("微软雅黑", 12, "bold"),
                                    bg=C["success"], fg="white", relief="flat",
                                    padx=20, pady=8, cursor="hand2", command=self._start_upload)
        self.btn_upload.pack(side=tk.LEFT)
        self.btn_stop = tk.Button(bot, text="⏹ 停止", font=("微软雅黑", 11),
                                  bg=C["danger"], fg="white", relief="flat",
                                  padx=14, pady=8, cursor="hand2", command=self._stop_upload,
                                  state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=10)
        self.progress = ttk.Progressbar(bot, mode="determinate", maximum=100)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.lbl_eta = tk.Label(bot, text="", font=("Consolas", 10, "bold"),
                                bg=C["card"], fg=C["primary"])
        self.lbl_eta.pack(side=tk.LEFT)

        # 日志区
        log_frame = tk.Frame(main, bg=C["card"], padx=12, pady=8)
        log_frame.pack(fill=tk.X)
        tk.Label(log_frame, text="📝 日志", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        self.log_text = tk.Text(log_frame, height=6, font=("Consolas", 9),
                                bg="#1E1E1E", fg="#D4D4D4", insertbackground="white",
                                relief="flat", wrap=tk.WORD)
        self.log_text.pack(fill=tk.X, pady=4)
        scroll = tk.Scrollbar(self.log_text, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        print(line, end="", flush=True)
        self.root.after(0, lambda: (
            self.log_text.insert(tk.END, line),
            self.log_text.see(tk.END)
        ))

    # ═══════ 登录 ═══════
    def _login_cookie(self):
        win = tk.Toplevel(self.root)
        win.title("获取Cookie")
        win.geometry("550x300")
        win.configure(bg=C["bg"])
        tk.Label(win, text="📋 粘贴Cookie（F12 → Application → Cookies）",
                 font=("微软雅黑", 11, "bold"), bg=C["bg"], fg=C["text"]).pack(anchor="w", padx=12, pady=(12, 4))
        fields = {}
        for name in ["SESSDATA", "bili_jct", "DedeUserID"]:
            fr = tk.Frame(win, bg=C["bg"])
            fr.pack(fill=tk.X, padx=12, pady=2)
            tk.Label(fr, text=f"{name}:", font=("Consolas", 9), bg=C["bg"],
                     fg=C["text"], width=12, anchor="e").pack(side=tk.LEFT)
            e = tk.Entry(fr, font=("Consolas", 9), width=40, bg="#F6F8FA", relief="flat")
            e.pack(side=tk.LEFT, padx=6)
            fields[name] = e

        def save():
            cookie = {k: e.get().strip() for k, e in fields.items()}
            if not all(cookie.values()):
                messagebox.showwarning("提示", "请填写所有Cookie字段"); return
            self._save_cookie(cookie)
            win.destroy()
            self._test_login()

        tk.Button(win, text="保存并测试", font=("微软雅黑", 10), bg=C["primary"], fg="white",
                  relief="flat", padx=16, cursor="hand2", command=save).pack(pady=12)

    def _qr_login(self):
        """扫码登录B站"""
        self._log("📱 正在获取二维码...")
        def _do():
            try:
                import urllib.request
                req = urllib.request.Request(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                    headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                if data.get("code") != 0:
                    self.root.after(0, lambda: self._log("❌ 获取二维码失败"))
                    return
                qr_url = data["data"]["url"]
                qrcode_key = data["data"]["qrcode_key"]
                try:
                    import qrcode
                    qr = qrcode.QRCode(box_size=6, border=2)
                    qr.add_data(qr_url)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                except ImportError:
                    qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={qr_url}"
                    with urllib.request.urlopen(qr_api, timeout=10) as r:
                        img_data = r.read()
                    from PIL import Image
                    img = Image.open(io.BytesIO(img_data))
                qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_temp_qr.png")
                img.save(qr_path)
                self.root.after(0, lambda: self._show_qr_window(qr_path, qrcode_key))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda e=err: self._log(f"❌ 获取二维码失败: {e}"))
        threading.Thread(target=_do, daemon=True).start()

    def _show_qr_window(self, qr_path, qrcode_key):
        win = tk.Toplevel(self.root)
        win.title("扫码登录")
        win.geometry("320x400")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text="使用哔哩哔哩APP扫码登录", font=("微软雅黑", 11, "bold"),
                 bg=C["bg"], fg=C["text"]).pack(pady=(16, 8))
        try:
            from PIL import Image, ImageTk
            img = Image.open(qr_path)
            img = img.resize((200, 200), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            lbl_img = tk.Label(win, image=photo, bg="white", relief="solid", bd=1)
            lbl_img.image = photo
            lbl_img.pack(pady=8)
        except Exception:
            tk.Label(win, text="[二维码加载失败]", font=("微软雅黑", 10),
                     bg=C["bg"], fg=C["danger"]).pack(pady=20)
        lbl_status = tk.Label(win, text="等待扫码...", font=("微软雅黑", 10),
                              bg=C["bg"], fg=C["text2"])
        lbl_status.pack(pady=8)
        self._qr_poling = True

        def poll():
            if not self._qr_poling:
                return
            try:
                import urllib.request
                poll_url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}"
                req = urllib.request.Request(poll_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read().decode())
                code = result.get("data", {}).get("code", -1)
                if code == 0:
                    url_str = result["data"].get("url", "")
                    cookie_dict = {}
                    for part in url_str.split("?")[-1].split("&"):
                        if "=" in part:
                            k, v = part.split("=", 1)
                            cookie_dict[k] = v
                    if cookie_dict.get("SESSDATA"):
                        self._save_cookie({
                            "SESSDATA": cookie_dict["SESSDATA"],
                            "bili_jct": cookie_dict.get("bili_jct", ""),
                            "DedeUserID": cookie_dict.get("DedeUserID", "")
                        })
                        self._qr_poling = False
                        self.root.after(0, lambda: (
                            win.destroy(), self._log("✅ Cookie已保存!"), self._test_login()))
                    else:
                        self._qr_poling = False
                        self.root.after(0, lambda: self._log("❌ 未提取到SESSDATA"))
                elif code == 86038:
                    self._qr_poling = False
                    self.root.after(0, lambda: (
                        lbl_status.config(text="❌ 二维码已过期", fg=C["danger"]),
                        self._log("❌ 二维码已过期")))
                elif code == 86090:
                    self.root.after(0, lambda: lbl_status.config(
                        text="已扫码，请在手机上确认", fg=C["warning"]))
                    win.after(2000, poll)
                else:
                    win.after(2000, poll)
            except Exception:
                if self._qr_poling:
                    win.after(3000, poll)
        win.after(2000, poll)
        def on_close():
            self._qr_poling = False
            try: os.remove(qr_path)
            except: pass
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

    def _save_cookie(self, cookie):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bili_cookie.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookie, f, ensure_ascii=False, indent=2)
        self.cookie = cookie
        self._log("✅ Cookie已保存")

    def _load_cookie(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bili_cookie.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _test_login(self):
        cookie = self._load_cookie()
        if not cookie:
            self.lbl_status.config(text="❌ 未登录", fg="#FFCDD2")
            self._log("❌ 未找到Cookie，请先登录")
            return
        self.cookie = cookie

        def _do():
            try:
                session = self._headers()
                r = session.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
                data = r.json()
                if data.get("code") == 0:
                    uname = data["data"].get("uname", "未知")
                    self.root.after(0, lambda: (
                        self.lbl_status.config(text=f"✅ 已登录: {uname}", fg="#C8E6C9"),
                        self._log(f"✅ 登录成功: {uname}")))
                else:
                    self.root.after(0, lambda: (
                        self.lbl_status.config(text="❌ Cookie已过期", fg="#FFCDD2"),
                        self._log(f"❌ Cookie无效 (code={data.get('code')})")))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda m=err: self._log(f"❌ 登录失败: {m}"))
        self._log("🔍 测试登录中...")
        threading.Thread(target=_do, daemon=True).start()

    def _cookie_str(self):
        return f"SESSDATA={self.cookie['SESSDATA']}; bili_jct={self.cookie['bili_jct']}; DedeUserID={self.cookie['DedeUserID']}"

    def _headers(self):
        """创建带Cookie的requests.Session"""
        if not hasattr(self, '_session') or not self._session:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
                "connection": "keep-alive",
            })
            if self.cookie:
                self._session.cookies.set("SESSDATA", self.cookie["SESSDATA"])
                self._session.cookies.set("bili_jct", self.cookie["bili_jct"])
                self._session.cookies.set("DedeUserID", self.cookie["DedeUserID"])
        return self._session

    def _auto_login(self):
        cookie = self._load_cookie()
        if cookie and cookie.get("SESSDATA"):
            self.cookie = cookie
            self._log("🔑 发现已保存Cookie，自动登录...")
            self._test_login()

    # ═══════ 添加视频 ═══════
    def _add_folder(self):
        d = filedialog.askdirectory()
        if not d:
            return
        exts = ('.mp4', '.mkv', '.avi', '.flv', '.ts')
        videos = sorted([f for f in os.listdir(d) if f.lower().endswith(exts)])
        if not videos:
            messagebox.showwarning("提示", "文件夹内没有视频文件")
            return
        folder_name = os.path.basename(d)
        meta = self._show_meta_dialog(folder_name, len(videos))
        if not meta:
            return
        group = {
            "name": folder_name, "path": d,
            "files": [os.path.join(d, v) for v in videos],
            "file_names": videos,
            "title": meta["title"], "desc": meta["desc"],
            "tags": meta["tags"], "tid": meta["tid"], "cover": meta.get("cover", ""),
            "type": "folder",
        }
        self.upload_groups.append(group)
        self._refresh_tree()
        self._save_config()
        self._log(f"📂 添加文件夹: {folder_name} ({len(videos)}个视频 → 分P)")

    def _add_single(self):
        files = filedialog.askopenfilenames(filetypes=[("视频", "*.mp4 *.mkv *.avi *.flv *.ts")])
        if not files:
            return
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            meta = self._show_meta_dialog(name, 1)
            if not meta:
                continue
            group = {
                "name": name, "path": os.path.dirname(f),
                "files": [f], "file_names": [os.path.basename(f)],
                "title": meta["title"], "desc": meta["desc"],
                "tags": meta["tags"], "tid": meta["tid"], "cover": meta.get("cover", ""),
                "type": "single",
            }
            self.upload_groups.append(group)
        self._refresh_tree()
        self._save_config()

    def _show_meta_dialog(self, default_title, file_count):
        win = tk.Toplevel(self.root)
        win.title("视频信息")
        win.geometry("500x430")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        DEFAULT_DESC = "本账号未开通任何激励，大会员每月可领5B币券，想支持up的话可以用这个券给up发电哦感谢大家ღ( ´･ᴗ･` )比心\nhttps://account.bilibili.com/account/big/myPackage"
        DEFAULT_TAGS = "动漫,番剧,新番,动画,4K,无删减,热血"
        DEFAULT_TID = "24"
        result = {}
        tk.Label(win, text=f"视频信息 ({file_count}个文件)", font=("微软雅黑", 11, "bold"),
                 bg=C["bg"], fg=C["text"]).pack(anchor="w", padx=12, pady=(12, 8))
        # 标题
        fr = tk.Frame(win, bg=C["bg"])
        fr.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(fr, text="标题:", font=("微软雅黑", 10), bg=C["bg"], width=8, anchor="e").pack(side=tk.LEFT)
        title_var = tk.StringVar(value=default_title)
        tk.Entry(fr, textvariable=title_var, font=("微软雅黑", 10), width=38,
                 bg="#F6F8FA", relief="flat").pack(side=tk.LEFT, padx=6)
        # 简介
        fr = tk.Frame(win, bg=C["bg"])
        fr.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(fr, text="简介:", font=("微软雅黑", 10), bg=C["bg"], width=8, anchor="ne").pack(side=tk.LEFT)
        desc_text = tk.Text(fr, font=("微软雅黑", 9), width=38, height=3, bg="#F6F8FA", relief="flat")
        desc_text.pack(side=tk.LEFT, padx=6)
        desc_text.insert("1.0", DEFAULT_DESC)
        # 标签
        fr = tk.Frame(win, bg=C["bg"])
        fr.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(fr, text="标签:", font=("微软雅黑", 10), bg=C["bg"], width=8, anchor="e").pack(side=tk.LEFT)
        tags_var = tk.StringVar(value=DEFAULT_TAGS)
        tk.Entry(fr, textvariable=tags_var, font=("微软雅黑", 10), width=38,
                 bg="#F6F8FA", relief="flat").pack(side=tk.LEFT, padx=6)
        # 分区
        fr = tk.Frame(win, bg=C["bg"])
        fr.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(fr, text="分区:", font=("微软雅黑", 10), bg=C["bg"], width=8, anchor="e").pack(side=tk.LEFT)
        tid_var = tk.StringVar(value=DEFAULT_TID)
        tid_options = [("24", "动画综合"), ("25", "动画鬼畜"), ("47", "短片·手书·配音"),
                       ("138", "搞笑"), ("210", "数码"), ("122", "野生技术协会"),
                       ("17", "单机游戏"), ("171", "电子竞技"), ("172", "手机游戏"),
                       ("5", "日常"), ("129", "其他")]
        ttk.Combobox(fr, textvariable=tid_var, values=[f"{t[0]} - {t[1]}" for t in tid_options],
                     state="readonly", width=30).pack(side=tk.LEFT, padx=6)
        # 封面
        fr = tk.Frame(win, bg=C["bg"])
        fr.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(fr, text="封面:", font=("微软雅黑", 10), bg=C["bg"], width=8, anchor="e").pack(side=tk.LEFT)
        cover_var = tk.StringVar(value="")
        cover_lbl = tk.Label(fr, text="未选择(自动生成)", font=("微软雅黑", 9),
                             bg=C["bg"], fg=C["text3"], width=22, anchor="w")
        cover_lbl.pack(side=tk.LEFT, padx=6)
        def pick_cover():
            p = filedialog.askopenfilename(filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp")])
            if p:
                cover_var.set(p)
                cover_lbl.config(text=os.path.basename(p))
        def search_cover():
            url = self._search_cover()
            if url:
                cover_var.set(url)
                cover_lbl.config(text="网络图片")
        tk.Button(fr, text="本地", font=("微软雅黑", 9), bg="#E5E7EB", fg=C["text"],
                  relief="flat", padx=6, cursor="hand2", command=pick_cover).pack(side=tk.LEFT)
        tk.Button(fr, text="搜索", font=("微软雅黑", 9), bg=C["primary"], fg="white",
                  relief="flat", padx=6, cursor="hand2", command=search_cover).pack(side=tk.LEFT, padx=4)

        def confirm():
            tid_str = tid_var.get().split(" - ")[0].strip()
            result["title"] = title_var.get().strip()
            result["desc"] = desc_text.get("1.0", tk.END).strip()
            result["tags"] = [t.strip() for t in tags_var.get().split(",") if t.strip()]
            result["tid"] = int(tid_str)
            result["cover"] = cover_var.get()
            win.destroy()
        def cancel():
            win.destroy()
        br = tk.Frame(win, bg=C["bg"])
        br.pack(pady=12)
        tk.Button(br, text="确定", font=("微软雅黑", 10), bg=C["primary"], fg="white",
                  relief="flat", padx=20, cursor="hand2", command=confirm).pack(side=tk.LEFT, padx=8)
        tk.Button(br, text="取消", font=("微软雅黑", 10), bg="#E5E7EB", fg=C["text"],
                  relief="flat", padx=20, cursor="hand2", command=cancel).pack(side=tk.LEFT)
        win.wait_window()
        return result if result else None

    def _search_cover(self):
        win = tk.Toplevel(self.root)
        win.title("搜索封面")
        win.geometry("650x520")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text="百度图片搜索封面", font=("微软雅黑", 11, "bold"),
                 bg=C["bg"], fg=C["text"]).pack(pady=(12, 8))
        sr = tk.Frame(win, bg=C["bg"])
        sr.pack(fill=tk.X, padx=12)
        e = tk.Entry(sr, font=("微软雅黑", 10), width=40, bg="#F6F8FA", relief="flat")
        e.pack(side=tk.LEFT, padx=(0, 8))
        e.insert(0, "输入动漫名称搜索...")
        results_frame = tk.Frame(win, bg=C["bg"])
        results_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        selected = {"path": ""}

        def do_search():
            for w in results_frame.winfo_children():
                w.destroy()
            keyword = e.get().strip()
            if not keyword:
                return
            tk.Label(results_frame, text="搜索中...", font=("微软雅黑", 9),
                     bg=C["bg"], fg=C["text3"]).pack()
            def _fetch():
                try:
                    r = requests.get(
                        f"https://image.baidu.com/search/acjson?tn=resultjson_com&word={keyword}+封面&pn=0&rn=20",
                        headers={"User-Agent": UA}, timeout=10)
                    data = r.json()
                    results = [x for x in data.get("data", []) if x.get("thumbURL") or x.get("middleURL")]
                    self.root.after(0, lambda: _show_results(results))
                except Exception as ex:
                    err = str(ex)
                    self.root.after(0, lambda m=err: tk.Label(results_frame, text=f"搜索失败: {m}",
                                                        font=("微软雅黑", 9), bg=C["bg"], fg=C["danger"]).pack())
            def _show_results(results):
                for w in results_frame.winfo_children():
                    w.destroy()
                if not results:
                    tk.Label(results_frame, text="未找到结果", font=("微软雅黑", 9),
                             bg=C["bg"], fg=C["text3"]).pack()
                    return
                canvas = tk.Canvas(results_frame, bg=C["bg"], highlightthickness=0)
                scrollbar = tk.Scrollbar(results_frame, orient="vertical", command=canvas.yview)
                inner = tk.Frame(canvas, bg=C["bg"])
                inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
                canvas.create_window((0, 0), window=inner, anchor="nw")
                canvas.configure(yscrollcommand=scrollbar.set)
                canvas.pack(side="left", fill="both", expand=True)
                scrollbar.pack(side="right", fill="y")
                def on_mousewheel(event):
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                canvas.bind_all("<MouseWheel>", on_mousewheel)
                photo_refs = []
                for item in results:
                    pic = item.get("thumbURL") or item.get("middleURL") or ""
                    title = item.get("fromPageTitleEnc", "") or item.get("title", "")
                    if not pic or not title:
                        continue
                    row = tk.Frame(inner, bg=C["card"], padx=6, pady=4)
                    row.pack(fill=tk.X, pady=2)
                    tk.Label(row, text=title[:30], font=("微软雅黑", 9),
                             bg=C["card"], fg=C["text"], width=30, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
                    img_lbl = tk.Label(row, bg=C["card"])
                    img_lbl.pack(side=tk.LEFT, padx=4)
                    def load_img(url=pic, lbl=img_lbl, ref_list=photo_refs):
                        try:
                            from PIL import Image, ImageTk
                            rr = requests.get(url, timeout=10)
                            img = Image.open(io.BytesIO(rr.content))
                            img.thumbnail((180, 120), Image.LANCZOS)
                            photo = ImageTk.PhotoImage(img)
                            ref_list.append(photo)
                            self.root.after(0, lambda l=lbl, p=photo: l.config(image=p))
                        except:
                            pass
                    threading.Thread(target=load_img, daemon=True).start()
                    def pick(url=pic, t=title):
                        selected["path"] = url
                        win.destroy()
                    tk.Button(row, text="选择", font=("微软雅黑", 9), bg=C["primary"], fg="white",
                              relief="flat", padx=8, cursor="hand2", command=pick).pack(side=tk.RIGHT)
            threading.Thread(target=_fetch, daemon=True).start()
        tk.Button(sr, text="搜索", font=("微软雅黑", 9), bg=C["primary"], fg="white",
                  relief="flat", padx=10, cursor="hand2", command=do_search).pack(side=tk.LEFT)
        e.bind("<Return>", lambda _: do_search())
        win.wait_window()
        return selected.get("path", "")

    def _edit_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选中一项")
            return
        idx = self.tree.index(sel[0])
        group = self.upload_groups[idx]
        meta = self._show_meta_dialog(group["title"], len(group["files"]))
        if meta:
            group["title"] = meta["title"]
            group["desc"] = meta["desc"]
            group["tags"] = meta["tags"]
            group["tid"] = meta["tid"]
            group["cover"] = meta.get("cover", "")
            self._refresh_tree()
            self._save_config()

    def _remove_item(self):
        sel = self.tree.selection()
        if not sel:
            return
        for s in reversed(self.tree.selection()):
            idx = self.tree.index(s)
            self.upload_groups.pop(idx)
        self._refresh_tree()
        self._save_config()

    def _clear_list(self):
        self.upload_groups.clear()
        self._refresh_tree()
        self._save_config()

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for g in self.upload_groups:
            self.tree.insert("", tk.END, values=(g["name"], len(g["files"]), g["title"], g["tid"]))

    # ═══════ 上传（纯requests，不用aiohttp） ═══════
    def _start_upload(self):
        if self._uploading:
            return
        if not self.cookie:
            messagebox.showwarning("提示", "请先登录B站")
            return
        if not self.upload_groups:
            messagebox.showwarning("提示", "请先添加视频")
            return
        self._uploading = True
        self._cancel = False
        self.btn_upload.config(state="disabled")
        self.btn_stop.config(state="normal")
        threading.Thread(target=self._upload_worker, daemon=True).start()

    def _stop_upload(self):
        self._cancel = True
        self._log("⏹ 用户停止上传")

    def _upload_worker(self):
        total = len(self.upload_groups)
        for i, group in enumerate(self.upload_groups):
            if self._cancel:
                break
            self._log(f"🚀 [{i+1}/{total}] 开始上传: {group['title']}")
            try:
                pages = []
                if group["type"] == "folder" and len(group["files"]) > 1:
                    self._log(f"  📂 分P模式: {len(group['files'])}个视频")
                    pages = group["files"]
                else:
                    pages = [group["files"][0]]
                self._api_upload(group, pages)
            except Exception as e:
                self._log(f"❌ 上传失败: {e}")
                import traceback
                self._log(traceback.format_exc()[-300:])
        self._uploading = False
        self.root.after(0, lambda: (
            self.btn_upload.config(state="normal"),
            self.btn_stop.config(state="disabled"),
            self.progress.config(value=100),
            self.lbl_eta.config(text="✅ 全部完成" if not self._cancel else "⏹ 已停止")))
        self._log("✅ 上传任务结束")

    def _api_upload(self, group, file_list):
        """纯requests上传B站视频"""
        session = self._headers()  # 返回requests.Session
        # 1. 上传封面
        cover_url = ""
        cover_path = group.get("cover", "")
        if cover_path and cover_path.startswith("http"):
            cover_url = cover_path
        elif cover_path and os.path.exists(cover_path):
            self._log("  🖼️ 上传封面...")
            try:
                import base64
                from PIL import Image
                with Image.open(cover_path) as im:
                    # 裁剪为16:10
                    xsize, ysize = im.size
                    if xsize / ysize > 1.6:
                        delta = xsize - ysize * 1.6
                        region = im.crop((delta // 2, 0, xsize - delta // 2, ysize))
                    else:
                        delta = ysize - xsize * 10 // 16
                        region = im.crop((0, delta // 2, xsize, ysize - delta // 2))
                    buf = io.BytesIO()
                    region.save(buf, format="JPEG", quality=90)
                cover_b64 = b"data:image/jpeg;base64," + base64.b64encode(buf.getvalue())
                r = session.post("https://member.bilibili.com/x/vu/web/cover/up",
                                  data={"cover": cover_b64, "csrf": self.cookie["bili_jct"]},
                                  timeout=30)
                d = r.json()
                if d.get("code") == 0:
                    cover_url = d["data"]["url"]
                    self._log("  ✅ 封面上传成功")
                else:
                    self._log(f"  ⚠️ 封面上传失败: {d.get('message', '')}")
            except Exception as e:
                self._log(f"  ⚠️ 封面上传异常: {e}")
        else:
            # 自动生成封面
            cover_url = self._auto_upload_cover(group["title"])

        # 3. 分P上传
        all_pages = []
        for pi, filepath in enumerate(file_list):
            if self._cancel:
                break
            fname = os.path.basename(filepath)
            fsize = os.path.getsize(filepath)
            fsize_mb = fsize / 1048576
            page_title = f"P{pi+1} {os.path.splitext(fname)[0]}" if len(file_list) > 1 else group["title"]
            self._log(f"  📄 [{pi+1}/{len(file_list)}] {fname} ({fsize_mb:.1f}MB)")
            # 每个文件单独获取上传线路
            self._log(f"  📡 获取P{pi+1}上传线路...")
            r = session.get("https://member.bilibili.com/preupload", params={
                "r": "upos",
                "profile": "ugcupos/bup",
                "ssl": 0,
                "version": "2.8.12",
                "build": 2081200,
                "name": fname,
                "size": fsize,
            }, timeout=5)
            predata = r.json()
            if "upos_uri" not in predata:
                self._log(f"  ❌ P{pi+1}获取线路失败: {predata}")
                continue
            upos_uri = predata["upos_uri"].replace("upos://", "")
            auth = predata.get("auth", "")
            biz_id = predata.get("biz_id", 0)
            endpoint = predata.get("endpoint", "")
            upload_base = f"https:{endpoint}/{upos_uri}" if endpoint else f"https://upos-sz-{upos_uri}"

            # 上传单个文件
            upload_id = self._upload_file(filepath, fsize, upload_base, auth, biz_id, pi, len(file_list))
            if upload_id:
                all_pages.append({
                    "title": page_title,
                    "description": f"第{pi+1}集" if len(file_list) > 1 else group["desc"],
                    "filename": upos_uri.split("/")[-1],
                    "part_len": fsize,
                    "upload_id": upload_id,
                })
                self._log(f"  ✅ P{pi+1} 上传完成")
            else:
                self._log(f"  ❌ P{pi+1} 上传失败")
                return

        # 4. 提交稿件
        self._log("  📝 提交稿件...")
        submit_data = {
            "copyright": 1,
            "source": "",
            "desc": group["desc"],
            "desc_format_id": 0,
            "dynamic": "",
            "interactive": 0,
            "no_reprint": 1,
            "open_elec": 0,
            "origin_state": 0,
            "subtitles": json.dumps({"lan": "", "open": 0}),
            "tag": ",".join(group["tags"]),
            "tid": group["tid"],
            "title": group["title"],
            "up_close_danmu": False,
            "up_close_reply": False,
            "up_selection_reply": False,
            "videos": json.dumps([{
                "title": p["title"],
                "desc": p["description"],
                "filename": p["filename"],
                "part_len": p["part_len"],
                "cid": biz_id,
                "edit_num": 0,
            } for p in all_pages]),
            "csrf": self.cookie["bili_jct"],
        }
        if cover_url:
            submit_data["cover"] = cover_url

        r = session.post("https://member.bilibili.com/x/vu/web/add",
                         data=submit_data, timeout=30)
        result = r.json()
        if result.get("code") == 0:
            bvid = result["data"].get("bvid", "?")
            aid = result["data"].get("aid", "?")
            self._log(f"  🎉 发布成功! bvid={bvid} aid={aid}")
        else:
            self._log(f"  ❌ 发布失败: {result.get('message', result)}")

    def _upload_file(self, filepath, filesize, upload_base, auth, biz_id, page_idx, total_pages):
        """上传单个文件到B站"""
        session = self._headers()
        api_base = upload_base

        # 初始化上传
        r = session.post(f"{api_base}?uploads&output=json",
                         headers={"X-Upos-Auth": auth},
                         timeout=15)
        upload_data = r.json()
        upload_id = upload_data.get("upload_id", "")
        if not upload_id:
            self._log(f"    ❌ 初始化上传失败: {upload_data}")
            return None

        # 分片上传
        chunk_size = 4 * 1024 * 1024  # 4MB
        total_chunks = math.ceil(filesize / chunk_size)

        with open(filepath, "rb") as f:
            for ci in range(total_chunks):
                if self._cancel:
                    return None
                chunk = f.read(chunk_size)
                chunk_no = ci + 1

                # 进度
                pct = ((ci + 1) / total_chunks) * 100
                # 整体进度 = 已完成的分P + 当前分P进度
                overall = (page_idx / total_pages + pct / total_pages) * 100
                speed_mb = len(chunk) / 1024 / 1024 / max(time.time() - chunk_start, 0.1) if 'chunk_start' in dir() else 0
                chunk_start = time.time()
                self.root.after(0, lambda p=overall, pi=page_idx, pc=pct, sp=speed_mb, tc=total_chunks, cn=chunk_no: (
                    self.progress.config(value=min(p, 100)),
                    self.lbl_eta.config(text=f"P{pi+1} {cn}/{tc} {pc:.0f}% | {sp:.1f}MB/s | 总{p:.1f}%")))

                # 上传分片
                for retry in range(3):
                    try:
                        r = session.put(
                            f"{api_base}?partNumber={chunk_no}&uploadId={upload_id}&chunk={ci}&chunks={total_chunks}&size={len(chunk)}&start={ci*chunk_size}&end={ci*chunk_size+len(chunk)}&total={filesize}",
                            headers={"X-Upos-Auth": auth},
                            data=chunk,
                            timeout=60)
                        resp_text = r.text.strip()
                        if r.status_code == 200:
                            break  # 200即成功（响应为MULTIPART_PUT_SUCCESS）
                        else:
                            self._log(f"    ⚠️ 分片{chunk_no} HTTP {r.status_code}: {resp_text[:200]}")
                    except Exception as e:
                        self._log(f"    ⚠️ 分片{chunk_no}异常: {e}")
                        time.sleep(2)

        # 完成分片
        filename = api_base.split("/")[-1].split("?")[0]  # 从URL提取文件名
        r = session.post(
            f"{api_base}?output=json&name={filename}&profile=ugcupos/bup&uploadId={upload_id}&biz_id={biz_id}",
            headers={"X-Upos-Auth": auth},
            json={"parts": [{"partNumber": i + 1, "eTag": "etag"} for i in range(total_chunks)]},
            timeout=15)

        return upload_id

    def _auto_upload_cover(self, title):
        """自动生成并上传默认封面"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new("RGB", (1920, 1080), "#00A1D6")
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("msyh.ttc", 60)
            except:
                font = ImageFont.load_default()
            text = title[:20]
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((1920 - tw) // 2, (1080 - th) // 2), text, fill="white", font=font)
            import base64
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            buf.seek(0)
            session = self._headers()
            cover_b64 = b"data:image/jpeg;base64," + base64.b64encode(buf.getvalue())
            r = session.post("https://member.bilibili.com/x/vu/web/cover/up",
                              data={"cover": cover_b64, "csrf": self.cookie["bili_jct"]}, timeout=30)
            d = r.json()
            if d.get("code") == 0:
                return d["data"]["url"]
        except:
            pass
        return ""

    # ═══════ 配置保存/加载 ═══════
    def _save_config(self):
        cfg = {"groups": [{
            "name": g["name"], "path": g["path"], "files": g["files"],
            "file_names": g["file_names"], "title": g["title"],
            "desc": g["desc"], "tags": g["tags"], "tid": g["tid"],
            "cover": g.get("cover", ""), "type": g["type"],
        } for g in self.upload_groups]}
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _load_config(self):
        if not os.path.exists(self._config_path):
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for g in cfg.get("groups", []):
                valid_files = [f for f in g.get("files", []) if os.path.exists(f)]
                if valid_files:
                    g["files"] = valid_files
                    self.upload_groups.append(g)
            self._refresh_tree()
            self._log(f"📋 已加载 {len(self.upload_groups)} 个上传任务")
        except:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BiliUploader()
    app.run()
