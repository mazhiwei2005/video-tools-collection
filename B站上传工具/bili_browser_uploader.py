#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站视频自动上传工具 - Selenium版
文件夹导入 → 自动分P上传
"""
import os, sys, json, time, glob, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

C = {
    "bg": "#F6F8FA", "card": "#FFFFFF", "primary": "#00A1D6",
    "text": "#222", "text2": "#666", "text3": "#999",
    "success": "#67C23A", "danger": "#F56C6C",
}

DEFAULT_DESC = "本账号未开通任何激励，大会员每月可领5B币券，想支持up的话可以用这个券给up发电哦感谢大家( ´･ᴗ･ )比心\nhttps://account.bilibili.com/account/big/myPackage"
DEFAULT_TAGS = "动漫,番剧,新番,动画,4K,无删减,热血"
DEFAULT_TID = "24"
DEBUG_PORT = 9222
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload_config.json")


class UploadItem:
    def __init__(self, folder, files):
        self.folder = folder
        self.files = files
        self.title = os.path.basename(folder)
        self.desc = DEFAULT_DESC
        self.tags = DEFAULT_TAGS
        self.tid = DEFAULT_TID
        self.part_titles = [os.path.splitext(os.path.basename(f))[0] for f in files]
        self.status = "等待"


class BiliBrowserUploader:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("B站分P上传工具")
        self.root.geometry("850x750")
        self.root.configure(bg=C["bg"])

        self.driver = None
        self.uploads = []
        self._uploading = False
        self._cancel = False
        self._last_folder = ""

        self._load_config()
        self._build_ui()

    def _load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self._last_folder = json.load(f).get("last_folder", "")
        except:
            pass

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"last_folder": self._last_folder}, f, ensure_ascii=False)
        except:
            pass

    def _build_ui(self):
        header = tk.Frame(self.root, bg=C["primary"], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="B站分P上传工具", font=("微软雅黑", 14, "bold"),
                 bg=C["primary"], fg="white").pack(side=tk.LEFT, padx=16)
        self.lbl_status = tk.Label(header, text="准备就绪", font=("微软雅黑", 10),
                                   bg=C["primary"], fg="#B3E5FC")
        self.lbl_status.pack(side=tk.RIGHT, padx=16)

        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        f1 = tk.LabelFrame(main, text="1. 连接浏览器", font=("微软雅黑", 10, "bold"),
                           bg=C["card"], fg=C["primary"], padx=12, pady=8)
        f1.pack(fill=tk.X, pady=(0, 8))
        row1 = tk.Frame(f1, bg=C["card"])
        row1.pack(fill=tk.X)
        self.btn_browser = tk.Button(row1, text="打开B站上传页",
                                      font=("微软雅黑", 10, "bold"), bg=C["primary"], fg="white",
                                      relief=tk.FLAT, padx=16, pady=6, command=self._open_browser)
        self.btn_browser.pack(side=tk.LEFT)
        tk.Label(row1, text="会关闭现有Edge，请先保存工作",
                 font=("微软雅黑", 9), bg=C["card"], fg=C["danger"]).pack(side=tk.LEFT, padx=12)

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

        f3 = tk.LabelFrame(main, text="3. 默认设置",
                           font=("微软雅黑", 10, "bold"), bg=C["card"], fg=C["primary"], padx=12, pady=8)
        f3.pack(fill=tk.X, pady=(0, 8))
        row = tk.Frame(f3, bg=C["card"])
        row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row, text="分区:", font=("微软雅黑", 9), bg=C["card"]).pack(side=tk.LEFT)
        self.tid_var = tk.StringVar(value=DEFAULT_TID)
        ttk.Combobox(row, textvariable=self.tid_var,
                     values=["24 - 动画综合", "25 - MAD/AMV", "47 - MMD/3D"],
                     width=16, state="readonly").pack(side=tk.LEFT, padx=(6, 16))
        tk.Label(row, text="标签:", font=("微软雅黑", 9), bg=C["card"]).pack(side=tk.LEFT)
        self.tags_var = tk.StringVar(value=DEFAULT_TAGS)
        tk.Entry(row, textvariable=self.tags_var, width=40, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=(6, 0))
        row2 = tk.Frame(f3, bg=C["card"])
        row2.pack(fill=tk.X)
        tk.Label(row2, text="简介:", font=("微软雅黑", 9), bg=C["card"]).pack(side=tk.LEFT, anchor=tk.N)
        self.desc_text = tk.Text(row2, height=2, width=60, font=("微软雅黑", 9))
        self.desc_text.insert(tk.END, DEFAULT_DESC)
        self.desc_text.pack(side=tk.LEFT, padx=(6, 0))

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

    # ═══════ Browser ═══════
    def _open_browser(self):
        if self.driver:
            self._log("浏览器已连接")
            return
        self._log("正在准备Edge浏览器...")
        self.btn_browser.config(state=tk.DISABLED)
        threading.Thread(target=self._init_browser, daemon=True).start()

    def _init_browser(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.edge.options import Options
            import subprocess

            edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

            # 先尝试连接已有的Edge
            self._log("正在尝试连接Edge...")
            options = Options()
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{DEBUG_PORT}")

            try:
                self.driver = webdriver.Edge(options=options)
                self._log("已连接到Edge")
            except:
                # 没有调试模式的Edge，提示用户手动启动
                self._log("无法连接Edge！请手动启动调试模式:")
                self._log(f'  关闭所有Edge后运行: msedge.exe --remote-debugging-port={DEBUG_PORT}')
                self.root.after(0, lambda: self.btn_browser.config(state=tk.NORMAL))
                return

            # 强制切换到最后一个标签页
            self.driver.switch_to.window(self.driver.window_handles[-1])

            # 用window.open新开标签页（不要用driver.get）
            self.driver.execute_script('window.open("https://member.bilibili.com/platform/upload/video/frame");')
            time.sleep(3)
            self.driver.switch_to.window(self.driver.window_handles[-1])

            self.root.after(0, lambda: (
                self._log("浏览器已连接！请在新标签页中登录B站"),
                self.lbl_status.config(text="已连接"),
                self.btn_browser.config(state=tk.NORMAL)
            ))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"连接失败: {e}"))
            self.root.after(0, lambda: self.btn_browser.config(state=tk.NORMAL))

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
        upload.tags = self.tags_var.get().strip()
        upload.tid = self.tid_var.get().split(" - ")[0]
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
        if not self.driver:
            messagebox.showwarning("提示", "请先连接浏览器！")
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
                self._log(f"投稿 {u_idx+1} 失败: {str(e)[:200]}")

            time.sleep(3)

        self.root.after(0, lambda: (
            self.btn_upload.config(state=tk.NORMAL),
            self.btn_cancel.config(state=tk.DISABLED),
            self.lbl_status.config(text="全部完成"),
        ))
        self._uploading = False
        self._log("全部完成！")

    def _upload_one(self, upload, u_idx):
        """Selenium上传一个投稿"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        driver = self.driver

        # 检查窗口是否还活着
        if len(driver.window_handles) == 0:
            self._log("  浏览器窗口已关闭")
            return

        # 打开上传页
        driver.execute_script('window.open("https://member.bilibili.com/platform/upload/video/frame");')
        time.sleep(3)
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(3)

        # =========================
        # P1 上传
        # =========================
        fp = os.path.abspath(upload.files[0])
        self._log(f"  P1/{len(upload.files)}: {os.path.basename(upload.files[0])}")

        upload_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
        upload_input.send_keys(fp)
        self._log(f"    P1 上传成功")
        time.sleep(10)

        # =========================
        # 后续P
        # =========================
        for p_idx in range(1, len(upload.files)):
            if self._cancel:
                return

            fp = os.path.abspath(upload.files[p_idx])
            self._log(f"  P{p_idx+1}/{len(upload.files)}: {os.path.basename(upload.files[p_idx])}")

            # =========================
            # 找添加分P按钮
            # =========================
            try:
                add_btn = driver.find_element(By.XPATH, '//button[contains(., "添加分P")]')
                # 滚动到底部
                driver.execute_script("arguments[0].scrollIntoView(true);", add_btn)
                time.sleep(1)
                # JS点击
                driver.execute_script("arguments[0].click();", add_btn)
                self._log(f"    已点击添加分P")
            except Exception as e:
                self._log(f"    添加分P失败: {e}")
                continue

            # 等待DOM刷新
            time.sleep(3)
            # 滚动到底部
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # =========================
            # 获取真正有效的上传框
            # =========================
            all_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            valid_inputs = []
            for inp in all_inputs:
                try:
                    if inp.is_displayed() and inp.is_enabled():
                        valid_inputs.append(inp)
                except:
                    pass
            self._log(f"    有效上传框: {len(valid_inputs)} 个")

            if not valid_inputs:
                self._log(f"    未找到有效上传框")
                continue

            # 拿最后一个有效上传框
            target_input = valid_inputs[-1]
            try:
                # 滚动到input
                driver.execute_script("arguments[0].scrollIntoView(true);", target_input)
                time.sleep(1)
                # 上传
                target_input.send_keys(fp)
                self._log(f"    P{p_idx+1} 上传成功")
            except Exception as e:
                self._log(f"    上传失败: {e}")
                continue

            # 等待上传初始化
            time.sleep(10)

        # =========================
        # 等待上传完成
        # =========================
        self._log(f"  等待上传完成...")
        time.sleep(15)

        # =========================
        # 填写表单
        # =========================
        self._log(f"  填写投稿信息...")
        self._fill_form(upload)
        self._log(f"  请在浏览器中确认并提交")

    def _fill_form(self, upload):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        driver = self.driver

        # 标题
        try:
            el = driver.find_element(By.CSS_SELECTOR,
                "input[placeholder*='标题'], input[placeholder*='title'], .input-val, .title-input input")
            el.clear()
            el.send_keys(upload.title[:80])
            self._log("    标题已填写")
        except:
            self._log("    未找到标题输入框")

        # 标签
        try:
            el = driver.find_element(By.CSS_SELECTOR,
                "input[placeholder*='标签'], input[placeholder*='tag'], .tag-container input")
            for tag in upload.tags.split(",")[:10]:
                tag = tag.strip()
                if tag:
                    el.send_keys(tag)
                    el.send_keys(Keys.ENTER)
                    time.sleep(0.3)
            self._log("    标签已填写")
        except:
            self._log("    未找到标签输入框")

        # 简介
        try:
            el = driver.find_element(By.CSS_SELECTOR,
                "textarea[placeholder*='简介'], textarea[placeholder*='desc'], .desc-container textarea, textarea")
            el.clear()
            el.send_keys(upload.desc)
            self._log("    简介已填写")
        except:
            self._log("    未找到简介输入框")

    def run(self):
        self.root.mainloop()
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass


if __name__ == "__main__":
    app = BiliBrowserUploader()
    app.run()
