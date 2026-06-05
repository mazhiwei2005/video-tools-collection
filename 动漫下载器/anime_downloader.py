#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动漫下载器 v1.0
支持站点：omofun (O站) | 哔咪动漫 (bimiacg) | 661dm
tkinter GUI — B站蓝白配色
"""
import os, re, json, time, subprocess, threading, queue
from urllib.parse import unquote
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── 常量 ───
BLUE = "#00a1d6"
BLUE_LIGHT = "#e3f2fd"
BLUE_DARK = "#0095c8"
GREEN = "#4caf50"
RED = "#f44336"
GRAY = "#999"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def extract_player_data(html):
    """从HTML提取player_aaaa JSON，正确处理嵌套括号"""
    for pat in ["var player_aaaa={", "var player_aaaa = {", "var player_aaaa= {"]:
        idx = html.find(pat)
        if idx >= 0:
            start = html.index("{", idx)
            depth = 0
            for i in range(start, min(start + 10000, len(html))):
                if html[i] == "{":
                    depth += 1
                elif html[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(html[start : i + 1])
                        except:
                            return None
    return None


def extract_episodes(html, sid):
    """从页面HTML提取所有集数 — 兼容多种URL格式"""
    nids = set()
    for m in re.findall(rf"play/{sid}/(\d+)[/.]", html):
        nids.add(int(m))
    for m in re.findall(rf"sid/{sid}/nid/(\d+)", html):
        nids.add(int(m))
    for m in re.findall(rf"sid[=/]{sid}[^0-9]*nid[=/](\d+)", html):
        nids.add(int(m))
    if nids:
        return [{"nid": i, "label": f"第{i:02d}集"} for i in range(1, max(nids) + 1)]
    return []


def detect_site(url):
    if "omofuns" in url or "omofun." in url:
        return "omofun"
    elif "bimiacg" in url:
        return "bimiacg"
    elif "661dm" in url:
        return "661dm"
    return None


# ═══════════════════════════════════════════
# 解析器
# ═══════════════════════════════════════════

class SiteParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = False

    def parse(self, url):
        site = detect_site(url)
        if not site:
            return {"error": "不支持的站点，请输入 omofun / bimiacg / 661dm 的链接"}
        fn = {"omofun": self._omofun, "bimiacg": self._bimiacg, "661dm": self._661dm}
        return fn[site](url)

    def get_url(self, site, anime_id, sid, nid):
        fn = {"omofun": self._omofun_url, "bimiacg": self._bimiacg_url, "661dm": self._661dm_url}
        return fn[site](anime_id, sid, nid)

    # ── omofun ──
    def _omofun(self, url):
        try:
            r = self.session.get(url, timeout=15, verify=False)
            if r.status_code == 404:
                return {"error": "页面不存在(404), 请检查链接是否正确"}
            if len(r.text) < 1000:
                return {"error": f"页面内容异常({len(r.text)}字节), 站点可能维护中"}
            d = extract_player_data(r.text)
            if not d:
                return {"error": "找不到播放数据, 该集可能下架或链接格式已变"}
            episodes = extract_episodes(r.text, d.get("sid", 1))
            return {
                "success": True, "site": "omofun",
                "anime_name": d.get("vod_data", {}).get("vod_name", ""),
                "anime_id": d.get("id", ""), "sid": d.get("sid", 1),
                "episodes": episodes or [{"nid": d.get("nid", 1), "label": "第01集"}],
                "first_url": d.get("url", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def _omofun_url(self, anime_id, sid, nid):
        try:
            r = self.session.get(f"https://omofuns.xyz/vod/play/id/{anime_id}/sid/{sid}/nid/{nid}.html", timeout=15, verify=False)
            d = extract_player_data(r.text)
            return d.get("url", "") if d else ""
        except:
            return ""

    # ── bimiacg ──
    def _req_with_retry(self, url, retries=3, **kwargs):
        """带重试的请求（应对连接重置）"""
        kwargs.setdefault("verify", False)
        kwargs.setdefault("timeout", 15)
        for i in range(retries):
            try:
                return self.session.get(url, **kwargs)
            except (ConnectionResetError, ConnectionError, OSError) as e:
                if i < retries - 1:
                    time.sleep(2 * (i + 1))
                else:
                    raise

    def _bimiacg(self, url):
        try:
            r = self._req_with_retry(url, allow_redirects=True)
            d = extract_player_data(r.text)
            if not d:
                return {"error": "找不到播放数据"}
            # 灵活提取动漫名: 第X话/第X集/|分隔/-分隔
            title_m = re.search(r"<title>\s*(.+?)\s*第\d+[话集]", r.text)
            if not title_m:
                title_m = re.search(r"<title>\s*(.+?)\s*[|｜\-]", r.text)
            if not title_m:
                title_m = re.search(r"<title>\s*(.+?)\s*</title>", r.text)
            episodes = extract_episodes(r.text, d.get("sid", 2))
            return {
                "success": True, "site": "bimiacg",
                "anime_name": title_m.group(1).strip() if title_m else "",
                "anime_id": d.get("id", ""), "sid": d.get("sid", 2),
                "episodes": episodes or [{"nid": d.get("nid", 1), "label": "第01集"}],
                "first_token": d.get("url", ""), "page_url": r.url,
            }
        except Exception as e:
            return {"error": str(e)}

    def _bimiacg_url(self, anime_id, sid, nid):
        try:
            page = f"https://www.bimiacg14.net/bangumi/{anime_id}/play/{sid}/{nid}/"
            r = self._req_with_retry(page, allow_redirects=True)
            d = extract_player_data(r.text)
            if not d:
                return ""
            token = d.get("url", "")
            if not token:
                return ""
            r2 = self._req_with_retry(
                f"https://www.bimiacg14.net/static/danmu/play.php?url={token}&myurl={page}",
                headers={**HEADERS, "Referer": page},
            )
            m = re.search(r'<source\s+src=["\']([^"\']+)["\']', r2.text)
            if m:
                return m.group(1)
            m = re.search(r"var\s+url\s*=\s*['\"]([^'\"]+)['\"]", r2.text)
            return m.group(1) if m else ""
        except:
            return ""




    # ── 661dm ──
    def _661dm(self, url):
        try:
            r = self.session.get(url, timeout=15, verify=False)
            d = extract_player_data(r.text)
            if not d:
                return {"error": "找不到播放数据"}
            episodes = extract_episodes(r.text, d.get("sid", 3))
            name = d.get("vod_data", {}).get("vod_name", "")
            if not name:
                tm = re.search(r"<title>\s*(.+?)\s*[-|]", r.text)
                name = tm.group(1).strip() if tm else ""
            return {
                "success": True, "site": "661dm",
                "anime_name": name,
                "anime_id": d.get("id", ""), "sid": d.get("sid", 3),
                "episodes": episodes or [{"nid": d.get("nid", 1), "label": "第01集"}],
                "first_url": d.get("url", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def _661dm_get_url(self, anime_id, sid, nid):
        """从指定线路获取视频URL"""
        try:
            r = self.session.get(f"https://www.661dm.com/anime/{anime_id}/play/{sid}/{nid}.html",
                                 timeout=12, verify=False)
            d = extract_player_data(r.text)
            if not d:
                return ""
            raw = d.get("url", "")
            enc = d.get("encrypt", 0)
            if enc == 1:
                return unquote(raw)
            elif enc == 2:
                return unquote(__import__("base64").b64decode(raw).decode())
            return raw
        except:
            return ""

    def _661dm_url(self, anime_id, sid, nid):
        """自动遍历4个线路, 返回第一个能下载的URL"""
        fallback = [4, 3, 2, 1]  # 西瓜→天堂→暴风→精品
        if sid in fallback:
            fallback.remove(sid)
            fallback.insert(0, sid)

        for try_sid in fallback:
            video_url = self._661dm_get_url(anime_id, try_sid, nid)
            if not video_url:
                continue
            # 验证M3U8是否有效
            if "m3u8" in video_url:
                try:
                    r = self.session.get(video_url, timeout=5, verify=False,
                                         headers={"Referer": "https://www.661dm.com/"})
                    if r.status_code == 200:
                        content = r.text
                        # 检查假M3U8(引用图片)
                        lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
                        bad_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
                        if any(l.lower().endswith(bad_exts) for l in lines[:3]):
                            continue
                        if "#EXTINF" in content or "#EXT-X-STREAM-INF" in content:
                            return video_url
                except:
                    pass
            else:
                return video_url  # MP4直接返回
        return ""


# ═══════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════

class AnimeDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("动漫下载器 v1.0 — omofun | 哔咪动漫 | 661dm")
        self.root.geometry("850x680")
        self.root.minsize(750, 550)

        self.parser = SiteParser()
        self.msg_queue = queue.Queue()
        self._downloading = False
        self._cancel = False
        self.tasks = []  # [{site, anime_id, sid, anime_name, episodes, status, done}]

        self._setup_style()
        self._setup_ui()
        self._poll_queue()

    # ── 样式 ──
    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f5f7")
        style.configure("TLabel", background="#f4f5f7", font=("微软雅黑", 9))
        style.configure("TButton", font=("微软雅黑", 9))
        style.configure("TLabelframe", background="#f4f5f7", font=("微软雅黑", 9, "bold"))
        style.configure("TLabelframe.Label", background="#f4f5f7", font=("微软雅黑", 9, "bold"))
        style.configure("Blue.TButton", background=BLUE, foreground="white", font=("微软雅黑", 9, "bold"))
        style.map("Blue.TButton", background=[("active", BLUE_DARK)])
        style.configure("Green.TButton", background=GREEN, foreground="white", font=("微软雅黑", 9, "bold"))
        style.map("Green.TButton", background=[("active", "#43a047")])
        style.configure("Red.TButton", background=RED, foreground="white", font=("微软雅黑", 9))
        style.map("Red.TButton", background=[("active", "#d32f2f")])
        # Treeview
        style.configure("Treeview", font=("微软雅黑", 9), rowheight=24)
        style.configure("Treeview.Heading", font=("微软雅黑", 9, "bold"), background=BLUE_LIGHT)

    # ── UI ──
    def _setup_ui(self):
        # === 标题栏 ===
        hd = tk.Frame(self.root, bg=BLUE, height=44)
        hd.pack(fill=tk.X)
        tk.Label(hd, text="📥 动漫下载器", bg=BLUE, fg="white", font=("微软雅黑", 14, "bold")).pack(side=tk.LEFT, padx=14, pady=6)
        tk.Label(hd, text="omofun · 哔咪动漫 · 661dm", bg=BLUE, fg="#cce5ff", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=6)
        tk.Label(hd, text="v1.0", bg=BLUE, fg="white", font=("微软雅黑", 8)).pack(side=tk.RIGHT, padx=14)

        # === 链接输入 ===
        f1 = ttk.LabelFrame(self.root, text="🔗 输入动漫播放页链接", padding=8)
        f1.pack(fill=tk.X, padx=10, pady=(10, 4))

        row1 = tk.Frame(f1, bg="#f4f5f7")
        row1.pack(fill=tk.X)
        self.link_var = tk.StringVar()
        ent = ttk.Entry(row1, textvariable=self.link_var, width=72)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ent.bind("<Return>", lambda e: self._add_link())
        ttk.Button(row1, text="➕ 添加", style="Blue.TButton", command=self._add_link).pack(side=tk.LEFT, padx=6)

        ttk.Label(f1, text='支持 omofuns.xyz / bimiacg*.net / 661dm.com 播放页链接',
                  foreground=GRAY, font=("微软雅黑", 8)).pack(anchor="w", pady=(4, 0))

        # === 下载队列 ===
        f2 = ttk.LabelFrame(self.root, text="🎬 下载队列", padding=8)
        f2.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        cols = ("动漫名称", "站点", "集数", "状态", "进度")
        self.tree = ttk.Treeview(f2, columns=cols, show="headings", height=10)
        self.tree.heading("动漫名称", text="动漫名称")
        self.tree.heading("站点", text="站点")
        self.tree.heading("集数", text="总集数")
        self.tree.heading("状态", text="状态")
        self.tree.heading("进度", text="下载进度")
        self.tree.column("动漫名称", width=280)
        self.tree.column("站点", width=80, anchor="center")
        self.tree.column("集数", width=60, anchor="center")
        self.tree.column("状态", width=80, anchor="center")
        self.tree.column("进度", width=120, anchor="center")

        sb = ttk.Scrollbar(f2, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # === 保存目录 ===
        f3 = ttk.LabelFrame(self.root, text="💾 输出设置", padding=8)
        f3.pack(fill=tk.X, padx=10, pady=4)

        row3 = tk.Frame(f3, bg="#f4f5f7")
        row3.pack(fill=tk.X)
        ttk.Label(row3, text="保存目录:").pack(side=tk.LEFT)
        self.out_dir = tk.StringVar(value=r"G:\动漫下载")
        ttk.Entry(row3, textvariable=self.out_dir, width=55).pack(side=tk.LEFT, padx=5)
        ttk.Button(row3, text="选择", command=self._choose_dir).pack(side=tk.LEFT)

        # === 日志 ===
        f4 = ttk.LabelFrame(self.root, text="📋 日志", padding=8)
        f4.pack(fill=tk.X, padx=10, pady=4)

        self.log_text = tk.Text(f4, height=6, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="white", state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.X)
        self.log_text.tag_configure("ok", foreground="#4ec9b0")
        self.log_text.tag_configure("err", foreground="#f44747")
        self.log_text.tag_configure("info", foreground="#569cd6")

        # === 底部按钮+统计 ===
        f5 = tk.Frame(self.root, bg="#f4f5f7")
        f5.pack(fill=tk.X, padx=10, pady=6)

        # 统计
        self.lbl_total = tk.Label(f5, text="队列: 0", bg="#f4f5f7", fg=BLUE, font=("微软雅黑", 9))
        self.lbl_total.pack(side=tk.LEFT, padx=10)
        self.lbl_ok = tk.Label(f5, text="完成: 0", bg="#f4f5f7", fg=GREEN, font=("微软雅黑", 9))
        self.lbl_ok.pack(side=tk.LEFT, padx=10)
        self.lbl_fail = tk.Label(f5, text="失败: 0", bg="#f4f5f7", fg=RED, font=("微软雅黑", 9))
        self.lbl_fail.pack(side=tk.LEFT, padx=10)
        self.lbl_status = tk.Label(f5, text="就绪", bg="#f4f5f7", fg=GRAY, font=("微软雅黑", 9))
        self.lbl_status.pack(side=tk.RIGHT, padx=10)

        # 按钮
        btn_frame = tk.Frame(self.root, bg="#f4f5f7")
        btn_frame.pack(pady=(0, 10))
        ttk.Button(btn_frame, text="▶ 开始下载", style="Green.TButton", command=self._start).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="⏹ 停止", style="Red.TButton", command=self._stop).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="🗑 清空队列", command=self._clear).pack(side=tk.LEFT, padx=8)

    # ── 逻辑 ──
    def _choose_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.out_dir.set(path)

    def _log(self, msg, tag="info"):
        self.msg_queue.put(("log", msg, tag))

    def _add_link(self):
        url = self.link_var.get().strip()
        if not url:
            return
        self.link_var.set("")
        threading.Thread(target=self._parse_and_add, args=(url,), daemon=True).start()

    def _parse_and_add(self, url):
        try:
            self._log(f"🔍 解析中: {url[:60]}...", "info")
            result = self.parser.parse(url)
            if "error" in result:
                self._log(f"❌ {result['error']}", "err")
                return

            # 检查已下载的集数
            save_dir = self.out_dir.get()
            anime_name = result["anime_name"].replace("/", "_").replace("\\", "_") or "未知动漫"
            save_path = os.path.join(save_dir, anime_name)
            existing = set()
            if os.path.isdir(save_path):
                for f in os.listdir(save_path):
                    if f.endswith(".mp4") and f.startswith("第"):
                        # 提取集数: 第01集.mp4 -> 1
                        m = re.search(r"第(\d+)集", f)
                        if m:
                            ep_file = os.path.join(save_path, f)
                            # 检查文件大小 > 1MB 才算有效
                            if os.path.getsize(ep_file) > 1024*1024:
                                existing.add(int(m.group(1)))

            # 标记每集状态
            episodes = result["episodes"]
            for ep in episodes:
                ep["exists"] = ep["nid"] in existing

            exist_count = len(existing)
            miss_count = len(episodes) - exist_count
            task = {
                "site": result["site"],
                "anime_id": result["anime_id"],
                "sid": result["sid"],
                "anime_name": result["anime_name"],
                "episodes": episodes,
                "status": "等待",
                "done": 0,
            }
            self.msg_queue.put(("add_task", task))

            if exist_count > 0:
                self._log(f"✅ 已添加: {anime_name} ({len(episodes)}集) [{result['site']}] — 已有{exist_count}集, 缺少{miss_count}集", "ok")
            else:
                self._log(f"✅ 已添加: {anime_name} ({len(episodes)}集) [{result['site']}] — 全部缺少", "ok")
        except Exception as e:
            self._log(f"❌ 解析异常: {e}", "err")

    def _start(self):
        if self._downloading:
            return
        # 收集未完成的任务
        pending = [t for t in self.tasks if t["status"] in ("等待", "失败")]
        if not pending:
            messagebox.showinfo("提示", "没有待下载的任务")
            return
        self._downloading = True
        self._cancel = False
        threading.Thread(target=self._download_worker, args=(pending,), daemon=True).start()

    def _stop(self):
        self._cancel = True
        self._downloading = False
        self._log("⏹ 用户停止", "err")

    def _clear(self):
        if self._downloading:
            return
        self.tasks.clear()
        self.msg_queue.put(("refresh_tree",))

    def _download_worker(self, tasks):
        save_dir = self.out_dir.get()
        total_ok = 0
        total_fail = 0

        for task in tasks:
            if self._cancel:
                break
            task["status"] = "下载中"
            self.msg_queue.put(("refresh_tree",))

            anime_name = task["anime_name"].replace("/", "_").replace("\\", "_") or "未知动漫"
            save_path = os.path.join(save_dir, anime_name)
            os.makedirs(save_path, exist_ok=True)
            site = task["site"]
            anime_id = task["anime_id"]
            sid = task["sid"]
            eps = task["episodes"]
            self._log(f"▶ {anime_name} ({len(eps)}集) → {save_path}", "info")

            skip_count = sum(1 for ep in eps if ep.get("exists"))
            if skip_count > 0:
                self._log(f"  ⏭  跳过已有 {skip_count} 集, 下载缺少的 {len(eps)-skip_count} 集", "info")

            for i, ep in enumerate(eps):
                if self._cancel:
                    break
                nid = ep["nid"]

                # 跳过已下载的集数
                if ep.get("exists"):
                    task["done"] = f"{i+1}/{len(eps)} ⏭"
                    self.msg_queue.put(("refresh_tree",))
                    continue

                task["done"] = f"{i+1}/{len(eps)}"
                self.msg_queue.put(("refresh_tree",))

                self._log(f"  🔗 [{i+1}/{len(eps)}] 第{nid:02d}集 获取链接...", "info")
                video_url = self.parser.get_url(site, anime_id, sid, nid)
                if not video_url:
                    self._log(f"  ❌ 第{nid:02d}集: 获取链接失败(线路均不可用)", "err")
                    task["done"] = f"{i+1}/{len(eps)} ✗"
                    total_fail += 1
                    continue

                self._log(f"  ⬇️  第{nid:02d}集: 下载中...", "info")
                ok = self._download_one(video_url, save_path, nid, site)
                if ok:
                    self._log(f"  ✅ 第{nid:02d}集: 完成", "ok")
                    task["done"] = f"{i+1}/{len(eps)} ✓"
                    total_ok += 1
                else:
                    self._log(f"  ❌ 第{nid:02d}集: 下载失败", "err")
                    task["done"] = f"{i+1}/{len(eps)} ✗"
                    total_fail += 1
                self.msg_queue.put(("refresh_tree",))
                if i < len(eps) - 1:
                    time.sleep(1)

            task["status"] = "完成" if not self._cancel else "已停止"
            self.msg_queue.put(("refresh_tree",))

        self._downloading = False
        self._log(f"🎉 全部完成! 成功: {total_ok}, 失败: {total_fail}", "ok")
        self.msg_queue.put(("update_stats", total_ok, total_fail))

    @staticmethod
    def _fmt_size(b):
        if b < 1024: return f"{b}B"
        if b < 1024*1024: return f"{b/1024:.0f}KB"
        if b < 1024*1024*1024: return f"{b/1024/1024:.1f}MB"
        return f"{b/1024/1024/1024:.2f}GB"


    def _download_one(self, url, save_path, ep_idx, site):
        final = os.path.join(save_path, f"第{ep_idx:02d}集.mp4")
        referer = {"omofun": "https://omofuns.xyz/", "bimiacg": "https://www.bimiacg14.net/",
                    "661dm": "https://www.661dm.com/"}.get(site, "")
        if "m3u8" in url:
            return self._download_m3u8(url, final, ep_idx, referer)
        return self._download_with_requests(url, final, ep_idx, referer)

    def _download_with_requests(self, url, final, ep_idx, referer):
        """requests直接下载MP4, 零CPU消耗"""
        headers = {**HEADERS, "Referer": referer}
        try:
            import requests as _req
            # streaming下载, 不占内存
            r = _req.get(url, headers=headers, verify=False, stream=True, timeout=30)
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            last_update = time.time()
            start_time = time.time()

            with open(final, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):  # 1MB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_update >= 2:
                            last_update = now
                            if total_size > 0:
                                pct = downloaded / total_size * 100
                                self._log(f"  ⬇️  第{ep_idx:02d}集: {self._fmt_size(downloaded)}/{self._fmt_size(total_size)} ({pct:.0f}%)", "info")
                            else:
                                self._log(f"  ⬇️  第{ep_idx:02d}集: {self._fmt_size(downloaded)}", "info")

            if os.path.getsize(final) > 10000:
                self._log(f"  📦 第{ep_idx:02d}集: {self._fmt_size(downloaded)}", "info")
                return True
            if os.path.exists(final):
                os.remove(final)
        except Exception as e:
            self._log(f"  ❌ 第{ep_idx:02d}集: {e}", "err")
            if os.path.exists(final):
                try: os.remove(final)
                except: pass
        return False

    def _download_m3u8(self, url, final, ep_idx, referer):
        """M3U8下载: requests下载TS分片 + ffmpeg合并"""
        import shutil, tempfile
        try:
            r = self.session.get(url, headers={**HEADERS, "Referer": referer}, verify=False, timeout=10)
            content = r.text
        except Exception as e:
            self._log(f"  ❌ 第{ep_idx:02d}集: 获取M3U8失败 {e}", "err")
            return False

        # 检查假M3U8
        lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
        bad_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        if any(l.lower().endswith(bad_exts) for l in lines[:5]):
            self._log(f"  ❌ 第{ep_idx:02d}集: M3U8是假的", "err")
            return False

        # master playlist → 解析子流
        if "#EXT-X-STREAM-INF" in content and "#EXTINF" not in content:
            streams = []
            cl = content.strip().split("\n")
            for i, line in enumerate(cl):
                if line.startswith("#EXT-X-STREAM-INF"):
                    bw = re.search(r"BANDWIDTH=(\d+)", line)
                    bw_val = int(bw.group(1)) if bw else 0
                    if i + 1 < len(cl):
                        sub = cl[i + 1].strip()
                        if not sub.startswith("http"):
                            sub = url.rsplit("/", 1)[0] + "/" + sub
                        streams.append((bw_val, sub))
            if streams:
                streams.sort(key=lambda x: x[0], reverse=True)
                url = streams[0][1]
                self._log(f"  📡 第{ep_idx:02d}集: master→子流({len(streams)}条)", "info")
                try:
                    r = self.session.get(url, headers={**HEADERS, "Referer": referer}, verify=False, timeout=10)
                    content = r.text
                except:
                    self._log(f"  ❌ 第{ep_idx:02d}集: 获取子流失败", "err")
                    return False

        # 提取TS分片
        base = url.rsplit("/", 1)[0] + "/"
        ts_full = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                ts_full.append(line if line.startswith("http") else base + line)
        if not ts_full:
            self._log(f"  ❌ 第{ep_idx:02d}集: 无TS分片", "err")
            return False

        # 下载TS分片
        tmp_dir = tempfile.mkdtemp(prefix="anime_dl_")
        try:
            downloaded = 0
            failed = 0
            t0 = time.time()
            last_update = time.time()

            for i, ts_url in enumerate(ts_full):
                for retry in range(3):
                    try:
                        r2 = self.session.get(ts_url, timeout=15, verify=False,
                                              headers={"Referer": referer})
                        if r2.status_code == 200:
                            with open(os.path.join(tmp_dir, f"{i:05d}.ts"), "wb") as f:
                                f.write(r2.content)
                            downloaded += 1
                            break
                    except:
                        if retry < 2:
                            time.sleep(1)
                else:
                    failed += 1

                now = time.time()
                if now - last_update >= 2:
                    last_update = now
                    pct = (i + 1) / len(ts_full) * 100
                    self._log(f"  ⬇️  第{ep_idx:02d}集: {i+1}/{len(ts_full)} ({pct:.0f}%)", "info")

            if downloaded == 0:
                self._log(f"  ❌ 第{ep_idx:02d}集: 所有TS下载失败", "err")
                return False

            # ffmpeg合并
            self._log(f"  🔧 第{ep_idx:02d}集: 合并{downloaded}个分片...", "info")
            concat_file = os.path.join(tmp_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for i in range(downloaded):
                    f.write(f"file '{i:05d}.ts'\n")

            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", final]
            subprocess.run(cmd, capture_output=True, timeout=120)

            if os.path.exists(final) and os.path.getsize(final) > 10000:
                elapsed = time.time() - t0
                self._log(f"  📦 第{ep_idx:02d}集: {self._fmt_size(os.path.getsize(final))} ({elapsed:.0f}s)", "info")
                return True
            self._log(f"  ❌ 第{ep_idx:02d}集: 合并失败", "err")
            if os.path.exists(final):
                try: os.remove(final)
                except: pass
            return False
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


    # ── 消息队列 ──
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "log":
                    self._append_log(msg[1], msg[2])
                elif msg[0] == "add_task":
                    self.tasks.append(msg[1])
                    self._refresh_tree()
                elif msg[0] == "refresh_tree":
                    self._refresh_tree()
                elif msg[0] == "update_stats":
                    self._update_stats(msg[1], msg[2])
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def _append_log(self, msg, tag="info"):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        total = 0
        for t in self.tasks:
            ep_count = len(t["episodes"])
            exist_count = sum(1 for ep in t["episodes"] if ep.get("exists"))
            total += ep_count
            done_str = t.get("done", "")
            if exist_count > 0 and t["status"] == "等待":
                ep_str = f"{ep_count}集 (已有{exist_count})"
            else:
                ep_str = f"{ep_count}集"
            self.tree.insert("", tk.END, values=(t["anime_name"], t["site"], ep_str, t["status"], done_str))
        self.lbl_total.configure(text=f"队列: {len(self.tasks)} ({total}集)")

    def _update_stats(self, ok, fail):
        self.lbl_ok.configure(text=f"完成: {ok}")
        self.lbl_fail.configure(text=f"失败: {fail}")
        self.lbl_status.configure(text="✅ 全部完成" if fail == 0 else f"⚠️ {fail}集失败", fg=GREEN if fail == 0 else RED)


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    app = AnimeDownloader(root)
    root.mainloop()
