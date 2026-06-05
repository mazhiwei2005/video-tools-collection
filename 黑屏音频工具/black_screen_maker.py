#!/usr/bin/env python3
"""
黑屏音频视频生成器
功能：将音频文件包装成B站可上传的MP4视频
背景：纯黑屏 / 自定义图片 / 视频循环
"""
import os, sys, subprocess, json, time, threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ═══ 颜色常量（B站风格） ═══
C = {
    "bg": "#F1F2F3", "card": "#FFFFFF", "primary": "#00AEEC",
    "primary_dark": "#0091D4", "primary_light": "#E8F4FD",
    "success": "#00B578", "warning": "#FF9F18", "danger": "#FF3B30",
    "text": "#1D2129", "text2": "#6B7280", "text3": "#9CA3AF",
    "border": "#E5E7EB",
}


class BlackScreenMaker:
    """黑屏音频视频生成器"""

    def __init__(self, root):
        self.root = root
        self.root.title("🎬 黑屏音频视频生成器")
        self.root.geometry("780x680")
        self.root.configure(bg=C["bg"])
        self.root.resizable(True, True)

        self.ffmpeg = self._find_ffmpeg()
        self._processing = False
        self._cancel = False

        # 数据
        self.audio_files = []
        self.bg_mode = tk.StringVar(value="black")  # black / image / video
        self.bg_path = None
        self.resolution = tk.StringVar(value="1280x720")
        self.output_dir = tk.StringVar(value="")
        self.bitrate = tk.StringVar(value="128")  # 音频码率

        self._build()
        self._load_config()

    def _find_ffmpeg(self):
        for p in ["ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe"]:
            try:
                subprocess.run([p, "-version"], capture_output=True, timeout=5)
                return p
            except:
                continue
        return "ffmpeg"

    # ═══════════════════════════════════════
    #  UI构建
    # ═══════════════════════════════════════
    def _build(self):
        # 顶部标题
        header = tk.Frame(self.root, bg=C["primary"], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🎬 黑屏音频视频生成器",
                 font=("微软雅黑", 16, "bold"), bg=C["primary"], fg="white").pack(expand=True)

        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        # ── 左侧：设置区 ──
        left = tk.Frame(main, bg=C["bg"], width=380)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 8))

        # 1. 音频文件
        self._card_audio(left)

        # 2. 背景设置
        self._card_bg(left)

        # 3. 输出设置
        self._card_output(left)

        # ── 右侧：日志 ──
        right = tk.Frame(main, bg=C["bg"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_card = tk.Frame(right, bg=C["card"], relief="flat", bd=0)
        log_card.pack(fill=tk.BOTH, expand=True)
        tk.Label(log_card, text="📋 日志", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"], anchor="w").pack(fill=tk.X, padx=12, pady=(8, 4))

        self.log_text = tk.Text(log_card, font=("Consolas", 9), bg="#F6F8FA",
                                fg=C["text"], relief="flat", wrap=tk.WORD, state="disabled")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # ── 底部：按钮+进度 ──
        bot = tk.Frame(self.root, bg=C["card"], padx=12, pady=10)
        bot.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_start = tk.Button(bot, text="🚀 开始生成", font=("微软雅黑", 12, "bold"),
                                   bg=C["success"], fg="white", relief="flat",
                                   padx=20, pady=8, cursor="hand2", command=self._start)
        self.btn_start.pack(side=tk.LEFT)

        self.btn_stop = tk.Button(bot, text="⏹ 停止", font=("微软雅黑", 11),
                                  bg=C["danger"], fg="white", relief="flat",
                                  padx=14, pady=8, cursor="hand2", command=self._stop,
                                  state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=10)

        self.progress = ttk.Progressbar(bot, mode="determinate", maximum=100)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        self.lbl_eta = tk.Label(bot, text="", font=("Consolas", 10, "bold"),
                                bg=C["card"], fg=C["primary"], padx=6)
        self.lbl_eta.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(self.root, text="就绪 · 添加音频文件后点击开始",
                                   font=("微软雅黑", 10), bg=C["primary_light"],
                                   fg=C["primary"], padx=12, pady=6)
        self.lbl_status.pack(fill=tk.X, side=tk.BOTTOM)

    def _card_audio(self, parent):
        """音频文件卡片"""
        card = tk.Frame(parent, bg=C["card"], relief="flat", bd=0)
        card.pack(fill=tk.X, pady=(0, 8))

        tk.Label(card, text="🎵 音频文件", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"], anchor="w").pack(fill=tk.X, padx=12, pady=(8, 4))

        # 按钮行
        btn_row = tk.Frame(card, bg=C["card"])
        btn_row.pack(fill=tk.X, padx=12)

        tk.Button(btn_row, text="➕ 添加音频", font=("微软雅黑", 10),
                  bg=C["primary"], fg="white", relief="flat", padx=10, pady=4,
                  cursor="hand2", command=self._add_audio).pack(side=tk.LEFT)
        tk.Button(btn_row, text="📁 添加文件夹", font=("微软雅黑", 10),
                  bg=C["primary_dark"], fg="white", relief="flat", padx=10, pady=4,
                  cursor="hand2", command=self._add_audio_dir).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_row, text="🗑 清空", font=("微软雅黑", 10),
                  bg=C["danger"], fg="white", relief="flat", padx=10, pady=4,
                  cursor="hand2", command=self._clear_audio).pack(side=tk.LEFT)

        self.audio_listbox = tk.Listbox(card, height=5, font=("微软雅黑", 9),
                                        bg="#F6F8FA", fg=C["text"], relief="flat",
                                        selectbackground=C["primary_light"])
        self.audio_listbox.pack(fill=tk.X, padx=12, pady=(6, 4))

        self.lbl_audio_count = tk.Label(card, text="共 0 个音频",
                                        font=("微软雅黑", 9), bg=C["card"], fg=C["text3"])
        self.lbl_audio_count.pack(padx=12, pady=(0, 8), anchor="w")

    def _card_bg(self, parent):
        """背景设置卡片"""
        card = tk.Frame(parent, bg=C["card"], relief="flat", bd=0)
        card.pack(fill=tk.X, pady=(0, 8))

        tk.Label(card, text="🖼 背景设置", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"], anchor="w").pack(fill=tk.X, padx=12, pady=(8, 4))

        modes = tk.Frame(card, bg=C["card"])
        modes.pack(fill=tk.X, padx=12)

        for val, txt in [("black", "⬛ 纯黑屏"), ("image", "🖼 图片背景"), ("video", "🎬 视频循环")]:
            tk.Radiobutton(modes, text=txt, variable=self.bg_mode, value=val,
                           font=("微软雅黑", 10), bg=C["card"], fg=C["text"],
                           activebackground=C["card"], activeforeground=C["text"],
                           command=self._on_bg_mode_change).pack(side=tk.LEFT, padx=(0, 12))

        # 背景文件选择
        self.bg_frame = tk.Frame(card, bg=C["card"])
        self.bg_frame.pack(fill=tk.X, padx=12, pady=(6, 0))

        self.lbl_bg_path = tk.Label(self.bg_frame, text="（纯黑屏模式，无需选择文件）",
                                    font=("微软雅黑", 9), bg=C["card"], fg=C["text3"])
        self.lbl_bg_path.pack(side=tk.LEFT)

        self.btn_bg_select = tk.Button(self.bg_frame, text="选择文件", font=("微软雅黑", 9),
                                       bg=C["primary"], fg="white", relief="flat",
                                       padx=8, pady=2, cursor="hand2",
                                       command=self._select_bg, state="disabled")
        self.btn_bg_select.pack(side=tk.RIGHT)

        # 分辨率
        res_row = tk.Frame(card, bg=C["card"])
        res_row.pack(fill=tk.X, padx=12, pady=(8, 8))

        tk.Label(res_row, text="分辨率:", font=("微软雅黑", 10),
                 bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)

        for res in ["1920x1080", "1280x720", "854x480"]:
            tk.Radiobutton(res_row, text=res, variable=self.resolution, value=res,
                           font=("微软雅黑", 9), bg=C["card"], fg=C["text"],
                           activebackground=C["card"]).pack(side=tk.LEFT, padx=(8, 0))

    def _card_output(self, parent):
        """输出设置卡片"""
        card = tk.Frame(parent, bg=C["card"], relief="flat", bd=0)
        card.pack(fill=tk.X, pady=(0, 8))

        tk.Label(card, text="📤 输出设置", font=("微软雅黑", 11, "bold"),
                 bg=C["card"], fg=C["text"], anchor="w").pack(fill=tk.X, padx=12, pady=(8, 4))

        out_row = tk.Frame(card, bg=C["card"])
        out_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.out_entry = tk.Entry(out_row, textvariable=self.output_dir,
                                  font=("微软雅黑", 9), relief="flat", bg="#F6F8FA")
        self.out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(out_row, text="📁", font=("微软雅黑", 9),
                  bg=C["primary"], fg="white", relief="flat", padx=6,
                  cursor="hand2", command=self._select_output).pack(side=tk.RIGHT, padx=(6, 0))

    # ═══════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════
    def _on_bg_mode_change(self):
        mode = self.bg_mode.get()
        if mode == "black":
            self.btn_bg_select.config(state="disabled")
            self.lbl_bg_path.config(text="（纯黑屏模式，无需选择文件）")
            self.bg_path = None
        else:
            self.btn_bg_select.config(state="normal")
            if self.bg_path:
                self.lbl_bg_path.config(text=os.path.basename(self.bg_path), fg=C["text"])
            else:
                self.lbl_bg_path.config(text="请点击选择文件", fg=C["warning"])

    def _add_audio(self):
        files = filedialog.askopenfilenames(
            title="选择音频文件",
            filetypes=[("音频文件", "*.mp3 *.flac *.wav *.aac *.ogg *.wma *.m4a"), ("所有文件", "*.*")]
        )
        for f in files:
            if f not in self.audio_files:
                self.audio_files.append(f)
                self.audio_listbox.insert(tk.END, os.path.basename(f))
        self._update_audio_count()

    def _add_audio_dir(self):
        d = filedialog.askdirectory(title="选择包含音频的文件夹")
        if not d:
            return
        exts = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.wma', '.m4a')
        count = 0
        for root_dir, dirs, files in os.walk(d):
            for f in sorted(files):
                if f.lower().endswith(exts):
                    fp = os.path.join(root_dir, f)
                    if fp not in self.audio_files:
                        self.audio_files.append(fp)
                        self.audio_listbox.insert(tk.END, f)
                        count += 1
        self._update_audio_count()
        self._log(f"📁 从文件夹添加了 {count} 个音频")

    def _clear_audio(self):
        self.audio_files.clear()
        self.audio_listbox.delete(0, tk.END)
        self._update_audio_count()

    def _update_audio_count(self):
        self.lbl_audio_count.config(text=f"共 {len(self.audio_files)} 个音频")

    def _select_bg(self):
        mode = self.bg_mode.get()
        if mode == "image":
            f = filedialog.askopenfilename(title="选择背景图片",
                filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp"), ("所有", "*.*")])
        else:
            f = filedialog.askopenfilename(title="选择背景视频",
                filetypes=[("视频", "*.mp4 *.mkv *.avi *.flv *.ts"), ("所有", "*.*")])
        if f:
            self.bg_path = f
            self.lbl_bg_path.config(text=os.path.basename(f), fg=C["text"])

    def _select_output(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_dir.set(d)

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        print(line, end="", flush=True)
        try:
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, line)
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        except:
            pass

    def _set_status(self, t):
        try:
            self.lbl_status.config(text=t)
        except:
            pass

    def _update_progress(self, pct, eta_text=""):
        try:
            self.progress.config(value=min(pct, 100))
            self.lbl_eta.config(text=eta_text)
        except:
            pass

    def _format_eta(self, seconds):
        if seconds < 0:
            return ""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"⏳ {h}h{m:02d}m{s:02d}s"
        return f"⏳ {m}m{s:02d}s"

    # ═══════════════════════════════════════
    #  生成逻辑
    # ═══════════════════════════════════════
    def _start(self):
        if not self.audio_files:
            messagebox.showwarning("提示", "请先添加音频文件！")
            return
        if not self.output_dir.get():
            # 默认输出到第一个音频同目录
            self.output_dir.set(os.path.dirname(self.audio_files[0]))

        self._processing = True
        self._cancel = False
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress["value"] = 0
        self.lbl_eta.config(text="🔄 启动中...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _stop(self):
        self._cancel = True
        self._log("⏹ 已停止")

    def _worker(self):
        out_dir = self.output_dir.get()
        os.makedirs(out_dir, exist_ok=True)
        total = len(self.audio_files)
        w, h = self.resolution.get().split("x")
        mode = self.bg_mode.get()
        t0 = time.time()

        self._log(f"🚀 开始生成 [{total}个音频] 分辨率={self.resolution.get()} 背景={mode}")

        success = 0
        fail = 0

        for i, audio in enumerate(self.audio_files):
            if self._cancel:
                break

            name = os.path.splitext(os.path.basename(audio))[0]
            out_path = os.path.join(out_dir, f"{name}.mp4")

            # 避免覆盖
            if os.path.exists(out_path):
                base, ext = os.path.splitext(out_path)
                n = 1
                while os.path.exists(f"{base}_{n}{ext}"):
                    n += 1
                out_path = f"{base}_{n}{ext}"

            pct = i / total * 100
            self._update_progress(pct, f"{i+1}/{total}")
            self._set_status(f"🎬 生成中 [{i+1}/{total}]: {name}")
            self._log(f"🎬 [{i+1}/{total}] {name}")

            cmd = self._build_cmd(audio, out_path, w, h, mode)
            if cmd is None:
                self._log(f"  ❌ 跳过（背景文件不存在）")
                fail += 1
                continue

            r = self._run_ffmpeg(cmd)
            if r == 0:
                sz = os.path.getsize(out_path) / 1024 / 1024
                self._log(f"  ✅ 完成 ({sz:.1f}MB): {os.path.basename(out_path)}")
                success += 1
            else:
                self._log(f"  ❌ 失败 (code={r})")
                fail += 1

        elapsed = time.time() - t0
        self._processing = False
        self._update_progress(100, f"✅ {success}/{total}")
        self._set_status(f"✅ 完成 · {success}成功 {fail}失败 · 耗时 {elapsed:.1f}秒")
        self._log(f"🎉 全部完成 · {success}成功 {fail}失败 · 耗时 {elapsed:.1f}秒")

        try:
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
        except:
            pass

    def _build_cmd(self, audio, out_path, w, h, mode):
        """构建ffmpeg命令"""
        cmd = ['ffmpeg', '-y']

        if mode == "black":
            # 纯黑屏
            cmd.extend(['-f', 'lavfi', '-i', f'color=c=black:s={w}x{h}:r=24:d=10000'])
        elif mode == "image":
            if not self.bg_path or not os.path.exists(self.bg_path):
                return None
            cmd.extend(['-loop', '1', '-i', self.bg_path])
        elif mode == "video":
            if not self.bg_path or not os.path.exists(self.bg_path):
                return None
            cmd.extend(['-stream_loop', '-1', '-i', self.bg_path])

        cmd.extend(['-i', audio])

        # 音频索引
        audio_idx = 2 if mode != "black" else 1
        # 如果是black模式，-f lavfi没有索引问题，audio是input 1
        if mode == "black":
            audio_idx = 1

        # 视频滤镜：缩放+强制比例
        if mode == "image":
            cmd.extend(['-vf', f'scale={w}:{h}:force_original_aspect_ratio=decrease,'
                        f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1'])
        elif mode == "video":
            cmd.extend(['-vf', f'scale={w}:{h}:force_original_aspect_ratio=decrease,'
                        f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1'])

        cmd.extend([
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', f'{self.bitrate.get()}k',
            '-map', '0:v', '-map', f'{audio_idx}:a',
            '-shortest',
            '-movflags', '+faststart',
            '-max_muxing_queue_size', '1024',
            out_path
        ])
        return cmd

    def _run_ffmpeg(self, cmd):
        """运行ffmpeg并实时输出进度"""
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, encoding='utf-8', errors='replace'
            )
        except Exception as e:
            self._log(f"❌ 启动失败: {e}")
            return 1

        # 读取stderr获取进度
        try:
            for line in proc.stderr:
                line = line.strip()
                if line.startswith("time="):
                    # 解析 time=HH:MM:SS.ss
                    try:
                        t = line.split("time=")[1].split(" ")[0]
                        parts = t.split(":")
                        secs = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
                        # 无法知道总时长（每个音频不同），显示已处理时间
                        m, s = divmod(int(secs), 60)
                        h, m = divmod(m, 60)
                        self.root.after(0, lambda s=f"{h:02d}:{m:02d}:{s:02d}":
                                       self.lbl_eta.config(text=f"⏱ {s}"))
                    except:
                        pass
                elif "speed=" in line:
                    try:
                        spd = line.split("speed=")[1].split(" ")[0].strip()
                        self.root.after(0, lambda s=spd: self.lbl_eta.config(
                            text=f"{self.lbl_eta.cget('text')} ×{s}"))
                    except:
                        pass
        except:
            pass

        proc.wait()
        return proc.returncode

    # ═══════════════════════════════════════
    #  配置保存/加载
    # ═══════════════════════════════════════
    def _save_config(self):
        cfg = {
            "bg_mode": self.bg_mode.get(),
            "bg_path": self.bg_path,
            "resolution": self.resolution.get(),
            "output_dir": self.output_dir.get(),
            "bitrate": self.bitrate.get(),
        }
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "black_screen_config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _load_config(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "black_screen_config.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.bg_mode.set(cfg.get("bg_mode", "black"))
            self.bg_path = cfg.get("bg_path")
            self.resolution.set(cfg.get("resolution", "1280x720"))
            self.output_dir.set(cfg.get("output_dir", ""))
            self.bitrate.set(cfg.get("bitrate", "128"))
            self._on_bg_mode_change()
        except:
            pass


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = BlackScreenMaker(root)
        root.protocol("WM_DELETE_WINDOW", lambda: (app._save_config(), root.destroy()))
        root.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input(f"\n❌ 错误: {e}\n按回车退出...")
