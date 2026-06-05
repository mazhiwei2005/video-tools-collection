#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站视频自动上传工具 - API直传版
使用biliup库直接调用B站上传接口
无需浏览器，稳定可靠
"""
import os, sys, json, time, glob, threading, pathlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

C = {
    "bg": "#F6F8FA", "card": "#FFFFFF", "primary": "#00A1D6",
    "text": "#222", "text2": "#666", "text3": "#999",
    "success": "#67C23A", "danger": "#F56C6C",
}

DEFAULT_DESC = "本账号未开通任何激励，大会员每月可领5B币券，想支持up的话可以用这个券给up发电哦感谢大家( ´･ᴗ･ )比心\nhttps://account.bilibili.com/account/big/myPackage"
DEFAULT_TAGS = ["动漫", "番剧", "新番", "动画", "4K", "无删减", "热血"]
DEFAULT_TID = 24
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_upload_config.json")


class UploadItem:
    def __init__(self, folder, files):
        self.folder = folder
        self.files = files
        self.title = os.path.basename(folder)
        self.desc = DEFAULT_DESC
        self.tags = DEFAULT_TAGS.copy()
        self.tid = DEFAULT_TID
        self.part_titles = [os.path.splitext(os.path.basename(f))[0] for f in files]
        self.status = "等待"


class BiliAPIUploader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("B站投稿工具 (API直传)")
        self.root.geometry("850x750")
        self.root.configure(bg=C["bg"])

        self.uploads = []
        self._uploading = False
        self._cancel = False
        self._last_folder = ""
        self._cookie_data = None  # {SESSDATA, bili_jct, DedeUserID, ...}

        self._load_config()
        self._build_ui()

    def _load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self._last_folder = cfg.get("last_folder", "")
                self._cookie_data = cfg.get("cookie_data")
        except:
            pass

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "last_folder": self._last_folder,
                    "cookie_data": self._cookie_data,
                }, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _build_ui(self):
        header = tk.Frame(self.root, bg=C["primary"], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="B站投稿工具 (API直传)", font=("微软雅黑", 14, "bold"),
                 bg=C["primary"], fg="white").pack(side=tk.LEFT, padx=16)
        self.lbl_status = tk.Label(header, text="准备就绪", font=("微软雅黑", 10),
                                   bg=C["primary"], fg="#B3E5FC")
        self.lbl_status.pack(side=tk.RIGHT, padx=16)

        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # 1. 登录
        f1 = tk.LabelFrame(main, text="1. 登录B站", font=("微软雅黑", 10, "bold"),
                           bg=C["card"], fg=C["primary"], padx=12, pady=8)
        f1.pack(fill=tk.X, pady=(0, 8))
        row1 = tk.Frame(f1, bg=C["card"])
        row1.pack(fill=tk.X)
        self.btn_cookie = tk.Button(row1, text="导入Cookie文件", font=("微软雅黑", 10, "bold"),
                                     bg=C["primary"], fg="white", relief=tk.FLAT, padx=16, pady=6,
                                     command=self._import_cookie)
        self.btn_cookie.pack(side=tk.LEFT)
        tk.Label(row1, text="需要SESSDATA、bili_jct、DedeUserID",
                 font=("微软雅黑", 9), bg=C["card"], fg=C["text2"]).pack(side=tk.LEFT, padx=12)
        self.lbl_login = tk.Label(row1, text="未登录" if not self._cookie_data else "已登录",
                                   font=("微软雅黑", 9), bg=C["card"],
                                   fg=C["success"] if self._cookie_data else C["danger"])
        self.lbl_login.pack(side=tk.RIGHT, padx=12)

        # 2. 投稿列表
        f2 = tk.LabelFrame(main, text="2. 投稿列表（每个文件夹=一个独立投稿）",
                           font=("微软雅黑", 10, "bold"), bg=C["card"], fg=C["primary"], padx=12, pady=8)
        f2.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        btn_row = tk.Frame(f2, bg=C["card"])
        btn_row.pack(fill=tk.X, pady=(0, 6))
        tk.Button(btn_row, text="导入文件夹(自动分P)", font=("微软雅黑", 9, "bold"),
                  bg="#409EFF", fg="white", relief=tk.FLAT, padx=12,
                  command=self._add_folder).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_row, text="删除选中", font=("微软雅黑", 9),
                  bg=C["danger"], fg="white", relief=tk.FLAT, padx=10,
                  command=self._remove_upload).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_row, text="清空", font=("微软雅黑", 9),
                  bg="#909399", fg="white", relief=tk.FLAT, padx=10,
                  command=self._clear_all).pack(side=tk.LEFT)

        tree_frame = tk.Frame(f2, bg=C["card"])
        tree_frame.pack(fill=tk.BOTH, expand=True)
        cols = ("info", "title", "status")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings", height=10)
        self.tree.heading("#0", text="文件")
        self.tree.heading("info", text="信息")
        self.tree.heading("title", text="标题")
        self.tree.heading("status", text="状态")
        self.tree.column("#0", width=200)
        self.tree.column("info", width=80)
        self.tree.column("title", width=280)
        self.tree.column("status", width=80, anchor=tk.CENTER)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda e: self._edit_item())

        edit_row = tk.Frame(f2, bg=C["card"])
        edit_row.pack(fill=tk.X, pady=(6, 0))
        tk.Button(edit_row, text="编辑标题", font=("微软雅黑", 9),
                  bg="#909399", fg="white", relief=tk.FLAT, padx=10,
                  command=self._edit_item).pack(side=tk.LEFT, padx=(0, 6))

        # 3. 设置
        f3 = tk.LabelFrame(main, text="3. 默认设置",
                           font=("微软雅黑", 10, "bold"), bg=C["card"], fg=C["primary"], padx=12, pady=8)
        f3.pack(fill=tk.X, pady=(0, 8))
        row = tk.Frame(f3, bg=C["card"])
        row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row, text="分区:", font=("微软雅黑", 9), bg=C["card"]).pack(side=tk.LEFT)
        self.tid_var = tk.StringVar(value=str(DEFAULT_TID))
        ttk.Combobox(row, textvariable=self.tid_var,
                     values=["24 - 动画综合", "25 - MAD/AMV", "47 - MMD/3D"],
                     width=16, state="readonly").pack(side=tk.LEFT, padx=(6, 16))
        tk.Label(row, text="标签:", font=("微软雅黑", 9), bg=C["card"]).pack(side=tk.LEFT)
        self.tags_var = tk.StringVar(value=",".join(DEFAULT_TAGS))
        tk.Entry(row, textvariable=self.tags_var, width=40, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=(6, 0))
        row2 = tk.Frame(f3, bg=C["card"])
        row2.pack(fill=tk.X)
        tk.Label(row2, text="简介:", font=("微软雅黑", 9), bg=C["card"]).pack(side=tk.LEFT, anchor=tk.N)
        self.desc_text = tk.Text(row2, height=2, width=60, font=("微软雅黑", 9))
        self.desc_text.insert(tk.END, DEFAULT_DESC)
        self.desc_text.pack(side=tk.LEFT, padx=(6, 0))

        # 4. 上传
        f4 = tk.Frame(main, bg=C["card"], padx=12, pady=8)
        f4.pack(fill=tk.X, pady=(0, 8))
        self.btn_upload = tk.Button(f4, text="开始上传全部",
                                     font=("微软雅黑", 11, "bold"), bg=C["primary"], fg="white",
                                     relief=tk.FLAT, padx=24, pady=8, command=self._start_upload)
        self.btn_upload.pack(side=tk.LEFT)
        self.btn_cancel = tk.Button(f4, text="取消", font=("微软雅黑", 10),
                                     bg=C["danger"], fg="white", relief=tk.FLAT, padx=16, pady=8,
                                     command=self._cancel_upload, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=(12, 0))

        self.log_text = tk.Text(main, height=4, font=("Consolas", 9), bg="#1E1E1E", fg="#D4D4D4",
                                insertbackground="white", state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _log(self, msg):
        def _w():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _w)

    def _refresh_tree(self):
        def _w():
            self.tree.delete(*self.tree.get_children())
            for i, upload in enumerate(self.uploads):
                n = len(upload.files)
                parent = self.tree.insert("", tk.END,
                    text=f"投稿{i+1}: {upload.title}",
                    values=(f"{n}P", upload.title, upload.status))
                for j, (fname, ptitle) in enumerate(zip(upload.files, upload.part_titles)):
                    self.tree.insert(parent, tk.END, text=f"P{j+1}: {os.path.basename(fname)}",
                                     values=("", ptitle, ""))
        self.root.after(0, _w)

    def _set_status(self, idx, status):
        self.uploads[idx].status = status
        self._refresh_tree()

    # ═══════ Login ═══════
    def _import_cookie(self):
        """导入Cookie JSON文件"""
        path = filedialog.askopenfilename(
            title="选择Cookie文件",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 支持多种格式
            if "cookie_info" in data:
                # biliup格式: {cookie_info: {cookies: [...]}, token_info: {...}}
                cookies = {}
                for c in data["cookie_info"]["cookies"]:
                    cookies[c["name"]] = c["value"]
                if "token_info" in data and "access_token" in data["token_info"]:
                    cookies["access_token"] = data["token_info"]["access_token"]
                self._cookie_data = cookies
            elif "SESSDATA" in data:
                # 简单格式: {SESSDATA: "...", bili_jct: "...", ...}
                self._cookie_data = data
            else:
                # 尝试从cookies数组提取
                for key in ["SESSDATA", "bili_jct", "DedeUserID"]:
                    if key in data:
                        self._cookie_data = data
                        break

            if not self._cookie_data or "SESSDATA" not in self._cookie_data:
                messagebox.showerror("错误", "Cookie文件格式不对，需要包含SESSDATA")
                self._cookie_data = None
                return

            self._save_config()
            self.lbl_login.config(text="已登录", fg=C["success"])
            self._log(f"Cookie已导入 (SESSDATA={self._cookie_data['SESSDATA'][:15]}...)")

        except Exception as e:
            messagebox.showerror("错误", f"导入Cookie失败: {e}")

    # ═══════ Add Folder ═══════
    def _add_folder(self):
        d = filedialog.askdirectory(title="选择视频文件夹",
                                     initialdir=self._last_folder if self._last_folder else None)
        if not d:
            return
        files = sorted(
            glob.glob(os.path.join(d, "*.mp4")) + glob.glob(os.path.join(d, "*.mkv")) +
            glob.glob(os.path.join(d, "*.flv")) + glob.glob(os.path.join(d, "*.avi")))
        if not files:
            messagebox.showwarning("提示", "没有找到视频文件")
            return
        self._last_folder = d
        self._save_config()
        upload = UploadItem(d, files)
        upload.tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        upload.tid = int(self.tid_var.get().split(" - ")[0])
        upload.desc = self.desc_text.get("1.0", tk.END).strip()
        self.uploads.append(upload)
        self._refresh_tree()
        self._log(f"已添加: {upload.title} ({len(files)}P)")

    def _remove_upload(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item in sel:
            parent = self.tree.parent(item)
            if parent:
                item = parent
            idx = self.tree.index(item)
            if idx < len(self.uploads):
                self.uploads.pop(idx)
        self._refresh_tree()

    def _clear_all(self):
        self.uploads.clear()
        self._refresh_tree()

    def _edit_item(self):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        parent = self.tree.parent(item)
        if parent:
            upload_idx = self.tree.index(parent)
            part_idx = self.tree.index(item)
            upload = self.uploads[upload_idx]
            old = upload.part_titles[part_idx]
            win = tk.Toplevel(self.root)
            win.title("编辑P标题")
            win.geometry("400x100")
            win.configure(bg=C["card"])
            tk.Label(win, text="P标题:", font=("微软雅黑", 10), bg=C["card"]).pack(padx=16, pady=(16, 8))
            var = tk.StringVar(value=old)
            tk.Entry(win, textvariable=var, width=40, font=("微软雅黑", 10)).pack(padx=16)
            def save():
                upload.part_titles[part_idx] = var.get().strip()
                self._refresh_tree()
                win.destroy()
            tk.Button(win, text="保存", font=("微软雅黑", 9, "bold"), bg=C["primary"], fg="white",
                      relief=tk.FLAT, padx=16, command=save).pack(pady=8)
        else:
            idx = self.tree.index(item)
            upload = self.uploads[idx]
            win = tk.Toplevel(self.root)
            win.title("编辑投稿标题")
            win.geometry("400x100")
            win.configure(bg=C["card"])
            tk.Label(win, text="投稿标题:", font=("微软雅黑", 10), bg=C["card"]).pack(padx=16, pady=(16, 8))
            var = tk.StringVar(value=upload.title)
            tk.Entry(win, textvariable=var, width=40, font=("微软雅黑", 10)).pack(padx=16)
            def save():
                upload.title = var.get().strip()
                self._refresh_tree()
                win.destroy()
            tk.Button(win, text="保存", font=("微软雅黑", 9, "bold"), bg=C["primary"], fg="white",
                      relief=tk.FLAT, padx=16, command=save).pack(pady=8)

    # ═══════ Upload ═══════
    def _start_upload(self):
        if not self._cookie_data:
            messagebox.showwarning("提示", "请先导入Cookie！")
            return
        if not self.uploads:
            messagebox.showwarning("提示", "投稿列表为空！")
            return
        self._uploading = True
        self._cancel = False
        self.btn_upload.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        threading.Thread(target=self._upload_all, daemon=True).start()

    def _cancel_upload(self):
        self._cancel = True
        self._log("正在取消...")

    def _upload_all(self):
        total = len(self.uploads)
        self._log(f"开始上传，共 {total} 个投稿")

        for u_idx, upload in enumerate(self.uploads):
            if self._cancel:
                break
            self._log(f"\n{'='*40}")
            self._log(f"投稿 {u_idx+1}/{total}: {upload.title} ({len(upload.files)}P)")
            self._set_status(u_idx, "上传中")

            try:
                self._upload_one(upload, u_idx)
                self._set_status(u_idx, "已完成")
                self._log(f"投稿 {u_idx+1} 完成！")
            except Exception as e:
                self._set_status(u_idx, "失败")
                self._log(f"投稿 {u_idx+1} 失败: {str(e)[:300]}")

            time.sleep(3)

        self.root.after(0, lambda: (
            self.btn_upload.config(state=tk.NORMAL),
            self.btn_cancel.config(state=tk.DISABLED),
            self.lbl_status.config(text="全部完成"),
        ))
        self._uploading = False
        self._log("全部完成！")

    def _upload_one(self, upload, u_idx):
        """用biliup库上传一个投稿（含分P）"""
        from biliup.plugins.bili_webup import BiliBili, Data

        # 创建Data对象
        video = Data()
        video.copyright = 1  # 1=自制 2=转载
        video.title = upload.title[:80]
        video.desc = upload.desc
        video.tid = upload.tid
        video.set_tag(upload.tags)

        with BiliBili(video) as bili:
            # 登录
            bili.login_by_cookies(self._cookie_data)

            # 逐个上传分P
            for p_idx, filepath in enumerate(upload.files):
                if self._cancel:
                    return

                self._log(f"  P{p_idx+1}/{len(upload.files)}: {os.path.basename(filepath)}")

                # 上传文件
                video_part = bili.upload_file(filepath, lines='AUTO', tasks=3)
                video_part['title'] = upload.part_titles[p_idx][:80]
                video.append(video_part)

                self._log(f"    P{p_idx+1} 上传成功")

            # 提交稿件
            self._log(f"  提交稿件...")
            ret = bili.submit()

            if ret.get('code') == 0:
                self._log(f"  投稿成功！")
            else:
                self._log(f"  投稿失败: {ret.get('message', '未知错误')}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BiliAPIUploader()
    app.run()
