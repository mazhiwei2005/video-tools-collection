#!/usr/bin/env python3
"""Anime Folder Dedup Tool"""
import os, shutil, tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

C = {
    "bg": "#F4F5F7", "card": "#FFFFFF", "primary": "#00AEEC",
    "primary_dark": "#0095D9", "primary_light": "#E8F7FF",
    "success": "#00B578", "warning": "#FF9F18", "danger": "#FF3B30",
    "text": "#1D2129", "text2": "#6B7280", "text3": "#9CA3AF", "border": "#E5E7EB",
}

class AnimeDedupTool:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Anime Dedup Tool")
        self.root.geometry("800x680")
        self.root.configure(bg=C["bg"])
        self.root.resizable(True, True)
        self.matched = []
        self._build()
        self.root.mainloop()

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=C["primary"])
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="动漫文件夹去重工具", font=("微软雅黑", 16, "bold"),
                 bg=C["primary"], fg="white").pack(anchor="w", padx=20, pady=12)

        # Folder selection card
        card = tk.Frame(self.root, bg=C["card"])
        card.pack(fill=tk.X, padx=20, pady=8)
        inner = tk.Frame(card, bg=C["card"])
        inner.pack(padx=20, pady=16, fill=tk.X)

        # Source
        tk.Label(inner, text="来源文件夹", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        r1 = tk.Frame(inner, bg=C["card"])
        r1.pack(fill=tk.X, pady=4)
        self.src_var = tk.StringVar(value=r"G:\测试下载")
        tk.Entry(r1, textvariable=self.src_var, font=("微软雅黑", 10), bg="#F6F8FA",
                 relief="flat", highlightthickness=1, highlightcolor=C["primary"],
                 highlightbackground=C["border"]).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(r1, text="Browse", command=lambda: self._choose(self.src_var),
                  font=("微软雅黑", 10), bg="#E5E7EB", relief="flat", padx=10, pady=4,
                  cursor="hand2").pack(side=tk.LEFT, padx=8)

        # Dest
        tk.Label(inner, text="目标文件夹（用来比对）", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w", pady="10 0")
        r2 = tk.Frame(inner, bg=C["card"])
        r2.pack(fill=tk.X, pady=4)
        self.dst_var = tk.StringVar(value=r"G:\测试下载\按类型分类")
        tk.Entry(r2, textvariable=self.dst_var, font=("微软雅黑", 10), bg="#F6F8FA",
                 relief="flat", highlightthickness=1, highlightcolor=C["primary"],
                 highlightbackground=C["border"]).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(r2, text="Browse", command=lambda: self._choose(self.dst_var),
                  font=("微软雅黑", 10), bg="#E5E7EB", relief="flat", padx=10, pady=4,
                  cursor="hand2").pack(side=tk.LEFT, padx=8)

        # Move to
        tk.Label(inner, text="重复项移动到", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w", pady="10 0")
        r3 = tk.Frame(inner, bg=C["card"])
        r3.pack(fill=tk.X, pady=4)
        self.move_var = tk.StringVar(value=r"G:\测试下载\重复动漫")
        tk.Entry(r3, textvariable=self.move_var, font=("微软雅黑", 10), bg="#F6F8FA",
                 relief="flat", highlightthickness=1, highlightcolor=C["primary"],
                 highlightbackground=C["border"]).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(r3, text="Browse", command=lambda: self._choose(self.move_var),
                  font=("微软雅黑", 10), bg="#E5E7EB", relief="flat", padx=10, pady=4,
                  cursor="hand2").pack(side=tk.LEFT, padx=8)

        # Buttons
        bf = tk.Frame(self.root, bg=C["bg"])
        bf.pack(fill=tk.X, padx=20, pady=4)
        tk.Button(bf, text="扫描重复", command=self._scan,
                  font=("微软雅黑", 12, "bold"), bg=C["primary"], fg="white",
                  relief="flat", padx=20, pady=8, cursor="hand2").pack(side=tk.LEFT, padx="0 10")
        tk.Button(bf, text="移动重复项", command=self._move,
                  font=("微软雅黑", 12, "bold"), bg=C["warning"], fg="white",
                  relief="flat", padx=20, pady=8, cursor="hand2").pack(side=tk.LEFT, padx="0 10")
        tk.Button(bf, text="清空", command=self._clear,
                  font=("微软雅黑", 11), bg="#E5E7EB", relief="flat", padx=14, pady=8,
                  cursor="hand2").pack(side=tk.LEFT)
        self.lbl_count = tk.Label(bf, text="", font=("微软雅黑", 11), bg=C["bg"], fg=C["primary"])
        self.lbl_count.pack(side=tk.RIGHT)

        # Result list
        card2 = tk.Frame(self.root, bg=C["card"])
        card2.pack(fill=tk.BOTH, expand=True, padx=20, pady=8)
        inner2 = tk.Frame(card2, bg=C["card"])
        inner2.pack(fill=tk.BOTH, expand=True, padx=20, pady=12)

        tk.Label(inner2, text="重复文件夹列表", font=("微软雅黑", 12, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")

        style = ttk.Style()
        style.configure("DD.Treeview", rowheight=30, font=("微软雅黑", 10))
        style.configure("DD.Treeview.Heading", font=("微软雅黑", 10, "bold"))

        cols = ("序号", "文件夹名称", "来源路径", "目标路径", "状态")
        self.tree = ttk.Treeview(inner2, columns=cols, show="headings", style="DD.Treeview", height=10)
        for c, w in zip(cols, [50, 200, 250, 250, 80]):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center" if c != "文件夹名称" else "w")
        sb = ttk.Scrollbar(inner2, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True, pady="8 0")

        # Progress + Status
        bot = tk.Frame(self.root, bg=C["bg"])
        bot.pack(fill=tk.X, padx=20, pady="0 20")
        self.progress = ttk.Progressbar(bot, mode="determinate", length=400)
        self.progress.pack(fill=tk.X, pady="0 6")
        self.lbl_status = tk.Label(bot, text="就绪 - 选择文件夹后点击扫描",
                                   font=("微软雅黑", 10), bg=C["primary_light"],
                                   fg=C["primary"], padx=12, pady=6)
        self.lbl_status.pack(fill=tk.X)

    def _choose(self, var):
        p = filedialog.askdirectory()
        if p: var.set(p)

    def _set_status(self, text):
        self.lbl_status.config(text=text)
        self.root.update_idletasks()

    def _scan(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        if not os.path.isdir(src):
            messagebox.showerror("错误", f"Source not found:\n{src}"); return
        if not os.path.isdir(dst):
            messagebox.showerror("错误", f"Dest not found:\n{dst}"); return

        self._set_status("扫描中...")
        self.tree.delete(*self.tree.get_children())
        self.matched = []

        src_subs = {}
        for name in os.listdir(src):
            p = os.path.join(src, name)
            if os.path.isdir(p):
                src_subs[name] = p

        dst_subs = {}
        for root_dir, dirs, files in os.walk(dst):
            for name in dirs:
                if name not in dst_subs:
                    dst_subs[name] = os.path.join(root_dir, name)

        for name, src_path in src_subs.items():
            if name in dst_subs:
                self.matched.append((name, src_path, dst_subs[name]))

        for i, (name, sp, dp) in enumerate(self.matched):
            self.tree.insert("", tk.END, values=(i + 1, name, sp, dp, "待处理"))

        n = len(self.matched)
        t = len(src_subs)
        self.lbl_count.config(text=f"{t} folders, {n} duplicates")
        self._set_status(f"Scan done - {t} folders, {n} duplicates")

    def _move(self):
        if not self.matched:
            messagebox.showinfo("提示", "没有重复项，请先扫描"); return
        d = self.move_var.get().strip()
        if not d:
            messagebox.showerror("错误", "请选择移动目标文件夹"); return
        if not messagebox.askyesno("确认", f"将 {len(self.matched)} 个重复文件夹移动到:\n{d}\n\n确定继续？"):
            return
        threading.Thread(target=self._do_move, args=(d,), daemon=True).start()

    def _do_move(self, move_dir):
        os.makedirs(move_dir, exist_ok=True)
        ok = fail = 0
        total = len(self.matched)
        for i, (name, src_path, _) in enumerate(self.matched):
            self.root.after(0, lambda v=int(i / total * 100): self.progress.configure(value=v))
            self.root.after(0, lambda n=name: self._set_status(f"移动中: {n}"))
            items = self.tree.get_children()
            item = items[i] if i < len(items) else None
            if item:
                self.root.after(0, lambda it=item: self.tree.set(it, "状态", "移动中..."))
            try:
                dst_path = os.path.join(move_dir, name)
                if os.path.exists(dst_path):
                    k = 1
                    while os.path.exists(f"{dst_path}_{k}"):
                        k += 1
                    dst_path = f"{dst_path}_{k}"
                shutil.move(src_path, dst_path)
                ok += 1
                if item:
                    self.root.after(0, lambda it=item: self.tree.set(it, "状态", "Done"))
            except Exception as e:
                fail += 1
                if item:
                    self.root.after(0, lambda it=item, err=str(e)[:20]: self.tree.set(it, "状态", f"Fail:{err}"))

        self.root.after(0, lambda: self.progress.configure(value=100))
        self._set_status(f"完成 - 成功 {ok} 个，失败 {fail} 个")
        self.root.after(0, lambda: messagebox.showinfo("Done", f"成功: {ok}\n失败: {fail}"))

    def _clear(self):
        self.tree.delete(*self.tree.get_children())
        self.matched = []
        self.lbl_count.config(text="")
        self.progress.configure(value=0)
        self._set_status("就绪")

if __name__ == "__main__":
    AnimeDedupTool()
