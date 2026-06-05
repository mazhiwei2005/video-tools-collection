#!/usr/bin/env python3
"""视频处理模块 - 合并/分割/画质/B站/字幕/水印/压缩/GIF"""
import os, sys, subprocess, json, time, shutil, tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

class VideoProcessorPage:
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vp_config.json")

    def __init__(self, parent, colors):
        self.C = colors
        self.frame = tk.Frame(parent, bg=colors["bg"])
        self.input_dir = None
        self.output_dir = None
        self.video_batches = []
        self.intro_path = None
        self.outro_path = None

        # 设置变量
        self.merge_count = tk.IntVar(value=1)
        self.add_intro = tk.BooleanVar(value=False)
        self.add_outro = tk.BooleanVar(value=False)
        self.split_enabled = tk.BooleanVar(value=False)
        self.split_duration = tk.StringVar(value="600")
        self.use_gpu = tk.BooleanVar(value=True)
        self.keep_bitrate = tk.BooleanVar(value=True)
        self.merge_then_add = tk.BooleanVar(value=False)
        self.quality_preset = tk.StringVar(value="保持原画质")
        self.custom_bitrate = tk.StringVar(value="8000")

        # B站
        self.bili_border = tk.BooleanVar(value=False)
        self.bili_scale = tk.BooleanVar(value=False)
        self.bili_speed = tk.BooleanVar(value=False)
        self.bili_mirror = tk.BooleanVar(value=False)
        self.bili_black_intro = tk.BooleanVar(value=False)

        # 字幕
        self.subtitle_path = None
        self.subtitle_burn = tk.BooleanVar(value=False)
        self.subtitle_fontsize = tk.StringVar(value="24")
        self.subtitle_color = tk.StringVar(value="white")
        self.ai_subtitle_enabled = tk.BooleanVar(value=False)
        self.ai_subtitle_lang = tk.StringVar(value="ja")
        self.ai_subtitle_model = tk.StringVar(value="medium")
        self.ai_subtitle_translate = tk.BooleanVar(value=False)
        self.ai_subtitle_target_lang = tk.StringVar(value="zh")

        # 水印
        self.watermark_path = None
        self.watermark_enabled = tk.BooleanVar(value=False)
        self.watermark_position = tk.StringVar(value="右下角")
        self.watermark_opacity = tk.StringVar(value="0.7")
        self.watermark_scale = tk.StringVar(value="0.15")

        # 工具
        self.compress_enabled = tk.BooleanVar(value=False)
        self.compress_quality = tk.StringVar(value="23")
        self.extract_audio = tk.BooleanVar(value=False)
        self.audio_format = tk.StringVar(value="mp3")
        self.gif_enabled = tk.BooleanVar(value=False)
        self.gif_start = tk.StringVar(value="0")
        self.gif_duration = tk.StringVar(value="5")
        self.gif_fps = tk.StringVar(value="15")
        self.gif_width = tk.StringVar(value="480")

        self._processing = False
        self._cancel = False
        self.gpu_available = self._check_gpu()

        self._build_ui()
        self._load_config()

    def show(self): pass
    def hide(self): pass

    def _check_gpu(self):
        try:
            r = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=5)
            return 'hevc_nvenc' in r.stdout
        except: return False

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
        # 顶部状态栏
        top = tk.Frame(self.frame, bg=self.C["bg"])
        top.pack(fill=tk.X, padx=15, pady=(10, 5))
        gpu_txt = "✅ NVENC H265" if self.gpu_available else "⚠ CPU编码"
        gpu_clr = self.C["success"] if self.gpu_available else self.C["warning"]
        tk.Label(top, text=gpu_txt, font=("微软雅黑", 9, "bold"),
                 bg=self.C["bg"], fg=gpu_clr).pack(side=tk.LEFT)
        tk.Label(top, text="  |  ", bg=self.C["bg"], fg=self.C["text3"]).pack(side=tk.LEFT)
        self._btn(top, "📂 输入文件夹", self._choose_input).pack(side=tk.LEFT, padx=2)
        self._btn(top, "🎬 添加视频", self._add_video).pack(side=tk.LEFT, padx=2)
        self._btn(top, "💾 输出目录", self._choose_output).pack(side=tk.LEFT, padx=2)
        self.lbl_output = tk.Label(top, text="未选择", font=("微软雅黑", 9),
                                   bg=self.C["bg"], fg=self.C["text3"])
        self.lbl_output.pack(side=tk.LEFT, padx=8)

        # 主体双栏
        paned = tk.PanedWindow(self.frame, orient=tk.HORIZONTAL, bg=self.C["bg"])
        paned.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # 左栏: 列表+进度
        left = tk.Frame(paned, bg=self.C["bg"])
        paned.add(left, minsize=400)

        # 视频列表
        lf = tk.LabelFrame(left, text="  📋 视频列表  ", font=("微软雅黑", 9, "bold"))
        lf.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        self.listbox = tk.Listbox(lf, font=("Consolas", 8), selectmode=tk.EXTENDED)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        bf = tk.Frame(lf)
        bf.pack(fill=tk.X, padx=4, pady=2)
        self._btn(bf, "清空", self._clear_list, "secondary").pack(side=tk.LEFT, padx=2)
        self._btn(bf, "删除选中", self._remove_sel, "danger").pack(side=tk.LEFT, padx=2)
        self.lbl_count = tk.Label(bf, text="0 个视频", font=("微软雅黑", 9), fg="gray")
        self.lbl_count.pack(side=tk.RIGHT, padx=4)

        # 进度
        lf2 = tk.LabelFrame(left, text="  📊 进度  ", font=("微软雅黑", 9, "bold"))
        lf2.pack(fill=tk.X)
        r = tk.Frame(lf2); r.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(r, text="总:", width=3).pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(r, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.lbl_progress = tk.Label(r, text="0%", width=6, font=("Consolas", 9, "bold"), fg="blue")
        self.lbl_progress.pack(side=tk.LEFT)

        r = tk.Frame(lf2); r.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(r, text="当:", width=3).pack(side=tk.LEFT)
        self.progress_bar_cur = ttk.Progressbar(r, mode='determinate')
        self.progress_bar_cur.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.lbl_progress_cur = tk.Label(r, text="0%", width=6, font=("Consolas", 9, "bold"), fg="green")
        self.lbl_progress_cur.pack(side=tk.LEFT)

        self.log_text = tk.Text(lf2, height=5, font=("Consolas", 8), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 右栏: 设置Notebook
        right = tk.Frame(paned, bg=self.C["bg"], width=320)
        paned.add(right, minsize=280)

        nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True)

        self._build_tab_basic(nb)
        self._build_tab_quality(nb)
        self._build_tab_bili(nb)
        self._build_tab_subtitle(nb)
        self._build_tab_watermark(nb)
        self._build_tab_tools(nb)

        # 底部按钮
        bf = tk.Frame(self.frame, bg=self.C["bg"])
        bf.pack(fill=tk.X, padx=15, pady=(2, 10))
        self.btn_start = self._btn(bf, "🚀 开始处理", self._start_process, "success")
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_cancel = self._btn(bf, "⏹ 取消", self._cancel_process, "danger")
        self.btn_cancel.pack(side=tk.LEFT, padx=4)

    def _tab_frame(self, nb, title):
        f = tk.Frame(nb)
        nb.add(f, text=f" {title} ")
        return f

    def _build_tab_basic(self, nb):
        f = self._tab_frame(nb, "基本")
        # 片头片尾
        lf = tk.LabelFrame(f, text="片头/片尾", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=1)
        tk.Checkbutton(r, text="片头", variable=self.add_intro).pack(side=tk.LEFT)
        self._btn(r, "选择", self._choose_intro, "secondary").pack(side=tk.RIGHT)
        self.lbl_intro = tk.Label(r, text="未选择", fg="gray", width=16, anchor="e")
        self.lbl_intro.pack(side=tk.RIGHT, padx=4)
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=1)
        tk.Checkbutton(r, text="片尾", variable=self.add_outro).pack(side=tk.LEFT)
        self._btn(r, "选择", self._choose_outro, "secondary").pack(side=tk.RIGHT)
        self.lbl_outro = tk.Label(r, text="未选择", fg="gray", width=16, anchor="e")
        self.lbl_outro.pack(side=tk.RIGHT, padx=4)

        # 合并
        lf = tk.LabelFrame(f, text="合并", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=1)
        tk.Label(r, text="每").pack(side=tk.LEFT)
        tk.Spinbox(r, from_=1, to=100, textvariable=self.merge_count, width=4).pack(side=tk.LEFT, padx=2)
        tk.Label(r, text="个合并为1个").pack(side=tk.LEFT)
        tk.Checkbutton(lf, text="先合并再加片头尾", variable=self.merge_then_add).pack(anchor="w")

        # 分割
        lf = tk.LabelFrame(f, text="分割", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="启用分割", variable=self.split_enabled).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Label(r, text="每段(秒):").pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.split_duration, width=8).pack(side=tk.LEFT, padx=4)

    def _build_tab_quality(self, nb):
        f = self._tab_frame(nb, "画质")
        lf = tk.LabelFrame(f, text="编码", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="GPU加速 (NVENC)", variable=self.use_gpu).pack(anchor="w")
        tk.Checkbutton(lf, text="保持原视频码率", variable=self.keep_bitrate).pack(anchor="w")

        lf = tk.LabelFrame(f, text="画质预设", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        for p in ["保持原画质", "4K 20Mbps + FLAC", "1080P 5Mbps + FLAC",
                   "1080P 3Mbps + FLAC", "720P 2Mbps + FLAC", "480P 1Mbps + FLAC", "自定义码率"]:
            tk.Radiobutton(lf, text=p, variable=self.quality_preset, value=p).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, padx=(20, 0), pady=2)
        tk.Label(r, text="码率:").pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.custom_bitrate, width=8).pack(side=tk.LEFT, padx=4)
        tk.Label(r, text="kbps", fg="gray").pack(side=tk.LEFT)

    def _build_tab_bili(self, nb):
        f = self._tab_frame(nb, "B站")
        lf = tk.LabelFrame(f, text="B站搬运优化", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        for text, var in [("🔲 加黑边框", self.bili_border), ("📐 画面微缩放98%", self.bili_scale),
                          ("⏩ 轻微变速1.02x", self.bili_speed), ("🪞 镜像翻转", self.bili_mirror),
                          ("⬛ 片头加2秒黑屏", self.bili_black_intro)]:
            tk.Checkbutton(lf, text=text, variable=var).pack(anchor="w", pady=2)
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=4)
        self._btn(r, "一键全选", lambda: self._set_bili(True)).pack(side=tk.LEFT, padx=2)
        self._btn(r, "一键全关", lambda: self._set_bili(False), "secondary").pack(side=tk.LEFT, padx=2)

    def _build_tab_subtitle(self, nb):
        f = self._tab_frame(nb, "字幕")
        lf = tk.LabelFrame(f, text="字幕烧录", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="🔤 烧录字幕到视频", variable=self.subtitle_burn).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=4)
        self._btn(r, "选择字幕文件", self._choose_subtitle, "secondary").pack(side=tk.LEFT)
        self.lbl_subtitle = tk.Label(r, text="未选择", fg="gray")
        self.lbl_subtitle.pack(side=tk.LEFT, padx=10)
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Label(r, text="字号:").pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.subtitle_fontsize, width=5).pack(side=tk.LEFT, padx=4)
        tk.Label(r, text="颜色:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Combobox(r, textvariable=self.subtitle_color, values=["white", "yellow", "green"],
                     width=8, state="readonly").pack(side=tk.LEFT, padx=4)

        lf = tk.LabelFrame(f, text="AI字幕生成", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="🤖 启用AI字幕", variable=self.ai_subtitle_enabled).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Label(r, text="源语言:").pack(side=tk.LEFT)
        ttk.Combobox(r, textvariable=self.ai_subtitle_lang, values=["ja", "zh", "en", "auto"],
                     width=6, state="readonly").pack(side=tk.LEFT, padx=4)
        tk.Label(r, text="模型:").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Combobox(r, textvariable=self.ai_subtitle_model,
                     values=["tiny", "base", "small", "medium", "large-v3"],
                     width=10, state="readonly").pack(side=tk.LEFT, padx=4)
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Checkbutton(r, text="翻译", variable=self.ai_subtitle_translate).pack(side=tk.LEFT)
        tk.Label(r, text="目标:").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Combobox(r, textvariable=self.ai_subtitle_target_lang,
                     values=["zh", "en", "ja"], width=6, state="readonly").pack(side=tk.LEFT, padx=4)

    def _build_tab_watermark(self, nb):
        f = self._tab_frame(nb, "水印")
        lf = tk.LabelFrame(f, text="批量加水印", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="💧 添加图片水印", variable=self.watermark_enabled).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=4)
        self._btn(r, "选择水印图片", self._choose_watermark, "secondary").pack(side=tk.LEFT)
        self.lbl_watermark = tk.Label(r, text="未选择", fg="gray")
        self.lbl_watermark.pack(side=tk.LEFT, padx=10)
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Label(r, text="位置:").pack(side=tk.LEFT)
        ttk.Combobox(r, textvariable=self.watermark_position,
                     values=["左上角", "右上角", "左下角", "右下角", "居中"],
                     width=8, state="readonly").pack(side=tk.LEFT, padx=4)
        tk.Label(r, text="透明度:").pack(side=tk.LEFT, padx=(8, 0))
        tk.Entry(r, textvariable=self.watermark_opacity, width=5).pack(side=tk.LEFT, padx=4)

    def _build_tab_tools(self, nb):
        f = self._tab_frame(nb, "工具")
        lf = tk.LabelFrame(f, text="视频压缩", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="📦 压缩视频", variable=self.compress_enabled).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Label(r, text="质量CRF:").pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.compress_quality, width=5).pack(side=tk.LEFT, padx=4)
        tk.Label(r, text="(18-28常用)", fg="gray").pack(side=tk.LEFT, padx=4)

        lf = tk.LabelFrame(f, text="提取音频", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="🎵 提取音频", variable=self.extract_audio).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Label(r, text="格式:").pack(side=tk.LEFT)
        ttk.Combobox(r, textvariable=self.audio_format, values=["mp3", "aac", "flac", "wav"],
                     width=8, state="readonly").pack(side=tk.LEFT, padx=4)

        lf = tk.LabelFrame(f, text="视频转GIF", padx=6, pady=4)
        lf.pack(fill=tk.X, padx=6, pady=4)
        tk.Checkbutton(lf, text="🖼️ 转GIF", variable=self.gif_enabled).pack(anchor="w")
        r = tk.Frame(lf); r.pack(fill=tk.X, pady=2)
        tk.Label(r, text="起始:").pack(side=tk.LEFT)
        tk.Entry(r, textvariable=self.gif_start, width=5).pack(side=tk.LEFT, padx=4)
        tk.Label(r, text="时长:").pack(side=tk.LEFT, padx=(8, 0))
        tk.Entry(r, textvariable=self.gif_duration, width=5).pack(side=tk.LEFT, padx=4)
        tk.Label(r, fg="gray", text="帧率:").pack(side=tk.LEFT, padx=(8, 0))
        tk.Entry(r, textvariable=self.gif_fps, width=5).pack(side=tk.LEFT, padx=4)

    # ========== 文件操作 ==========
    def _choose_input(self):
        path = filedialog.askdirectory()
        if not path: return
        self.input_dir = path
        exts = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm')
        existing = set(self.video_files)
        count = 0
        for rd, _, files in os.walk(path):
            for f in sorted(files):
                if f.lower().endswith(exts):
                    fp = os.path.join(rd, f)
                    if fp not in existing:
                        self.video_batches.append((fp, os.path.basename(path), True))
                        existing.add(fp)
                        self.listbox.insert(tk.END, f)
                        count += 1
        self.lbl_count.config(text=f"{len(self.video_batches)} 个视频")
        self._log(f"导入 {count} 个视频")

    def _add_video(self):
        files = filedialog.askopenfilenames(filetypes=[("视频", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.webm")])
        existing = set(self.video_files)
        for f in files:
            if f not in existing:
                self.video_batches.append((f, os.path.splitext(os.path.basename(f))[0], False))
                existing.add(f)
                self.listbox.insert(tk.END, os.path.basename(f))
        self.lbl_count.config(text=f"{len(self.video_batches)} 个视频")

    def _choose_output(self):
        p = filedialog.askdirectory()
        if p:
            self.output_dir = p
            self.lbl_output.config(text=p, fg="black")
            self._save_config()

    def _choose_intro(self):
        p = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.avi *.mov *.mkv")])
        if p:
            self.intro_path = p
            self.lbl_intro.config(text=os.path.basename(p), fg="black")

    def _choose_outro(self):
        p = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.avi *.mov *.mkv")])
        if p:
            self.outro_path = p
            self.lbl_outro.config(text=os.path.basename(p), fg="black")

    def _choose_subtitle(self):
        p = filedialog.askopenfilename(filetypes=[("字幕", "*.srt *.ass *.ssa *.vtt")])
        if p:
            self.subtitle_path = p
            self.lbl_subtitle.config(text=os.path.basename(p), fg="black")

    def _choose_watermark(self):
        p = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp")])
        if p:
            self.watermark_path = p
            self.lbl_watermark.config(text=os.path.basename(p), fg="black")

    def _clear_list(self):
        self.video_batches.clear()
        self.listbox.delete(0, tk.END)
        self.lbl_count.config(text="0 个视频")

    def _remove_sel(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            self.video_batches.pop(i)
        self.lbl_count.config(text=f"{len(self.video_batches)} 个视频")

    @property
    def video_files(self):
        return [f for f, _, _ in self.video_batches]

    def _set_bili(self, val):
        for v in [self.bili_border, self.bili_scale, self.bili_speed, self.bili_mirror, self.bili_black_intro]:
            v.set(val)

    def _log(self, msg):
        def _do():
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
        self.frame.after(0, _do)

    # ========== 处理逻辑 ==========
    def _start_process(self):
        if not self.video_files:
            messagebox.showerror("错误", "请先添加视频"); return
        if not self.output_dir:
            messagebox.showerror("错误", "请选择输出目录"); return
        self._save_config()
        self._processing = True
        self._cancel = False
        self.progress_bar['value'] = 0
        self.progress_bar_cur['value'] = 0
        self.log_text.delete(1.0, tk.END)
        threading.Thread(target=self._process_all, daemon=True).start()

    def _cancel_process(self):
        self._cancel = True

    def _get_video_info(self, path):
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', '-i', path]
            r = subprocess.run(cmd, capture_output=True, timeout=30, text=True, errors='replace')
            data = json.loads(r.stdout)
            info = {'duration': 0, 'video_bitrate': 0, 'audio_bitrate': 0, 'width': 0, 'height': 0, 'fps': 25}
            fb = 0
            if 'format' in data:
                info['duration'] = float(data['format'].get('duration', 0))
                fb = int(data['format'].get('bit_rate', 0))
            for s in data.get('streams', []):
                if s['codec_type'] == 'video':
                    info['width'] = int(s.get('width', 0))
                    info['height'] = int(s.get('height', 0))
                    try:
                        fps = eval(s.get('avg_frame_rate', '25/1'))
                        info['fps'] = fps if fps > 0 else eval(s.get('r_frame_rate', '25/1'))
                    except: info['fps'] = 25
                    if 'bit_rate' in s:
                        info['video_bitrate'] = int(s['bit_rate'])
                elif s['codec_type'] == 'audio' and 'bit_rate' in s:
                    info['audio_bitrate'] = int(s['bit_rate'])
            if info['video_bitrate'] == 0:
                info['video_bitrate'] = max(fb - info['audio_bitrate'], fb)
            return info
        except: return None

    def _get_encode_params(self, use_gpu, keep_bitrate, vi):
        cmd = []
        preset = self.quality_preset.get()
        min_br = 1800
        if vi:
            w, h = vi.get('width', 0), vi.get('height', 0)
            if w >= 3840 or h >= 2160: min_br = 15000

        audio_params = ['-c:a', 'flac', '-ar', '48000', '-sample_fmt', 's32']
        br_map = {
            "4K 20Mbps + FLAC": (20000, 30000, 40000),
            "1080P 5Mbps + FLAC": (5000, 7500, 10000),
            "1080P 3Mbps + FLAC": (3000, 4500, 6000),
            "720P 2Mbps + FLAC": (2000, 3000, 4000),
            "480P 1Mbps + FLAC": (1000, 1500, 2000),
        }
        target = maxrate = bufsize = 0
        if preset in br_map:
            target, maxrate, bufsize = br_map[preset]
        elif preset == "自定义码率":
            try: target = max(int(self.custom_bitrate.get()), 500)
            except: target = 8000
            maxrate = int(target * 1.5)
            bufsize = target * 2

        actual_br = 0
        if keep_bitrate and vi and vi['video_bitrate'] > 0:
            actual_br = max(vi['video_bitrate'] // 1000, min_br)

        if use_gpu:
            cmd.extend(['-c:v', 'hevc_nvenc', '-preset', 'p1', '-rc', 'vbr', '-tune', 'hq'])
            br = target or actual_br or 8000
            cmd.extend(['-b:v', f'{br}k', '-maxrate', f'{int(br*1.5)}k', '-bufsize', f'{br*2}k'])
        else:
            cmd.extend(['-c:v', 'libx265', '-preset', 'fast'])
            if target: cmd.extend(['-b:v', f'{target}k'])
            elif actual_br: cmd.extend(['-b:v', f'{actual_br}k'])
            else: cmd.extend(['-crf', '23'])

        cmd.extend(audio_params)
        cmd.extend(['-pix_fmt', 'yuv420p', '-movflags', '+faststart'])
        return cmd

    def _build_bili_filter(self, vi):
        filters = []
        af = None
        w = vi.get('width', 1920) if vi else 1920
        h = vi.get('height', 1080) if vi else 1080
        if self.bili_mirror.get(): filters.append("hflip")
        if self.bili_scale.get():
            nw, nh = int(w*0.98), int(h*0.98)
            nw += nw % 2; nh += nh % 2
            filters.append(f"scale={nw}:{nh}")
            filters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
        if self.bili_border.get():
            filters.append(f"pad={w+16}:{h+16}:8:8:black")
        if self.bili_speed.get():
            filters.append("setpts=PTS/1.02")
            af = "atempo=1.02"
        return (",".join(filters) if filters else None), af

    def _run_ffmpeg_progress(self, cmd, total_dur, name="处理"):
        self._log(f"  {name}中...")
        cmd2 = cmd + ['-progress', 'pipe:1', '-stats_period', '0.5']
        proc = subprocess.Popen(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors='replace')
        err_lines = []
        def drain():
            for l in proc.stderr: err_lines.append(l)
        threading.Thread(target=drain, daemon=True).start()
        cur = 0; t0 = time.time()
        while True:
            if self._cancel: proc.terminate(); raise Exception("取消")
            line = proc.stdout.readline()
            if not line: break
            if line.startswith('out_time_ms='):
                try: cur = int(line.split('=')[1].strip()) / 1e6
                except: pass
            if total_dur > 0:
                pct = min(100, cur / total_dur * 100)
                self.frame.after(0, lambda p=pct: self._update_cur_progress(p))
        proc.wait()
        if proc.returncode != 0:
            raise Exception(f"FFmpeg错误: {''.join(err_lines[-10:])[:300]}")
        self.frame.after(0, lambda: self._update_cur_progress(100))
        self._log(f"  {name}完成")

    def _update_cur_progress(self, pct):
        self.progress_bar_cur['value'] = pct
        self.lbl_progress_cur.config(text=f"{pct:.1f}%")

    def _process_all(self):
        try:
            t0 = time.time()
            use_gpu = self.use_gpu.get() and self.gpu_available
            mc = self.merge_count.get()
            batches = list(self.video_batches)
            groups = []
            sources = []
            for i in range(0, len(batches), mc):
                g = batches[i:i+mc]
                groups.append([p for p, _, _ in g])
                sources.append(g[0][1])

            self._log(f"{'='*30}\n开始处理 {len(groups)} 组视频\nGPU: {'是' if use_gpu else '否'}\n{'='*30}")

            for i, group in enumerate(groups):
                if self._cancel: self._log("已取消"); break
                first = group[0]
                base = os.path.splitext(os.path.basename(first))[0]
                out_name = f"{base}_merged.mp4" if len(group) > 1 else os.path.basename(first)
                src = sources[i]
                if len(group) > 1:
                    out_dir = os.path.join(self.output_dir, src)
                else:
                    out_dir = self.output_dir
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, out_name)

                pct = i / len(groups) * 100
                self.frame.after(0, lambda p=pct: (self.progress_bar.__setitem__('value', p),
                                                    self.lbl_progress.config(text=f"{p:.1f}%")))
                self._log(f"\n[{i+1}/{len(groups)}] {os.path.basename(first)}")
                try:
                    self._process_group(group, out_path, out_dir, use_gpu)
                    self._log(f"  ✓ 完成!")
                except Exception as e:
                    self._log(f"  ✗ 失败: {e}")

            total = time.time() - t0
            self._log(f"\n{'='*30}\n完成! 耗时 {total/60:.1f} 分钟")
            self.frame.after(0, lambda: messagebox.showinfo("完成", f"处理完成!\n耗时 {total/60:.1f} 分钟"))
        except Exception as e:
            self._log(f"错误: {e}")
        self._processing = False

    def _process_group(self, group, out_path, out_dir, use_gpu):
        vi = self._get_video_info(group[0])
        if not vi: raise Exception("无法获取视频信息")

        bili_vf, bili_af = self._build_bili_filter(vi)
        enc_params = self._get_encode_params(use_gpu, self.keep_bitrate.get(), vi)

        # 片头片尾
        parts = []
        if self.bili_black_intro.get():
            bp = os.path.join(out_dir, "_black.mp4")
            if not os.path.exists(bp):
                subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i',
                    f'color=c=black:s={vi["width"]}x{vi["height"]}:r={int(vi["fps"])}:d=2',
                    '-c:v', 'libx264', '-preset', 'ultrafast', bp], capture_output=True, timeout=30)
            parts.append(bp)
        if self.add_intro.get() and self.intro_path: parts.append(self.intro_path)
        parts.extend(group)
        if self.add_outro.get() and self.outro_path: parts.append(self.outro_path)

        if len(parts) > 1:
            # 拼接
            lf = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
            for p in parts:
                lf.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39)).replace(os.sep, '/')}'\n")
            lf.close()
            tmp = out_path + "_tmp.mp4"
            r = subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', lf.name, '-c', 'copy', tmp],
                               capture_output=True, text=True, timeout=7200)
            os.remove(lf.name)
            if r.returncode != 0: raise Exception(f"拼接失败: {r.stderr[:200]}")

            # 重编码
            cmd = ['ffmpeg', '-y', '-i', tmp]
            if bili_vf: cmd.extend(['-vf', bili_vf])
            cmd.extend(enc_params)
            if bili_af: cmd.extend(['-af', bili_af])
            cmd.extend(['-pix_fmt', 'yuv420p', '-r', str(int(vi['fps']))])
            cmd.append(out_path)
            self._run_ffmpeg_progress(cmd, sum(self._get_video_info(p)['duration'] for p in group if self._get_video_info(p)), "重编码")
            try: os.remove(tmp)
            except: pass
        else:
            shutil.copy2(parts[0], out_path)

        # 清理
        for tmp in [os.path.join(out_dir, "_black.mp4")]:
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except: pass

        # 分割
        if self.split_enabled.get():
            sd = int(self.split_duration.get())
            base = os.path.splitext(out_path)[0]
            cmd = ['ffmpeg', '-y', '-i', out_path, '-f', 'segment', '-segment_time', str(sd),
                   '-reset_timestamps', '1', '-c', 'copy', f"{base}_%03d.mp4"]
            subprocess.run(cmd, capture_output=True, timeout=3600)
            self._log(f"  分割为每段{sd}秒")

        # 提取音频
        if self.extract_audio.get():
            fmt = self.audio_format.get()
            aout = os.path.join(out_dir, os.path.splitext(os.path.basename(out_path))[0] + f".{fmt}")
            cmd = ['ffmpeg', '-y', '-i', group[0], '-vn']
            if fmt == 'mp3': cmd.extend(['-c:a', 'libmp3lame', '-b:a', '192k'])
            elif fmt == 'flac': cmd.extend(['-c:a', 'flac'])
            else: cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
            cmd.append(aout)
            subprocess.run(cmd, capture_output=True, timeout=3600)

        # GIF
        if self.gif_enabled.get():
            try:
                gs, gd, gf, gw = float(self.gif_start.get()), float(self.gif_duration.get()), int(self.gif_fps.get()), int(self.gif_width.get())
                gif_out = os.path.join(out_dir, os.path.splitext(os.path.basename(out_path))[0] + ".gif")
                pal = gif_out + ".pal.png"
                subprocess.run(['ffmpeg', '-y', '-ss', str(gs), '-t', str(gd), '-i', group[0],
                    '-vf', f'fps={gf},scale={gw}:-1:flags=lanczos,palettegen', pal], capture_output=True, timeout=300)
                subprocess.run(['ffmpeg', '-y', '-ss', str(gs), '-t', str(gd), '-i', group[0],
                    '-i', pal, '-filter_complex', f'fps={gf},scale={gw}:-1:flags=lanczos[x];[x][1:v]paletteuse',
                    gif_out], capture_output=True, timeout=600)
                try: os.remove(pal)
                except: pass
            except: pass

    # ========== 配置 ==========
    def _save_config(self):
        cfg = {
            'output_dir': self.output_dir,
            'merge_count': self.merge_count.get(), 'use_gpu': self.use_gpu.get(),
            'keep_bitrate': self.keep_bitrate.get(), 'quality_preset': self.quality_preset.get(),
            'custom_bitrate': self.custom_bitrate.get(),
            'bili_border': self.bili_border.get(), 'bili_scale': self.bili_scale.get(),
            'bili_speed': self.bili_speed.get(), 'bili_mirror': self.bili_mirror.get(),
            'bili_black_intro': self.bili_black_intro.get(),
        }
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except: pass

    def _load_config(self):
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                if cfg.get('output_dir') and os.path.exists(cfg['output_dir']):
                    self.output_dir = cfg['output_dir']
                    self.lbl_output.config(text=self.output_dir, fg="black")
                for k in ['merge_count', 'use_gpu', 'keep_bitrate']:
                    if k in cfg: getattr(self, k).set(cfg[k])
                for k in ['quality_preset', 'custom_bitrate']:
                    if k in cfg: getattr(self, k).set(cfg[k])
                for k in ['bili_border', 'bili_scale', 'bili_speed', 'bili_mirror', 'bili_black_intro']:
                    if k in cfg: getattr(self, k).set(cfg[k])
        except: pass
