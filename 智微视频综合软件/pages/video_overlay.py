#!/usr/bin/env python3
"""视频叠加模块 - 绿幕去除/画中画"""
import os, subprocess, json, tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

class VideoOverlayPage:
    def __init__(self, parent, colors):
        self.C = colors
        self.frame = tk.Frame(parent, bg=colors["bg"])
        self.main_video = tk.StringVar()
        self.overlay_videos = []
        self.output_path = tk.StringVar()
        self.green_color = tk.StringVar(value="0x00FF00")
        self.green_similarity = tk.DoubleVar(value=0.15)
        self.green_blend = tk.DoubleVar(value=0.05)
        self.overlay_scale = tk.DoubleVar(value=100)
        self.overlay_x = tk.StringVar(value="0")
        self.overlay_y = tk.StringVar(value="0")
        self.processing = False
        self._build_ui()

    def show(self): pass
    def hide(self): pass

    def _card(self, parent=None):
        p = parent or self.scroll_frame
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
        canvas = tk.Canvas(self.frame, bg=self.C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self.frame, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=self.C["bg"])
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 本体视频
        card = self._card()
        self._card_title(card, "🎬 本体视频（底层）")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(0, 10))
        tk.Entry(r, textvariable=self.main_video, font=("微软雅黑", 10), width=60).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn(r, "选择文件", self._sel_main).pack(side=tk.LEFT, padx=5)
        self._btn(r, "选择文件夹", self._sel_main_folder).pack(side=tk.LEFT)

        # 叠加视频
        card = self._card()
        self._card_title(card, "📎 叠加视频（从下到上排列）")
        btn_row = tk.Frame(card, bg=self.C["card"])
        btn_row.pack(fill=tk.X, padx=15, pady=(0, 5))
        self._btn(btn_row, "添加视频", self._add_overlay).pack(side=tk.LEFT, padx=(0, 5))
        self._btn(btn_row, "删除选中", self._del_overlay, "danger").pack(side=tk.LEFT, padx=(0, 5))
        self._btn(btn_row, "清空", self._clear_overlay, "secondary").pack(side=tk.LEFT)

        list_frame = tk.Frame(card, bg=self.C["card"])
        list_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        self.overlay_listbox = tk.Listbox(list_frame, height=5, font=("微软雅黑", 9))
        self.overlay_listbox.pack(fill=tk.X)

        # 绿幕设置
        card = self._card()
        self._card_title(card, "🟢 绿幕去除设置")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="绿色值:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.green_color, width=12, font=("Consolas", 10)).pack(side=tk.LEFT, padx=5)
        tk.Label(r, text="(如 0x00FF00, 0x00D900)", font=("微软雅黑", 9),
                 bg=self.C["card"], fg=self.C["text3"]).pack(side=tk.LEFT)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="相似度:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        tk.Scale(r, from_=0.01, to=0.5, resolution=0.01, orient=tk.HORIZONTAL,
                 variable=self.green_similarity, length=200).pack(side=tk.LEFT, padx=5)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(3, 10))
        tk.Label(r, text="混合度:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        tk.Scale(r, from_=0.01, to=0.3, resolution=0.01, orient=tk.HORIZONTAL,
                 variable=self.green_blend, length=200).pack(side=tk.LEFT, padx=5)

        # 叠加位置
        card = self._card()
        self._card_title(card, "📍 叠加位置与大小")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="X偏移:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.overlay_x, width=8, font=("Consolas", 10)).pack(side=tk.LEFT, padx=5)
        tk.Label(r, text="Y偏移:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT, padx=(15, 0))
        tk.Entry(r, textvariable=self.overlay_y, width=8, font=("Consolas", 10)).pack(side=tk.LEFT, padx=5)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(3, 10))
        tk.Label(r, text="缩放%:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        tk.Scale(r, from_=10, to=200, orient=tk.HORIZONTAL,
                 variable=self.overlay_scale, length=250).pack(side=tk.LEFT, padx=5)

        # 输出和控制
        card = self._card()
        self._card_title(card, "💾 输出与处理")
        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=3)
        tk.Label(r, text="输出:", font=("微软雅黑", 10), bg=self.C["card"]).pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.output_path, width=50, font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=5)
        self._btn(r, "浏览", self._sel_output, "secondary").pack(side=tk.LEFT)

        r = tk.Frame(card, bg=self.C["card"])
        r.pack(fill=tk.X, padx=15, pady=(3, 10))
        self._btn(r, "🚀 开始叠加", self._start, "success").pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_status = tk.Label(card, text="就绪", font=("微软雅黑", 10),
                                   bg=self.C["primary_light"], fg=self.C["primary"], padx=12, pady=6)
        self.lbl_status.pack(fill=tk.X, padx=15, pady=(0, 10))

        self.log_text = tk.Text(self.scroll_frame, height=6, font=("Consolas", 9), bg="#F8F9FA")
        self.log_text.pack(fill=tk.X, padx=15, pady=(0, 10))

    def _sel_main(self):
        p = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.avi *.mov *.mkv")])
        if p: self.main_video.set(p)

    def _sel_main_folder(self):
        p = filedialog.askdirectory()
        if p: self.main_video.set(p)

    def _add_overlay(self):
        files = filedialog.askopenfilenames(filetypes=[("视频", "*.mp4 *.avi *.mov *.mkv")])
        for f in files:
            if f not in [v for v, _ in self.overlay_videos]:
                self.overlay_videos.append((f, True))
                self.overlay_listbox.insert(tk.END, os.path.basename(f))

    def _del_overlay(self):
        sel = self.overlay_listbox.curselection()
        if sel:
            for i in reversed(sel):
                self.overlay_listbox.delete(i)
                self.overlay_videos.pop(i)

    def _clear_overlay(self):
        self.overlay_videos.clear()
        self.overlay_listbox.delete(0, tk.END)

    def _sel_output(self):
        p = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if p: self.output_path.set(p)

    def _log(self, msg):
        self.frame.after(0, lambda: (self.log_text.insert(tk.END, msg + "\n"), self.log_text.see(tk.END)))

    def _start(self):
        main = self.main_video.get()
        if not main:
            messagebox.showwarning("警告", "请选择本体视频"); return
        if not self.overlay_videos:
            messagebox.showwarning("警告", "请添加叠加视频"); return
        out = self.output_path.get()
        if not out:
            messagebox.showwarning("警告", "请选择输出路径"); return
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        self.processing = True
        self.frame.after(0, lambda: self.lbl_status.config(text="处理中..."))
        try:
            main = self.main_video.get()
            out = self.output_path.get()
            overlays = self.overlay_videos

            # 检测是否文件夹模式
            if os.path.isdir(main):
                self._process_folder(main, out)
            else:
                self._process_single(main, overlays, out)

            self.frame.after(0, lambda: self.lbl_status.config(text="✅ 完成!"))
            self._log("处理完成!")
        except Exception as e:
            self._log(f"错误: {e}")
            self.frame.after(0, lambda: self.lbl_status.config(text=f"❌ {e}"))
        self.processing = False

    def _process_single(self, main, overlays, out):
        # 获取主视频信息
        info = self._get_video_info(main)
        w = info.get('width', 1920) if info else 1920
        h = info.get('height', 1080) if info else 1080

        # 构建ffmpeg命令
        inputs = ['-i', main]
        for ov, _ in overlays:
            inputs.extend(['-i', ov])

        scale_pct = self.overlay_scale.get() / 100.0
        gx = self.green_color.get()
        sim = self.green_similarity.get()
        blend = self.green_blend.get()
        ox = self.overlay_x.get()
        oy = self.overlay_y.get()

        # 构建滤镜
        n = len(overlays)
        filter_parts = []
        for i in range(n):
            vf = f"[{i+1}:v]scale=iw*{scale_pct}:-1"
            if overlays[i][1]:  # 去绿幕
                vf += f",chromakey={gx}:{sim}:{blend}"
            vf += f"[ov{i}]"
            filter_parts.append(vf)

        # 叠加链
        if n == 1:
            filter_parts.append(f"[0:v][ov0]overlay={ox}:{oy}[out]")
        else:
            filter_parts.append(f"[0:v][ov0]overlay={ox}:{oy}[tmp0]")
            for i in range(1, n):
                inp = f"[tmp{i-1}]" if i > 1 else "[tmp0]"
                out_tag = "out" if i == n - 1 else f"tmp{i}"
                filter_parts.append(f"{inp}[ov{i}]overlay={ox}:{oy}[{out_tag}]")

        filter_complex = ";".join(filter_parts)
        cmd = ['ffmpeg', '-y'] + inputs + [
            '-filter_complex', filter_complex,
            '-map', '[out]', '-c:v', 'libx264', '-preset', 'fast',
            '-crf', '18', '-c:a', 'copy', '-shortest', out
        ]
        self._log(f"命令: {' '.join(cmd[:15])}...")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if r.returncode != 0:
            raise Exception(f"ffmpeg失败: {r.stderr[-300:]}")

    def _process_folder(self, folder, out_folder):
        exts = ('.mp4', '.avi', '.mov', '.mkv')
        files = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)])
        os.makedirs(out_folder, exist_ok=True)
        for i, f in enumerate(files):
            self._log(f"[{i+1}/{len(files)}] {os.path.basename(f)}")
            out = os.path.join(out_folder, os.path.basename(f))
            self._process_single(f, self.overlay_videos, out)

    def _get_video_info(self, path):
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-i', path]
            r = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
            data = json.loads(r.stdout)
            for s in data.get('streams', []):
                if s['codec_type'] == 'video':
                    return {'width': int(s.get('width', 1920)), 'height': int(s.get('height', 1080))}
        except: pass
        return None
