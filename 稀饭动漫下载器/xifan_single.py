#!/usr/bin/env python3
"""稀饭动漫下载器 - 随时添加，持续下载"""
import os
import re
import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import queue
import requests
import urllib3
urllib3.disable_warnings()

SITE = "https://anime.xifanacg.com"

class XifanDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("稀饭动漫下载器")
        self.root.geometry("800x650")
        
        self.session = None
        self._downloading = False
        self._cancel = False
        self.download_queue = queue.Queue()  # 下载队列
        
        self.setup_ui()
        self.init_session()
        self.check_queue()  # 启动队列检查
    
    def setup_ui(self):
        # ---- 链接输入 ----
        f_input = ttk.LabelFrame(self.root, text="📥 添加动漫链接", padding=10)
        f_input.pack(fill=tk.X, padx=10, pady=5)
        
        link_row = ttk.Frame(f_input)
        link_row.pack(fill=tk.X, pady=3)
        
        self.link_var = tk.StringVar()
        ttk.Entry(link_row, textvariable=self.link_var, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(link_row, text="➕ 添加", command=self.add_link).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(f_input, text='输入链接后点击"添加"，支持 /bangumi/3235.html 或 /watch/3235/1/1.html', 
                  foreground='gray', font=('微软雅黑', 8)).pack(anchor='w')
        
        # ---- 动漫列表 ----
        f_list = ttk.LabelFrame(self.root, text="🎬 下载队列", padding=10)
        f_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = ("名称", "集数", "状态", "进度")
        self.tree = ttk.Treeview(f_list, columns=columns, show="headings", height=12)
        
        self.tree.heading("名称", text="动漫名称")
        self.tree.heading("集数", text="总集数")
        self.tree.heading("状态", text="状态")
        self.tree.heading("进度", text="下载进度")
        
        self.tree.column("名称", width=350)
        self.tree.column("集数", width=80, anchor="center")
        self.tree.column("状态", width=100, anchor="center")
        self.tree.column("进度", width=120, anchor="center")
        
        scrollbar = ttk.Scrollbar(f_list, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # ---- 输出设置 ----
        f_out = ttk.LabelFrame(self.root, text="💾 输出设置", padding=10)
        f_out.pack(fill=tk.X, padx=10, pady=5)
        
        out_row = ttk.Frame(f_out)
        out_row.pack(fill=tk.X)
        
        ttk.Label(out_row, text="保存目录:").pack(side=tk.LEFT)
        self.out_dir = tk.StringVar(value=r"G:\测试下载\百合番")
        ttk.Entry(out_row, textvariable=self.out_dir, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(out_row, text="选择", command=self.choose_dir).pack(side=tk.LEFT)
        
        # ---- 统计信息 ----
        f_stats = ttk.LabelFrame(self.root, text="📊 统计", padding=10)
        f_stats.pack(fill=tk.X, padx=10, pady=5)
        
        stats_row = ttk.Frame(f_stats)
        stats_row.pack(fill=tk.X)
        
        self.lbl_total = ttk.Label(stats_row, text="队列: 0", foreground='blue')
        self.lbl_total.pack(side=tk.LEFT, padx=15)
        
        self.lbl_success = ttk.Label(stats_row, text="已完成: 0", foreground='green')
        self.lbl_success.pack(side=tk.LEFT, padx=15)
        
        self.lbl_failed = ttk.Label(stats_row, text="失败: 0", foreground='red')
        self.lbl_failed.pack(side=tk.LEFT, padx=15)
        
        self.lbl_status = ttk.Label(stats_row, text="就绪", foreground='gray')
        self.lbl_status.pack(side=tk.RIGHT, padx=15)
        
        # ---- 按钮 ----
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="▶ 开始下载", command=self.start_download).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="⏹ 停止", command=self.stop_download).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="🗑 清空队列", command=self.clear_queue).pack(side=tk.LEFT, padx=10)
    
    def init_session(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        try:
            self.session.get(SITE, verify=False, timeout=15)
        except:
            pass
    
    def choose_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.out_dir.set(path)
    
    def add_link(self):
        """添加单个链接"""
        link = self.link_var.get().strip()
        if not link:
            messagebox.showwarning("警告", "请输入链接")
            return
        
        self.link_var.set("")  # 清空输入框
        
        # 解析并添加到队列
        threading.Thread(target=self._parse_and_add, args=(link,), daemon=True).start()
    
    def _parse_and_add(self, link):
        """解析链接并添加到列表"""
        try:
            self.update_status("正在解析...")
            
            match = re.search(r'/watch/(\d+)/', link) or re.search(r'/bangumi/(\d+)', link)
            if not match:
                self.update_status("❌ 无法解析链接")
                return
            
            vod_id = match.group(1)
            
            resp = self.session.get(f"{SITE}/bangumi/{vod_id}.html", verify=False, timeout=30)
            resp.encoding = "utf-8"
            
            # 提取动漫名称
            title_match = re.search(r'<title>(.*?)</title>', resp.text)
            if title_match:
                full_title = title_match.group(1).strip()
                anime_name = re.split(r'_第\d+集', full_title)[0].strip()
                anime_name = re.split(r'\s*-\s*稀饭动漫', anime_name)[0].strip()
            else:
                name_match = re.search(r'<h1[^>]*>(.*?)</h1>', resp.text)
                anime_name = name_match.group(1).strip() if name_match else f"动漫_{vod_id}"
            
            # 提取集数 - 只取第一条线路
            all_eps = re.findall(r'/watch/(\d+)/(\d+)/(\d+)\.html', resp.text)
            
            if not all_eps:
                self.update_status(f"❌ {anime_name} - 未找到集数")
                return
            
            first_line_eps = [(v, s, n) for v, s, n in all_eps if s == "1"]
            if not first_line_eps:
                min_line = min(int(s) for _, s, _ in all_eps)
                first_line_eps = [(v, s, n) for v, s, n in all_eps if int(s) == min_line]
            
            eps = sorted(set(first_line_eps), key=lambda x: int(x[2]))
            
            # 添加到队列
            anime_info = {
                "id": vod_id,
                "name": anime_name,
                "eps": eps,
                "total": len(eps)
            }
            
            self.download_queue.put(anime_info)
            
            # 更新UI
            self.root.after(0, lambda n=anime_name, t=len(eps): 
                self.tree.insert("", tk.END, values=(n, t, "待下载", "0%")))
            self.root.after(0, lambda: self.lbl_total.config(text=f"队列: {self.download_queue.qsize()}"))
            
            self.update_status(f"✅ 已添加: {anime_name} ({len(eps)}集)")
            
        except Exception as e:
            self.update_status(f"❌ 解析失败: {str(e)[:30]}")
    
    def check_queue(self):
        """定时检查队列，自动下载"""
        if self._downloading and not self._cancel:
            pass  # 正在下载中
        elif not self.download_queue.empty() and not self._cancel:
            # 有待下载的，自动开始
            self.start_download()
        
        self.root.after(1000, self.check_queue)  # 每秒检查
    
    def start_download(self):
        """开始下载"""
        if self._downloading:
            return
        
        if self.download_queue.empty():
            messagebox.showinfo("提示", "队列为空，请先添加动漫链接")
            return
        
        self._downloading = True
        self._cancel = False
        
        self.stats = {
            "success": 0,
            "failed": 0,
            "downloaded_eps": 0,
            "failed_eps": 0
        }
        
        threading.Thread(target=self._download_worker, daemon=True).start()
    
    def stop_download(self):
        """停止下载"""
        self._cancel = True
        self._downloading = False
    
    def clear_queue(self):
        """清空队列"""
        while not self.download_queue.empty():
            try:
                self.download_queue.get_nowait()
            except:
                break
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.lbl_total.config(text="队列: 0")
    
    def _download_worker(self):
        """下载工作线程"""
        out_dir = self.out_dir.get()
        
        while not self.download_queue.empty() and not self._cancel:
            try:
                anime = self.download_queue.get(timeout=1)
            except:
                break
            
            # 找到对应的Treeview项
            items = self.tree.get_children()
            current_item = None
            for item in items:
                if self.tree.item(item, "values")[0] == anime["name"]:
                    current_item = item
                    break
            
            if not current_item:
                continue
            
            name = anime["name"]
            eps = anime["eps"]
            safe_name = re.sub(r'[<>:"/\\|?*]', '', name)[:80]
            
            # 更新状态
            self.root.after(0, lambda i=current_item: self.tree.set(i, "状态", "下载中"))
            
            # 创建文件夹
            anime_dir = os.path.join(out_dir, safe_name)
            os.makedirs(anime_dir, exist_ok=True)
            
            anime_success = 0
            anime_failed = 0
            
            for ep_idx, (v, s, n) in enumerate(eps):
                if self._cancel:
                    break
                
                # 文件名：第01集.mp4
                ep_num = n.zfill(2)
                ep_file = os.path.join(anime_dir, f"第{ep_num}集.mp4")
                
                # 断点续传
                if os.path.exists(ep_file) and os.path.getsize(ep_file) > 1024*1024:
                    anime_success += 1
                    self.stats["downloaded_eps"] += 1
                    continue
                
                # 更新进度
                progress = f"{ep_idx+1}/{len(eps)}"
                self.root.after(0, lambda i=current_item, p=progress: self.tree.set(i, "进度", p))
                
                try:
                    resp = self.session.get(f"{SITE}/watch/{v}/{s}/{n}.html", verify=False, timeout=30)
                    match = re.search(r'player_aaaa=(\{.*?\})</script>', resp.text)
                    
                    if not match:
                        anime_failed += 1
                        self.stats["failed_eps"] += 1
                        continue
                    
                    player_data = json.loads(match.group(1).replace('\\/', '/'))
                    video_url = player_data.get('url', '')
                    
                    if not video_url:
                        anime_failed += 1
                        self.stats["failed_eps"] += 1
                        continue
                    
                    r1 = self.session.get(video_url, allow_redirects=False, verify=False, timeout=15)
                    real_url = r1.headers.get('Location', video_url) if r1.status_code == 302 else video_url
                    
                    r2 = self.session.get(real_url, stream=True, verify=False, timeout=1800)
                    
                    if r2.status_code == 200:
                        with open(ep_file, 'wb') as f:
                            for chunk in r2.iter_content(8192):
                                if self._cancel:
                                    break
                                f.write(chunk)
                        
                        size = os.path.getsize(ep_file)
                        if size > 1024*1024:
                            anime_success += 1
                            self.stats["downloaded_eps"] += 1
                        else:
                            os.remove(ep_file)
                            anime_failed += 1
                            self.stats["failed_eps"] += 1
                    else:
                        anime_failed += 1
                        self.stats["failed_eps"] += 1
                    
                except Exception as e:
                    anime_failed += 1
                    self.stats["failed_eps"] += 1
                
                time.sleep(0.3)
            
            # 更新状态
            if anime_failed == 0:
                status = "✅ 完成"
                self.stats["success"] += 1
            elif anime_success > 0:
                status = f"⚠️ 部分({anime_success}/{len(eps)})"
                self.stats["success"] += 1
            else:
                status = "❌ 失败"
                self.stats["failed"] += 1
            
            self.root.after(0, lambda i=current_item, s=status, a=anime_success, t=len(eps): (
                self.tree.set(i, "状态", s),
                self.tree.set(i, "进度", f"{a}/{t}")
            ))
            
            self.root.after(0, self._update_stats)
        
        self._downloading = False
        self.update_status("✅ 下载完成！等待新任务...")
    
    def _update_stats(self):
        self.lbl_success.config(text=f"已完成: {self.stats['success']}")
        self.lbl_failed.config(text=f"失败: {self.stats['failed']}")
        self.lbl_total.config(text=f"队列: {self.download_queue.qsize()}")
    
    def update_status(self, text):
        self.root.after(0, lambda: self.lbl_status.config(text=text))


if __name__ == "__main__":
    root = tk.Tk()
    app = XifanDownloader(root)
    root.mainloop()
