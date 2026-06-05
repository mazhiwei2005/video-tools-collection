#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番薯动漫全自动下载器
Playwright Edge + 网络监听 + ffmpeg
"""
import re, json, time, os, sys, subprocess, threading, queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ─── 常量 ───
BLUE = "#00a1d6"
BLUE_LIGHT = "#e3f2fd"
BLUE_DARK = "#0095c8"
GREEN = "#4caf50"
RED = "#f44336"
GRAY = "#999"

# ═══════════════════════════════════════════
# 核心: Playwright 网络监听爬取
# ═══════════════════════════════════════════
class FsdmCrawler:
    """用Playwright控制Edge浏览器, 监听网络请求抓m3u8"""
    
    def __init__(self, log_fn=None):
        self.log = log_fn or print
        self._cancel = False
    
    def cancel(self):
        self._cancel = True
    
    def scrape_episodes(self, url):
        """从播放页获取全集列表"""
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="msedge",
                                        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            page = ctx.new_page()
            
            try:
                self.log(f"🔍 加载页面...")
                page.goto(url, timeout=30000)
                time.sleep(5)
                
                content = page.content()
                title = page.title()
                
                # 提取动漫名
                name = title.split('|')[0].split('-')[0].strip() if title else "未知动漫"
                # 去掉 "第XX集" 后缀
                name = re.sub(r'\s*第\d+集\s*$', '', name)
                name = re.sub(r'\s*第\d+话\s*$', '', name)
                
                # 提取集数: 找所有 /vodplay/xxx-sid-ep.html
                ep_pattern = re.findall(r'href="([^"]*vodplay/[^"]*-(\d+)-(\d+)\.html)"', content)
                
                episodes = []
                seen = set()
                for full_url, sid, nid in ep_pattern:
                    key = f"{sid}-{nid}"
                    if key not in seen:
                        seen.add(key)
                        ep_url = full_url if full_url.startswith("http") else f"https://www.fsdm02.com{full_url}"
                        episodes.append({"sid": int(sid), "nid": int(nid), "url": ep_url})
                
                episodes.sort(key=lambda x: (x["sid"], x["nid"]))
                
                self.log(f"✅ 动漫名: {name}")
                self.log(f"📋 找到 {len(episodes)} 集 (线路{len(set(e['sid'] for e in episodes))}条)")
                
                return {"success": True, "name": name, "episodes": episodes, "first_url": url}
            
            except Exception as e:
                return {"error": str(e)}
            finally:
                browser.close()
    
    def grab_m3u8(self, url, timeout=20):
        """打开页面, 监听网络请求, 抓取m3u8 URL"""
        from playwright.sync_api import sync_playwright
        
        m3u8_urls = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="msedge",
                                        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            page = ctx.new_page()
            
            # 监听网络响应
            def on_response(response):
                resp_url = response.url
                if ".m3u8" in resp_url and resp_url not in m3u8_urls:
                    m3u8_urls.append(resp_url)
                elif ".mp4" in resp_url and resp_url not in m3u8_urls:
                    # MP4直链也记录
                    if "blob:" not in resp_url and response.status == 200:
                        ct = response.headers.get("content-type", "")
                        cl = response.headers.get("content-length", "0")
                        if int(cl) > 100000:  # >100KB才是真视频
                            m3u8_urls.append(resp_url)
            
            page.on("response", on_response)
            
            try:
                page.goto(url, timeout=30000)
                
                # 等guard验证 + 视频加载
                start = time.time()
                while time.time() - start < timeout:
                    if self._cancel:
                        break
                    if m3u8_urls:
                        # 找到一个URL后多等2秒看有没有更好的
                        time.sleep(2)
                        break
                    time.sleep(1)
                
                # 也检查页面里的player数据作为备用
                if not m3u8_urls:
                    content = page.content()
                    player_m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;', content, re.S)
                    if player_m:
                        try:
                            d = json.loads(player_m.group(1))
                            raw = d.get("url", "")
                            if d.get("encrypt", 0) == 1:
                                from urllib.parse import unquote
                                raw = unquote(raw)
                            if raw and ("m3u8" in raw or "mp4" in raw):
                                m3u8_urls.append(raw)
                        except:
                            pass
                
            except Exception as e:
                self.log(f"  ⚠️ 浏览器异常: {e}")
            finally:
                browser.close()
        
        return m3u8_urls


# ═══════════════════════════════════════════
# 下载器
# ═══════════════════════════════════════════
class Downloader:
    """下载m3u8→TS分片→合并MP4"""
    
    def __init__(self, log_fn=None):
        self.log = log_fn or print
    
    def download_m3u8(self, m3u8_url, output_path, referer=""):
        """下载m3u8流到mp4"""
        import requests, tempfile, shutil
        import urllib3
        urllib3.disable_warnings()
        
        s = requests.Session()
        s.verify = False
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": referer,
        })
        
        # 1. 获取M3U8内容
        try:
            r = s.get(m3u8_url, timeout=10)
            content = r.text
        except Exception as e:
            self.log(f"  ❌ 获取M3U8失败: {e}")
            return False
        
        # 2. master playlist → 解析子流
        if "#EXT-X-STREAM-INF" in content and "#EXTINF" not in content:
            streams = []
            lines = content.strip().split("\n")
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF"):
                    bw = re.search(r"BANDWIDTH=(\d+)", line)
                    bw_val = int(bw.group(1)) if bw else 0
                    if i + 1 < len(lines):
                        sub = lines[i + 1].strip()
                        if not sub.startswith("http"):
                            sub = m3u8_url.rsplit("/", 1)[0] + "/" + sub
                        streams.append((bw_val, sub))
            if streams:
                streams.sort(key=lambda x: x[0], reverse=True)
                m3u8_url = streams[0][1]
                self.log(f"  📡 master→子流({len(streams)}条)")
                try:
                    r = s.get(m3u8_url, timeout=10)
                    content = r.text
                except:
                    self.log(f"  ❌ 获取子流失败")
                    return False
        
        # 3. 提取TS分片
        base = m3u8_url.rsplit("/", 1)[0] + "/"
        ts_full = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                ts_full.append(line if line.startswith("http") else base + line)
        
        if not ts_full:
            self.log(f"  ❌ 无TS分片")
            return False
        
        self.log(f"  📦 {len(ts_full)}个TS分片")
        
        # 4. 下载TS
        tmp_dir = tempfile.mkdtemp(prefix="fsdm_dl_")
        try:
            downloaded = 0
            for i, ts_url in enumerate(ts_full):
                for retry in range(3):
                    try:
                        r2 = s.get(ts_url, timeout=15)
                        if r2.status_code == 200:
                            with open(os.path.join(tmp_dir, f"{i:05d}.ts"), "wb") as f:
                                f.write(r2.content)
                            downloaded += 1
                            break
                    except:
                        if retry < 2:
                            time.sleep(1)
                
                if (i + 1) % 50 == 0 or i == len(ts_full) - 1:
                    self.log(f"  ⬇️  {i+1}/{len(ts_full)} ({(i+1)/len(ts_full)*100:.0f}%)")
            
            if downloaded == 0:
                self.log(f"  ❌ 所有TS下载失败")
                return False
            
            # 5. ffmpeg合并
            concat_file = os.path.join(tmp_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for i in range(downloaded):
                    f.write(f"file '{i:05d}.ts'\n")
            
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output_path]
            subprocess.run(cmd, capture_output=True, timeout=120)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                sz = os.path.getsize(output_path)
                self.log(f"  ✅ 完成: {sz/1024/1024:.1f}MB")
                return True
            else:
                self.log(f"  ❌ 合并失败")
                return False
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    
    def download_with_ffmpeg(self, m3u8_url, output_path, referer=""):
        """直接用ffmpeg下载(备用方案)"""
        cmd = ["ffmpeg", "-y",
               "-headers", f"Referer: {referer}\r\n",
               "-multiple_requests", "0", "-reconnect", "1",
               "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
               "-reconnect_on_network_error", "1", "-timeout", "10000000",
               "-i", m3u8_url, "-c", "copy", output_path]
        try:
            subprocess.run(cmd, capture_output=True, timeout=600)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                return True
        except:
            pass
        return False


# ═══════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════
class FsdmDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("番薯动漫下载器 — Playwright全自动")
        self.root.geometry("900x680")
        self.root.minsize(800, 550)
        
        self.crawler = FsdmCrawler(log_fn=self._log)
        self.downloader = Downloader(log_fn=self._log)
        self.msg_queue = queue.Queue()
        self._downloading = False
        self._cancel = False
        self.tasks = []
        
        self._setup_style()
        self._setup_ui()
        self._poll_queue()
    
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
        style.configure("Treeview", font=("微软雅黑", 9), rowheight=24)
        style.configure("Treeview.Heading", font=("微软雅黑", 9, "bold"), background=BLUE_LIGHT)
    
    def _setup_ui(self):
        # === 标题栏 ===
        hd = tk.Frame(self.root, bg=BLUE, height=44)
        hd.pack(fill=tk.X)
        tk.Label(hd, text="📥 番薯动漫下载器", bg=BLUE, fg="white", font=("微软雅黑", 14, "bold")).pack(side=tk.LEFT, padx=14, pady=6)
        tk.Label(hd, text="Playwright + Edge + ffmpeg", bg=BLUE, fg="#cce5ff", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=6)
        tk.Label(hd, text="v1.0", bg=BLUE, fg="white", font=("微软雅黑", 8)).pack(side=tk.RIGHT, padx=14)
        
        # === 链接输入 ===
        f1 = ttk.LabelFrame(self.root, text="🔗 输入番薯动漫播放页链接", padding=8)
        f1.pack(fill=tk.X, padx=10, pady=(10, 4))
        
        row1 = tk.Frame(f1, bg="#f4f5f7")
        row1.pack(fill=tk.X)
        self.link_var = tk.StringVar()
        ent = ttk.Entry(row1, textvariable=self.link_var, width=72)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ent.bind("<Return>", lambda e: self._parse_link())
        ttk.Button(row1, text="🔍 解析", style="Blue.TButton", command=self._parse_link).pack(side=tk.LEFT, padx=6)
        
        ttk.Label(f1, text='支持 fsdm02.com / fsdm01.com 等番薯动漫播放页链接',
                  foreground=GRAY, font=("微软雅黑", 8)).pack(anchor="w", pady=(4, 0))
        
        # === 下载队列 ===
        f2 = ttk.LabelFrame(self.root, text="📋 下载队列", padding=8)
        f2.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        
        cols = ("动漫", "集数", "状态", "进度")
        self.tree = ttk.Treeview(f2, columns=cols, show="headings", height=8)
        for c, w in [("动漫", 250), ("集数", 80), ("状态", 100), ("进度", 300)]:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, minwidth=60)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        sb = ttk.Scrollbar(f2, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(fill=tk.Y, side=tk.RIGHT)
        
        # === 按钮栏 ===
        f3 = tk.Frame(self.root, bg="#f4f5f7")
        f3.pack(fill=tk.X, padx=10, pady=4)
        
        self.btn_start = ttk.Button(f3, text="▶ 开始下载", style="Green.TButton", command=self._start)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(f3, text="⏹ 停止", style="Red.TButton", command=self._stop)
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        ttk.Button(f3, text="🗑 清空", command=self._clear).pack(side=tk.LEFT, padx=4)
        
        # 保存目录
        ttk.Label(f3, text="保存到:").pack(side=tk.LEFT, padx=(20, 4))
        self.out_dir = tk.StringVar(value=os.path.expanduser("~/Desktop/动漫下载"))
        ttk.Entry(f3, textvariable=self.out_dir, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f3, text="📁", command=self._choose_dir).pack(side=tk.LEFT, padx=4)
        
        # === 状态栏 ===
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, bg="#e8e8e8", fg=GRAY,
                 font=("微软雅黑", 8), anchor="w").pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)
        
        # === 日志区 ===
        f4 = ttk.LabelFrame(self.root, text="📝 日志", padding=4)
        f4.pack(fill=tk.X, padx=10, pady=(0, 4))
        
        self.log_text = tk.Text(f4, height=6, font=("Consolas", 8), wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.X)
    
    def _choose_dir(self):
        d = filedialog.askdirectory(title="选择保存目录")
        if d:
            self.out_dir.set(d)
    
    def _log(self, msg, tag="info"):
        self.msg_queue.put(("log", msg))
    
    def _parse_link(self):
        url = self.link_var.get().strip()
        if not url:
            return
        if "fsdm" not in url and "fsdm" not in url.lower():
            messagebox.showwarning("提示", "请输入番薯动漫的链接")
            return
        
        self._log(f"🔍 解析中: {url}")
        threading.Thread(target=self._parse_worker, args=(url,), daemon=True).start()
    
    def _parse_worker(self, url):
        result = self.crawler.scrape_episodes(url)
        if "error" in result:
            self._log(f"❌ {result['error']}", "err")
            return
        
        name = result["name"]
        episodes = result["episodes"]
        
        if not episodes:
            self._log(f"❌ 未找到集数", "err")
            return
        
        task = {
            "name": name,
            "episodes": episodes,
            "status": "等待",
            "done": 0,
            "first_url": result.get("first_url", url),
        }
        self.tasks.append(task)
        self.msg_queue.put(("add_task", task, len(episodes)))
        self._log(f"✅ 已添加: {name} ({len(episodes)}集)", "ok")
    
    def _start(self):
        if self._downloading:
            return
        pending = [t for t in self.tasks if t["status"] in ("等待", "失败")]
        if not pending:
            messagebox.showinfo("提示", "没有待下载的任务")
            return
        self._downloading = True
        self._cancel = False
        threading.Thread(target=self._download_worker, args=(pending,), daemon=True).start()
    
    def _stop(self):
        self._cancel = True
        self.crawler.cancel()
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
            
            name = task["name"].replace("/", "_").replace("\\", "_") or "未知动漫"
            save_path = os.path.join(save_dir, name)
            os.makedirs(save_path, exist_ok=True)
            episodes = task["episodes"]
            first_url = task.get("first_url", "")
            
            self._log(f"▶ {name} ({len(episodes)}集) → {save_path}")
            
            for i, ep in enumerate(episodes):
                if self._cancel:
                    break
                
                nid = ep["nid"]
                sid = ep["sid"]
                ep_url = ep["url"]
                
                task["done"] = f"{i+1}/{len(episodes)}"
                self.msg_queue.put(("refresh_tree",))
                
                # 如果没有具体集URL, 从first_url推导
                if not ep_url and first_url:
                    ep_url = re.sub(r'-(\d+)-(\d+)\.html$', f'-{sid}-{nid}.html', first_url)
                
                self._log(f"  🔗 [{i+1}/{len(episodes)}] 第{nid:02d}集 抓取m3u8...")
                
                # Playwright抓m3u8
                m3u8_urls = self.crawler.grab_m3u8(ep_url, timeout=20)
                
                if not m3u8_urls:
                    self._log(f"  ❌ 第{nid:02d}集: 未抓到视频URL", "err")
                    task["done"] = f"{i+1}/{len(episodes)} ✗"
                    total_fail += 1
                    self.msg_queue.put(("refresh_tree",))
                    continue
                
                video_url = m3u8_urls[0]
                self._log(f"  🎬 第{nid:02d}集: {'M3U8' if 'm3u8' in video_url else 'MP4'}")
                
                # 下载
                output = os.path.join(save_path, f"第{nid:02d}集.mp4")
                ok = self.downloader.download_m3u8(video_url, output, referer="https://www.fsdm02.com/")
                
                if ok:
                    self._log(f"  ✅ 第{nid:02d}集: 完成", "ok")
                    task["done"] = f"{i+1}/{len(episodes)} ✓"
                    total_ok += 1
                else:
                    self._log(f"  ❌ 第{nid:02d}集: 下载失败", "err")
                    task["done"] = f"{i+1}/{len(episodes)} ✗"
                    total_fail += 1
                
                self.msg_queue.put(("refresh_tree",))
                time.sleep(2)  # 防止请求过快
            
            task["status"] = "完成" if not self._cancel else "已停止"
            self.msg_queue.put(("refresh_tree",))
        
        self._downloading = False
        self._log(f"🎉 全部完成! 成功: {total_ok}, 失败: {total_fail}", "ok")
        self.msg_queue.put(("update_stats", total_ok, total_fail))
    
    # ── 消息队列 ──
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "log":
                    self._append_log(msg[1])
                elif msg[0] == "add_task":
                    task, count = msg[1], msg[2]
                    self.tree.insert("", tk.END, values=(task["name"], f"{count}集", task["status"], ""), iid=str(id(task)))
                elif msg[0] == "refresh_tree":
                    self._refresh_tree()
                elif msg[0] == "update_stats":
                    self.status_var.set(f"完成! 成功: {msg[1]}, 失败: {msg[2]}")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)
    
    def _append_log(self, msg):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def _refresh_tree(self):
        for task in self.tasks:
            iid = str(id(task))
            try:
                self.tree.item(iid, values=(task["name"], f"{len(task['episodes'])}集", task["status"], task.get("done", "")))
            except:
                pass


def main():
    root = tk.Tk()
    app = FsdmDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
