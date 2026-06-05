#!/usr/bin/env python3
"""动漫查询模块"""
import os, re, json, tkinter as tk
from tkinter import messagebox, ttk
import threading
import requests
import urllib3
urllib3.disable_warnings()

SITE = "https://anime.xifanacg.com"

class AnimeSearchPage:
    def __init__(self, parent, colors):
        self.C = colors
        self.frame = tk.Frame(parent, bg=colors["bg"])
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        self._build_ui()

    def show(self): pass
    def hide(self): pass

    def _card(self, parent=None):
        p = parent or self.frame
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
        # 搜索栏
        card = self._card()
        self._card_title(card, "🔍 搜索动漫")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(0, 10))
        self.search_var = tk.StringVar()
        entry = tk.Entry(r, textvariable=self.search_var, font=("微软雅黑", 12), width=40)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda e: self._search())
        self._btn(r, "搜索", self._search).pack(side=tk.LEFT, padx=8)

        # B站番剧查询
        card = self._card()
        self._card_title(card, "📺 B站番剧索引")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="年份:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        self.year_var = tk.StringVar(value="2025")
        tk.Spinbox(r, from_=2000, to=2026, textvariable=self.year_var, width=6,
                   font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=5)
        self._btn(r, "查询B站番剧", self._query_bili).pack(side=tk.LEFT, padx=8)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(3, 10))
        tk.Label(r, text="类型:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        self.type_var = tk.StringVar(value="全部")
        ttk.Combobox(r, textvariable=self.type_var, width=10, state="readonly",
                     values=["全部", "番剧", "国创", "电影", "电视剧"]).pack(side=tk.LEFT, padx=5)

        # 结果
        card = self._card()
        self._card_title(card, "📋 查询结果")
        self.result_text = tk.Text(card, height=18, font=("微软雅黑", 10), bg="#F8F9FA",
                                   wrap=tk.WORD, state=tk.DISABLED)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        # 操作按钮
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(0, 10))
        self._btn(r, "复制链接", self._copy_link, "secondary").pack(side=tk.LEFT, padx=(0, 5))
        self._btn(r, "添加到下载", self._add_to_download, "success").pack(side=tk.LEFT)

        self.lbl_status = tk.Label(card, text="输入动漫名称搜索，或查询B站番剧索引",
                                   font=("微软雅黑", 10), bg=self.C["primary_light"],
                                   fg=self.C["primary"], padx=12, pady=6)
        self.lbl_status.pack(fill=tk.X, padx=15, pady=(0, 10))

    def _set_result(self, text):
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", text)
        self.result_text.config(state=tk.DISABLED)

    def _search(self):
        keyword = self.search_var.get().strip()
        if not keyword:
            messagebox.showwarning("警告", "请输入搜索关键词"); return
        self.lbl_status.config(text=f"搜索中: {keyword}...")
        threading.Thread(target=self._do_search, args=(keyword,), daemon=True).start()

    def _do_search(self, keyword):
        try:
            # 稀饭动漫API搜索
            resp = self.session.post(f"{SITE}/index.php/ds_api/vod",
                                     data={"wd": keyword, "limit": 20},
                                     verify=False, timeout=15)
            data = resp.json()
            results = data.get("data", []) or data.get("list", [])

            if not results:
                self.frame.after(0, lambda: self._set_result(f"未找到「{keyword}」相关结果"))
                self.frame.after(0, lambda: self.lbl_status.config(text="无结果"))
                return

            lines = [f"搜索「{keyword}」找到 {len(results)} 个结果:\n"]
            for item in results:
                name = item.get("vod_name", "未知")
                vod_id = item.get("vod_id", "")
                year = item.get("vod_year", "")
                remarks = item.get("vod_remarks", "")
                url = f"{SITE}/bangumi/{vod_id}.html"
                lines.append(f"  {name} ({year}) {remarks}")
                lines.append(f"    链接: {url}")
                lines.append("")

            self.frame.after(0, lambda: self._set_result("\n".join(lines)))
            self.frame.after(0, lambda: self.lbl_status.config(
                text=f"找到 {len(results)} 个结果"))
        except Exception as e:
            self.frame.after(0, lambda: self._set_result(f"搜索失败: {e}"))
            self.frame.after(0, lambda: self.lbl_status.config(text="搜索失败"))

    def _query_bili(self):
        year = self.year_var.get()
        self.lbl_status.config(text=f"查询B站 {year} 年番剧...")
        threading.Thread(target=self._do_bili_query, args=(year,), daemon=True).start()

    def _do_bili_query(self, year):
        try:
            y = int(year)
            url = "https://api.bilibili.com/pgc/season/index/result"
            params = {
                "st": 1, "type": 1, "season_type": 1,
                "area": 2, "year": f"[{y},{y+1})",
                "pagesize": 50, "page": 1
            }
            all_items = []
            page = 1
            while True:
                params["page"] = page
                resp = self.session.get(url, params=params, timeout=15)
                data = resp.json()
                items = data.get("data", {}).get("list", [])
                if not items: break
                all_items.extend(items)
                if len(items) < 50: break
                page += 1

            lines = [f"B站 {year} 年番剧 (共 {len(all_items)} 部):\n"]
            for item in all_items:
                title = item.get("title", "")
                rating = item.get("order", {}).get("", "")
                follow = item.get("order_type", "")
                lines.append(f"  {title}")

            self.frame.after(0, lambda: self._set_result("\n".join(lines)))
            self.frame.after(0, lambda: self.lbl_status.config(
                text=f"B站 {year} 年共 {len(all_items)} 部番剧"))
        except Exception as e:
            self.frame.after(0, lambda: self._set_result(f"查询失败: {e}"))
            self.frame.after(0, lambda: self.lbl_status.config(text="查询失败"))

    def _copy_link(self):
        try:
            text = self.result_text.get("sel.first", "sel.last")
        except:
            text = self.result_text.get("1.0", tk.END)
        self.frame.clipboard_clear()
        self.frame.clipboard_append(text)
        self.lbl_status.config(text="已复制到剪贴板")

    def _add_to_download(self):
        try:
            text = self.result_text.get("sel.first", "sel.last")
        except:
            text = self.result_text.get("1.0", tk.END)
        urls = re.findall(r'https?://dm\.xifanacg\.com/bangumi/\d+\.html', text)
        if urls:
            self.frame.clipboard_clear()
            self.frame.clipboard_append("\n".join(urls))
            self.lbl_status.config(text=f"已复制 {len(urls)} 个链接到剪贴板，请粘贴到稀饭下载页面")
        else:
            messagebox.showinfo("提示", "未找到可下载的链接，请先搜索动漫")
