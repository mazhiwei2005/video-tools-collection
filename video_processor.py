#!/usr/bin/env python3
"""
视频处理工具 - 重构版
功能：画中画、视频套框、横转竖、流水线串联
GPU加速：NVENC H264/H265
UI框架：customtkinter（现代圆角风格）
"""
import os, sys, subprocess, json, time, re, threading, hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np

# 现代UI框架
try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    print("⚠️ customtkinter 未安装，使用默认UI")

# 拖拽支持
try:
    import tkinterdnd2
    HAS_DND = True
except ImportError:
    HAS_DND = False
    print("⚠️ tkinterdnd2 未安装，拖拽功能不可用")

# ═══════════════════════════════════════
#  颜色常量（Dieter Rams × Tadao Ando 深色主题）
# ═══════════════════════════════════════
#  Design Tokens — VideoCraft Web Style
# ═══════════════════════════════════════
C = {
    # Backgrounds (darkest → lightest)
    "bg": "#06080c",            # 最深背景
    "bg1": "#0a0e14",          # 主背景
    "bg2": "#111822",          # 次背景
    "card": "#111822",         # 卡片表面
    "card_border": "#2a3545",  # 卡片边框
    "input": "#0d1117",        # 输入框背景
    "btn": "#1a2332",          # 按钮背景
    "btn_hover": "#222d3d",    # 按钮悬停
    # Accent colors
    "primary": "#4c9aff",       # 冷蓝高亮
    "primary_dark": "#3d7fd4",  # 深蓝
    "primary_light": "#0d1a2a", # 蓝调微光
    "primary_glow": "rgba(76,154,255,0.15)",  # 蓝色辉光
    "success": "#4ecdc4",       # 翠绿成功
    "success_dark": "#3dbdb5",
    "warning": "#f0a500",       # 琥珀警告
    "warning_dark": "#d49200",
    "danger": "#ff6b6b",        # 珊瑚红危险
    "danger_dark": "#e05555",
    # Text (brightest → dimmest)
    "text": "#f0f4f8",          # 最亮文字
    "text1": "#c8d6e5",         # 主文字
    "text2": "#7a8a9e",         # 次要文字
    "text3": "#4a5568",         # 弱化文字
    # Borders & Code
    "border": "#2a3545",        # 边框分割线
    "border_focus": "#4c9aff",  # 聚焦边框
    "code_bg": "#0d1117",       # 代码区背景
    "code_fg": "#8b949e",       # 代码区前景
    # Scrollbar
    "scroll": "#2a3545",        # 滚动条
    "scroll_hover": "#3a4a5a",  # 滚动条悬停
}

VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.flv', '.ts')

def _natural_sort_key(s):
    """自然排序：第1集 < 第02集 < 第12集"""
    import re as _re
    return [int(c) if c.isdigit() else c.lower() for c in _re.split(r'(\d+)', str(s))]


class VideoProcessor:
    """综合视频处理工具（重构版）"""

    def __init__(self, root):
        self.root = root
        self.root.title("视频处理工具")
        # 设置窗口图标
        import sys
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0] if hasattr(sys, 'argv') else __file__)), "app_icon.ico")
        if os.path.exists(_icon_path):
            try:
                self.root.iconbitmap(_icon_path)
            except Exception:
                try:
                    _icon_img = tk.PhotoImage(file=_icon_path.replace('.ico', '.png'))
                    self.root.iconphoto(True, _icon_img)
                except Exception: pass
        # 自适应屏幕分辨率（占屏幕90%）
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = min(1440, int(sw * 0.92))
        h = min(900, int(sh * 0.88))
        x = (sw - w) // 2
        y = (sh - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.minsize(900, 560)

        self._init_drag_drop()
        self.root.configure(bg=C["bg"])

        self.ffmpeg = self._find_ffmpeg()
        self.gpu = self._check_gpu()
        self._processing = False
        self._cancel = False
        self._total_duration = 0
        self._encode_start_time = 0
        self._current_proc = None

        self._config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_processor_config.json")

        # ═══ 统一视频列表（所有模式共享）═══
        self.videos = []           # 视频文件路径列表
        self.folder_groups = []    # [{"name": "文件夹名", "videos": [路径]}]
        self.folder_name = None    # 当前导入的文件夹名

        # ═══ 模式特定设置 ═══
        # 套框
        self.frame_template = None
        self.frame_roi = None
        self.bg_color = None
        self.output_resolution = "1920x1080"
        # 画中画
        self.pip_template = None
        self.pip_regions = {}
        self.pip_left_files = []   # 左装饰视频
        self.pip_right_files = []  # 右装饰视频
        # 区域/装饰启用开关
        self.pip_enable_left = tk.BooleanVar(value=True)
        self.pip_enable_center = tk.BooleanVar(value=True)
        self.pip_enable_right = tk.BooleanVar(value=True)
        self.pip_enable_left_decor = tk.BooleanVar(value=True)
        self.pip_enable_right_decor = tk.BooleanVar(value=True)
        # 横转竖
        self.rotate_dir = tk.StringVar(value="cw")
        # 片头片尾
        self.enable_intro = tk.BooleanVar(value=True)
        self.enable_outro = tk.BooleanVar(value=True)
        self.intro_video = None
        self.outro_video = None
        # 片头片尾独立模式变量
        self.io_intro_var = tk.StringVar(value="")
        self.io_outro_var = tk.StringVar(value="")
        self.io_fade_var = tk.BooleanVar(value=False)
        self.io_fade_sec_var = tk.DoubleVar(value=1.0)

        self._build()
        self._load_config()

    # ═══════════════════════════════════════
    #  FFmpeg / GPU 检测
    # ═══════════════════════════════════════
    def _find_ffmpeg(self):
        for p in ["ffmpeg", r"C:\Program Files\FFmpeg\bin\ffmpeg.exe",
                  r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
            try:
                subprocess.run([p, "-version"], capture_output=True, timeout=5)
                return p
            except:
                continue
        return "ffmpeg"

    def _check_gpu(self):
        try:
            r = subprocess.run([self.ffmpeg, "-encoders"], capture_output=True, text=True, errors="replace", timeout=5)
            return "hevc_nvenc" in r.stdout
        except:
            return False

    def _get_video_info(self, path):
        try:
            ffprobe = self.ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in self.ffmpeg else "ffprobe"
            r = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", path],
                capture_output=True, text=True, errors="replace", timeout=10
            )
            if r.returncode != 0:
                return {}
            data = json.loads(r.stdout)
            info = {}
            fmt = data.get("format", {})
            if fmt.get("duration"):
                info["duration"] = float(fmt["duration"])
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    if s.get("width"): info["width"] = int(s["width"])
                    if s.get("height"): info["height"] = int(s["height"])
                    if s.get("r_frame_rate"):
                        try:
                            num, den = s["r_frame_rate"].split("/")
                            info["fps"] = f"{int(num)/int(den):.2f}" if int(den) > 0 else s["r_frame_rate"]
                        except:
                            info["fps"] = s["r_frame_rate"]
                    info["pix_fmt"] = s.get("pix_fmt", "yuv420p")
                    break
            return info
        except:
            return {}

    def _get_real_duration(self, path):
        """获取视频真实时长，自动检测并修正多流时长异常"""
        try:
            ffprobe = self.ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in self.ffmpeg else "ffprobe"
            r = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", 
                 "stream=codec_type,duration",
                 "-show_entries", "format=duration",
                 "-of", "json", path],
                capture_output=True, text=True, errors="replace", timeout=10
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                fmt_dur = float(data.get("format", {}).get("duration", 0))
                audio_durs = []
                video_durs = []
                for s in data.get("streams", []):
                    d = float(s.get("duration", 0))
                    if d > 0:
                        if s.get("codec_type") == "audio":
                            audio_durs.append(d)
                        elif s.get("codec_type") == "video":
                            video_durs.append(d)

                # 如果视频时长远大于音频时长（>2倍），说明视频流损坏，用音频时长
                if audio_durs and video_durs:
                    v_dur = min(video_durs)
                    a_dur = min(audio_durs)
                    if v_dur > a_dur * 2:
                        self._log(f"  ⚠️ 视频流时长异常({v_dur:.0f}s vs 音频{a_dur:.0f}s)，使用音频时长")
                        return a_dur
                    return v_dur

                # 只有时长数据可用
                if fmt_dur > 0:
                    return fmt_dur
                if video_durs:
                    return min(video_durs)
                if audio_durs:
                    return min(audio_durs)
        except:
            pass
        return self._get_video_info(path).get("duration", 0)

    # ═══════════════════════════════════════
    #  动画系统
    # ═══════════════════════════════════════

    def _animate_button_click(self, btn, original_color, flash_color="#ffffff"):
        """按钮点击闪光动效"""
        if not HAS_CTK:
            return
        try:
            btn.configure(fg_color=flash_color)
            self.root.after(80, lambda: btn.configure(fg_color=original_color))
        except:
            pass

    def _animate_progress(self, target_pct, duration=500):
        """进度条平滑动画"""
        if not hasattr(self, 'progress'):
            return
        current = self.progress["value"]
        diff = target_pct - current
        steps = max(1, int(duration / 30))
        step = diff / steps

        def _step(i=0):
            if i < steps:
                self.progress["value"] = current + step * (i + 1)
                self.root.after(30, lambda: _step(i + 1))
            else:
                self.progress["value"] = target_pct
        _step()

    def _animate_loading_dots(self, label, base_text="处理中"):
        """加载动画 - 跳动的点"""
        if not hasattr(self, '_loading_frame'):
            self._loading_frame = 0
        self._loading_frame += 1
        dots = "." * (self._loading_frame % 4)
        try:
            label.configure(text=f"{base_text}{dots}")
        except:
            pass
        if hasattr(self, '_loading_active') and self._loading_active:
            self.root.after(400, lambda: self._animate_loading_dots(label, base_text))

    def _start_loading(self, label, text="处理中"):
        """启动加载动画"""
        self._loading_active = True
        self._animate_loading_dots(label, text)

    def _stop_loading(self, label, final_text="完成"):
        """停止加载动画"""
        self._loading_active = False
        try:
            label.configure(text=final_text)
        except:
            pass

    def _animate_pulse(self, widget, color1, color2, count=6):
        """脉冲闪烁动效"""
        if count <= 0:
            try:
                widget.configure(fg_color=color1)
            except:
                pass
            return
        try:
            widget.configure(fg_color=color2)
            self.root.after(200, lambda: self._animate_pulse(widget, color1, color2, count - 1))
        except:
            pass

    def _create_loading_spinner(self, parent, size=24):
        """创建旋转加载动画（Canvas绘制）"""
        canvas = tk.Canvas(parent, width=size, height=size,
                          bg=C["card"], highlightthickness=0)
        canvas.pack(side=tk.LEFT, padx=4)
        self._spinner_angle = 0
        self._spinner_canvas = canvas

        def _draw():
            if not hasattr(self, '_spinner_active') or not self._spinner_active:
                return
            canvas.delete("all")
            angle = self._spinner_angle
            # 画8个圆点，渐变透明度
            import math
            for i in range(8):
                a = (angle + i * 45) * math.pi / 180
                x = size/2 + (size/2 - 4) * 0.8 * math.cos(a)
                y = size/2 + (size/2 - 4) * 0.8 * math.sin(a)
                opacity = int(255 * (1 - i / 8))
                color = f"#{opacity:02x}{opacity:02x}{min(255, opacity+80):02x}"
                r = max(2, 3 - i * 0.3)
                canvas.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="")
            self._spinner_angle = (self._spinner_angle + 20) % 360
            self.root.after(50, _draw)

        self._spinner_active = True
        _draw()
        return canvas

    def _stop_spinner(self):
        """停止旋转动画"""
        self._spinner_active = False

    # ═══════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════

    def _configure_label(self, label, **kwargs):
        """兼容 CTkLabel 和 tk.Label 的 configure"""
        if HAS_CTK and isinstance(label, ctk.CTkLabel):
            if "fg" in kwargs:
                kwargs["text_color"] = kwargs.pop("fg")
        label.configure(**kwargs)

    def _btn(self, parent, text, command, color="primary", width=None, **kw):
        """创建统一风格的 CTk 按钮（带 fallback）"""
        color_map = {
            "primary": (C["primary"], C["primary_dark"]),
            "success": (C["success"], C["success_dark"]),
            "danger": (C["danger"], C["danger_dark"]),
            "warning": (C["warning"], C["warning_dark"]),
            "btn": (C["btn"], C["btn_hover"]),
        }
        fg, hover = color_map.get(color, (C["btn"], C["btn_hover"]))
        if HAS_CTK:
            kw.setdefault("corner_radius", 6)
            kw.setdefault("font", ("Microsoft YaHei UI", 11))
            if width:
                kw["width"] = width
            return ctk.CTkButton(parent, text=text, command=command,
                                 fg_color=fg, hover_color=hover, **kw)
        else:
            return tk.Button(parent, text=text, command=command,
                             font=("Microsoft YaHei UI", 10),
                             bg=fg, fg="white" if color != "btn" else C["text1"],
                             activebackground=hover, relief="flat",
                             padx=10, pady=4, cursor="hand2")

    def _card(self, parent, **kwargs):
        """创建带边框的卡片容器（customtkinter圆角风格）"""
        if HAS_CTK:
            # customtkinter: 自带圆角和边框
            card = ctk.CTkFrame(parent, fg_color=C["card"],
                               border_color=C["card_border"],
                               border_width=1,
                               corner_radius=10)
            card.pack(fill=kwargs.get("fill", tk.X),
                     expand=kwargs.get("expand", False),
                     pady=kwargs.get("pady_pack", (0, 8)))
            # 内容容器
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill=tk.BOTH, expand=True,
                      padx=kwargs.get("padx", 14),
                      pady=kwargs.get("pady", 12))
            return inner
        else:
            # fallback: tkinter 模拟
            outer = tk.Frame(parent, bg=C["card_border"], padx=1, pady=1)
            inner = tk.Frame(outer, bg=C["card"], padx=kwargs.get("padx", 12),
                             pady=kwargs.get("pady", 10))
            inner.pack(fill=kwargs.get("fill", tk.X), expand=kwargs.get("expand", False))
            outer.pack(fill=kwargs.get("fill", tk.X), expand=kwargs.get("expand", False),
                       pady=kwargs.get("pady_pack", (0, 6)))
            return inner

    def _init_ttk_styles(self):
        """初始化深色主题 ttk 样式（VideoCraft Web 风格）"""
        style = ttk.Style()
        style.theme_use("clam")
        # 进度条 — 蓝色渐变风格
        style.configure("Dark.Horizontal.TProgressbar",
                        background=C["primary"], troughcolor=C["border"],
                        borderwidth=0, lightcolor=C["primary"],
                        darkcolor=C["primary"])
        # 下拉框 — 深色风格
        style.configure("TCombobox",
                        fieldbackground=C["input"], background=C["btn"],
                        foreground=C["text"], bordercolor=C["border"],
                        arrowcolor=C["text2"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", C["input"])],
                  foreground=[("readonly", C["text"])])
        # 滚动条
        style.configure("TScrollbar",
                        background=C["scroll"], troughcolor=C["bg"],
                        borderwidth=0, arrowcolor=C["text3"])
        style.map("TScrollbar",
                  background=[("active", C["scroll_hover"])])

    def _build(self):
        self._init_ttk_styles()
        # Root background — 最深色
        self.root.configure(bg=C["bg"])

        # ═══════════════════════════════════════
        #  顶部工具栏（参考网页 Header 设计）
        #  网页设计: Logo图标 + 标题 + 副标题 + 右侧状态
        # ═══════════════════════════════════════
        toolbar = tk.Frame(self.root, bg=C["bg2"], padx=12, pady=6)
        toolbar.pack(fill=tk.X)

        # Logo图标（参考网页 .header-logo-icon）
        logo_icon = tk.Frame(toolbar, bg=C["primary"], width=36, height=36)
        logo_icon.pack(side=tk.LEFT, padx=(0, 12))
        logo_icon.pack_propagate(False)
        tk.Label(logo_icon, text="V", font=("Consolas", 16, "bold"),
                 bg=C["primary"], fg="white").pack(expand=True)

        # 标题 + 副标题（参考网页 .header-logo-text）
        title_frame = tk.Frame(toolbar, bg=C["bg2"])
        title_frame.pack(side=tk.LEFT, padx=(0, 24))
        tk.Label(title_frame, text="VideoCraft", font=("Microsoft YaHei UI", 14, "bold"),
                 bg=C["bg2"], fg=C["text"]).pack(anchor="w")
        tk.Label(title_frame, text="视频处理工具", font=("Microsoft YaHei UI", 9),
                 bg=C["bg2"], fg=C["text3"]).pack(anchor="w")

        # 核心操作按钮（参考网页 .header-nav）
        if HAS_CTK:
            ctk.CTkButton(toolbar, text="添加文件", font=("Microsoft YaHei UI", 11),
                         fg_color=C["primary"], hover_color=C["primary_dark"],
                         corner_radius=6, width=80, height=30,
                         command=self._add_videos).pack(side=tk.LEFT, padx=3)
            ctk.CTkButton(toolbar, text="导入文件夹", font=("Microsoft YaHei UI", 11),
                         fg_color=C["btn"], hover_color=C["btn_hover"],
                         corner_radius=6, width=90, height=30,
                         command=self._import_folder).pack(side=tk.LEFT, padx=3)
            ctk.CTkButton(toolbar, text="开始处理", font=("Microsoft YaHei UI", 11, "bold"),
                         fg_color=C["success"], hover_color=C["success_dark"],
                         corner_radius=6, width=80, height=30,
                         command=self._on_start_click).pack(side=tk.LEFT, padx=3)
            ctk.CTkButton(toolbar, text="停止", font=("Microsoft YaHei UI", 11),
                         fg_color=C["danger"], hover_color=C["danger_dark"],
                         corner_radius=6, width=50, height=30,
                         command=self._on_stop_click).pack(side=tk.LEFT, padx=3)

        # 右侧GPU状态（参考网页 .hero-badge）
        gpu_txt = "NVENC Ready" if self.gpu else "CPU Only" 
        if HAS_CTK:
            ctk.CTkLabel(toolbar, text=gpu_txt, font=("Consolas", 10),
                        fg_color=C["success"] if self.gpu else C["warning"],
                        text_color="#111111", corner_radius=10,
                        padx=10, pady=3).pack(side=tk.RIGHT, padx=8)
        else:
            tk.Label(toolbar, text=gpu_txt, font=("Consolas", 10),
                     bg=C["success"] if self.gpu else C["warning"], fg="#111111",
                     padx=10, pady=3).pack(side=tk.RIGHT, padx=8)

        # 分割线
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill=tk.X)

        # ═══════════════════════════════════════
        #  源信息区（参考网页 .hero-stats 设计）
        #  网页设计: 水平排列的统计项，等宽字体
        # ═══════════════════════════════════════
        source_frame = tk.Frame(self.root, bg=C["bg1"], padx=12, pady=4)
        source_frame.pack(fill=tk.X)

        # 源文件信息
        src_col = tk.Frame(source_frame, bg=C["bg1"])
        src_col.pack(side=tk.LEFT, padx=(0, 24))
        tk.Label(src_col, text="源文件", font=("Microsoft YaHei UI", 8),
                 bg=C["bg1"], fg=C["text3"]).pack(anchor="w")
        self.source_info_label = tk.Label(src_col, text="未选择",
                                          font=("Consolas", 10), bg=C["bg1"], fg=C["text2"])
        self.source_info_label.pack(anchor="w")

        # 输出目录
        out_col = tk.Frame(source_frame, bg=C["bg1"])
        out_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(out_col, text="输出目录", font=("Microsoft YaHei UI", 8),
                 bg=C["bg1"], fg=C["text3"]).pack(anchor="w")
        out_row = tk.Frame(out_col, bg=C["bg1"])
        out_row.pack(fill=tk.X, pady=(2, 0))
        self.out_dir = tk.StringVar(value=r"E:\视频")
        if HAS_CTK:
            ctk.CTkEntry(out_row, textvariable=self.out_dir, font=("Consolas", 10),
                        fg_color=C["input"], text_color=C["text"],
                        border_color=C["border"], corner_radius=4,
                        height=26).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ctk.CTkButton(out_row, text="浏览", font=("Microsoft YaHei UI", 9),
                         fg_color=C["btn"], hover_color=C["btn_hover"],
                         corner_radius=4, width=40, height=26,
                         command=lambda: self.out_dir.set(filedialog.askdirectory() or self.out_dir.get())
                         ).pack(side=tk.LEFT, padx=(6, 0))
        else:
            tk.Entry(out_row, textvariable=self.out_dir, font=("Consolas", 10),
                     bg=C["input"], fg=C["text"]).pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Button(out_row, text="浏览", font=("Microsoft YaHei UI", 9),
                      bg=C["btn"], fg=C["text2"],
                      command=lambda: self.out_dir.set(filedialog.askdirectory() or self.out_dir.get())
                      ).pack(side=tk.LEFT, padx=(6, 0))

        # 分割线
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill=tk.X)

        # ═══════════════════════════════════════
        #  模式选择条（参考网页 .mode-tabs 设计）
        #  网页设计: 圆角标签，active状态高亮
        # ═══════════════════════════════════════
        mode_bar = tk.Frame(self.root, bg=C["bg1"], padx=12, pady=4)
        mode_bar.pack(fill=tk.X)
        self.mode_var = tk.StringVar(value="套框")
        self._mode_btns = {}
        modes = [("套框", "套框"), ("画中画", "画中画"),
                 ("横转竖", "横转竖"), ("流水线", "流水线"), ("片头片尾", "片头片尾")]
        for txt, val in modes:
            if HAS_CTK:
                b = ctk.CTkButton(mode_bar, text=txt,
                                 font=("Microsoft YaHei UI", 11),
                                 fg_color=C["btn"], hover_color=C["btn_hover"],
                                 text_color=C["text2"], corner_radius=6,
                                 width=80, height=26,
                                 command=lambda v=val: self._on_mode_click(v))
                self._mode_btns[val] = b
            else:
                b = tk.Radiobutton(mode_bar, text=txt, variable=self.mode_var, value=val,
                                   font=("Microsoft YaHei UI", 11), bg=C["btn"], fg=C["text2"],
                                   activebackground=C["primary"], activeforeground="white",
                                   selectcolor=C["primary"], indicatoron=0,
                                   padx=16, pady=8, relief="flat", borderwidth=0,
                                   command=self._switch_mode)
            b.pack(side=tk.LEFT, padx=(0, 6))
        if HAS_CTK:
            self._update_mode_btn_style()

        # ═══ 左右分栏 ═══
        panes = tk.Frame(self.root, bg=C["bg"])
        panes.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        panes.columnconfigure(0, weight=3)
        panes.columnconfigure(1, weight=2)
        panes.rowconfigure(0, weight=1)

        # ── 左栏：模式内容区（可滚动） + 视频列表（固定底部）──
        left = tk.Frame(panes, bg=C["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        left.rowconfigure(0, weight=1)  # 模式内容区可伸缩
        left.rowconfigure(1, weight=0)  # 视频列表固定
        left.columnconfigure(0, weight=1)

        # 模式内容区 — 用Canvas+Scrollbar实现滚动
        mode_outer = tk.Frame(left, bg=C["bg"])
        mode_outer.grid(row=0, column=0, sticky="nsew")
        mode_canvas = tk.Canvas(mode_outer, bg=C["bg"], highlightthickness=0)
        mode_scrollbar = tk.Scrollbar(mode_outer, orient=tk.VERTICAL, command=mode_canvas.yview)
        self.content = tk.Frame(mode_canvas, bg=C["bg"])
        self.content.bind("<Configure>", lambda e: mode_canvas.configure(scrollregion=mode_canvas.bbox("all")))
        mode_canvas.create_window((0, 0), window=self.content, anchor="nw")
        mode_canvas.configure(yscrollcommand=mode_scrollbar.set)
        mode_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        mode_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # 左栏滚轮：进入时绑定，离开时解绑
        def _bind_left_scroll(e):
            mode_canvas.bind_all("<MouseWheel>", lambda ev: mode_canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units"))
        def _unbind_left_scroll(e):
            mode_canvas.unbind_all("<MouseWheel>")
        mode_canvas.bind("<Enter>", _bind_left_scroll)
        mode_canvas.bind("<Leave>", _unbind_left_scroll)

        # 统一视频列表（固定底部，只创建一次）
        video_list_frame = tk.Frame(left, bg=C["bg"])
        video_list_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._build_video_list(video_list_frame)

        # ── 右栏：设置 + 控制 ──
        right = tk.Frame(panes, bg=C["bg"])
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 0))

        # 右栏用Canvas+Scrollbar实现滚动（小屏幕也能用）
        right_canvas = tk.Canvas(right, bg=C["bg"], highlightthickness=0)
        right_scrollbar = tk.Scrollbar(right, orient=tk.VERTICAL, command=right_canvas.yview)
        self.right_inner = tk.Frame(right_canvas, bg=C["bg"])
        self.right_inner.bind("<Configure>", lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
        right_canvas.create_window((0, 0), window=self.right_inner, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # 鼠标滚轮支持（仅在右栏Canvas上生效，不全局绑定）
        def _on_right_mousewheel(event):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        right_canvas.bind("<MouseWheel>", _on_right_mousewheel)
        # 鼠标进入右栏时绑定滚轮，离开时解绑，避免干扰其他区域
        def _bind_scroll(e):
            right_canvas.bind_all("<MouseWheel>", _on_right_mousewheel)
        def _unbind_scroll(e):
            right_canvas.unbind_all("<MouseWheel>")
        right_canvas.bind("<Enter>", _bind_scroll)
        right_canvas.bind("<Leave>", _unbind_scroll)

        ri = self.right_inner  # 简写

        # 编码设置
        ef = self._card(ri)
        if HAS_CTK:
            ctk.CTkLabel(ef, text="编码设置", font=("Microsoft YaHei UI", 10, "bold"),
                         text_color=C["text"]).pack(anchor="w")
        else:
            tk.Label(ef, text="⚙️ 编码设置", font=("Microsoft YaHei UI", 10, "bold"),
                     bg=C["card"], fg=C["text"]).pack(anchor="w")

        erow = tk.Frame(ef, bg=C["card"])
        erow.pack(fill=tk.X, pady=(2, 0))
        if HAS_CTK:
            ctk.CTkLabel(erow, text="编码:", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT)
        else:
            tk.Label(erow, text="编码:", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
        self.codec_var = tk.StringVar(value="hevc_nvenc" if self.gpu else "libx265")
        codec_cb = ttk.Combobox(erow, textvariable=self.codec_var, values=["hevc_nvenc", "h264_nvenc", "libx265", "libx264"],
                     state="readonly", width=12)
        codec_cb.pack(side=tk.LEFT, padx=4)
        if HAS_CTK:
            ctk.CTkLabel(erow, text="码率:", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT, padx=(8, 0))
        else:
            tk.Label(erow, text="码率:", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(8, 0))
        self.bitrate_var = tk.StringVar(value="8000")
        if HAS_CTK:
            ctk.CTkEntry(erow, textvariable=self.bitrate_var, font=("Microsoft YaHei UI", 9),
                         width=50, fg_color=C["input"], text_color=C["text"],
                         border_color=C["border"], corner_radius=4, height=24).pack(side=tk.LEFT, padx=4)
            ctk.CTkLabel(erow, text="kbps", font=("Microsoft YaHei UI", 9), text_color=C["text2"]).pack(side=tk.LEFT)
        else:
            tk.Entry(erow, textvariable=self.bitrate_var, font=("Microsoft YaHei UI", 9),
                     width=6, bg=C["input"], fg=C["text"], insertbackground=C["text"],
                     relief="flat").pack(side=tk.LEFT, padx=4)
            tk.Label(erow, text="kbps", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text2"]).pack(side=tk.LEFT)

        # 编码预设
        if HAS_CTK:
            ctk.CTkLabel(erow, text="预设:", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT, padx=(8, 0))
        else:
            tk.Label(erow, text="预设:", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(8, 0))
        self.preset_var = tk.StringVar(value="自定义")
        self._presets = {
            "自定义": {},
            "🎬 高质量 (慢)": {"codec": "hevc_nvenc", "bitrate": "12000"},
            "⚡ 快速 (中)": {"codec": "hevc_nvenc", "bitrate": "6000"},
            "📦 小文件 (低)": {"codec": "libx265", "bitrate": "3000"},
            "🎯 B站推荐": {"codec": "hevc_nvenc", "bitrate": "4500"},
            "🖥️ 软件H265": {"codec": "libx265", "bitrate": "6000"},
            "🖥️ 软件H264": {"codec": "libx264", "bitrate": "8000"},
        }
        preset_cb = ttk.Combobox(erow, textvariable=self.preset_var,
                     values=list(self._presets.keys()),
                     state="readonly", width=14)
        preset_cb.pack(side=tk.LEFT, padx=4)
        preset_cb.bind("<<ComboboxSelected>>", self._apply_preset)

        # 合并选项
        erow2 = tk.Frame(ef, bg=C["card"])
        erow2.pack(fill=tk.X, pady=(4, 0))
        self.merge_var = tk.BooleanVar(value=False)
        self.segment_var = tk.BooleanVar(value=False)
        self.segment_minutes_var = tk.IntVar(value=90)
        self.batch_output_var = tk.BooleanVar(value=False)
        self.batch_episodes_var = tk.IntVar(value=11)
        if HAS_CTK:
            ctk.CTkCheckBox(erow2, text="合并", variable=self.merge_var,
                           font=("Microsoft YaHei UI", 9),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4,
                           command=self._toggle_merge).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(erow2, text="合并", variable=self.merge_var,
                           font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["card"],
                           command=self._toggle_merge).pack(side=tk.LEFT)
        self.merge_mode = tk.StringVar(value="count")
        tk.Radiobutton(erow2, text="按数量", variable=self.merge_mode, value="count",
                       font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text"],
                       selectcolor=C["card"], activebackground=C["card"],
                       command=self._toggle_merge).pack(side=tk.LEFT, padx=(6, 0))
        self.merge_count = tk.IntVar(value=2)
        self.merge_count_spin = tk.Spinbox(erow2, from_=2, to=20, textvariable=self.merge_count, width=3,
                   font=("Microsoft YaHei UI", 9), bg=C["input"], fg=C["text"],
                   buttonbackground=C["btn"], insertbackground=C["text"],
                   state="disabled")
        self.merge_count_spin.pack(side=tk.LEFT, padx=2)
        if HAS_CTK:
            ctk.CTkLabel(erow2, text="个合1", font=("Microsoft YaHei UI", 8), text_color=C["text2"]).pack(side=tk.LEFT)
        else:
            tk.Label(erow2, text="个合1", font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text2"]).pack(side=tk.LEFT)
        tk.Radiobutton(erow2, text="文件夹合1", variable=self.merge_mode, value="folder",
                       font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text"],
                       selectcolor=C["card"], activebackground=C["card"],
                       command=self._toggle_merge).pack(side=tk.LEFT, padx=(8, 0))

        # 并行处理 + 游戏模式
        erow3 = tk.Frame(ef, bg=C["card"])
        erow3.pack(fill=tk.X, pady=(4, 0))
        self.parallel_var = tk.IntVar(value=1)
        if HAS_CTK:
            ctk.CTkLabel(erow3, text="并行:", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT)
        else:
            tk.Label(erow3, text="🚀 并行:", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
        tk.Spinbox(erow3, from_=1, to=4, textvariable=self.parallel_var, width=2,
                   font=("Microsoft YaHei UI", 9), bg=C["input"], fg=C["text"],
                   buttonbackground=C["btn"], insertbackground=C["text"]).pack(side=tk.LEFT, padx=2)
        if HAS_CTK:
            ctk.CTkLabel(erow3, text="路", font=("Microsoft YaHei UI", 8), text_color=C["text2"]).pack(side=tk.LEFT)
            ctk.CTkLabel(erow3, text="(多文件同时处理)", font=("Microsoft YaHei UI", 8), text_color=C["text3"]).pack(side=tk.LEFT, padx=(2, 0))
        else:
            tk.Label(erow3, text="路", font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text2"]).pack(side=tk.LEFT)
            tk.Label(erow3, text="(多文件同时处理)", font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT, padx=(2, 0))

        # 游戏模式 + 片头片尾
        erow4 = tk.Frame(ef, bg=C["card"])
        erow4.pack(fill=tk.X, pady=(4, 0))
        self.game_mode = tk.BooleanVar(value=False)
        if HAS_CTK:
            ctk.CTkCheckBox(erow4, text="游戏模式", variable=self.game_mode,
                           font=("Microsoft YaHei UI", 9),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(erow4, text="🎮 游戏模式", variable=self.game_mode,
                           font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["card"]).pack(side=tk.LEFT)
        if HAS_CTK:
            ctk.CTkLabel(erow4, text="片头:", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT, padx=(12, 0))
            self.intro_label = ctk.CTkLabel(erow4, text="无", font=("Microsoft YaHei UI", 8), text_color=C["text3"])
        else:
            tk.Label(erow4, text="片头:", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(12, 0))
            self.intro_label = tk.Label(erow4, text="无", font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text3"])
        self.intro_label.pack(side=tk.LEFT, padx=2)
        self._btn(erow4, "选择", self._select_intro, "btn").pack(side=tk.LEFT, padx=1)
        self._btn(erow4, "x", lambda: self._clear_intro_outro("intro"), "btn").pack(side=tk.LEFT, padx=(0, 8))
        if HAS_CTK:
            ctk.CTkLabel(erow4, text="片尾:", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT)
            self.outro_label = ctk.CTkLabel(erow4, text="无", font=("Microsoft YaHei UI", 8), text_color=C["text3"])
        else:
            tk.Label(erow4, text="片尾:", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
            self.outro_label = tk.Label(erow4, text="无", font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text3"])
        self.outro_label.pack(side=tk.LEFT, padx=2)
        self._btn(erow4, "选择", self._select_outro, "btn").pack(side=tk.LEFT, padx=1)
        self._btn(erow4, "x", lambda: self._clear_intro_outro("outro"), "btn").pack(side=tk.LEFT)

        # 开始/停止按钮（参考网页 .btn-success 设计）
        bf = self._card(ri, pady=12)
        btn_row = tk.Frame(bf, bg=C["card"])
        btn_row.pack(fill=tk.X)
        if HAS_CTK:
            self.btn_start = ctk.CTkButton(btn_row, text="开始处理",
                                          font=("Microsoft YaHei UI", 13, "bold"),
                                          fg_color=C["success"], hover_color=C["success_dark"],
                                          text_color="#111111", corner_radius=8,
                                          height=40, command=self._on_start_click)
            self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.btn_stop = ctk.CTkButton(btn_row, text="停止",
                                         font=("Microsoft YaHei UI", 12),
                                         fg_color=C["danger"], hover_color=C["danger_dark"],
                                         text_color="white", corner_radius=8,
                                         width=70, height=40,
                                         command=self._on_stop_click, state="disabled")
            self.btn_stop.pack(side=tk.LEFT, padx=(10, 0))
        else:
            self.btn_start = tk.Button(btn_row, text="开始处理",
                                       font=("Microsoft YaHei UI", 12, "bold"),
                                       bg=C["success"], fg="#111111", relief="flat",
                                       activebackground=C["success_dark"],
                                       padx=20, pady=10, cursor="hand2", command=self._start)
            self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.btn_stop = tk.Button(btn_row, text="停止", font=("Microsoft YaHei UI", 11),
                                      bg=C["danger"], fg="white", relief="flat",
                                      activebackground=C["danger_dark"],
                                      padx=12, pady=10, cursor="hand2", command=self._stop,
                                      state="disabled")
            self.btn_stop.pack(side=tk.LEFT, padx=(10, 0))

        # 总进度条（参考网页 .progress-bar 设计）
        pf = tk.Frame(bf, bg=C["card"])
        pf.pack(fill=tk.X, pady=(10, 0))
        self.progress = ttk.Progressbar(pf, mode="determinate", maximum=100,
                                        style="Dark.Horizontal.TProgressbar")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if HAS_CTK:
            self.lbl_eta = ctk.CTkLabel(pf, text="", font=("Consolas", 10, "bold"),
                                        text_color=C["primary"], padx=6)
        else:
            self.lbl_eta = tk.Label(pf, text="", font=("Consolas", 10, "bold"),
                                    bg=C["card"], fg=C["primary"], padx=6)
        self.lbl_eta.pack(side=tk.LEFT)

        # 多路并行状态面板（动态创建/销毁）
        self.worker_panel = tk.Frame(bf, bg=C["card"])
        self.worker_panel.pack(fill=tk.X, pady=(4, 0))
        self._worker_widgets = {}

        # 状态指示器
        if HAS_CTK:
            self.lbl_status = ctk.CTkLabel(ri, text="就绪 - 选择文件后点击开始",
                                           font=("Microsoft YaHei UI", 10),
                                           fg_color=C["primary_light"], text_color=C["primary"],
                                           corner_radius=6, padx=12, pady=8)
        else:
            self.lbl_status = tk.Label(ri, text="就绪 · 选择文件后点击开始",
                                       font=("Microsoft YaHei UI", 10), bg=C["primary_light"],
                                       fg=C["primary"], padx=12, pady=8)
        self.lbl_status.pack(fill=tk.X, pady=(0, 8))

        # 命令预览
        cpf = self._card(ri)
        if HAS_CTK:
            ctk.CTkLabel(cpf, text="命令预览", font=("Consolas", 10, "bold"),
                         text_color=C["text2"]).pack(anchor="w")
        else:
            tk.Label(cpf, text="命令预览", font=("Consolas", 10, "bold"),
                     bg=C["card"], fg=C["text2"]).pack(anchor="w")
        self.cmd_preview = tk.Text(cpf, height=3, font=("Consolas", 9), bg=C["code_bg"],
                                fg=C["code_fg"], relief="flat", wrap=tk.WORD,
                                insertbackground=C["text"], state=tk.DISABLED)
        self.cmd_preview.pack(fill=tk.X, pady=(6, 0))

        # 日志
        lf = self._card(ri, fill=tk.BOTH, expand=True, pady_pack=(0, 0))
        if HAS_CTK:
            ctk.CTkLabel(lf, text="处理日志", font=("Consolas", 10, "bold"),
                         text_color=C["text2"]).pack(anchor="w")
        else:
            tk.Label(lf, text="处理日志", font=("Consolas", 10, "bold"),
                     bg=C["card"], fg=C["text2"]).pack(anchor="w")
        self.log_text = tk.Text(lf, height=6, font=("Consolas", 9), bg=C["code_bg"],
                                fg=C["code_fg"], relief="flat", wrap=tk.WORD,
                                insertbackground=C["text"])
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        # 绑定变量变化更新预览
        self.codec_var.trace_add("write", lambda *a: self._update_cmd_preview())
        self.bitrate_var.trace_add("write", lambda *a: self._update_cmd_preview())
        self._switch_mode()

    # ═══════════════════════════════════════
    #  模式切换
    # ═══════════════════════════════════════
    def _on_mode_click(self, val):
        self.mode_var.set(val)
        self._update_mode_btn_style()
        self._switch_mode()

    def _update_mode_btn_style(self):
        cur = self.mode_var.get()
        for v, btn in self._mode_btns.items():
            if v == cur:
                btn.configure(fg_color=C["primary"], text_color="white")
            else:
                btn.configure(fg_color=C["btn"], text_color=C["text2"])

    def _switch_mode(self):
        for w in self.content.winfo_children():
            w.destroy()
        mode = self.mode_var.get()
        if mode == "套框":
            self._build_frame_page()
        elif mode == "画中画":
            self._build_pip_page()
        elif mode == "横转竖":
            self._build_rotate_page()
        elif mode == "流水线":
            self._build_pipeline_page()
        elif mode == "片头片尾":
            self._build_intro_outro_page()
        self._update_cmd_preview()

    # ═══════════════════════════════════════
    #  统一视频列表构建
    # ═══════════════════════════════════════
    def _build_video_list(self, parent, height=4):
        """统一的视频文件列表UI（参考网页 .card 设计）"""
        # 使用 _card 辅助方法创建带边框的卡片
        outer = tk.Frame(parent, bg=C["card_border"], padx=1, pady=1)
        vf = tk.Frame(outer, bg=C["card"], padx=12, pady=8)
        vf.pack(fill=tk.BOTH, expand=True)
        outer.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # 标题栏
        title_row = tk.Frame(vf, bg=C["card"])
        title_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(title_row, text="视频文件", font=("Microsoft YaHei UI", 12, "bold"),
                 bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
        # 文件计数
        self.video_count_label = tk.Label(title_row, text="0 个文件",
                                          font=("Consolas", 10), bg=C["card"], fg=C["text3"])
        self.video_count_label.pack(side=tk.RIGHT)

        # 列表框 — 带边框
        list_border = tk.Frame(vf, bg=C["border"], padx=1, pady=1)
        list_border.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        vrow = tk.Frame(list_border, bg=C["input"])
        vrow.pack(fill=tk.BOTH, expand=True)
        self.video_listbox = tk.Listbox(vrow, height=height, font=("Consolas", 10),
                                        bg=C["input"], fg=C["text1"],
                                        selectbackground=C["primary"],
                                        selectforeground="white",
                                        highlightthickness=0,
                                        relief="flat",
                                        borderwidth=0)
        self.video_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(vrow, command=self.video_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.video_listbox.configure(yscrollcommand=sb.set)

        # 操作按钮栏（参考网页 .btn 设计）
        bb = tk.Frame(vf, bg=C["card"])
        bb.pack(fill=tk.X)
        buttons = [
            ("添加视频", self._add_videos, C["primary"]),
            ("导入文件夹", self._import_folder, C["btn"]),
            ("文件夹合并", self._folder_merge, C["btn"]),
            ("批量合并", self._batch_folder_merge, C["btn"]),
            ("移除", self._remove_selected, C["btn"]),
            ("清空", self._clear_all, C["btn"]),
        ]
        for txt, cmd, bg in buttons:
            tk.Button(bb, text=txt, font=("Microsoft YaHei UI", 9),
                      bg=bg, fg=C["text1"] if bg == C["btn"] else "white",
                      activebackground=C["btn_hover"] if bg == C["btn"] else C["primary_dark"],
                      relief="flat", padx=10, pady=4, cursor="hand2",
                      command=cmd).pack(side=tk.LEFT, padx=(0, 6))

        # 恢复数据显示
        for f in self.videos:
            self.video_listbox.insert(tk.END, os.path.basename(f))
        for g in self.folder_groups:
            self.video_listbox.insert(tk.END, f"{g['name']} ({len(g['videos'])}个视频)")
        self._update_video_count()

        # 设置拖拽
        self._setup_listbox_dnd()

    def _update_video_count(self):
        """更新视频文件计数"""
        if hasattr(self, 'video_count_label'):
            count = len(self.videos) + len(self.folder_groups)
            self.video_count_label.configure(text=f"{count} 个文件")

    def _setup_listbox_dnd(self):
        """为当前listbox设置拖拽"""
        if HAS_DND and hasattr(self, 'video_listbox'):
            try:
                self.video_listbox.drop_target_register(tkinterdnd2.DND_FILES)
                self.video_listbox.dnd_bind('<<Drop>>', self._on_listbox_drop)
            except Exception as e:
                self._log(f"⚠️ Listbox拖拽绑定失败: {e}")

    # ═══════════════════════════════════════
    #  统一文件管理
    # ═══════════════════════════════════════
    def _add_videos(self):
        files = filedialog.askopenfilenames(filetypes=[("视频", "*.mp4 *.mkv *.avi *.flv *.ts")])
        for f in files:
            if f not in self.videos:
                self.videos.append(f)
                self.video_listbox.insert(tk.END, os.path.basename(f))
        if files:
            self._save_config()
            self._update_source_info()

    def _update_source_info(self):
        """更新源信息显示"""
        if not hasattr(self, 'source_info_label'):
            return
        if self.videos:
            count = len(self.videos)
            total_size = sum(os.path.getsize(f) for f in self.videos if os.path.exists(f))
            size_mb = total_size / 1024 / 1024
            info = f"{count}个文件, {size_mb:.0f}MB"
            self._configure_label(self.source_info_label, text=info, fg=C["text"])
        elif self.folder_groups:
            total = sum(len(g["videos"]) for g in self.folder_groups)
            info = f"{len(self.folder_groups)}个文件夹, {total}个视频"
            self._configure_label(self.source_info_label, text=info, fg=C["text"])
        else:
            self._configure_label(self.source_info_label, text="未选择文件", fg=C["text3"])

    def _import_folder(self):
        """导入文件夹：加载所有视频，自动合并"""
        d = filedialog.askdirectory()
        if not d:
            return
        videos = sorted([os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(VIDEO_EXTS)], key=_natural_sort_key)
        if not videos:
            messagebox.showwarning("提示", "文件夹内没有视频文件")
            return
        self.video_listbox.delete(0, tk.END)
        self.videos.clear()
        self.folder_groups.clear()
        for v in videos:
            self.videos.append(v)
            self.video_listbox.insert(tk.END, os.path.basename(v))
        folder_name = os.path.basename(d)
        self.folder_name = folder_name
        self.folder_groups.append({"name": folder_name, "videos": videos})
        self._log(f"📂 导入文件夹: {d} ({len(videos)}个视频) → 自动合并模式")
        self._save_config()
        self._update_source_info()

    def _folder_merge(self):
        """文件夹合并：导入文件夹内所有视频，合并为1个"""
        d = filedialog.askdirectory()
        if not d:
            return
        videos = sorted([os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(VIDEO_EXTS)], key=_natural_sort_key)
        if not videos:
            messagebox.showwarning("提示", "文件夹内没有视频文件")
            return
        self.video_listbox.delete(0, tk.END)
        self.videos.clear()
        self.folder_groups.clear()
        for v in videos:
            self.videos.append(v)
            self.video_listbox.insert(tk.END, os.path.basename(v))
        self.folder_name = os.path.basename(d)
        self.merge_var.set(True)
        self.merge_count.set(len(videos))
        self._toggle_merge()
        self._log(f"📂 文件夹合并: {d} ({len(videos)}个视频 → 合并为1个)")
        self._save_config()

    def _batch_folder_merge(self):
        """批量导入文件夹：逐个文件夹处理"""
        while True:
            d = filedialog.askdirectory(title=f"选择文件夹（已选{len(self.folder_groups)}个，取消结束）")
            if not d:
                break
            folder_videos = sorted([os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(VIDEO_EXTS)], key=_natural_sort_key)
            if not folder_videos:
                messagebox.showwarning("提示", f"文件夹内没有视频文件:\n{d}")
                continue
            folder_name = os.path.basename(d)
            self.folder_groups.append({"name": folder_name, "videos": folder_videos})
            self.video_listbox.insert(tk.END, f"📁 {folder_name} ({len(folder_videos)}个视频)")
            self._log(f"📁 添加文件夹: {folder_name} ({len(folder_videos)}个视频)")
        if self.folder_groups:
            self._log(f"📁 共添加{len(self.folder_groups)}个文件夹，处理时自动逐个合并")
            self._save_config()

    def _remove_selected(self):
        sel = self.video_listbox.curselection()
        if not sel:
            return
        video_count = len(self.videos)
        for i in reversed(sel):
            self.video_listbox.delete(i)
            if i < video_count:
                self.videos.pop(i)
            else:
                gi = i - video_count
                if 0 <= gi < len(self.folder_groups):
                    self.folder_groups.pop(gi)
        self._save_config()
        self._update_video_count()
        self._update_source_info()

    def _clear_all(self):
        self.video_listbox.delete(0, tk.END)
        self.videos.clear()
        self.folder_groups.clear()
        self.folder_name = None
        self._save_config()

    # ═══════════════════════════════════════
    #  统一拖拽处理
    # ═══════════════════════════════════════
    def _init_drag_drop(self):
        if HAS_DND:
            try:
                self.root.drop_target_register(tkinterdnd2.DND_FILES)
                self.root.dnd_bind('<<Drop>>', self._on_drop)
            except Exception as e:
                print(f"⚠️ 拖拽初始化失败: {e}")

    def _on_drop(self, event):
        if event.data:
            files = self._parse_drop_data(event.data)
            self._process_dropped_items(files)

    def _on_listbox_drop(self, event):
        if event.data:
            files = self._parse_drop_data(event.data)
            self._process_dropped_items(files)

    def _parse_drop_data(self, data):
        files = []
        if isinstance(data, str):
            parts = re.findall(r'\{([^}]+)\}|([^\s]+)', data)
            for part in parts:
                path = part[0] if part[0] else part[1]
                if path:
                    files.append(path)
        return files

    def _process_dropped_items(self, items):
        if not items:
            return
        folders, video_files = [], []
        for item in items:
            if os.path.isdir(item):
                vids = [f for f in os.listdir(item) if f.lower().endswith(VIDEO_EXTS)]
                if vids:
                    folders.append(item)
                else:
                    self._log(f"⚠️ 文件夹内没有视频文件: {os.path.basename(item)}")
            elif os.path.isfile(item) and item.lower().endswith(VIDEO_EXTS):
                video_files.append(item)

        if folders:
            for folder in folders:
                folder_name = os.path.basename(folder)
                folder_videos = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(VIDEO_EXTS)], key=_natural_sort_key)
                if not any(g['name'] == folder_name for g in self.folder_groups):
                    self.folder_groups.append({"name": folder_name, "videos": folder_videos})
                    if hasattr(self, 'video_listbox'):
                        self.video_listbox.insert(tk.END, f"📁 {folder_name} ({len(folder_videos)}个视频)")
                    self._log(f"📁 拖拽添加文件夹: {folder_name} ({len(folder_videos)}个视频)")
                else:
                    self._log(f"⚠️ 文件夹已存在: {folder_name}")
            self._save_config()

        if video_files:
            for video in video_files:
                if video not in self.videos:
                    self.videos.append(video)
                    if hasattr(self, 'video_listbox'):
                        self.video_listbox.insert(tk.END, os.path.basename(video))
            self._save_config()

        if folders or video_files:
            self._log(f"📊 当前: {len(self.folder_groups)}个文件夹, {len(self.videos)}个视频")

    # ═══════════════════════════════════════
    #  页面1: 视频套框
    # ═══════════════════════════════════════
    def _build_frame_page(self):
        card = self._card(self.content, padx=12, pady=10)

        ctk.CTkLabel(card, text="模板 / 背景", font=("Microsoft YaHei UI", 12, "bold"),
                     text_color=C["text"]).pack(anchor="w") if HAS_CTK else tk.Label(card, text="模板 / 背景", font=("Microsoft YaHei UI", 12, "bold"), bg=C["card"], fg=C["text"]).pack(anchor="w")
        ctk.CTkLabel(card, text="选择模板图片或纯色背景，然后框选视频区域",
                     font=("Microsoft YaHei UI", 9), text_color=C["text3"]).pack(anchor="w", pady=(2, 8)) if HAS_CTK else tk.Label(card, text="选择模板图片或纯色背景，然后框选视频区域", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w", pady=(2, 8))

        tr = tk.Frame(card, bg=C["card"])
        tr.pack(fill=tk.X)
        if HAS_CTK:
            self.frame_template_label = ctk.CTkLabel(tr, text="未选择模板", font=("Consolas", 10),
                                                     fg_color=C["input"], text_color=C["text3"],
                                                     corner_radius=4, anchor="w", padx=10, pady=8)
        else:
            self.frame_template_label = tk.Label(tr, text="未选择模板", font=("Consolas", 10),
                                                 bg=C["input"], fg=C["text3"], anchor="w", padx=10, pady=8)
        self.frame_template_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn(tr, "选择模板", self._frame_load_template, "primary").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(tr, "纯色背景", self._pick_bg_color, "warning").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(tr, "框选区域", self._frame_select_roi, "warning").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(tr, "保存", lambda: (self._save_config(), messagebox.showinfo("保存", "套框模板和区域设置已保存！")),
                  "success").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(tr, "预览", self._frame_preview, "btn").pack(side=tk.LEFT, padx=(8, 0))
        if HAS_CTK:
            self.frame_roi_label = ctk.CTkLabel(card, text="", font=("Consolas", 10), text_color=C["text2"])
        else:
            self.frame_roi_label = tk.Label(card, text="", font=("Consolas", 10), bg=C["card"], fg=C["text2"])
        self.frame_roi_label.pack(anchor="w", pady=(6, 0))

        # 恢复数据显示
        if self.bg_color:
            self._configure_label(self.frame_template_label, text=f"纯色背景: {self.bg_color}", fg=C["text"])
        elif self.frame_template:
            if HAS_CTK:
                self.frame_template_label.configure(text=os.path.basename(self.frame_template), text_color=C["text"])
            else:
                self._configure_label(self.frame_template_label, text=os.path.basename(self.frame_template), fg=C["text"])
        if self.frame_roi:
            x, y, w, h = self.frame_roi
            w, h = w // 2 * 2, h // 2 * 2
            self.frame_roi_label.configure(text=f"已框选: x={x} y={y} w={w} h={h}")

    def _frame_load_template(self):
        p = filedialog.askopenfilename(filetypes=[("媒体文件", "*.png *.jpg *.jpeg *.bmp *.mp4 *.mkv *.avi *.flv *.ts")])
        if p:
            self.frame_template = p
            self.bg_color = None  # 清除纯色背景
            ext = os.path.splitext(p)[1].lower()
            is_video = ext in VIDEO_EXTS
            label = f"{'🎬' if is_video else '🖼'} {os.path.basename(p)}"
            self._configure_label(self.frame_template_label, text=label, fg=C["text"])
            self._save_config()

    def _pick_bg_color(self):
        """选择纯色背景颜色"""
        try:
            from tkinter import colorchooser
            color = colorchooser.askcolor(title="选择背景颜色", initialcolor="#000000")
            if color[1]:
                self.bg_color = color[1]  # hex like "#000000"
                self.frame_template = None  # 清除模板
                self._configure_label(self.frame_template_label, text=f"纯色背景: {self.bg_color}", fg=C["text"])
                # 纯色背景需要输出分辨率
                if not hasattr(self, 'output_resolution'):
                    self.output_resolution = "1920x1080"
                self._save_config()
        except Exception as e:
            self._log(f"⚠️ 颜色选择失败: {e}")

    def _frame_select_roi(self):
        if not self.frame_template and not self.bg_color:
            messagebox.showwarning("提示", "请先选择模板图片或设置纯色背景"); return
        try:
            import cv2

            if self.bg_color:
                # 纯色背景：创建纯色图片用于框选
                res = getattr(self, 'output_resolution', '1920x1080')
                ow, oh = map(int, res.split('x'))
                hex_color = self.bg_color.lstrip('#')
                r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
                img = np.full((oh, ow, 3), (b, g, r), dtype=np.uint8)
            else:
                ext = os.path.splitext(self.frame_template)[1].lower()
                is_video = ext in VIDEO_EXTS

                if is_video:
                    cap = cv2.VideoCapture(self.frame_template)
                    ret, img = cap.read()
                    cap.release()
                    if not ret:
                        messagebox.showerror("错误", "无法读取视频模板第一帧"); return
                else:
                    from PIL import Image, ExifTags
                    pil_img = Image.open(self.frame_template)
                    try:
                        exif = pil_img._getexif()
                        if exif:
                            for tag, val in exif.items():
                                if ExifTags.TAGS.get(tag) == 'Orientation':
                                    if val == 3: pil_img = pil_img.rotate(180, expand=True)
                                    elif val == 6: pil_img = pil_img.rotate(270, expand=True)
                                    elif val == 8: pil_img = pil_img.rotate(90, expand=True)
                                    break
                    except: pass
                    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            if img is None:
                messagebox.showerror("错误", "无法读取模板图片"); return
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            h, w = img.shape[:2]
            scale = min((screen_w - 40) / w, (screen_h - 80) / h, 1.0)
            disp = cv2.resize(img, (int(w * scale), int(h * scale)))

            messagebox.showinfo("框选步骤",
                "1. 用鼠标在图片上拖拽画出矩形框\n"
                "2. 按 Enter 确认\n"
                "3. 按 ESC 取消")

            roi = cv2.selectROI("用鼠标拖拽框选视频区域 → 按Enter确认", disp, showCrosshair=True)
            cv2.destroyAllWindows()
            if roi[2] > 0 and roi[3] > 0:
                self.frame_roi = (int(roi[0]/scale), int(roi[1]/scale), int(roi[2]/scale), int(roi[3]/scale))
                x, y, w2, h2 = self.frame_roi
                self.frame_roi_label.configure(text=f"✅ 已框选: x={x} y={y} w={w2} h={h2}")
                self._save_config()
            else:
                messagebox.showwarning("提示", "未选择区域")
        except ImportError:
            messagebox.showerror("错误", "需要安装opencv: pip install opencv-python")

    # ═══════════════════════════════════════
    #  页面2: 画中画
    # ═══════════════════════════════════════
    def _build_pip_page(self):
        card = self._card(self.content, padx=12, pady=10)

        if HAS_CTK:
            ctk.CTkLabel(card, text="模板", font=("Microsoft YaHei UI", 12, "bold"),
                         text_color=C["text"]).pack(anchor="w")
            ctk.CTkLabel(card, text="选择背景模板，然后框选各区域",
                         font=("Microsoft YaHei UI", 9), text_color=C["text3"]).pack(anchor="w", pady=(2, 8))
        else:
            tk.Label(card, text="模板", font=("Microsoft YaHei UI", 12, "bold"),
                     bg=C["card"], fg=C["text"]).pack(anchor="w")
            tk.Label(card, text="选择背景模板，然后框选各区域",
                     font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w", pady=(2, 8))

        tr = tk.Frame(card, bg=C["card"])
        tr.pack(fill=tk.X)
        if HAS_CTK:
            self.pip_template_label = ctk.CTkLabel(tr, text="未选择模板", font=("Consolas", 10),
                                                    fg_color=C["input"], text_color=C["text3"],
                                                    corner_radius=4, anchor="w", padx=10, pady=8)
        else:
            self.pip_template_label = tk.Label(tr, text="未选择模板", font=("Consolas", 10),
                                               bg=C["input"], fg=C["text3"], anchor="w", padx=10, pady=8)
        self.pip_template_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn(tr, "选择模板", self._pip_load_template, "primary").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(tr, "预览模板", self._pip_preview_template, "btn").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(tr, "保存", lambda: (self._save_config(), messagebox.showinfo("保存", "模板和区域设置已保存！")),
                  "success").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(tr, "预览布局", self._pip_preview, "btn").pack(side=tk.LEFT, padx=(8, 0))

        rr = tk.Frame(card, bg=C["card"])
        rr.pack(fill=tk.X, pady=(10, 0))
        for name, txt, var in [("left", "左区域", self.pip_enable_left), 
                                ("center", "中区域", self.pip_enable_center),
                                ("right", "右区域", self.pip_enable_right)]:
            row = tk.Frame(rr, bg=C["card"])
            row.pack(side=tk.LEFT, padx=(0, 12))
            if HAS_CTK:
                ctk.CTkCheckBox(row, text="", variable=var, width=24,
                               fg_color=C["primary"], hover_color=C["btn_hover"],
                               corner_radius=4).pack(side=tk.LEFT)
            else:
                tk.Checkbutton(row, text="", variable=var, bg=C["card"], fg=C["text"],
                              selectcolor=C["primary"], activebackground=C["card"]).pack(side=tk.LEFT)
            self._btn(row, f"框选{txt}", lambda n=name: self._pip_select_region(n), "btn").pack(side=tk.LEFT, padx=(4, 0))
        if HAS_CTK:
            self.pip_region_label = ctk.CTkLabel(card, text="", font=("Consolas", 10), text_color=C["text2"])
        else:
            self.pip_region_label = tk.Label(card, text="", font=("Consolas", 10), bg=C["card"], fg=C["text2"])
        self.pip_region_label.pack(anchor="w", pady=(6, 0))

        # 恢复数据显示
        if self.pip_template:
            if HAS_CTK:
                self.pip_template_label.configure(text=os.path.basename(self.pip_template), text_color=C["text"])
            else:
                self._configure_label(self.pip_template_label, text=os.path.basename(self.pip_template), fg=C["text"])
        if self.pip_regions:
            txts = [f"{k}: {v}" for k, v in self.pip_regions.items() if getattr(self, f'pip_enable_{k}', tk.BooleanVar(value=True)).get()]
            self.pip_region_label.configure(text="✅ " + " | ".join(txts) if txts else "❌ 未选择区域")

        # 左/右装饰视频（PIP特有）
        decor_frame = tk.Frame(self.content, bg=C["card"], padx=16, pady=8)
        decor_frame.pack(fill=tk.X, pady=(0, 6))
        if HAS_CTK:
            ctk.CTkLabel(decor_frame, text="装饰视频（可选）", font=("Microsoft YaHei UI", 10, "bold"),
                         text_color=C["text"]).pack(anchor="w")
        else:
            tk.Label(decor_frame, text="🎨 装饰视频（可选）", font=("Microsoft YaHei UI", 10, "bold"),
                     bg=C["card"], fg=C["text"]).pack(anchor="w")
        decor_row = tk.Frame(decor_frame, bg=C["card"])
        decor_row.pack(fill=tk.X, pady=4)
        
        # 左装饰
        if HAS_CTK:
            ctk.CTkCheckBox(decor_row, text="", variable=self.pip_enable_left_decor, width=24,
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           corner_radius=4).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(decor_row, text="", variable=self.pip_enable_left_decor, bg=C["card"],
                          fg=C["text"], selectcolor=C["primary"], activebackground=C["card"]).pack(side=tk.LEFT)
        if HAS_CTK:
            self.pip_left_label = ctk.CTkLabel(decor_row, text="左装饰: 无", font=("Microsoft YaHei UI", 9), text_color=C["text3"])
        else:
            self.pip_left_label = tk.Label(decor_row, text="左装饰: 无", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"])
        self.pip_left_label.pack(side=tk.LEFT, padx=(4, 10))
        self._btn(decor_row, "选择左", lambda: self._pip_select_decor("left"), "btn").pack(side=tk.LEFT, padx=(0, 20))
        
        # 右装饰
        if HAS_CTK:
            ctk.CTkCheckBox(decor_row, text="", variable=self.pip_enable_right_decor, width=24,
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           corner_radius=4).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(decor_row, text="", variable=self.pip_enable_right_decor, bg=C["card"],
                          fg=C["text"], selectcolor=C["primary"], activebackground=C["card"]).pack(side=tk.LEFT)
        if HAS_CTK:
            self.pip_right_label = ctk.CTkLabel(decor_row, text="右装饰: 无", font=("Microsoft YaHei UI", 9), text_color=C["text3"])
        else:
            self.pip_right_label = tk.Label(decor_row, text="右装饰: 无", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"])
        self.pip_right_label.pack(side=tk.LEFT, padx=(4, 10))
        self._btn(decor_row, "选择右", lambda: self._pip_select_decor("right"), "btn").pack(side=tk.LEFT)
        # 恢复装饰视频显示
        if self.pip_left_files:
            if HAS_CTK:
                self.pip_left_label.configure(text=f"左装饰: {os.path.basename(self.pip_left_files[0])}", text_color=C["text"])
            else:
                self._configure_label(self.pip_left_label, text=f"左装饰: {os.path.basename(self.pip_left_files[0])}", fg=C["text"])
            # 选中高亮
            if HAS_CTK:
                self.pip_left_label.configure(fg_color="#1a3a2a", text_color=C["success"])
            else:
                self.pip_left_label.configure(highlightthickness=2, highlightbackground=C["success"])
        if self.pip_right_files:
            if HAS_CTK:
                self.pip_right_label.configure(text=f"右装饰: {os.path.basename(self.pip_right_files[0])}", text_color=C["text"])
            else:
                self._configure_label(self.pip_right_label, text=f"右装饰: {os.path.basename(self.pip_right_files[0])}", fg=C["text"])
            # 选中高亮
            if HAS_CTK:
                self.pip_right_label.configure(fg_color="#1a3a2a", text_color=C["success"])
            else:
                self.pip_right_label.configure(highlightthickness=2, highlightbackground=C["success"])

        # 分段/分批选项
        seg_card = tk.Frame(self.content, bg=C["card"], padx=16, pady=8)
        seg_card.pack(fill=tk.X, pady=(0, 6))
        seg_row = tk.Frame(seg_card, bg=C["card"])
        seg_row.pack(fill=tk.X)
        if HAS_CTK:
            ctk.CTkCheckBox(seg_row, text="超长视频分段处理", variable=self.segment_var,
                           font=("Microsoft YaHei UI", 10),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4,
                           command=self._toggle_segment).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(seg_row, text="🔪 超长视频分段处理", variable=self.segment_var,
                           font=("Microsoft YaHei UI", 10), bg=C["card"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["card"],
                           command=self._toggle_segment).pack(side=tk.LEFT)
        tk.Label(seg_row, text="  每段时长:", font=("Microsoft YaHei UI", 10),
                 bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(10, 2))
        self.seg_entry = tk.Entry(seg_row, textvariable=self.segment_minutes_var,
                                  width=5, font=("Microsoft YaHei UI", 10))
        self.seg_entry.pack(side=tk.LEFT)
        tk.Label(seg_row, text="分钟", font=("Microsoft YaHei UI", 10),
                 bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(seg_card, text="💡 超过此时长自动分段处理后合并，建议90-120分钟，避免内存不足",
                 font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w", pady=(2, 0))

        batch_card = tk.Frame(self.content, bg=C["card"], padx=16, pady=8)
        batch_card.pack(fill=tk.X, pady=(0, 6))
        batch_row = tk.Frame(batch_card, bg=C["card"])
        batch_row.pack(fill=tk.X)
        if HAS_CTK:
            ctk.CTkCheckBox(batch_row, text="分批次输出（按集数分割文件夹）", variable=self.batch_output_var,
                           font=("Microsoft YaHei UI", 10),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4,
                           command=self._toggle_batch).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(batch_row, text="📦 分批次输出（按集数分割文件夹）", variable=self.batch_output_var,
                           font=("Microsoft YaHei UI", 10), bg=C["card"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["card"],
                           command=self._toggle_batch).pack(side=tk.LEFT)
        tk.Label(batch_row, text="  每批:", font=("Microsoft YaHei UI", 10),
                 bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(10, 2))
        self.batch_entry = tk.Entry(batch_row, textvariable=self.batch_episodes_var,
                                    width=5, font=("Microsoft YaHei UI", 10))
        self.batch_entry.pack(side=tk.LEFT)
        tk.Label(batch_row, text="集", font=("Microsoft YaHei UI", 10),
                 bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(batch_card, text="💡 每个文件夹按集数分割，如26集按11集分割→输出_P1(1-11),_P2(12-22),_P3(23-26)",
                 font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w", pady=(2, 0))

    def _toggle_segment(self):
        state = "normal" if self.segment_var.get() else "disabled"
        self.seg_entry.configure(state=state)

    def _toggle_batch(self):
        state = "normal" if self.batch_output_var.get() else "disabled"
        self.batch_entry.configure(state=state)

    def _pip_load_template(self):
        p = filedialog.askopenfilename(filetypes=[
            ("媒体文件", "*.png *.jpg *.jpeg *.bmp *.webp *.mp4 *.mkv *.avi *.mov *.flv *.wmv"),
            ("图片", "*.png *.jpg *.jpeg *.bmp *.webp"),
            ("视频", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv"),
            ("所有文件", "*.*")
        ])
        if p:
            self.pip_template = p
            self._configure_label(self.pip_template_label, text=os.path.basename(p), fg=C["text"])
            self._save_config()

    def _pip_select_region(self, name):
        """在模板图片上对参考文件进行缩放、移动、拉框"""
        if not self.pip_template:
            messagebox.showwarning("提示", "请先选择模板图片或视频"); return
        
        try:
            from PIL import Image, ImageTk, ImageDraw, ExifTags
            import cv2
        except ImportError:
            messagebox.showerror("错误", "需要安装 Pillow 和 opencv:\npip install Pillow opencv-python")
            return
        
        # ═══════════════════════════════════════
        #  读取模板图片
        # ═══════════════════════════════════════
        ext = os.path.splitext(self.pip_template)[1].lower()
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts')
        is_tpl_video = ext in video_exts
        
        if is_tpl_video:
            cap = cv2.VideoCapture(self.pip_template)
            if not cap.isOpened():
                messagebox.showerror("错误", "无法打开视频文件"); return
            ret, cv_img = cap.read()
            cap.release()
            if not ret or cv_img is None:
                messagebox.showerror("错误", "无法读取视频帧"); return
            template_img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))
        else:
            template_img = Image.open(self.pip_template)
            try:
                exif = template_img._getexif()
                if exif:
                    for tag, val in exif.items():
                        if ExifTags.TAGS.get(tag) == 'Orientation':
                            if val == 3: template_img = template_img.rotate(180, expand=True)
                            elif val == 6: template_img = template_img.rotate(270, expand=True)
                            elif val == 8: template_img = template_img.rotate(90, expand=True)
                            break
            except: pass
        
        tpl_w, tpl_h = template_img.size
        
        # ═══════════════════════════════════════
        #  导入参考文件
        # ═══════════════════════════════════════
        ref_path = filedialog.askopenfilename(
            title=f"选择【{name}】参考文件（正片/图片）",
            filetypes=[
                ("媒体文件", "*.png *.jpg *.jpeg *.bmp *.mp4 *.mkv *.avi *.mov"),
                ("图片", "*.png *.jpg *.jpeg *.bmp"),
                ("视频", "*.mp4 *.mkv *.avi *.mov"),
            ]
        )
        if not ref_path:
            return
        
        # 读取参考文件第一帧
        ref_ext = os.path.splitext(ref_path)[1].lower()
        if ref_ext in video_exts:
            cap = cv2.VideoCapture(ref_path)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                messagebox.showerror("错误", "无法读取视频帧"); return
            ref_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        else:
            ref_img = Image.open(ref_path)
        
        ref_w, ref_h = ref_img.size
        
        # 参考文件尺寸自动对应选区大小
        # 根据区域名称自动设置位置
        default_positions = {
            "left": (0, 0),
            "center": ((tpl_w - ref_w) // 2, (tpl_h - ref_h) // 2),
            "right": (tpl_w - ref_w, 0),
        }
        default_x, default_y = default_positions.get(name, (0, 0))
        
        # 如果已有区域，使用已有区域；否则用参考文件尺寸
        if name in self.pip_regions:
            init_roi = self.pip_regions[name]
        else:
            init_roi = (default_x, default_y, ref_w, ref_h)
        
        # ═══════════════════════════════════════
        #  创建窗口
        # ═══════════════════════════════════════
        win = tk.Toplevel(self.root)
        win.title(f"调整【{name}】区域 - 滚轮缩放画布 | 左键拖拽画布 | 右键拖拽参考文件 | 拉框调整大小")
        win.configure(bg=C["bg"])
        win.geometry("1100x700")
        
        # 状态变量
        state = {
            "canvas_scale": 0.5,  # 画布缩放
            "canvas_ox": 0, "canvas_oy": 0,  # 画布偏移
            "dragging_canvas": False, "canvas_drag_start": None,
            "dragging_ref": False, "ref_drag_start": None,
            "drawing": False, "draw_start": None,
            "roi": list(init_roi),  # [x, y, w, h] 在模板坐标系中
            "ref_scale": 1.0,  # 参考文件缩放比例
        }
        
        # ═══════════════════════════════════════
        #  顶部工具栏
        # ═══════════════════════════════════════
        toolbar = tk.Frame(win, bg=C["card"])
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        lbl_info = tk.Label(toolbar, text=f"模板: {tpl_w}×{tpl_h} | 参考: {ref_w}×{ref_h}",
                           font=("Consolas", 10), bg=C["card"], fg=C["text"])
        lbl_info.pack(side=tk.LEFT, padx=10)
        
        lbl_zoom = tk.Label(toolbar, text="画布缩放: 50%",
                           font=("Consolas", 10), bg=C["card"], fg=C["primary"])
        lbl_zoom.pack(side=tk.LEFT, padx=10)
        
        lbl_coord = tk.Label(toolbar, text="选区: (0, 0) 0×0",
                            font=("Consolas", 10), bg=C["card"], fg=C["success"])
        lbl_coord.pack(side=tk.LEFT, padx=10)
        
        tk.Label(toolbar, text="滚轮缩放画布 | 左键拖拽画布 | 右键拖拽参考文件 | 左键+Shift拉框",
                font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(side=tk.RIGHT, padx=10)
        
        # ═══════════════════════════════════════
        #  画布
        # ═══════════════════════════════════════
        canvas = tk.Canvas(win, bg="#1a1a2e", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ═══════════════════════════════════════
        #  视频时间线（模板为视频时显示）
        # ═══════════════════════════════════════
        tpl_cap = None
        tpl_fps = 30
        tpl_total_frames = 0
        if is_tpl_video:
            tpl_cap = cv2.VideoCapture(self.pip_template)
            tpl_total_frames = int(tpl_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            tpl_fps = tpl_cap.get(cv2.CAP_PROP_FPS) or 30
            
            timeline_frame = tk.Frame(win, bg=C["card"])
            timeline_frame.pack(fill=tk.X, padx=5, pady=(0, 2))
            
            lbl_tpl_time = tk.Label(timeline_frame, text="00:00 / 00:00",
                                   font=("Consolas", 10), bg=C["card"], fg=C["text"])
            lbl_tpl_time.pack(side=tk.LEFT, padx=10)
            
            var_tpl_frame = tk.IntVar(value=0)
            tpl_slider = tk.Scale(timeline_frame, from_=0, to=max(0, tpl_total_frames - 1),
                                 variable=var_tpl_frame, orient=tk.HORIZONTAL,
                                 bg=C["card"], fg=C["text"], highlightthickness=0,
                                 troughcolor=C["bg"], length=400, showvalue=False)
            tpl_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            def seek_tpl_frame(idx):
                nonlocal template_img
                if tpl_cap and tpl_cap.isOpened():
                    tpl_cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ret, f = tpl_cap.read()
                    if ret:
                        template_img = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
                        m, s = divmod(int(idx / tpl_fps), 60)
                        total_s = int(tpl_total_frames / tpl_fps)
                        tm, ts = divmod(total_s, 60)
                        lbl_tpl_time.configure(text=f"{m:02d}:{s:02d} / {tm:02d}:{ts:02d}")
                        update_preview()
            
            tpl_slider.configure(command=lambda v: seek_tpl_frame(int(v)))
        
        # ═══════════════════════════════════════
        #  底部控制面板
        # ═══════════════════════════════════════
        bottom = tk.Frame(win, bg=C["bg"])
        bottom.pack(fill=tk.X, padx=5, pady=5)
        
        # 数字输入
        tk.Label(bottom, text="X:", bg=C["bg"], fg=C["text"], font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        var_x = tk.IntVar(value=state["roi"][0])
        tk.Entry(bottom, textvariable=var_x, width=6, font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        
        tk.Label(bottom, text="Y:", bg=C["bg"], fg=C["text"], font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        var_y = tk.IntVar(value=state["roi"][1])
        tk.Entry(bottom, textvariable=var_y, width=6, font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        
        tk.Label(bottom, text="W:", bg=C["bg"], fg=C["text"], font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        var_w = tk.IntVar(value=state["roi"][2])
        tk.Entry(bottom, textvariable=var_w, width=6, font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        
        tk.Label(bottom, text="H:", bg=C["bg"], fg=C["text"], font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        var_h = tk.IntVar(value=state["roi"][3])
        tk.Entry(bottom, textvariable=var_h, width=6, font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        
        def apply_coords():
            state["roi"] = [var_x.get(), var_y.get(), var_w.get(), var_h.get()]
            update_preview()
        
        tk.Button(bottom, text="应用坐标", command=apply_coords,
                 bg=C["primary"], fg="white", font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=10)
        
        # 参考文件缩放
        tk.Label(bottom, text="参考缩放:", bg=C["bg"], fg=C["text"], font=("Consolas", 10)).pack(side=tk.LEFT, padx=(15, 2))
        var_ref_scale = tk.StringVar(value="100%")
        ref_scale_entry = tk.Spinbox(bottom, from_=10, to=500, textvariable=var_ref_scale, width=6,
                                     font=("Consolas", 10), command=lambda: apply_ref_scale())
        ref_scale_entry.pack(side=tk.LEFT, padx=2)
        tk.Label(bottom, text="%", bg=C["bg"], fg=C["text3"], font=("Consolas", 9)).pack(side=tk.LEFT)
        
        def apply_ref_scale():
            try:
                pct = int(var_ref_scale.get().replace("%", "")) / 100.0
                pct = max(0.1, min(5.0, pct))
                old_scale = state["ref_scale"]
                state["ref_scale"] = pct
                # 按比例调整选区大小（保持中心点）
                cx = state["roi"][0] + state["roi"][2] // 2
                cy = state["roi"][1] + state["roi"][3] // 2
                new_w = int(ref_w * pct)
                new_h = int(ref_h * pct)
                new_x = cx - new_w // 2
                new_y = cy - new_h // 2
                new_x = max(0, min(new_x, tpl_w - new_w))
                new_y = max(0, min(new_y, tpl_h - new_h))
                state["roi"] = [new_x, new_y, new_w, new_h]
                var_x.set(new_x); var_y.set(new_y)
                var_w.set(new_w); var_h.set(new_h)
                update_preview()
            except: pass
        
        # 预设
        tk.Label(bottom, text="预设:", bg=C["bg"], fg=C["text3"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=5)
        
        presets = [
            ("全屏", (0, 0, tpl_w, tpl_h)),
            ("左半", (0, 0, tpl_w // 2, tpl_h)),
            ("右半", (tpl_w // 2, 0, tpl_w // 2, tpl_h)),
            ("中心", (tpl_w // 4, tpl_h // 4, tpl_w // 2, tpl_h // 2)),
        ]
        
        for pname, proi in presets:
            tk.Button(bottom, text=pname, 
                     command=lambda r=proi: (state.update({"roi": list(r)}), 
                                            var_x.set(r[0]), var_y.set(r[1]), 
                                            var_w.set(r[2]), var_h.set(r[3]),
                                            update_preview()),
                     bg=C["card"], fg=C["text"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=2)
        
        result = {"roi": None}
        
        def on_confirm():
            result["roi"] = tuple(state["roi"])
            win.destroy()
        
        tk.Button(bottom, text="确认 (Enter)", command=on_confirm,
                 bg=C["success"], fg="white", font=("Microsoft YaHei UI", 10)).pack(side=tk.RIGHT, padx=5)
        tk.Button(bottom, text="取消 (Esc)", command=lambda: win.destroy(),
                 bg=C["card"], fg=C["text"], font=("Microsoft YaHei UI", 10)).pack(side=tk.RIGHT, padx=5)
        
        # ═══════════════════════════════════════
        #  渲染函数
        # ═══════════════════════════════════════
        def update_preview():
            s = state["canvas_scale"]
            ox, oy = state["canvas_ox"], state["canvas_oy"]
            
            # 缩放模板
            tpl_scaled_w = max(1, int(tpl_w * s))
            tpl_scaled_h = max(1, int(tpl_h * s))
            tpl_scaled = template_img.resize((tpl_scaled_w, tpl_scaled_h), Image.Resampling.LANCZOS)
            
            # 创建画布大小的图片
            cw = max(canvas.winfo_width(), 100)
            ch = max(canvas.winfo_height(), 100)
            view = Image.new("RGB", (cw, ch), (26, 26, 42))
            
            # 粘贴模板
            px = max(0, int(ox))
            py = max(0, int(oy))
            sx = max(0, int(-ox))
            sy = max(0, int(-oy))
            if px < cw and py < ch:
                crop_w = min(tpl_scaled_w - sx, cw - px)
                crop_h = min(tpl_scaled_h - sy, ch - py)
                if crop_w > 0 and crop_h > 0:
                    view.paste(tpl_scaled.crop((sx, sy, sx + crop_w, sy + crop_h)), (px, py))
            
            # 绘制选区（参考文件位置）
            rx, ry, rw, rh = state["roi"]
            sx1 = int(rx * s + ox)
            sy1 = int(ry * s + oy)
            sx2 = int((rx + rw) * s + ox)
            sy2 = int((ry + rh) * s + oy)
            
            # 在选区内绘制参考文件预览
            ref_in_region = ref_img.resize((max(1, int(rw * s)), max(1, int(rh * s))), Image.Resampling.LANCZOS)
            
            overlay = Image.new("RGBA", view.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            
            # 选区外半透明遮罩（带边界检查）
            if sy1 > 0:
                overlay_draw.rectangle([0, 0, cw, min(sy1, ch)], fill=(0, 0, 0, 120))
            if sy2 < ch:
                overlay_draw.rectangle([0, max(0, sy2), cw, ch], fill=(0, 0, 0, 120))
            if sx1 > 0 and sy1 < ch and sy2 > 0:
                overlay_draw.rectangle([0, max(0, sy1), min(sx1, cw), min(sy2, ch)], fill=(0, 0, 0, 120))
            if sx2 < cw and sy1 < ch and sy2 > 0:
                overlay_draw.rectangle([max(0, sx2), max(0, sy1), cw, min(sy2, ch)], fill=(0, 0, 0, 120))
            
            # 选区边框
            overlay_draw.rectangle([sx1, sy1, sx2, sy2], outline=(0, 255, 0, 255), width=2)
            
            # 角落手柄
            handle_size = 6
            for hx, hy in [(sx1, sy1), (sx2, sy1), (sx1, sy2), (sx2, sy2)]:
                overlay_draw.rectangle([hx - handle_size, hy - handle_size, hx + handle_size, hy + handle_size],
                                      fill=(0, 255, 0, 200))
            
            view = Image.alpha_composite(view.convert("RGBA"), overlay).convert("RGB")
            
            # 在选区内粘贴参考文件
            if rw > 0 and rh > 0:
                ref_crop_x = max(0, -rx)
                ref_crop_y = max(0, -ry)
                ref_crop_w = min(rw, tpl_w - rx)
                ref_crop_h = min(rh, tpl_h - ry)
                if ref_crop_w > 0 and ref_crop_h > 0:
                    ref_cropped = ref_img.crop((ref_crop_x, ref_crop_y, ref_crop_x + ref_crop_w, ref_crop_y + ref_crop_h))
                    ref_display = ref_cropped.resize((max(1, int(ref_crop_w * s)), max(1, int(ref_crop_h * s))), Image.Resampling.LANCZOS)
                    
                    paste_x = max(sx1, 0)
                    paste_y = max(sy1, 0)
                    paste_w = min(ref_display.width, cw - paste_x)
                    paste_h = min(ref_display.height, ch - paste_y)
                    if paste_w > 0 and paste_h > 0:
                        view.paste(ref_display.crop((0, 0, paste_w, paste_h)), (paste_x, paste_y))
            
            # 更新画布
            state["photo"] = ImageTk.PhotoImage(view)
            canvas.delete("all")
            canvas.create_image(0, 0, anchor=tk.NW, image=state["photo"])
            
            # 更新显示
            lbl_zoom.configure(text=f"画布缩放: {int(s * 100)}%")
            lbl_coord.configure(text=f"选区: ({rx}, {ry}) {rw}×{rh}")
        
        # ═══════════════════════════════════════
        #  事件处理
        # ═══════════════════════════════════════
        def on_mousewheel(event):
            delta = event.delta if hasattr(event, 'delta') else (120 if event.num == 4 else -120)
            
            # 检查鼠标是否在参考文件区域内
            s = state["canvas_scale"]
            rx, ry, rw, rh = state["roi"]
            sx1 = int(rx * s + state["canvas_ox"])
            sy1 = int(ry * s + state["canvas_oy"])
            sx2 = int((rx + rw) * s + state["canvas_ox"])
            sy2 = int((ry + rh) * s + state["canvas_oy"])
            
            if sx1 <= event.x <= sx2 and sy1 <= event.y <= sy2:
                # 在参考文件区域：缩放参考文件
                factor = 1.1 if delta > 0 else 0.9
                new_scale = max(0.1, min(5.0, state["ref_scale"] * factor))
                state["ref_scale"] = new_scale
                var_ref_scale.set(f"{int(new_scale * 100)}%")
                # 调整选区大小（保持中心点）
                cx = state["roi"][0] + state["roi"][2] // 2
                cy = state["roi"][1] + state["roi"][3] // 2
                new_w = int(ref_w * new_scale)
                new_h = int(ref_h * new_scale)
                new_x = cx - new_w // 2
                new_y = cy - new_h // 2
                new_x = max(0, min(new_x, tpl_w - new_w))
                new_y = max(0, min(new_y, tpl_h - new_h))
                state["roi"] = [new_x, new_y, new_w, new_h]
                var_x.set(new_x); var_y.set(new_y)
                var_w.set(new_w); var_h.set(new_h)
            else:
                # 在模板区域：缩放画布
                factor = 1.1 if delta > 0 else 0.9
                state["canvas_scale"] = max(0.1, min(3.0, state["canvas_scale"] * factor))
            
            update_preview()
        
        # 左键拖拽画布
        def on_left_press(event):
            if event.state & 0x0001:  # Shift键
                # Shift+左键拉框
                state["drawing"] = True
                state["draw_start"] = ((event.x - state["canvas_ox"]) / state["canvas_scale"],
                                       (event.y - state["canvas_oy"]) / state["canvas_scale"])
            else:
                state["dragging_canvas"] = True
                state["canvas_drag_start"] = (event.x, event.y)
        
        def on_left_drag(event):
            if state["dragging_canvas"] and state["canvas_drag_start"]:
                dx = event.x - state["canvas_drag_start"][0]
                dy = event.y - state["canvas_drag_start"][1]
                state["canvas_ox"] += dx
                state["canvas_oy"] += dy
                state["canvas_drag_start"] = (event.x, event.y)
                update_preview()
            elif state["drawing"] and state["draw_start"]:
                img_x = (event.x - state["canvas_ox"]) / state["canvas_scale"]
                img_y = (event.y - state["canvas_oy"]) / state["canvas_scale"]
                x1, y1 = state["draw_start"]
                x2, y2 = img_x, img_y
                
                rx = max(0, min(x1, x2))
                ry = max(0, min(y1, y2))
                rw = min(abs(x2 - x1), tpl_w - rx)
                rh = min(abs(y2 - y1), tpl_h - ry)
                
                state["roi"] = [int(rx), int(ry), int(rw), int(rh)]
                var_x.set(int(rx)); var_y.set(int(ry))
                var_w.set(int(rw)); var_h.set(int(rh))
                update_preview()
        
        def on_left_release(event):
            state["dragging_canvas"] = False
            state["drawing"] = False
            state["draw_start"] = None
        
        # 右键拖拽参考文件
        def on_right_press(event):
            state["dragging_ref"] = True
            state["ref_drag_start"] = (event.x, event.y)
        
        def on_right_drag(event):
            if state["dragging_ref"] and state["ref_drag_start"]:
                dx = (event.x - state["ref_drag_start"][0]) / state["canvas_scale"]
                dy = (event.y - state["ref_drag_start"][1]) / state["canvas_scale"]
                state["roi"][0] = max(0, min(int(state["roi"][0] + dx), tpl_w - state["roi"][2]))
                state["roi"][1] = max(0, min(int(state["roi"][1] + dy), tpl_h - state["roi"][3]))
                state["ref_drag_start"] = (event.x, event.y)
                var_x.set(state["roi"][0]); var_y.set(state["roi"][1])
                update_preview()
        
        def on_right_release(event):
            state["dragging_ref"] = False
        
        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        canvas.bind("<ButtonPress-1>", on_left_press)
        canvas.bind("<B1-Motion>", on_left_drag)
        canvas.bind("<ButtonRelease-1>", on_left_release)
        canvas.bind("<ButtonPress-3>", on_right_press)
        canvas.bind("<B3-Motion>", on_right_drag)
        canvas.bind("<ButtonRelease-3>", on_right_release)
        
        # 鼠标移动时改变光标（悬停在参考区域时显示手型）
        def on_motion(event):
            s = state["canvas_scale"]
            rx, ry, rw, rh = state["roi"]
            sx1 = int(rx * s + state["canvas_ox"])
            sy1 = int(ry * s + state["canvas_oy"])
            sx2 = int((rx + rw) * s + state["canvas_ox"])
            sy2 = int((ry + rh) * s + state["canvas_oy"])
            if sx1 <= event.x <= sx2 and sy1 <= event.y <= sy2:
                canvas.configure(cursor="hand2")
            else:
                canvas.configure(cursor="arrow")
        canvas.bind("<Motion>", on_motion)
        
        win.bind("<Return>", lambda e: on_confirm())
        win.bind("<Escape>", lambda e: win.destroy())
        
        def on_close():
            if tpl_cap and tpl_cap.isOpened():
                tpl_cap.release()
            win.destroy()
        
        win.protocol("WM_DELETE_WINDOW", on_close)
        
        # 初始化
        win.update_idletasks()
        update_preview()
        
        win.grab_set()
        win.wait_window()
        
        if result["roi"]:
            self.pip_regions[name] = result["roi"]
            txts = [f"{k}: {v}" for k, v in self.pip_regions.items() if getattr(self, f'pip_enable_{k}', tk.BooleanVar(value=True)).get()]
            self.pip_region_label.configure(text="✅ " + " | ".join(txts) if txts else "❌ 未选择区域")
            self._save_config()

    def _pip_select_decor(self, side):
        """选择左/右装饰视频 + 框选区域"""
        side_name = "左" if side == "left" else "右"
        p = filedialog.askopenfilename(
            title=f"选择{side_name}装饰视频",
            filetypes=[("视频", "*.mp4 *.mkv *.avi *.flv *.ts")]
        )
        if not p:
            return
        
        # 先保存文件
        if side == "left":
            self.pip_left_files = [p]
        else:
            self.pip_right_files = [p]
        
        # 弹出框选区域
        self._pip_select_region(side)
        
        # 如果用户没有框选区域（取消了），则不添加装饰
        if side not in self.pip_regions:
            if side == "left":
                self.pip_left_files = []
                self._configure_label(self.pip_left_label, text=f"{side_name}装饰: 无", fg=C["text3"])
                if HAS_CTK:
                    self.pip_left_label.configure(fg_color=C["input"], text_color=C["text3"])
                else:
                    self.pip_left_label.configure(highlightthickness=0)
            else:
                self.pip_right_files = []
                self._configure_label(self.pip_right_label, text=f"{side_name}装饰: 无", fg=C["text3"])
                if HAS_CTK:
                    self.pip_right_label.configure(fg_color=C["input"], text_color=C["text3"])
                else:
                    self.pip_right_label.configure(highlightthickness=0)
        else:
            if side == "left":
                self._configure_label(self.pip_left_label, text=f"{side_name}装饰: {os.path.basename(p)}", fg=C["text"])
                if HAS_CTK:
                    self.pip_left_label.configure(fg_color="#1a3a2a", text_color=C["success"])
                else:
                    self.pip_left_label.configure(highlightthickness=2, highlightbackground=C["success"])
            else:
                self._configure_label(self.pip_right_label, text=f"{side_name}装饰: {os.path.basename(p)}", fg=C["text"])
                if HAS_CTK:
                    self.pip_right_label.configure(fg_color="#1a3a2a", text_color=C["success"])
                else:
                    self.pip_right_label.configure(highlightthickness=2, highlightbackground=C["success"])
        
        self._save_config()

    def _preview_layout(self, mode="pip"):
        """预览布局：在模板图上叠加区域框"""
        try:
            import cv2
            from PIL import Image, ImageTk, ExifTags
        except ImportError:
            messagebox.showerror("错误", "需要安装 opencv 和 Pillow:\npip install opencv-python Pillow")
            return

        if mode == "pip":
            if not self.pip_template:
                messagebox.showwarning("提示", "请先选择模板图片")
                return
            if not self.pip_regions:
                messagebox.showwarning("提示", "请先框选至少一个区域")
                return
            template_path = self.pip_template
            regions = self.pip_regions
        else:  # frame
            if not self.frame_template and not self.bg_color:
                messagebox.showwarning("提示", "请先选择模板图片或设置纯色背景")
                return
            if not self.frame_roi:
                messagebox.showwarning("提示", "请先框选视频区域")
                return
            template_path = self.frame_template
            regions = {"video": self.frame_roi}

        # 读取模板图片（纯色背景跳过）
        if self.bg_color:
            res = getattr(self, 'output_resolution', '1920x1080')
            ow, oh = map(int, res.split('x'))
            hex_color = self.bg_color.lstrip('#')
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            img = np.full((oh, ow, 3), (b, g, r), dtype=np.uint8)
        else:
            ext = os.path.splitext(template_path)[1].lower()
            if ext in ('.mp4', '.mkv', '.avi', '.flv', '.ts'):
                cap = cv2.VideoCapture(template_path)
                ret, img = cap.read()
                cap.release()
                if not ret:
                    messagebox.showerror("错误", "无法读取视频模板")
                    return
            else:
                pil_img = Image.open(template_path)
                try:
                    exif = pil_img._getexif()
                    if exif:
                        for tag, val in exif.items():
                            if ExifTags.TAGS.get(tag) == 'Orientation':
                                if val == 3: pil_img = pil_img.rotate(180, expand=True)
                                elif val == 6: pil_img = pil_img.rotate(270, expand=True)
                                elif val == 8: pil_img = pil_img.rotate(90, expand=True)
                                break
                except:
                    pass
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        if img is None:
            messagebox.showerror("错误", "无法读取模板图片")
            return

        # 在图片上绘制区域
        overlay = img.copy()
        colors = {
            "left": (76, 154, 255),    # 蓝色
            "center": (78, 205, 196),  # 绿色
            "right": (255, 107, 107),  # 红色
            "video": (78, 205, 196),   # 绿色（套框模式）
        }
        for name, (x, y, w, h) in regions.items():
            color = colors.get(name, (255, 255, 255))
            # 半透明填充
            cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
            # 边框
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 3)
            # 标签
            label = f"{name} ({w}x{h})"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(img, (x, y - th - 10), (x + tw + 8, y), color, -1)
            cv2.putText(img, label, (x + 4, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

        # 混合透明
        cv2.addWeighted(overlay, 0.2, img, 0.8, 0, img)

        # 显示预览窗口
        h_img, w_img = img.shape[:2]
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        scale = min((screen_w - 100) / w_img, (screen_h - 150) / h_img, 1.0)
        disp_w, disp_h = int(w_img * scale), int(h_img * scale)

        preview_win = tk.Toplevel(self.root)
        preview_win.title(f"布局预览 - {mode.upper()}")
        preview_win.configure(bg=C["bg"])
        preview_win.geometry(f"{disp_w + 20}x{disp_h + 60}")

        # 标题
        title_text = f"模板: {os.path.basename(template_path)} | 区域: {len(regions)}个"
        if HAS_CTK:
            ctk.CTkLabel(preview_win, text=title_text, font=("Microsoft YaHei UI", 11),
                         text_color=C["text"]).pack(pady=(8, 4))
        else:
            tk.Label(preview_win, text=title_text, font=("Microsoft YaHei UI", 11),
                     bg=C["bg"], fg=C["text"]).pack(pady=(8, 4))

        # 图片
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_preview = Image.fromarray(img_rgb)
        pil_preview = pil_preview.resize((disp_w, disp_h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(pil_preview)

        canvas = tk.Canvas(preview_win, width=disp_w, height=disp_h,
                          bg=C["bg"], highlightthickness=0)
        canvas.pack(padx=10, pady=(0, 10))
        canvas.create_image(0, 0, anchor="nw", image=tk_img)
        canvas._tk_img = tk_img  # 防止GC回收

        # 图例
        legend_frame = tk.Frame(preview_win, bg=C["bg"])
        legend_frame.pack(pady=(0, 8))
        for name, color_bgr in colors.items():
            if name not in regions:
                continue
            color_hex = f"#{color_bgr[2]:02x}{color_bgr[1]:02x}{color_bgr[0]:02x}"
            dot = tk.Canvas(legend_frame, width=12, height=12, bg=C["bg"], highlightthickness=0)
            dot.pack(side=tk.LEFT, padx=(8, 2))
            dot.create_oval(2, 2, 10, 10, fill=color_hex, outline="")
            tk.Label(legend_frame, text=name, font=("Microsoft YaHei UI", 9),
                     bg=C["bg"], fg=C["text2"]).pack(side=tk.LEFT, padx=(0, 12))

    def _frame_preview(self):
        """套框模式预览"""
        self._preview_layout(mode="frame")

    def _pip_preview(self):
        """画中画模式预览"""
        self._preview_layout(mode="pip")

    def _pip_preview_template(self):
        """预览模板：支持缩放、旋转、视频播放"""
        if not self.pip_template:
            messagebox.showwarning("提示", "请先选择模板"); return
        try:
            from PIL import Image, ImageTk, ExifTags
            import cv2
        except ImportError:
            messagebox.showerror("错误", "需要安装 Pillow 和 opencv"); return

        ext = os.path.splitext(self.pip_template)[1].lower()
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts')
        is_video = ext in video_exts

        # 读取第一帧
        if is_video:
            cap = cv2.VideoCapture(self.pip_template)
            if not cap.isOpened():
                messagebox.showerror("错误", "无法打开视频"); return
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            ret, frame = cap.read()
            if not ret:
                cap.release(); messagebox.showerror("错误", "无法读取视频帧"); return
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        else:
            cap = None
            total_frames = 0; fps = 30
            pil_img = Image.open(self.pip_template)
            try:
                exif = pil_img._getexif()
                if exif:
                    for tag, val in exif.items():
                        if ExifTags.TAGS.get(tag) == 'Orientation':
                            if val == 3: pil_img = pil_img.rotate(180, expand=True)
                            elif val == 6: pil_img = pil_img.rotate(270, expand=True)
                            elif val == 8: pil_img = pil_img.rotate(90, expand=True)
                            break
            except: pass

        orig_w, orig_h = pil_img.size

        # 创建窗口
        win = tk.Toplevel(self.root)
        win.title(f"预览模板 - {os.path.basename(self.pip_template)} | 滚轮缩放 | R旋转 | {'视频播放' if is_video else '图片'}")
        win.configure(bg=C["bg"])
        win.geometry("1000x650")

        state = {"scale": 0.5, "ox": 0, "oy": 0, "dragging": False, "drag_start": None,
                 "rotation": 0, "img": pil_img, "frame_idx": 0, "playing": False}

        # 工具栏
        toolbar = tk.Frame(win, bg=C["card"])
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        lbl_info = tk.Label(toolbar, text=f"{orig_w}x{orig_h}" + (f" | {total_frames}帧 {fps:.1f}fps" if is_video else ""),
                           font=("Consolas", 10), bg=C["card"], fg=C["text"])
        lbl_info.pack(side=tk.LEFT, padx=10)
        lbl_zoom = tk.Label(toolbar, text="缩放: 50%", font=("Consolas", 10), bg=C["card"], fg=C["primary"])
        lbl_zoom.pack(side=tk.LEFT, padx=10)

        def zoom_in(): state["scale"] = min(state["scale"] * 1.25, 5.0); render()
        def zoom_out(): state["scale"] = max(state["scale"] / 1.25, 0.1); render()
        def rotate_img():
            state["rotation"] = (state["rotation"] + 90) % 360
            state["img"] = pil_img.rotate(-state["rotation"], expand=True)
            render()

        tk.Button(toolbar, text="-", command=zoom_out, width=3, bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="+", command=zoom_in, width=3, bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="旋转(R)", command=rotate_img, bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=5)

        # 画布
        canvas = tk.Canvas(win, bg="#1a1a2e", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 视频时间线
        if is_video:
            timeline_frame = tk.Frame(win, bg=C["card"])
            timeline_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
            lbl_time = tk.Label(timeline_frame, text="00:00 / 00:00", font=("Consolas", 10), bg=C["card"], fg=C["text"])
            lbl_time.pack(side=tk.LEFT, padx=10)

            var_frame = tk.IntVar(value=0)
            slider = tk.Scale(timeline_frame, from_=0, to=max(0, total_frames - 1), variable=var_frame,
                             orient=tk.HORIZONTAL, bg=C["card"], fg=C["text"], highlightthickness=0,
                             troughcolor=C["bg"], length=400, showvalue=False)
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            def seek_frame(idx):
                if cap and cap.isOpened():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ret, f = cap.read()
                    if ret:
                        state["img"] = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
                        state["frame_idx"] = idx
                        m, s = divmod(int(idx / fps), 60)
                        total_s = int(total_frames / fps)
                        tm, ts = divmod(total_s, 60)
                        lbl_time.configure(text=f"{m:02d}:{s:02d} / {tm:02d}:{ts:02d}")
                        render()

            slider.configure(command=lambda v: seek_frame(int(v)))

            # 播放/暂停
            def toggle_play():
                state["playing"] = not state["playing"]
                btn_play.configure(text="⏸ 暂停" if state["playing"] else "▶ 播放")
                if state["playing"]:
                    play_next()

            def play_next():
                if not state["playing"] or not cap or not cap.isOpened(): return
                idx = state["frame_idx"] + 1
                if idx >= total_frames:
                    state["playing"] = False
                    btn_play.configure(text="▶ 播放")
                    return
                var_frame.set(idx)
                seek_frame(idx)
                delay = max(1, int(1000 / fps))
                win.after(delay, play_next)

            btn_play = tk.Button(timeline_frame, text="▶ 播放", command=toggle_play,
                                bg=C["primary"], fg="white", font=("Microsoft YaHei UI", 9))
            btn_play.pack(side=tk.LEFT, padx=5)

        # 渲染
        def render():
            s = state["scale"]
            ox, oy = state["ox"], state["oy"]
            img = state["img"]
            iw, ih = img.size
            sw, sh = max(1, int(iw * s)), max(1, int(ih * s))
            resized = img.resize((sw, sh), Image.Resampling.LANCZOS)

            cw = max(canvas.winfo_width(), 100)
            ch = max(canvas.winfo_height(), 100)
            view = Image.new("RGB", (cw, ch), (26, 26, 42))

            px, py = max(0, int(ox + (cw - sw) // 2)), max(0, int(oy + (ch - sh) // 2))
            sx_off, sy_off = max(0, int(-(ox + (cw - sw) // 2))), max(0, int(-(oy + (ch - sh) // 2)))
            if px < cw and py < ch:
                crop_w = min(sw - sx_off, cw - px)
                crop_h = min(sh - sy_off, ch - py)
                if crop_w > 0 and crop_h > 0:
                    view.paste(resized.crop((sx_off, sy_off, sx_off + crop_w, sy_off + crop_h)), (px, py))

            state["photo"] = ImageTk.PhotoImage(view)
            canvas.delete("all")
            canvas.create_image(0, 0, anchor=tk.NW, image=state["photo"])
            lbl_zoom.configure(text=f"缩放: {int(s * 100)}%")

        # 事件
        def on_mousewheel(event):
            delta = event.delta if hasattr(event, 'delta') else (120 if event.num == 4 else -120)
            state["scale"] = max(0.1, min(5.0, state["scale"] * (1.1 if delta > 0 else 0.9)))
            render()

        def on_press(event):
            state["dragging"] = True; state["drag_start"] = (event.x, event.y)
        def on_drag(event):
            if state["dragging"] and state["drag_start"]:
                state["ox"] += event.x - state["drag_start"][0]
                state["oy"] += event.y - state["drag_start"][1]
                state["drag_start"] = (event.x, event.y); render()
        def on_release(event): state["dragging"] = False

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        win.bind("<r>", lambda e: rotate_img())
        win.bind("<R>", lambda e: rotate_img())
        win.bind("<Escape>", lambda e: (state.update({"playing": False}), win.destroy()))

        def on_close():
            state["playing"] = False
            if cap and cap.isOpened(): cap.release()
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)
        win.update_idletasks(); render()
        win.grab_set(); win.wait_window()
        if cap and cap.isOpened(): cap.release()

    # ═══════════════════════════════════════
    #  页面3: 横转竖
    # ═══════════════════════════════════════
    def _build_rotate_page(self):
        card = self._card(self.content, padx=10, pady=8)

        if HAS_CTK:
            ctk.CTkLabel(card, text="横屏转竖屏（旋转90°）", font=("Microsoft YaHei UI", 11, "bold"),
                         text_color=C["text"]).pack(anchor="w")
            ctk.CTkLabel(card, text="1920x1080 -> 1080x1920，视频旋转90°",
                         font=("Consolas", 9), text_color=C["text2"]).pack(anchor="w", pady=(2, 8))
        else:
            tk.Label(card, text="🔄 横屏转竖屏（旋转90°）", font=("Microsoft YaHei UI", 11, "bold"),
                     bg=C["card"], fg=C["text"]).pack(anchor="w")
            tk.Label(card, text="1920×1080 → 1080×1920，视频旋转90°",
                     font=("Consolas", 9), bg=C["card"], fg=C["text2"]).pack(anchor="w", pady=(2, 8))

        rr = tk.Frame(card, bg=C["card"])
        rr.pack(fill=tk.X)
        if HAS_CTK:
            ctk.CTkLabel(rr, text="旋转方向:", font=("Microsoft YaHei UI", 10), text_color=C["text"]).pack(side=tk.LEFT)
        else:
            tk.Label(rr, text="旋转方向:", font=("Microsoft YaHei UI", 10), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
        tk.Radiobutton(rr, text="顺时针90°", variable=self.rotate_dir, value="cw",
                       font=("Microsoft YaHei UI", 10), bg=C["card"], fg=C["text1"],
                       selectcolor=C["card"], activebackground=C["card"]).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(rr, text="逆时针90°", variable=self.rotate_dir, value="ccw",
                       font=("Microsoft YaHei UI", 10), bg=C["card"]).pack(side=tk.LEFT, padx=10)

    # ═══════════════════════════════════════
    #  页面4: 流水线（新增）
    # ═══════════════════════════════════════
    def _build_pipeline_page(self):
        # 使用 _card 辅助方法（Web风格）
        card = self._card(self.content, padx=10, pady=8)

        if HAS_CTK:
            ctk.CTkLabel(card, text="流水线模式 - 多步骤自动串联", font=("Microsoft YaHei UI", 11, "bold"),
                         text_color=C["text"]).pack(anchor="w")
            ctk.CTkLabel(card, text="勾选需要的步骤，视频会按顺序自动处理",
                         font=("Consolas", 9), text_color=C["text2"]).pack(anchor="w", pady=(2, 8))
        else:
            tk.Label(card, text="🔗 流水线模式 — 多步骤自动串联", font=("Microsoft YaHei UI", 11, "bold"),
                     bg=C["card"], fg=C["text"]).pack(anchor="w")
            tk.Label(card, text="勾选需要的步骤，视频会按顺序自动处理",
                     font=("Consolas", 9), bg=C["card"], fg=C["text2"]).pack(anchor="w", pady=(2, 8))

        # 步骤勾选
        if not hasattr(self, 'pipe_rotate_var'):
            self.pipe_rotate_var = tk.BooleanVar(value=False)
            self.pipe_frame_var = tk.BooleanVar(value=False)
            self.pipe_pip_var = tk.BooleanVar(value=False)
            self.pipe_intro_outro_var = tk.BooleanVar(value=False)

        step_frame = tk.Frame(card, bg=C["card"])
        step_frame.pack(fill=tk.X, pady=4)

        # 步骤1: 横转竖
        s1 = tk.Frame(step_frame, bg=C["primary_light"], padx=10, pady=6)
        s1.pack(fill=tk.X, pady=(0, 4))
        if HAS_CTK:
            ctk.CTkCheckBox(s1, text="① 横转竖", variable=self.pipe_rotate_var,
                           font=("Microsoft YaHei UI", 10, "bold"),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(s1, text="① 🔄 横转竖", variable=self.pipe_rotate_var,
                           font=("Microsoft YaHei UI", 10, "bold"), bg=C["primary_light"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["primary_light"]).pack(side=tk.LEFT)
        if HAS_CTK:
            ctk.CTkLabel(s1, text="顺时针90°", font=("Consolas", 9), text_color=C["text2"]).pack(side=tk.LEFT, padx=10)
        else:
            tk.Label(s1, text="顺时针90°", font=("Consolas", 9), bg=C["primary_light"], fg=C["text2"]).pack(side=tk.LEFT, padx=10)

        # 步骤2: 套框
        s2 = tk.Frame(step_frame, bg=C["primary_light"], padx=10, pady=6)
        s2.pack(fill=tk.X, pady=(0, 4))
        if HAS_CTK:
            ctk.CTkCheckBox(s2, text="② 视频套框", variable=self.pipe_frame_var,
                           font=("Microsoft YaHei UI", 10, "bold"),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(s2, text="② 🖼 视频套框", variable=self.pipe_frame_var,
                           font=("Microsoft YaHei UI", 10, "bold"), bg=C["primary_light"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["primary_light"]).pack(side=tk.LEFT)
        frame_status = "已设置" if (self.frame_template and self.frame_roi) else "未设置模板/区域"
        _frame_fg = C["success"] if self.frame_template and self.frame_roi else C["warning"]
        if HAS_CTK:
            ctk.CTkLabel(s2, text=frame_status, font=("Microsoft YaHei UI", 9), text_color=_frame_fg).pack(side=tk.LEFT, padx=10)
        else:
            tk.Label(s2, text=frame_status, font=("Microsoft YaHei UI", 9), bg=C["primary_light"], fg=_frame_fg).pack(side=tk.LEFT, padx=10)

        # 步骤3: 画中画
        s3 = tk.Frame(step_frame, bg=C["primary_light"], padx=10, pady=6)
        s3.pack(fill=tk.X, pady=(0, 4))
        if HAS_CTK:
            ctk.CTkCheckBox(s3, text="③ 画中画", variable=self.pipe_pip_var,
                           font=("Microsoft YaHei UI", 10, "bold"),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(s3, text="③ 📺 画中画", variable=self.pipe_pip_var,
                           font=("Microsoft YaHei UI", 10, "bold"), bg=C["primary_light"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["primary_light"]).pack(side=tk.LEFT)
        pip_status = "已设置" if (self.pip_template and "center" in self.pip_regions and self.pip_enable_center.get()) else "未设置模板/区域"
        _pip_fg = C["success"] if self.pip_template and "center" in self.pip_regions and self.pip_enable_center.get() else C["warning"]
        if HAS_CTK:
            ctk.CTkLabel(s3, text=pip_status, font=("Microsoft YaHei UI", 9), text_color=_pip_fg).pack(side=tk.LEFT, padx=10)
        else:
            tk.Label(s3, text=pip_status, font=("Microsoft YaHei UI", 9), bg=C["primary_light"], fg=_pip_fg).pack(side=tk.LEFT, padx=10)

        # 步骤4: 加片头片尾
        s4 = tk.Frame(step_frame, bg=C["primary_light"], padx=10, pady=6)
        s4.pack(fill=tk.X, pady=(0, 4))
        if HAS_CTK:
            ctk.CTkCheckBox(s4, text="④ 加片头片尾", variable=self.pipe_intro_outro_var,
                           font=("Microsoft YaHei UI", 10, "bold"),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4).pack(side=tk.LEFT)
        else:
            tk.Checkbutton(s4, text="④ 加片头片尾", variable=self.pipe_intro_outro_var,
                           font=("Microsoft YaHei UI", 10, "bold"), bg=C["primary_light"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["primary_light"]).pack(side=tk.LEFT)
        intro_status = ""
        _intro_fg = C["text3"]
        if self.intro_video:
            intro_status += f"片头:{os.path.basename(self.intro_video)} "
            _intro_fg = C["success"]
        if self.outro_video:
            intro_status += f"片尾:{os.path.basename(self.outro_video)}"
            _intro_fg = C["success"]
        if not intro_status:
            intro_status = "未设置（在套框页面设置）"
        if HAS_CTK:
            ctk.CTkLabel(s4, text=intro_status, font=("Microsoft YaHei UI", 9), text_color=_intro_fg).pack(side=tk.LEFT, padx=10)
        else:
            tk.Label(s4, text=intro_status, font=("Microsoft YaHei UI", 9), bg=C["primary_light"], fg=_intro_fg).pack(side=tk.LEFT, padx=10)

        # 提示
        if HAS_CTK:
            ctk.CTkLabel(card, text="先在各模式页面设置好模板和区域，再回到流水线页面勾选步骤",
                         font=("Microsoft YaHei UI", 9), text_color=C["text3"]).pack(anchor="w", pady=(4, 0))
        else:
            tk.Label(card, text="💡 先在各模式页面设置好模板和区域，再回到流水线页面勾选步骤",
                     font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w", pady=(4, 0))

    # ═══════════════════════════════════════
    #  页面5: 片头片尾（独立模式）
    # ═══════════════════════════════════════
    def _build_intro_outro_page(self):
        card = tk.Frame(self.content, bg=C["card"], padx=16, pady=12)
        card.pack(fill=tk.X, pady=(0, 8))
        if HAS_CTK:
            ctk.CTkLabel(card, text="片头片尾 - 独立添加模式", font=("Microsoft YaHei UI", 11, "bold"),
                         text_color=C["text"]).pack(anchor="w")
            ctk.CTkLabel(card, text="选择片头和/或片尾视频，批量添加到所有视频",
                         font=("Microsoft YaHei UI", 9), text_color=C["text3"]).pack(anchor="w", pady=(2, 8))
        else:
            tk.Label(card, text="片头片尾 - 独立添加模式", font=("Microsoft YaHei UI", 11, "bold"),
                     bg=C["card"], fg=C["text"]).pack(anchor="w")
            tk.Label(card, text="选择片头和/或片尾视频，批量添加到所有视频",
                     font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w", pady=(2, 8))

        # 片头选择
        s1 = tk.Frame(card, bg=C["card"])
        s1.pack(fill=tk.X, pady=4)
        if HAS_CTK:
            ctk.CTkLabel(s1, text="片头:", font=("Microsoft YaHei UI", 10), text_color=C["text"]).pack(side=tk.LEFT)
            self.io_intro_label = ctk.CTkLabel(s1, text="未选择", font=("Consolas", 10),
                                               fg_color=C["input"], text_color=C["text3"],
                                               corner_radius=4, padx=10, pady=6)
        else:
            tk.Label(s1, text="片头:", font=("Microsoft YaHei UI", 10), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
            self.io_intro_label = tk.Label(s1, text="未选择", font=("Consolas", 10),
                                           bg=C["input"], fg=C["text3"], padx=10, pady=6)
        self.io_intro_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self._btn(s1, "选择", self._io_select_intro, "primary").pack(side=tk.LEFT)
        self._btn(s1, "清除", self._io_clear_intro, "btn").pack(side=tk.LEFT, padx=(4, 0))

        # 片尾选择
        s2 = tk.Frame(card, bg=C["card"])
        s2.pack(fill=tk.X, pady=4)
        if HAS_CTK:
            ctk.CTkLabel(s2, text="片尾:", font=("Microsoft YaHei UI", 10), text_color=C["text"]).pack(side=tk.LEFT)
            self.io_outro_label = ctk.CTkLabel(s2, text="未选择", font=("Consolas", 10),
                                               fg_color=C["input"], text_color=C["text3"],
                                               corner_radius=4, padx=10, pady=6)
        else:
            tk.Label(s2, text="片尾:", font=("Microsoft YaHei UI", 10), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
            self.io_outro_label = tk.Label(s2, text="未选择", font=("Consolas", 10),
                                           bg=C["input"], fg=C["text3"], padx=10, pady=6)
        self.io_outro_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self._btn(s2, "选择", self._io_select_outro, "primary").pack(side=tk.LEFT)
        self._btn(s2, "清除", self._io_clear_outro, "btn").pack(side=tk.LEFT, padx=(4, 0))

        # 转场效果
        s3 = tk.Frame(card, bg=C["card"])
        s3.pack(fill=tk.X, pady=(8, 4))
        if HAS_CTK:
            ctk.CTkCheckBox(s3, text="添加淡入淡出转场", variable=self.io_fade_var,
                           font=("Microsoft YaHei UI", 10),
                           fg_color=C["primary"], hover_color=C["btn_hover"],
                           text_color=C["text"], corner_radius=4).pack(side=tk.LEFT)
            ctk.CTkLabel(s3, text="时长:", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT, padx=(12, 4))
            self.io_fade_entry = ctk.CTkEntry(s3, textvariable=self.io_fade_sec_var, width=50,
                                              font=("Microsoft YaHei UI", 10))
        else:
            tk.Checkbutton(s3, text="添加淡入淡出转场", variable=self.io_fade_var,
                           font=("Microsoft YaHei UI", 10), bg=C["card"], fg=C["text"],
                           selectcolor=C["primary"], activebackground=C["card"]).pack(side=tk.LEFT)
            tk.Label(s3, text="时长:", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(12, 4))
            self.io_fade_entry = tk.Entry(s3, textvariable=self.io_fade_sec_var, width=5, font=("Microsoft YaHei UI", 10))
        self.io_fade_entry.pack(side=tk.LEFT)
        if HAS_CTK:
            ctk.CTkLabel(s3, text="秒", font=("Microsoft YaHei UI", 9), text_color=C["text"]).pack(side=tk.LEFT, padx=(4, 0))
        else:
            tk.Label(s3, text="秒", font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text"]).pack(side=tk.LEFT, padx=(4, 0))

        # 提示
        if HAS_CTK:
            ctk.CTkLabel(card, text="片头片尾会使用 -c copy 快速拼接，不重新编码，速度极快",
                         font=("Microsoft YaHei UI", 9), text_color=C["text3"]).pack(anchor="w", pady=(8, 0))
        else:
            tk.Label(card, text="片头片尾会使用 -c copy 快速拼接，不重新编码，速度极快",
                     font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"]).pack(anchor="w", pady=(8, 0))

        # 恢复已选文件
        if self.io_intro_var.get():
            self.io_intro_label.configure(text=os.path.basename(self.io_intro_var.get()))
        if self.io_outro_var.get():
            self.io_outro_label.configure(text=os.path.basename(self.io_outro_var.get()))

    def _io_select_intro(self):
        p = filedialog.askopenfilename(title="选择片头视频", filetypes=[("视频", "*.mp4 *.mkv *.avi *.mov *.flv")])
        if p:
            self.io_intro_var.set(p)
            self.io_intro_label.configure(text=os.path.basename(p))
            if HAS_CTK:
                self.io_intro_label.configure(text_color=C["success"])
            self._save_config()

    def _io_clear_intro(self):
        self.io_intro_var.set("")
        self.io_intro_label.configure(text="未选择")
        if HAS_CTK:
            self.io_intro_label.configure(text_color=C["text3"])
        self._save_config()

    def _io_select_outro(self):
        p = filedialog.askopenfilename(title="选择片尾视频", filetypes=[("视频", "*.mp4 *.mkv *.avi *.mov *.flv")])
        if p:
            self.io_outro_var.set(p)
            self.io_outro_label.configure(text=os.path.basename(p))
            if HAS_CTK:
                self.io_outro_label.configure(text_color=C["success"])
            self._save_config()

    def _io_clear_outro(self):
        self.io_outro_var.set("")
        self.io_outro_label.configure(text="未选择")
        if HAS_CTK:
            self.io_outro_label.configure(text_color=C["text3"])
        self._save_config()

    # ═══════════════════════════════════════
    #  处理控制（带动画）
    # ═══════════════════════════════════════

    def _on_start_click(self):
        """开始按钮点击 — 带闪光动效"""
        if HAS_CTK:
            self._animate_button_click(self.btn_start, C["success"], "#88ffdd")
            # 脉冲效果
            self._animate_pulse(self.btn_start, C["success"], "#66ffcc", 4)
        self._start()

    def _on_stop_click(self):
        """停止按钮点击 — 带闪光动效"""
        if HAS_CTK:
            self._animate_button_click(self.btn_stop, C["danger"], "#ff9999")
        self._stop()

    def _start(self):
        if self._processing: return
        mode = self.mode_var.get()

        # 检查视频列表
        has_videos = len(self.videos) > 0 or len(self.folder_groups) > 0
        if not has_videos:
            messagebox.showwarning("提示", "请添加视频文件或文件夹"); return

        if mode == "套框":
            if not self.frame_template:
                messagebox.showwarning("提示", "请选择模板图片"); return
            if not self.frame_roi:
                messagebox.showwarning("提示", "请框选视频区域"); return
            info = f"模板: {os.path.basename(self.frame_template)}\n区域: {self.frame_roi}"
        elif mode == "画中画":
            if not self.pip_template:
                messagebox.showwarning("提示", "请选择模板图片"); return
            if not self.pip_regions:
                messagebox.showwarning("提示", "请至少框选一个区域"); return
            info = f"模板: {os.path.basename(self.pip_template)}\n区域: {len(self.pip_regions)}个"
        elif mode == "横转竖":
            info = f"方向: {'顺时针' if self.rotate_dir.get()=='cw' else '逆时针'}90°"
        elif mode == "流水线":
            steps = []
            if self.pipe_rotate_var.get(): steps.append("横转竖")
            if self.pipe_frame_var.get(): steps.append("套框")
            if self.pipe_pip_var.get(): steps.append("画中画")
            if self.pipe_intro_outro_var.get(): steps.append("片头片尾")
            if not steps:
                messagebox.showwarning("提示", "请至少勾选一个步骤"); return
            info = f"步骤: {' → '.join(steps)}"
        else:
            return

        file_info = ""
        if self.folder_groups:
            total_vids = sum(len(g["videos"]) for g in self.folder_groups)
            file_info = f"\n文件夹: {len(self.folder_groups)}个 ({total_vids}个视频)"
        else:
            file_info = f"\n视频: {len(self.videos)}个"

        merge_info = f"\n合并: 每{self.merge_count.get()}个合并" if self.merge_var.get() else ""
        codec_info = f"编码: {self.codec_var.get()} {self.bitrate_var.get()}kbps"

        if not messagebox.askyesno("确认处理",
            f"模式: {mode}\n{info}\n{codec_info}{merge_info}{file_info}\n\n输出: {self.out_dir.get()}\n\n开始处理？"):
            return

        self._processing = True
        self._cancel = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress["value"] = 0
        self.lbl_eta.configure(text="🔄 启动中...")
        self._log(f"🚀 准备处理 [{mode}]...")

        threading.Thread(target=self._process_worker, daemon=True).start()

    def _stop(self):
        self._cancel = True
        self._log("⏹ 正在停止...")
        if self._current_proc:
            try:
                self._current_proc.terminate()
                self._log("⏹ 已发送停止信号")
            except:
                try:
                    self._current_proc.kill()
                    self._log("⏹ 已强制终止ffmpeg进程")
                except:
                    pass
        # 清理临时文件
        self._cleanup_temp_files()
        self.btn_stop.configure(state="disabled")
        self.btn_start.configure(state="normal")
        # 清理所有动画状态
        if hasattr(self, '_loading_active'):
            self._loading_active = False
        self._stop_loading(self.lbl_status, "⏹ 已停止")
        self._processing = False
        self._log("⏹ 已停止")

    def _cleanup_temp_files(self):
        """清理输出目录中的临时文件"""
        try:
            out = self.out_dir.get()
            if not out or not os.path.isdir(out):
                return
            cleaned = 0
            for f in os.listdir(out):
                fp = os.path.join(out, f)
                # 清理 _temp_ 开头的文件和 .tmp.mp4 文件
                if f.startswith("_temp_") or f.endswith(".tmp.mp4"):
                    try:
                        os.remove(fp)
                        cleaned += 1
                    except: pass
                # 清理 .temp 目录
                if f == ".temp" and os.path.isdir(fp):
                    try:
                        shutil.rmtree(fp, ignore_errors=True)
                        cleaned += 1
                    except: pass
            if cleaned > 0:
                self._log(f"  🧹 已清理 {cleaned} 个临时文件")
        except: pass

    def _process_worker(self):
        mode = self.mode_var.get()
        out = self.out_dir.get()
        os.makedirs(out, exist_ok=True)
        t0 = time.time()

        self._log(f"🚀 开始处理 [{mode}]")

        try:
            if mode == "套框":
                self._process_with_folder_groups(self._process_frame_single, "_套框", out)
            elif mode == "画中画":
                self._process_with_folder_groups(self._process_pip_single_wrapper, "_画中画", out)
            elif mode == "横转竖":
                self._process_with_folder_groups(self._process_rotate_single, "_竖屏", out)
            elif mode == "流水线":
                self._process_pipeline(out)
            elif mode == "片头片尾":
                self._process_intro_outro_mode(out)
        except Exception as e:
            import traceback
            self._log(f"❌ 错误: {e}")
            self._log(traceback.format_exc()[-300:])

        elapsed = time.time() - t0
        self._processing = False
        try:
            def _finish():
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                # 清理临时文件
                self._cleanup_temp_files()
                # 确保 .temp 目录被清理（兜底）
                out_dir = self.out_dir.get()
                if out_dir:
                    temp_dir = os.path.join(out_dir, ".temp")
                    if os.path.isdir(temp_dir):
                        try:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            self._log("  🧹 已清理 .temp 目录")
                        except: pass
                # 完成脉冲动效
                if HAS_CTK:
                    self._animate_pulse(self.btn_start, C["success"], "#44ffcc", 3)
                self.progress["value"] = 100
                self.lbl_eta.configure(text=f"✅ 共 {elapsed:.1f}s")
                self._stop_loading(self.lbl_status, f"✅ 完成 · 耗时 {elapsed:.1f}秒")
            self.root.after(0, _finish)
        except Exception:
            pass

    # ═══════════════════════════════════════
    #  统一文件夹合并处理（核心重构）
    # ═══════════════════════════════════════

    def _process_single_folder_group(self, process_func, suffix, out, gname, gvids):
        """处理单个文件夹组：逐个处理视频，支持并行，最后合并"""
        if len(gvids) == 1:
            # 单个视频直接处理
            process_func(gvids[0], out, f"{gname}{suffix}.mp4")
        else:
            # 多个视频：逐个处理（支持并行），最后快速合并
            processed = []
            workers = self.parallel_var.get()
            if workers > 1 and len(gvids) > 1:
                # 并行处理
                self._log(f"  🚀 并行处理 ({workers}路)...")
                self._create_worker_slots(min(workers, len(gvids)))
                import queue
                task_queue = queue.Queue()
                for vi, vpath in enumerate(gvids):
                    task_queue.put((vi, vpath))
                results = []
                def worker_thread(worker_id):
                    while not self._cancel:
                        try:
                            vi, vpath = task_queue.get_nowait()
                        except queue.Empty:
                            break
                        self._update_worker(worker_id, os.path.basename(vpath), 0, "处理中...")
                        temp_dir = os.path.join(out, ".temp")
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_out = os.path.join(temp_dir, f"{vi:04d}.mp4")
                        try:
                            process_func(vpath, temp_dir, f"{vi:04d}.mp4")
                            if os.path.exists(temp_out):
                                results.append((vi, temp_out))
                            else:
                                default_out = os.path.join(out, f"{os.path.splitext(os.path.basename(vpath))[0]}{suffix}.mp4")
                                if os.path.exists(default_out):
                                    results.append((vi, default_out))
                            self._update_worker(worker_id, os.path.basename(vpath), 100, "✅ 完成")
                        except Exception as e:
                            self._log(f"  ❌ 第{vi+1}个失败: {e}")
                            self._update_worker(worker_id, os.path.basename(vpath), 0, "❌ 失败")
                        task_queue.task_done()
                threads = []
                for wi in range(min(workers, len(gvids))):
                    t = threading.Thread(target=worker_thread, args=(wi,), daemon=True)
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()
                self._clear_worker_slots()
                processed = results
                processed.sort(key=lambda x: x[0])
                processed = [p[1] for p in processed]
            else:
                # 串行处理
                for vi, vpath in enumerate(gvids):
                    if self._cancel: break
                    self._set_status(f"🎬 处理 {vi+1}/{len(gvids)}")
                    temp_dir = os.path.join(out, ".temp")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_out = os.path.join(temp_dir, f"{vi:04d}.mp4")
                    process_func(vpath, temp_dir, f"{vi:04d}.mp4")
                    if os.path.exists(temp_out):
                        processed.append(temp_out)
                    else:
                        default_out = os.path.join(out, f"{os.path.splitext(os.path.basename(vpath))[0]}{suffix}.mp4")
                        if os.path.exists(default_out):
                            processed.append(default_out)

            # 快速合并处理后的视频（-c copy，秒级完成）
            if len(processed) > 1:
                final_out = os.path.join(out, f"{gname}{suffix}.mp4")
                self._quick_concat(processed, final_out)
                for f in processed:
                    try: os.remove(f)
                    except: pass
                self._log(f"  ✅ 合并完成: {gname}{suffix}.mp4")
            elif len(processed) == 1:
                try: os.rename(processed[0], os.path.join(out, f"{gname}{suffix}.mp4"))
                except: pass
            # 清理 .temp 目录
            temp_dir = os.path.join(out, ".temp")
            if os.path.isdir(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    self._log(f"  🧹 已清理临时文件")
                except: pass

    def _process_with_folder_groups(self, process_func, suffix, out):
        """统一处理逻辑：逐个视频处理，有文件夹组时处理后快速合并结果"""
        # 有文件夹组时，逐个处理每个视频，然后合并结果
        if self.folder_groups:
            total = len(self.folder_groups)

            # 分批次输出：按集数分割文件夹
            if self.batch_output_var.get():
                batch_eps = self.batch_episodes_var.get()
                for gi, group in enumerate(self.folder_groups):
                    if self._cancel: break
                    gname = group["name"]
                    gvids = group["videos"]
                    if len(gvids) <= batch_eps:
                        self._log(f"📁 [{gi+1}/{total}] {gname} ({len(gvids)}集)")
                        self._set_status(f"📁 处理 {gname}...")
                        self._process_single_folder_group(process_func, suffix, out, gname, gvids)
                    else:
                        num_batches = (len(gvids) + batch_eps - 1) // batch_eps
                        self._log(f"📁 [{gi+1}/{total}] {gname} ({len(gvids)}集, 分{num_batches}段)")
                        for bi in range(num_batches):
                            if self._cancel: break
                            start_idx = bi * batch_eps
                            end_idx = min(start_idx + batch_eps, len(gvids))
                            batch_vids = gvids[start_idx:end_idx]
                            batch_name = f"{gname}_P{bi+1}"
                            self._log(f"  🎬 {batch_name} ({start_idx+1}-{end_idx}集)")
                            self._set_status(f"📁 {batch_name}")
                            self._process_single_folder_group(process_func, suffix, out, batch_name, batch_vids)
                    # 清理该文件夹的临时文件
                    temp_dir = os.path.join(out, ".temp")
                    if os.path.isdir(temp_dir):
                        try:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                        except: pass
                return

            for gi, group in enumerate(self.folder_groups):
                if self._cancel: break
                gname = group["name"]
                gvids = group["videos"]
                self._log(f"📁 [{gi+1}/{total}] 处理文件夹: {gname} ({len(gvids)}个视频)")
                self._set_status(f"📁 处理 {gname}...")

                self._process_single_folder_group(process_func, suffix, out, gname, gvids)
            return

        # 无文件夹组，按视频列表处理
        videos = list(self.videos)
        if self.merge_var.get() and len(videos) > 1:
            # 手动合并模式：先合并再处理
            if self.merge_mode.get() == "folder":
                d = filedialog.askdirectory(title="选择要合并的文件夹")
                if not d:
                    self._set_status("已取消"); return
                folder_videos = sorted([os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(VIDEO_EXTS)], key=_natural_sort_key)
                if not folder_videos:
                    messagebox.showwarning("提示", "文件夹内没有视频文件"); return
                self.folder_name = os.path.basename(d)
                self._log(f"📂 文件夹合并: {d} ({len(folder_videos)}个视频 → 合并为1个)")
                self._set_status("🔗 合并视频中...")
                videos = self._merge_videos(folder_videos, out)
            elif len(videos) > 1:
                if not self.folder_name and videos:
                    self.folder_name = os.path.basename(os.path.dirname(videos[0]))
                self._log("🔗 正在合并视频...")
                self._set_status("🔗 合并视频中...")
                videos = self._merge_videos(videos, out)

        for vpath in videos:
            if self._cancel: break
            process_func(vpath, out)

    # ═══════════════════════════════════════
    #  流水线处理（新增）
    # ═══════════════════════════════════════
    def _process_pipeline(self, out):
        """流水线模式：按顺序执行勾选的步骤"""
        steps = []
        if self.pipe_rotate_var.get(): steps.append("rotate")
        if self.pipe_frame_var.get(): steps.append("frame")
        if self.pipe_pip_var.get(): steps.append("pip")
        if self.pipe_intro_outro_var.get(): steps.append("intro_outro")

        if not steps:
            self._log("❌ 未选择任何步骤"); return

        step_names = {"rotate": "横转竖", "frame": "套框", "pip": "画中画", "intro_outro": "片头片尾"}
        self._log(f"🔗 流水线: {' → '.join(step_names[s] for s in steps)}")

        # 对每个视频/文件夹组，依次执行所有步骤
        items = []
        if self.folder_groups:
            for group in self.folder_groups:
                items.append(("group", group))
        else:
            for v in self.videos:
                items.append(("video", v))

        total_items = len(items)
        for idx, (item_type, item) in enumerate(items):
            if self._cancel: break

            if item_type == "group":
                gname = item["name"]
                gvids = item["videos"]
                self._log(f"\n📁 [{idx+1}/{total_items}] {gname} ({len(gvids)}个视频)")

                if len(gvids) == 1:
                    # 单个视频直接流水线
                    current = gvids[0]
                    for si, step in enumerate(steps):
                        if self._cancel: break
                        suffix = f"_{step_names[step]}"
                        out_name = f"{gname}{suffix}.mp4" if si == len(steps) - 1 else f"{gname}_temp_{step}.mp4"
                        current = self._pipeline_step(step, current, out, out_name)
                        if current is None:
                            self._log(f"❌ 步骤{step_names[step]}失败，跳过后续步骤")
                            break
                    self._pipeline_cleanup(gname, steps, out)
                else:
                    # 多个视频：逐个走流水线，最后快速合并
                    processed = []
                    for vi, vpath in enumerate(gvids):
                        if self._cancel: break
                        self._set_status(f"🎬 流水线 {vi+1}/{len(gvids)}")
                        current = vpath
                        for si, step in enumerate(steps):
                            if self._cancel: break
                            suffix = f"_{step_names[step]}"
                            temp_name = f"_temp_{gname}_{vi:03d}_{step}.mp4"
                            last_step = (si == len(steps) - 1)
                            out_name = f"_temp_{gname}_{vi:03d}_final.mp4" if last_step else temp_name
                            current = self._pipeline_step(step, current, out, out_name)
                            if current is None:
                                self._log(f"❌ 步骤{step_names[step]}失败")
                                break
                        if current and os.path.exists(current):
                            processed.append(current)

                    # 快速合并
                    if len(processed) > 1:
                        final_suffix = f"_{step_names[steps[-1]]}"
                        final_out = os.path.join(out, f"{gname}{final_suffix}.mp4")
                        self._quick_concat(processed, final_out)
                        for f in processed:
                            try: os.remove(f)
                            except: pass
                        self._log(f"  ✅ 合并完成: {os.path.basename(final_out)}")

                    # 清理中间临时文件
                    self._pipeline_cleanup(gname, steps, out)
            else:
                # 单个视频
                vpath = item
                basename = os.path.splitext(os.path.basename(vpath))[0]
                self._log(f"\n🎬 [{idx+1}/{total_items}] {basename}")

                current = vpath
                for si, step in enumerate(steps):
                    if self._cancel: break
                    suffix = f"_{step_names[step]}"
                    out_name = f"{basename}{suffix}.mp4" if si == len(steps) - 1 else f"{basename}_temp_{step}.mp4"
                    current = self._pipeline_step(step, current, out, out_name)
                    if current is None:
                        self._log(f"❌ 步骤{step_names[step]}失败，跳过后续步骤")
                        break

                self._pipeline_cleanup(basename, steps, out)

        if not self._cancel:
            self._log(f"\n✅ 流水线处理完成！共 {total_items} 个项目")

    def _pipeline_step(self, step, input_path, out, out_name):
        """执行流水线中的单个步骤，返回输出路径"""
        if step == "rotate":
            self._set_status(f"🔄 横转竖: {os.path.basename(input_path)}")
            return self._process_rotate_single(input_path, out, out_name, return_path=True)
        elif step == "frame":
            self._set_status(f"🖼 套框: {os.path.basename(input_path)}")
            return self._process_frame_single(input_path, out, out_name, return_path=True)
        elif step == "pip":
            self._set_status(f"📺 画中画: {os.path.basename(input_path)}")
            return self._process_pip_single_wrapper(input_path, out, out_name, return_path=True)
        elif step == "intro_outro":
            self._set_status(f"🎬 片头片尾: {os.path.basename(input_path)}")
            # 先复制到输出目录，再原地拼接
            import shutil
            temp_out = os.path.join(out, out_name)
            shutil.copy2(input_path, temp_out)
            self._append_intro_outro(temp_out)
            return temp_out if os.path.exists(temp_out) else None
        return None

    def _pipeline_cleanup(self, basename, steps, out):
        """清理流水线中间临时文件"""
        if len(steps) <= 1:
            return
        for step in steps[:-1]:
            step_names = {"rotate": "横转竖", "frame": "套框", "pip": "画中画", "intro_outro": "片头片尾"}
            temp = os.path.join(out, f"{basename}_temp_{step}.mp4")
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                    self._log(f"  🗑 清理临时文件: {os.path.basename(temp)}")
                except:
                    pass

    # ═══════════════════════════════════════
    #  套框处理
    # ═══════════════════════════════════════
    def _process_frame_single(self, vpath, out, out_name=None, return_path=False):
        self._log(f"🖼 处理: {os.path.basename(vpath)}")
        self._set_status("🖼 处理中...")

        info = self._get_video_info(vpath)
        x, y, w, h = self.frame_roi
        w, h = w // 2 * 2, h // 2 * 2
        codec = self.codec_var.get()
        bitrate = self.bitrate_var.get()

        converted_tmp = None
        if 'nvenc' in codec:
            orig_vpath = vpath
            vpath = self._ensure_nvenc_compatible(vpath, out)
            if vpath != orig_vpath:
                converted_tmp = vpath  # track for cleanup

        if out_name:
            name = out_name
        elif self.folder_name:
            name = f"{self.folder_name}_套框.mp4"
        else:
            name = os.path.splitext(os.path.basename(vpath))[0] + "_套框.mp4"
        outpath = os.path.join(out, name)

        ext = os.path.splitext(self.frame_template)[1].lower() if self.frame_template else ""
        is_video_template = ext in VIDEO_EXTS

        if self.bg_color:
            # 纯色背景 → 全GPU流程 (CUDA decode → scale_cuda → overlay_cuda → NVENC)
            color_hex = self.bg_color.lstrip('#')
            res = getattr(self, 'output_resolution', '1920x1080')
            vf = (f"[0:v]scale_cuda={w}:{h}:force_original_aspect_ratio=decrease[vid];"
                  f"color=c=0x{color_hex}:s={res}:d={info.get('duration', 9999)}:r=30,"
                  f"format=cuda[bg];"
                  f"[bg][vid]overlay_cuda={x}:{y}[out]")
            cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-i', vpath,
                   '-filter_complex', vf, '-map', '[out]', '-map', '0:a?',
                   '-t', str(info.get("duration", 9999))]
        elif is_video_template:
            t_info = self._get_video_info(self.frame_template)
            dur = info.get("duration", t_info.get("duration", 9999))
            # 视频模板: 上传GPU一次，全程CUDA处理
            vf = (f"[0:v]hwupload_cuda,format=cuda[bg];"
                  f"[1:v]scale_cuda={w}:{h}:force_original_aspect_ratio=decrease[vid];"
                  f"[bg][vid]overlay_cuda={x}:{y}[out]")
            cmd = ['ffmpeg', '-y', '-stream_loop', '-1', '-i', self.frame_template,
                   '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-i', vpath,
                   '-filter_complex', vf, '-map', '[out]', '-map', '1:a?', '-t', str(dur)]
        else:
            # 图片模板: 预编译成视频（只做一次，后续全程GPU解码）
            tpl_video = self._image_to_video_template(self.frame_template, w, h, info.get("duration", 9999))
            if tpl_video:
                vf = (f"[0:v]scale_cuda={w}:{h}[bg];"
                      f"[1:v]scale_cuda={w}:{h}:force_original_aspect_ratio=decrease[vid];"
                      f"[bg][vid]overlay_cuda={x}:{y}[out]")
                cmd = ['ffmpeg', '-y',
                       '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-i', tpl_video,
                       '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-i', vpath,
                       '-filter_complex', vf, '-map', '[out]', '-map', '1:a?',
                       '-t', str(info.get("duration", 9999))]
            else:
                # fallback: 直接用图片（兼容模式）
                vf = (f"[0:v]format=nv12,hwupload_cuda,format=cuda[bg];"
                      f"[1:v]scale_cuda={w}:{h}:force_original_aspect_ratio=decrease[vid];"
                      f"[bg][vid]overlay_cuda={x}:{y}[out]")
                cmd = ['ffmpeg', '-y', '-i', self.frame_template,
                       '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-i', vpath,
                       '-filter_complex', vf, '-map', '[out]', '-map', '1:a?',
                       '-t', str(info.get("duration", 9999))]

        cmd.extend(self._encode_args(codec, bitrate))
        cmd.extend(['-movflags', '+faststart'])
        cmd.append(outpath)

        dur = info.get("duration", 9999)
        r = self._run_ffmpeg_progress(cmd, dur, timeout=14400, outpath=outpath, bitrate_kbps=int(bitrate))
        if r != 0 and 'nvenc' in codec:
            self._log("⚠️ NVENC失败，自动切换到libx264...")
            self._nvenc_fallback(cmd, outpath, dur)
        if r == 0:
            self._log(f"  ✅ 完成: {name}")
            self._append_intro_outro(outpath)
            if converted_tmp and os.path.exists(converted_tmp):
                try: os.remove(converted_tmp)
                except: pass
            return outpath if return_path else None
        else:
            self._log(f"  ❌ 失败 (code={r})")
            if converted_tmp and os.path.exists(converted_tmp):
                try: os.remove(converted_tmp)
                except: pass
            return None

    def _trim_template_video(self, template_path, target_duration):
        """预裁剪模板视频到目标时长（stream copy，瞬间完成）"""
        cache_dir = os.path.join(os.path.dirname(template_path), '.tpl_cache')
        os.makedirs(cache_dir, exist_ok=True)
        h = hashlib.md5(template_path.encode()).hexdigest()[:8]
        name = f"trim_{h}_{int(target_duration)}.mp4"
        outpath = os.path.join(cache_dir, name)
        if os.path.exists(outpath):
            return outpath
        cmd = ['ffmpeg', '-y', '-i', template_path,
               '-t', str(target_duration), '-c', 'copy', outpath]
        r = self._run_ffmpeg_progress(cmd, target_duration, timeout=300, outpath=outpath)
        if r == 0:
            self._log(f"  📦 模板已裁剪到 {target_duration:.1f}秒")
            return outpath
        return None

    def _image_to_video_template(self, image_path, target_w, target_h, duration):
        """把静态图片预编译成视频文件，避免 -loop 1 每帧重读图片的CPU开销"""
        import tempfile
        cache_key = f"{os.path.basename(image_path)}_{target_w}x{target_h}"
        cache_path = os.path.join(tempfile.gettempdir(), f"tpl_{hash(cache_key) & 0xFFFFFFFF:08x}.mp4")
        # 有缓存直接返回
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
            # 验证缓存视频时长是否合理（至少1秒，不超过120秒）
            try:
                info = self._get_video_info(cache_path)
                cached_dur = info.get("duration", 0)
                if 1 <= cached_dur <= 120:
                    self._log(f"  📦 使用缓存模板视频: {os.path.basename(cache_path)}")
                    return cache_path
                else:
                    self._log(f"  ⚠️ 缓存模板时长异常({cached_dur}秒)，重新编译")
                    os.remove(cache_path)
            except:
                os.remove(cache_path)
        try:
            self._log(f"  🔄 预编译图片模板 → 视频 ({target_w}x{target_h})...")
            # 使用10秒时长，足够覆盖大部分场景，同时保持文件较小
            template_duration = 10
            cmd = ['ffmpeg', '-y', '-loop', '1', '-t', str(template_duration),
                   '-i', image_path,
                   '-vf', f'scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,'
                          f'pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '10',
                   '-r', '30', '-an', cache_path]
            r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)
            if r.returncode == 0 and os.path.exists(cache_path):
                # 验证生成的视频时长
                info = self._get_video_info(cache_path)
                actual_dur = info.get("duration", 0)
                if actual_dur >= 1 and actual_dur <= 120:
                    self._log(f"  ✅ 模板视频就绪: {os.path.basename(cache_path)} ({actual_dur}秒)")
                    return cache_path
                else:
                    self._log(f"  ⚠️ 生成的模板时长异常({actual_dur}秒)，使用兼容模式")
                    try: os.remove(cache_path)
                    except: pass
                    return None
            else:
                self._log(f"  ⚠️ 模板视频编译失败，使用兼容模式")
                return None
        except Exception as e:
            self._log(f"  ⚠️ 模板视频编译异常: {e}")
            return None

    def _nvenc_fallback(self, orig_cmd, outpath, dur):
        cmd = ['ffmpeg', '-y']
        parts = []
        skip_next = False
        cuda_parts = {'-hwaccel', '-hwaccel_output_format', '-hwaccel_device'}
        for part in orig_cmd[1:]:
            if skip_next:
                skip_next = False
                continue
            # 去掉编码器参数
            if part in ('-c:v', '-preset', '-rc', '-b:v', '-maxrate', '-bufsize', '-pix_fmt'):
                skip_next = True
                continue
            # 去掉CUDA硬件加速参数
            if part in cuda_parts:
                skip_next = True
                continue
            parts.append(part)
        out_file = parts[-1]
        main_parts = parts[:-1]
        # 把CUDA滤镜转换为CPU滤镜（同时处理 -filter_complex 和 -vf）
        for i, p in enumerate(main_parts):
            if p in ('-filter_complex', '-vf') and i + 1 < len(main_parts):
                fc = main_parts[i + 1]
                fc = fc.replace('hwdownload,', '')
                fc = fc.replace('hwupload_cuda,format=cuda,', '')
                fc = fc.replace('hwupload_cuda,', '')
                fc = fc.replace('format=nv12,hwupload_cuda,format=cuda', 'format=yuv420p')
                fc = fc.replace('format=cuda,', 'format=yuv420p,')
                fc = fc.replace('format=cuda', 'format=yuv420p')
                fc = fc.replace('scale_cuda=', 'scale=')
                fc = fc.replace('overlay_cuda=', 'overlay=')
                main_parts[i + 1] = fc
        cmd.extend(main_parts)
        fallback_br = 6000  # 默认fallback码率
        cmd.extend(['-pix_fmt', 'yuv420p', '-c:v', 'libx265', '-preset', 'medium',
                    '-b:v', f'{fallback_br}k', '-maxrate', f'{int(fallback_br*1.5)}k', '-bufsize', f'{int(fallback_br*2)}k',
                    '-x265-params', 'log-level=error', '-tag:v', 'hvc1',
                    '-c:a', 'flac', '-ar', '96000'])
        cmd.append(out_file)
        self._log("🔄 CUDA失败，使用CPU滤镜+libx265重新编码...")
        r = self._run_ffmpeg_progress(cmd, dur, timeout=14400, outpath=outpath, bitrate_kbps=fallback_br)
        if r == 0:
            self._log("  ✅ 完成（CPU降级）")
            self._append_intro_outro(outpath)

    def _ensure_nvenc_compatible(self, vpath, out_dir):
        info = self._get_video_info(vpath)
        pix_fmt = info.get('pix_fmt', 'unknown')
        if pix_fmt == 'yuv420p':
            return vpath
        self._log(f"🔄 转换格式: {pix_fmt} → yuv420p (NVENC兼容)")
        base = os.path.splitext(os.path.basename(vpath))[0]
        out_path = os.path.join(out_dir, f"{base}_converted.mp4")
        cmd = ['ffmpeg', '-y', '-i', vpath, '-pix_fmt', 'yuv420p',
               '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',
               '-c:a', 'copy', '-movflags', '+faststart', out_path]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=7200)
        if r.returncode == 0:
            self._log("✅ 格式转换完成")
            return out_path
        else:
            self._log("⚠️ 格式转换失败，使用原始文件")
            return vpath

    # ═══════════════════════════════════════
    #  画中画处理
    # ═══════════════════════════════════════
    def _process_pip_single_wrapper(self, vpath, out, out_name=None, return_path=False):
        """画中画包装器：处理单个视频"""
        if not self.pip_template or "center" not in self.pip_regions or not self.pip_enable_center.get():
            self._log("❌ 未设置画中画模板/区域"); return None

        if out_name:
            name = out_name
        elif self.folder_name:
            name = f"{self.folder_name}_画中画.mp4"
        else:
            name = os.path.splitext(os.path.basename(vpath))[0] + "_画中画.mp4"

        # 分段功能已移除，逐个视频处理避免合并损坏

        result = self._process_pip_single(vpath, out, name)
        if result == 0:
            result_path = os.path.join(out, name)
            return result_path if return_path else None
        return None

    def _process_pip_single(self, center_input, out, out_name, do_merge=False, total_duration=None):
        """处理画中画"""
        if isinstance(center_input, list):
            center_files = center_input
        else:
            center_files = [center_input]

        if total_duration is None:
            total_duration = sum(self._get_real_duration(f) for f in center_files)

        # 超长视频分段处理
        segment_sec = self.segment_minutes_var.get() * 60
        if self.segment_var.get() and total_duration > segment_sec:
            return self._process_pip_segmented(center_files, out, out_name, do_merge, total_duration, segment_sec)

        if not self.pip_template:
            self._log("❌ 未设置模板图片"); return
        if not self.pip_regions:
            self._log("❌ 未设置区域"); return
        if "center" not in self.pip_regions or not self.pip_enable_center.get():
            self._log("❌ 未设置正片区域"); return

        self._log(f"📊 开始处理画中画: {out_name}")
        self._log(f"  模板: {os.path.basename(self.pip_template)}")
        self._log(f"  区域: {[k for k in self.pip_regions.keys() if getattr(self, f'pip_enable_{k}', tk.BooleanVar(value=True)).get()]}")
        self._log(f"  正片: {len(center_files)}个文件")
        self._log(f"  装饰: 左={len(self.pip_left_files) if self.pip_left_files and self.pip_enable_left_decor.get() else 0}, 右={len(self.pip_right_files) if self.pip_right_files and self.pip_enable_right_decor.get() else 0}")
        self._log(f"  总时长: {total_duration:.1f}秒")

        # 缓存装饰视频（4K→1080p）
        left_files = [self._cache_decoration_video(f) for f in self.pip_left_files] if self.pip_left_files and self.pip_enable_left_decor.get() else []
        right_files = [self._cache_decoration_video(f) for f in self.pip_right_files] if self.pip_right_files and self.pip_enable_right_decor.get() else []
        codec = self.codec_var.get()
        bitrate = self.bitrate_var.get()
        outpath = os.path.join(out, out_name)

        cmd = ['ffmpeg', '-y']
        input_count = 0

        # 图片模板预编译成视频（避免 -loop 1 导致时长异常）
        tpl_ext = os.path.splitext(self.pip_template)[1].lower()
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts')
        if tpl_ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff'):
            tpl_info = self._get_video_info(self.pip_template)
            bg_w = tpl_info.get("width", 1920)
            bg_h = tpl_info.get("height", 1080)
            tpl_video = self._image_to_video_template(self.pip_template, bg_w, bg_h, total_duration)
            if tpl_video:
                cmd.extend(['-stream_loop', '-1', '-i', tpl_video])
                self._log(f"  📦 模板已预编译为视频")
            else:
                # 预编译失败时，使用 -loop 1 但添加安全限制
                self._log(f"  ⚠️ 使用兼容模式（-loop 1），时长限制: {total_duration}秒")
                cmd.extend(['-loop', '1', '-t', str(total_duration), '-i', self.pip_template])
        elif tpl_ext in video_exts:
            # 视频模板：预裁剪或循环
            tpl_dur = self._get_real_duration(self.pip_template)
            if tpl_dur > 0 and tpl_dur < total_duration:
                cmd.extend(['-stream_loop', '-1', '-i', self.pip_template])
                self._log(f"  📦 视频模板循环播放（{tpl_dur:.1f}秒 → {total_duration:.1f}秒）")
            else:
                # 模板比正片长：预裁剪到正片时长（避免 NVENC 不遵守 -t）
                trimmed = self._trim_template_video(self.pip_template, total_duration)
                if trimmed:
                    cmd.extend(['-i', trimmed])
                    self._log(f"  📦 模板已裁剪到 {total_duration:.1f}秒")
                else:
                    cmd.extend(['-t', str(total_duration), '-i', self.pip_template])
                    self._log(f"  ⚠️ 裁剪失败，使用 -t 输入限制")
        else:
            cmd.extend(['-i', self.pip_template])
        input_count += 1

        left_idx = None
        if left_files:
            left_idx = input_count
            lf = left_files[0]
            l_dur = self._get_real_duration(lf)
            if l_dur > 0 and l_dur < total_duration:
                cmd.extend(['-stream_loop', '-1', '-t', str(total_duration)])
            cmd.extend(['-i', lf])
            input_count += 1

        center_start_idx = input_count
        if do_merge:
            for cf in center_files:
                cmd.extend(['-i', cf])
                input_count += 1
            center_input_count = len(center_files)
        else:
            cmd.extend(['-i', center_files[0]])
            input_count += 1
            center_input_count = 1

        right_idx = None
        if right_files:
            right_idx = input_count
            rf = right_files[0]
            r_dur = self._get_real_duration(rf)
            if r_dur > 0 and r_dur < total_duration:
                cmd.extend(['-stream_loop', '-1', '-t', str(total_duration)])
            cmd.extend(['-i', rf])
            input_count += 1

        filter_parts = []
        center_label = "[center_v]"

        if do_merge:
            concat_v = "".join(f"[{center_start_idx + i}:v]" for i in range(center_input_count))
            filter_parts.append(f"{concat_v}concat=n={center_input_count}:v=1[center_v]")
            for i in range(center_input_count):
                filter_parts.append(f"[{center_start_idx + i}:a]aresample=48000,aformat=channel_layouts=stereo[c{i}_a]")
            concat_a = "".join(f"[c{i}_a]" for i in range(center_input_count))
            filter_parts.append(f"{concat_a}concat=n={center_input_count}:v=0:a=1[center_a]")
        else:
            center_label = f"[{center_start_idx}:v]"

        # 获取正片实际分辨率（只调用一次）
        probe_info = self._get_video_info(center_files[0])
        src_w = probe_info.get("width", 1920)
        src_h = probe_info.get("height", 1080)

        # 获取背景模板尺寸
        tpl_info = self._get_video_info(self.pip_template)
        bg_w = tpl_info.get("width", 1920)
        bg_h = tpl_info.get("height", 1080)

        out_w, out_h = bg_w, bg_h
        if out_w % 2 != 0: out_w -= 1
        if out_h % 2 != 0: out_h -= 1

        # 判断是否需要旋转：横屏视频(w>h)放竖屏区域时需要旋转
        center_region = self.pip_regions["center"]
        cx, cy, cw, ch = center_region
        need_rotate_center = src_w > src_h and ch > cw
        center_vf = f"{center_label}" + ("transpose=2," if need_rotate_center else "") + f"scale={cw}:{ch}:force_original_aspect_ratio=decrease[center_scaled]"
        filter_parts.append(center_vf)
        filter_parts.append(f"[0:v]scale={out_w}:{out_h}[bg]")
        filter_parts.append(f"[bg][center_scaled]overlay={cx}:{cy}[out]")

        output_label = "[out]"

        # 左区域
        if left_files and left_idx is not None and "left" in self.pip_regions and self.pip_enable_left.get():
            lx, ly, lw, lh = self.pip_regions["left"]
            # 获取装饰视频分辨率
            left_info = self._get_video_info(left_files[0])
            lsrc_w = left_info.get("width", 1920)
            lsrc_h = left_info.get("height", 1080)
            need_rotate_left = lsrc_w > lsrc_h and lh > lw
            left_vf = (f"[{left_idx}:v]" + ("transpose=2," if need_rotate_left else "") +
                       f"scale={lw}:{lh}:force_original_aspect_ratio=decrease[left_scaled]")
            filter_parts.append(left_vf)
            filter_parts.append(f"{output_label}[left_scaled]overlay={lx}:{ly}[out_left]")
            output_label = "[out_left]"

        # 右区域
        if right_files and right_idx is not None and "right" in self.pip_regions and self.pip_enable_right.get():
            rx, ry, rw, rh = self.pip_regions["right"]
            right_info = self._get_video_info(right_files[0])
            rsrc_w = right_info.get("width", 1920)
            rsrc_h = right_info.get("height", 1080)
            need_rotate_right = rsrc_w > rsrc_h and rh > rw
            right_vf = (f"[{right_idx}:v]" + ("transpose=2," if need_rotate_right else "") +
                        f"scale={rw}:{rh}:force_original_aspect_ratio=decrease[right_scaled]")
            filter_parts.append(right_vf)
            filter_parts.append(f"{output_label}[right_scaled]overlay={rx}:{ry}[out_right]")
            output_label = "[out_right]"

        # 缩放到1920x1080（NVENC兼容）+ RGBA→yuv420p转换
        filter_parts.append(f"{output_label}scale=1920:1080[out_scaled]")
        filter_parts.append(f"[out_scaled]format=yuv420p[out_fmt]")
        output_label = "[out_fmt]"

        cmd.extend(['-filter_complex', ';'.join(filter_parts)])
        cmd.extend(['-map', output_label])

        if do_merge:
            cmd.extend(['-map', '[center_a]'])
        else:
            cmd.extend(['-map', f'{center_start_idx}:a?'])

        cmd.extend(self._encode_args(codec, bitrate))
        cmd.extend(['-movflags', '+faststart', '-t', str(total_duration)])
        cmd.append(outpath)

        r = self._run_ffmpeg_progress(cmd, total_duration, timeout=14400, outpath=outpath, bitrate_kbps=int(bitrate))
        if r != 0 and 'nvenc' in codec:
            self._log("⚠️ NVENC失败，自动切换到libx265...")
            self._nvenc_fallback(cmd, outpath, total_duration)
        if r == 0:
            self._log(f"  ✅ 完成: {out_name}")
            self._append_intro_outro(outpath)
        return r

    def _process_pip_segmented(self, center_files, out, out_name, do_merge, total_duration, segment_sec):
        import tempfile
        seg_dir = tempfile.mkdtemp(prefix="pip_seg_")
        self._log(f"🔪 分段处理: {total_duration/60:.0f}分钟 → 每段{segment_sec/60:.0f}分钟")

        segments = []
        current_start = 0
        remaining = total_duration
        while remaining > 0:
            seg_dur = min(segment_sec, remaining)
            segments.append((current_start, seg_dur))
            current_start += seg_dur
            remaining -= seg_dur

        self._log(f"  共 {len(segments)} 段")

        segment_files = []

        # 获取背景模板尺寸（偶数修正）
        tpl_info = self._get_video_info(self.pip_template)
        out_w = tpl_info.get("width", 1920) // 2 * 2
        out_h = tpl_info.get("height", 1080) // 2 * 2

        for si, (start, dur) in enumerate(segments):
            if self._cancel: break
            seg_name = f"seg_{si:03d}.mp4"
            seg_path = os.path.join(seg_dir, seg_name)
            self._log(f"  🔪 处理第 {si+1}/{len(segments)} 段 ({start/60:.0f}-{(start+dur)/60:.0f}分钟)")

            # 构建分段FFmpeg命令
            cmd = ['ffmpeg', '-y']
            input_count = 0

            # 图片模板需要预编译成视频（避免 -loop 1 时长异常）
            tpl_ext = os.path.splitext(self.pip_template)[1].lower()
            video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts')
            if tpl_ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff'):
                tpl_video = self._image_to_video_template(self.pip_template, out_w, out_h, dur)
                if tpl_video:
                    cmd.extend(['-stream_loop', '-1', '-i', tpl_video])
                else:
                    # 预编译失败时的兼容模式
                    self._log(f"  ⚠️ 分段模式使用兼容模式（-loop 1）")
                    cmd.extend(['-loop', '1', '-t', str(dur), '-i', self.pip_template])
            elif tpl_ext in video_exts:
                # 视频模板：预裁剪到分段时长
                trimmed = self._trim_template_video(self.pip_template, dur)
                if trimmed:
                    cmd.extend(['-i', trimmed])
                else:
                    cmd.extend(['-stream_loop', '-1', '-i', self.pip_template])
            else:
                cmd.extend(['-i', self.pip_template])
            input_count += 1

            left_files = [self._cache_decoration_video(f) for f in self.pip_left_files] if self.pip_left_files else []
            right_files = [self._cache_decoration_video(f) for f in self.pip_right_files] if self.pip_right_files else []
            left_idx = None
            if left_files:
                left_idx = input_count
                cmd.extend(['-stream_loop', '-1', '-i', left_files[0]])
                input_count += 1

            center_start_idx = input_count
            for cf in center_files:
                cmd.extend(['-ss', str(start), '-t', str(dur), '-i', cf])
                input_count += 1
            center_input_count = len(center_files)

            right_idx = None
            if right_files:
                right_idx = input_count
                cmd.extend(['-stream_loop', '-1', '-i', right_files[0]])
                input_count += 1

            filter_parts = []
            if center_input_count > 1:
                concat_v = "".join(f"[{center_start_idx + i}:v]" for i in range(center_input_count))
                filter_parts.append(f"{concat_v}concat=n={center_input_count}:v=1[center_v]")
                for i in range(center_input_count):
                    filter_parts.append(f"[{center_start_idx + i}:a]aresample=48000,aformat=channel_layouts=stereo[c{i}_a]")
                concat_a = "".join(f"[c{i}_a]" for i in range(center_input_count))
                filter_parts.append(f"{concat_a}concat=n={center_input_count}:v=0:a=1[center_a]")
                center_label = "[center_v]"
            else:
                center_label = f"[{center_start_idx}:v]"

            cx, cy, cw, ch = self.pip_regions["center"]
            probe_info = self._get_video_info(center_files[0])
            src_w = probe_info.get("width", 1920)
            src_h = probe_info.get("height", 1080)
            need_rotate_c = src_w > src_h and ch > cw
            c_vf = (f"{center_label}" + ("transpose=2," if need_rotate_c else "") +
                    f"scale={cw}:{ch}:force_original_aspect_ratio=decrease[center_scaled]")
            filter_parts.append(c_vf)
            filter_parts.append(f"[0:v]scale={out_w}:{out_h}[bg]")
            filter_parts.append(f"[bg][center_scaled]overlay={cx}:{cy}[out]")
            output_label = "[out]"

            if left_files and left_idx is not None and "left" in self.pip_regions and self.pip_enable_left.get():
                lx, ly, lw, lh = self.pip_regions["left"]
                li = self._get_video_info(left_files[0])
                need_rotate_l = li.get("width", 1920) > li.get("height", 1080) and lh > lw
                l_vf = (f"[{left_idx}:v]" + ("transpose=2," if need_rotate_l else "") +
                        f"scale={lw}:{lh}:force_original_aspect_ratio=decrease[left_scaled]")
                filter_parts.append(l_vf)
                filter_parts.append(f"{output_label}[left_scaled]overlay={lx}:{ly}[out_left]")
                output_label = "[out_left]"

            if right_files and right_idx is not None and "right" in self.pip_regions and self.pip_enable_right.get():
                rx, ry, rw, rh = self.pip_regions["right"]
                ri = self._get_video_info(right_files[0])
                need_rotate_r = ri.get("width", 1920) > ri.get("height", 1080) and rh > rw
                r_vf = (f"[{right_idx}:v]" + ("transpose=2," if need_rotate_r else "") +
                        f"scale={rw}:{rh}:force_original_aspect_ratio=decrease[right_scaled]")
                filter_parts.append(f"{output_label}[right_scaled]overlay={rx}:{ry}[out_right]")
                output_label = "[out_right]"

            codec = self.codec_var.get()
            bitrate = self.bitrate_var.get()
            cmd.extend(['-filter_complex', ';'.join(filter_parts)])
            cmd.extend(['-map', output_label])
            if center_input_count > 1:
                cmd.extend(['-map', '[center_a]'])
            else:
                cmd.extend(['-map', f'{center_start_idx}:a?'])
            cmd.extend(self._encode_args(codec, bitrate))
            cmd.extend(['-movflags', '+faststart', '-t', str(dur)])
            cmd.append(seg_path)

            r = self._run_ffmpeg_progress(cmd, dur, timeout=14400, outpath=seg_path, bitrate_kbps=int(bitrate))
            if r != 0 and 'nvenc' in codec:
                # NVENC失败，用libx265重建命令重试
                self._log(f"    ⚠️ NVENC失败，切换libx265...")
                fallback_cmd = ['ffmpeg', '-y']
                # 复制所有 -i 输入和 -ss/-t/-stream_loop 参数（编码参数之前的全部）
                i = 1  # 跳过 'ffmpeg'
                while i < len(cmd) and cmd[i] not in ('-pix_fmt', '-c:v'):
                    fallback_cmd.append(cmd[i])
                    i += 1
                fallback_br = 6000
                fallback_cmd.extend(['-pix_fmt', 'yuv420p', '-c:v', 'libx265', '-preset', 'medium',
                            '-b:v', f'{fallback_br}k', '-maxrate', f'{int(fallback_br*1.5)}k', '-bufsize', f'{int(fallback_br*2)}k',
                            '-x265-params', 'log-level=error', '-tag:v', 'hvc1',
                            '-c:a', 'flac', '-ar', '96000', '-movflags', '+faststart',
                            '-t', str(dur), seg_path])
                r = self._run_ffmpeg_progress(fallback_cmd, dur, timeout=14400, outpath=seg_path, bitrate_kbps=int(bitrate))
            if r == 0:
                segment_files.append(seg_path)
                self._log(f"    ✅ 第{si+1}段完成")
            else:
                self._log(f"    ❌ 第{si+1}段失败")

        if segment_files and not self._cancel:
            self._merge_segments(segment_files, out, out_name)

        # 清理
        try:
            import shutil
            shutil.rmtree(seg_dir, ignore_errors=True)
        except:
            pass

    def _merge_segments(self, segment_files, out, final_name):
        import tempfile
        list_file = os.path.join(tempfile.gettempdir(), "pip_concat.txt")
        with open(list_file, 'w', encoding='utf-8') as f:
            for seg in segment_files:
                f.write(f"file '{seg.replace(chr(92), '/')}'\n")

        outpath = os.path.join(out, final_name)
        cmd = ['ffmpeg', '-y', '-fflags', '+discardcorrupt',
               '-f', 'concat', '-safe', '0', '-i', list_file,
               '-c', 'copy', '-max_muxing_queue_size', '1024', outpath]
        self._log(f"🔗 合并 {len(segment_files)} 段...")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait(timeout=7200)
            if proc.returncode == 0:
                self._log(f"  ✅ 合并完成: {final_name}")
                self._append_intro_outro(outpath)
            else:
                self._log(f"  ❌ 合并失败")
        except Exception as e:
            self._log(f"  ❌ 合并异常: {e}")

        try:
            os.remove(list_file)
            for seg in segment_files:
                os.remove(seg)
        except:
            pass

    # ═══════════════════════════════════════
    #  横转竖处理
    # ═══════════════════════════════════════
    def _process_rotate_single(self, vpath, out, out_name=None, return_path=False):
        self._log(f"🔄 处理: {os.path.basename(vpath)}")
        self._set_status("🔄 处理中...")

        info = self._get_video_info(vpath)
        codec = self.codec_var.get()
        bitrate = self.bitrate_var.get()
        direction = self.rotate_dir.get()

        if out_name:
            name = out_name
        elif self.folder_name:
            name = f"{self.folder_name}_竖屏.mp4"
        else:
            name = os.path.splitext(os.path.basename(vpath))[0] + "_竖屏.mp4"
        outpath = os.path.join(out, name)

        converted_tmp = None
        if 'nvenc' in codec:
            orig_vpath = vpath
            vpath = self._ensure_nvenc_compatible(vpath, out)
            if vpath != orig_vpath:
                converted_tmp = vpath

        transpose = "transpose=1" if direction == "cw" else "transpose=2" 
        cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
               '-i', vpath,
               '-vf', f'hwdownload,format=nv12,{transpose}',
               '-map', '0:v', '-map', '0:a?']
        cmd.extend(self._encode_args(codec, bitrate))
        cmd.extend(['-movflags', '+faststart'])
        cmd.append(outpath)

        dur = info.get("duration", 9999)
        r = self._run_ffmpeg_progress(cmd, dur, timeout=14400, outpath=outpath, bitrate_kbps=int(bitrate))
        if r != 0 and 'nvenc' in codec:
            self._log("⚠️ NVENC失败，自动切换到libx264...")
            self._nvenc_fallback(cmd, outpath, dur)
        if r == 0:
            self._log(f"  ✅ 完成: {name}")
            self._append_intro_outro(outpath)
            if converted_tmp and os.path.exists(converted_tmp):
                try: os.remove(converted_tmp)
                except: pass
            return outpath if return_path else None
        else:
            self._log(f"  ❌ 失败 (code={r})")
            if converted_tmp and os.path.exists(converted_tmp):
                try: os.remove(converted_tmp)
                except: pass
            return None

    # ═══════════════════════════════════════
    #  编码参数
    # ═══════════════════════════════════════
    def _encode_args(self, codec, bitrate):
        br = int(bitrate)
        preset = "p5" if self.game_mode.get() else "p1"
        if "nvenc" in codec:
            return ['-pix_fmt', 'yuv420p',
                    '-c:v', codec, '-preset', preset, '-rc', 'vbr',
                    '-b:v', f'{br}k', '-maxrate', f'{int(br*1.5)}k',
                    '-bufsize', f'{int(br*2)}k',
                    '-c:a', 'flac', '-ar', '96000']
        elif codec == 'libx265':
            if br > 0:
                return ['-pix_fmt', 'yuv420p',
                        '-c:v', 'libx265', '-preset', 'medium',
                        '-b:v', f'{br}k', '-maxrate', f'{int(br*1.5)}k', '-bufsize', f'{int(br*2)}k',
                        '-x265-params', 'log-level=error', '-tag:v', 'hvc1',
                        '-c:a', 'flac', '-ar', '96000']
            else:
                return ['-pix_fmt', 'yuv420p',
                        '-c:v', 'libx265', '-preset', 'medium',
                        '-crf', '20', '-x265-params', 'log-level=error', '-tag:v', 'hvc1',
                        '-c:a', 'flac', '-ar', '96000']
        else:
            if br > 0:
                return ['-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-preset', 'medium',
                        '-b:v', f'{br}k', '-maxrate', f'{int(br*1.5)}k', '-bufsize', f'{int(br*2)}k',
                        '-g', '48', '-keyint_min', '48', '-c:a', 'flac', '-ar', '96000']
            else:
                return ['-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-preset', 'medium',
                        '-crf', '23', '-g', '48', '-keyint_min', '48', '-c:a', 'flac', '-ar', '96000']

    # ═══════════════════════════════════════
    #  日志 / 进度
    # ═══════════════════════════════════════
    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        print(line, end="", flush=True)
        try:
            self.root.after(0, lambda: (self.log_text.insert(tk.END, line), self.log_text.see(tk.END)))
        except:
            pass

    def _set_status(self, t):
        try:
            def _update():
                self.lbl_status.configure(text=t)
                # 如果是处理中状态，启动加载动画
                if "处理中" in t or "正在" in t:
                    self._start_loading(self.lbl_status, t)
                else:
                    self._stop_loading(self.lbl_status, t)
            self.root.after(0, _update)
        except:
            pass

    def _update_progress(self, pct, eta_text=""):
        try:
            def _update():
                # 使用平滑动画
                self._animate_progress(min(pct, 100), duration=300)
                self.lbl_eta.configure(text=eta_text)
            self.root.after(0, _update)
        except:
            pass

    def _create_worker_slots(self, count):
        """创建多路并行状态槽位"""
        def _do():
            for w in self.worker_panel.winfo_children():
                w.destroy()
            self._worker_widgets = {}
            for i in range(count):
                row = tk.Frame(self.worker_panel, bg=C["card"])
                row.pack(fill=tk.X, pady=1)
                icon = tk.Label(row, text=f"⚙️ #{i+1}", font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text"], width=6, anchor="w")
                icon.pack(side=tk.LEFT)
                name_lbl = tk.Label(row, text="等待中...", font=("Microsoft YaHei UI", 8), bg=C["card"], fg=C["text3"], width=20, anchor="w")
                name_lbl.pack(side=tk.LEFT, padx=2)
                bar = ttk.Progressbar(row, mode="determinate", maximum=100, length=120)
                bar.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
                eta_lbl = tk.Label(row, text="", font=("Consolas", 8), bg=C["card"], fg=C["text2"], width=12)
                eta_lbl.pack(side=tk.LEFT)
                self._worker_widgets[i] = {"frame": row, "icon": icon, "name": name_lbl, "bar": bar, "eta": eta_lbl}
        try:
            self.root.after(0, _do)
        except: pass

    def _update_worker(self, worker_id, name, pct, eta_text=""):
        """更新指定worker的状态"""
        def _do():
            w = self._worker_widgets.get(worker_id)
            if not w: return
            short_name = os.path.basename(name) if name else "..."
            if len(short_name) > 18:
                short_name = short_name[:15] + "..."
            w["name"].configure(text=short_name, fg=C["text"])
            w["bar"]["value"] = min(pct, 100)
            w["eta"].configure(text=eta_text)
            if pct >= 100:
                w["icon"].configure(text=f"✅ #{worker_id+1}")
            else:
                w["icon"].configure(text=f"⚙️ #{worker_id+1}")
        try:
            self.root.after(0, _do)
        except: pass

    def _clear_worker_slots(self):
        """清除所有worker状态槽位"""
        def _do():
            for w in self.worker_panel.winfo_children():
                w.destroy()
            self._worker_widgets = {}
        try:
            self.root.after(0, _do)
        except: pass

    def _run_ffmpeg_progress(self, cmd, total_duration, timeout=43200, outpath=None, bitrate_kbps=None):
        cmd_str = ' '.join(cmd)
        if len(cmd_str) > 500:
            cmd_preview = cmd_str[:200] + ' ... ' + cmd_str[-200:]
        else:
            cmd_preview = cmd_str
        self._log(f"📋 CMD: {cmd_preview}")

        self._encode_start_time = time.time()
        self._update_progress(0, "编码中...")

        expected_bytes = 0
        if bitrate_kbps and total_duration:
            expected_bytes = bitrate_kbps * 1000 / 8 * total_duration * 0.8

        _running = [True]
        _last_size = [0]
        _last_time = [time.time()]
        def _tick():
            try:
                while _running[0]:
                    elapsed = time.time() - self._encode_start_time
                    em, es = divmod(int(elapsed), 60)
                    eh, em = divmod(em, 60)
                    size_info = ""
                    pct = 0
                    if outpath and expected_bytes > 0 and os.path.exists(outpath):
                        try:
                            cur_size = os.path.getsize(outpath)
                            pct = min(cur_size / expected_bytes * 100, 99)
                            dt = time.time() - _last_time[0]
                            if dt > 2:
                                rate = (cur_size - _last_size[0]) / dt
                                _last_size[0] = cur_size
                                _last_time[0] = time.time()
                                if rate > 0:
                                    remaining = (expected_bytes - cur_size) / rate
                                    rm, rs = divmod(int(remaining), 60)
                                    rh, rm = divmod(rm, 60)
                                    size_info = f" | 📦 {cur_size/1048576:.0f}MB → {expected_bytes/1048576:.0f}MB | ⏳ {rh}h{rm:02d}m{rs:02d}s"
                                else:
                                    size_info = f" | 📦 {cur_size/1048576:.0f}MB"
                            elif os.path.exists(outpath):
                                cur_size = os.path.getsize(outpath)
                                size_info = f" | 📦 {cur_size/1048576:.0f}MB"
                        except:
                            pass
                    elif outpath and os.path.exists(outpath):
                        try:
                            cur_size = os.path.getsize(outpath)
                            size_info = f" | 📦 {cur_size/1048576:.0f}MB"
                        except:
                            pass
                    self._update_progress(pct, f"⏱ {eh:02d}:{em:02d}:{es:02d}{size_info}")
                    time.sleep(3)
            except Exception:
                pass

        ticker = threading.Thread(target=_tick, daemon=True)
        ticker.start()

        try:
            self._current_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            stderr_chunks = []
            def _read_stderr():
                try:
                    while True:
                        chunk = self._current_proc.stderr.read(4096)
                        if not chunk: break
                        stderr_chunks.append(chunk)
                except:
                    pass
            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            while self._current_proc.poll() is None:
                if self._cancel:
                    self._current_proc.kill()
                    self._log("⏹ 已终止ffmpeg进程")
                    break
                time.sleep(0.1)

            if not self._cancel:
                self._current_proc.wait(timeout=timeout)
            stderr_thread.join(timeout=5)
            stderr_data = b''.join(stderr_chunks)
            returncode = self._current_proc.returncode
            if returncode != 0 and stderr_data:
                err_text = stderr_data.decode('utf-8', errors='replace')[-2000:]
                self._log(f"❌ ffmpeg错误:\n{err_text}")
        except subprocess.TimeoutExpired:
            self._log("❌ 超时终止")
            try: self._current_proc.kill()
            except: pass
            returncode = 1
        except Exception as e:
            self._log(f"❌ 错误: {e}")
            returncode = 1
        finally:
            self._current_proc = None

        _running[0] = False
        ticker.join(timeout=5)

        elapsed = time.time() - self._encode_start_time
        final_info = ""
        if outpath and os.path.exists(outpath):
            try:
                final_mb = os.path.getsize(outpath) / 1048576
                final_info = f" | 📦 {final_mb:.1f}MB"
            except:
                pass

        if returncode == 0:
            self._update_progress(100, f"✅ {elapsed:.1f}s{final_info}")
        else:
            self._update_progress(0, "❌ 失败")

        return returncode

    # ═══════════════════════════════════════
    #  片头片尾
    # ═══════════════════════════════════════
    def _select_intro(self):
        p = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.mkv *.avi *.flv *.ts")])
        if p:
            self.intro_video = p
            self._configure_label(self.intro_label, text=os.path.basename(p), fg=C["text"])
            self._save_config()

    def _select_outro(self):
        p = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.mkv *.avi *.flv *.ts")])
        if p:
            self.outro_video = p
            self._configure_label(self.outro_label, text=os.path.basename(p), fg=C["text"])
            self._save_config()

    def _clear_intro_outro(self, which):
        if which == "intro":
            self.intro_video = None
            self._configure_label(self.intro_label, text="无", fg=C["text3"])
        else:
            self.outro_video = None
            self._configure_label(self.outro_label, text="无", fg=C["text3"])
        self._save_config()

    def _process_intro_outro_mode(self, out):
        """片头片尾独立模式处理"""
        intro = self.io_intro_var.get()
        outro = self.io_outro_var.get()
        if not intro and not outro:
            self._log("❌ 请至少选择片头或片尾视频"); return
        
        # 检查文件是否存在
        if intro and not os.path.exists(intro):
            self._log(f"❌ 片头文件不存在: {intro}"); return
        if outro and not os.path.exists(outro):
            self._log(f"❌ 片尾文件不存在: {outro}"); return
        
        # 获取视频列表
        if self.folder_groups:
            all_videos = []
            for g in self.folder_groups:
                all_videos.extend(g["videos"])
        else:
            all_videos = list(self.videos)
        
        if not all_videos:
            self._log("❌ 没有视频文件"); return
        
        total = len(all_videos)
        self._log(f"🚀 片头片尾模式: {total}个视频")
        if intro:
            self._log(f"  片头: {os.path.basename(intro)}")
        if outro:
            self._log(f"  片尾: {os.path.basename(outro)}")
        
        # 处理每个视频
        for i, vpath in enumerate(all_videos):
            if self._cancel:
                self._log("⏹ 已取消"); break
            
            self._set_status(f"🎬 处理 {i+1}/{total}")
            self._log(f"  [{i+1}/{total}] {os.path.basename(vpath)}")
            
            # 构建输出路径
            basename = os.path.splitext(os.path.basename(vpath))[0]
            out_path = os.path.join(out, f"{basename}_片头片尾.mp4")
            
            # 构建拼接列表
            parts = []
            if intro:
                parts.append(intro)
            parts.append(vpath)
            if outro:
                parts.append(outro)
            
            # 使用 concat demuxer 快速拼接
            import tempfile
            list_file = os.path.join(tempfile.gettempdir(), f"io_concat_{i}.txt")
            with open(list_file, 'w', encoding='utf-8') as f:
                for p in parts:
                    f.write(f"file '{p.replace(chr(92), '/')}'\n")
            
            cmd = ['ffmpeg', '-y', '-fflags', '+discardcorrupt',
                   '-f', 'concat', '-safe', '0', '-i', list_file,
                   '-c', 'copy', '-max_muxing_queue_size', '1024',
                   '-movflags', '+faststart', out_path]
            
            r = self._run_ffmpeg_progress(cmd, 0, timeout=3600)
            
            # 清理临时文件
            try: os.remove(list_file)
            except: pass
            
            if r == 0:
                self._log(f"  ✅ 完成: {os.path.basename(out_path)}")
            else:
                self._log(f"  ❌ 失败: {os.path.basename(vpath)}")
            
            # 更新进度
            pct = int((i + 1) / total * 100)
            self.root.after(0, lambda p=pct: self.progress.configure(value=p))

    def _append_intro_outro(self, video_path):
        if not self.intro_video and not self.outro_video:
            return
        try:
            parts = []
            if self.intro_video and self.enable_intro.get():
                parts.append(self.intro_video)
            parts.append(video_path)
            if self.outro_video and self.enable_outro.get():
                parts.append(self.outro_video)

            import tempfile
            list_file = os.path.join(tempfile.gettempdir(), "intro_outro_concat.txt")
            with open(list_file, 'w', encoding='utf-8') as f:
                for p in parts:
                    f.write(f"file '{p.replace(chr(92), '/')}'\n")

            temp_out = video_path + ".tmp.mp4"
            # 清理可能残留的旧临时文件
            if os.path.exists(temp_out):
                try: os.remove(temp_out)
                except: pass
            cmd = ['ffmpeg', '-y', '-fflags', '+discardcorrupt',
                   '-f', 'concat', '-safe', '0', '-i', list_file,
                   '-c', 'copy', '-max_muxing_queue_size', '1024', temp_out]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.wait(timeout=3600)
                r = proc.returncode
            except:
                r = 1
            if r == 0:
                os.replace(temp_out, video_path)
                self._log("  🎬 片头片尾已添加")
            else:
                try: os.remove(temp_out)
                except: pass
            # 确保 .tmp.mp4 被清理
            if os.path.exists(temp_out):
                try: os.remove(temp_out)
                except: pass
            try: os.remove(list_file)
            except: pass
        except Exception as e:
            self._log(f"  ⚠️ 片头片尾添加失败: {e}")

    def _cache_decoration_video(self, video_path):
        """将装饰视频预处理为1080p缓存版本，避免每次处理都解码4K"""
        if not video_path or not os.path.exists(video_path):
            return video_path
        info = self._get_video_info(video_path)
        w = info.get("width", 0)
        h = info.get("height", 0)
        if w <= 1920 and h <= 1080:
            return video_path
        cache_dir = os.path.join(os.path.dirname(video_path), ".cache_1080p")
        os.makedirs(cache_dir, exist_ok=True)
        basename = os.path.splitext(os.path.basename(video_path))[0]
        cache_path = os.path.join(cache_dir, f"{basename}_1080p.mp4")
        if os.path.exists(cache_path):
            if os.path.getmtime(cache_path) >= os.path.getmtime(video_path):
                self._log(f"  📦 使用缓存装饰: {basename}_1080p.mp4")
                return cache_path
        self._log(f"  🔄 预处理装饰视频 {w}x{h} -> 1080p...")
        # 优先用NVENC（快10x），fallback到libx264
        # 注意：不用pad滤镜（在复杂filtergraph中会触发bug）
        if self.gpu:
            cmd = [
                'ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
                '-i', video_path,
                '-vf', 'scale_cuda=1920:1080:force_original_aspect_ratio=decrease,'
                       'hwdownload,format=nv12,format=yuv420p,hwupload',
                '-c:v', 'hevc_nvenc', '-preset', 'p5', '-rc', 'vbr', '-b:v', '8000k',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                cache_path
            ]
        else:
            cmd = [
                'ffmpeg', '-y', '-i', video_path,
                '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,format=yuv420p',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                cache_path
            ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait(timeout=3600)
            if proc.returncode != 0 and self.gpu:
                # NVENC失败，fallback到libx264
                self._log(f"  ⚠️ NVENC缓存失败，切换libx264...")
                cmd = [
                    'ffmpeg', '-y', '-i', video_path,
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,format=yuv420p',
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                    cache_path
                ]
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.wait(timeout=3600)
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
                self._log(f"  ✅ 缓存完成: {basename}_1080p.mp4")
                return cache_path
        except Exception as e:
            self._log(f"  ⚠️ 缓存失败: {e}")
        return video_path

    # _get_cached_video 已合并到 _cache_decoration_video

    def _apply_preset(self, event=None):
        """应用编码预设"""
        name = self.preset_var.get()
        preset = self._presets.get(name, {})
        if not preset:
            return
        codec = preset.get("codec", "")
        bitrate = preset.get("bitrate", "")
        if codec:
            self.codec_var.set(codec)
        if bitrate:
            self.bitrate_var.set(bitrate)
        self._log(f"\U0001f4cb 应用预设: {name} \u2192 {codec} {bitrate}kbps")
        self._update_cmd_preview()

    def _update_cmd_preview(self):
        """更新命令预览"""
        if not hasattr(self, "cmd_preview"):
            return
        codec = self.codec_var.get()
        bitrate = self.bitrate_var.get()
        mode = self.mode_var.get()
        mode_names = {"frame": "套框", "pip": "画中画", "rotate": "横转竖", "pipeline": "流水线",
                      "套框": "套框", "画中画": "画中画", "横转竖": "横转竖", "流水线": "流水线"}
        mode_name = mode_names.get(mode, mode)
        preview = f"# 模式: {mode_name} | 编码: {codec} | 码率: {bitrate}kbps\n"
        preview += f"# 输出: {self.out_dir.get()}\n"
        unset = "(未设置)"
        if mode in ("pip", "画中画"):
            tpl = self.pip_template or unset
            regions = ", ".join(k for k in self.pip_regions.keys() if getattr(self, f'pip_enable_{k}', tk.BooleanVar(value=True)).get()) or unset
            preview += f"# 模板: {tpl}\n"
            preview += f"# 区域: {regions}"
        elif mode in ("frame", "套框"):
            tpl = self.frame_template or unset
            preview += f"# 模板: {tpl}\n"
            preview += f"# ROI: {self.frame_roi}"
        elif mode in ("rotate", "横转竖"):
            preview += "# 方向: 左旋转90° (counter-clockwise)"
        self.cmd_preview.configure(state=tk.NORMAL)
        self.cmd_preview.delete("1.0", tk.END)
        self.cmd_preview.insert("1.0", preview)
        self.cmd_preview.configure(state=tk.DISABLED)

    def _toggle_merge(self):
        state = "normal" if self.merge_var.get() and self.merge_mode.get() == "count" else "disabled"
        self.merge_count_spin.configure(state=state)

    # ═══════════════════════════════════════
    #  合并视频
    # ═══════════════════════════════════════
    # ═══════════════════════════════════════
    #  合并后修复重复视频流
    # ═══════════════════════════════════════
    def _fix_merged_streams(self, video_path):
        """检测并修复合并后的文件（重复视频流 或 损坏的视频时长）"""
        try:
            ffprobe = self.ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in self.ffmpeg else "ffprobe"
            r = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
                capture_output=True, text=True, errors="replace", timeout=30
            )
            if r.returncode != 0: return
            streams = json.loads(r.stdout).get("streams", [])
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

            need_fix = False
            # 情况1: 多个视频流
            if len(video_streams) > 1:
                self._log(f"  ⚠️ 检测到 {len(video_streams)} 个视频流，修复中...")
                need_fix = True
            # 情况2: 视频时长远大于音频时长（>2倍）
            elif video_streams and audio_streams:
                v_dur = float(video_streams[0].get("duration", 0))
                a_dur = float(audio_streams[0].get("duration", 0))
                if v_dur > 0 and a_dur > 0 and v_dur > a_dur * 2:
                    self._log(f"  ⚠️ 视频流时长异常({v_dur:.0f}s vs 音频{a_dur:.0f}s)，重新编码修复...")
                    need_fix = True

            if not need_fix: return

            # 重新编码修复：提取第一个视频流+所有音频流，用libx264重新编码
            fixed = video_path + ".fixed.mp4"
            self._log(f"  🔧 重新编码修复中（⏳ 请稍候）...")
            cmd = ["ffmpeg", "-y", "-i", video_path,
                   "-map", "0:v:0", "-map", "0:a?",
                   "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                   "-pix_fmt", "yuv420p",
                   "-c:a", "copy", "-movflags", "+faststart", fixed]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # 后台线程显示修复进度（百分比+ETA）
            src_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
            _fix_done = [False]
            _fix_start = [time.time()]
            def _fix_tick():
                for _ in range(120):
                    if _fix_done[0]: break
                    time.sleep(15)
                    if os.path.exists(fixed):
                        cur = os.path.getsize(fixed)
                        pct = min(cur / src_size * 100, 99) if src_size > 0 else 0
                        elapsed = time.time() - _fix_start[0]
                        if pct > 1 and elapsed > 5:
                            eta = elapsed / pct * (100 - pct)
                            em, es = divmod(int(eta), 60)
                            eta_str = f" ETA {em}m{es:02d}s"
                        else:
                            eta_str = ""
                        self._log(f"  🔧 修复中... {cur/1048576:.0f}MB ({pct:.0f}%){eta_str}")
            ft = threading.Thread(target=_fix_tick, daemon=True)
            ft.start()
            try:
                proc.wait(timeout=7200)
            except:
                proc.kill()
            finally:
                _fix_done[0] = True
            if proc.returncode == 0:
                os.replace(fixed, video_path)
                self._log(f"  ✅ 修复完成")
            else:
                try: os.remove(fixed)
                except: pass
                self._log(f"  ⚠️ 修复失败，继续使用原文件")
        except Exception as e:
            self._log(f"  ⚠️ 流检测失败: {e}")

    def _quick_concat(self, video_list, out_path):
        """快速合并处理后的视频（-c copy）"""
        import tempfile
        list_file = os.path.join(tempfile.gettempdir(), "quick_concat.txt")
        with open(list_file, 'w', encoding='utf-8') as f:
            for v in video_list:
                f.write(f"file '{v.replace(chr(92), '/')}'\n")
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', out_path]
        self._log(f"  🔗 快速合并 {len(video_list)} 个视频...")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            start_time = time.time()
            while proc.poll() is None:
                time.sleep(10)
                elapsed = time.time() - start_time
                if elapsed > 7200:  # 2小时超时
                    proc.kill()
                    self._log(f"  ❌ 合并超时 (2小时)")
                    break
                if os.path.exists(out_path):
                    size_mb = os.path.getsize(out_path) / 1024 / 1024
                    speed = size_mb / elapsed if elapsed > 0 else 0
                    eta = (size_mb / speed - elapsed) if speed > 0 else 0
                    eta_str = f"{int(eta//60)}m{int(eta%60)}s" if eta > 0 else "..."
                    self._log(f"  ⏳ 合并中... {int(size_mb)}MB (速度 {speed:.0f}MB/s, ETA {eta_str})")
            if proc.returncode != 0:
                self._log(f"  ❌ 合并失败 (返回码 {proc.returncode})")
            else:
                self._log(f"  ✅ 合并完成: {os.path.basename(out_path)}")
        except Exception as e:
            self._log(f"  ❌ 合并失败: {e}")
        try: os.remove(list_file)
        except: pass

    def _merge_videos(self, video_list, out_dir):
        if len(video_list) <= 1:
            return video_list

        count = self.merge_count.get()
        merged_files = []

        for i in range(0, len(video_list), count):
            group = video_list[i:i+count]
            if len(group) == 1:
                merged_files.append(group[0])
                continue

            import tempfile
            list_file = os.path.join(tempfile.gettempdir(), f"concat_{i}.txt")
            with open(list_file, 'w', encoding='utf-8') as f:
                for v in group:
                    f.write(f"file '{v.replace(chr(92), '/')}'\n")

            out_name = f"merged_{i//count + 1:03d}.mp4"
            outpath = os.path.join(out_dir, out_name)
            cmd = ['ffmpeg', '-y', '-fflags', '+discardcorrupt',
                   '-f', 'concat', '-safe', '0', '-i', list_file,
                   '-c', 'copy', outpath]
            self._log(f"🔗 合并 {len(group)} 个视频 (⏳ 请稍候)...")
            # DEVNULL: 不捕获输出，彻底避免管道死锁
            # 计算预期总大小
            expected_bytes = sum(os.path.getsize(v) for v in group if os.path.exists(v))
            # 后台线程：显示合并进度（百分比+ETA）
            _merge_done = [False]
            _merge_start = [time.time()]
            def _merge_tick():
                for _ in range(120):  # 最多等120分钟
                    if _merge_done[0]: break
                    time.sleep(10)
                    if os.path.exists(outpath):
                        cur = os.path.getsize(outpath)
                        pct = min(cur / expected_bytes * 100, 99) if expected_bytes > 0 else 0
                        elapsed = time.time() - _merge_start[0]
                        if pct > 1 and elapsed > 5:
                            eta = elapsed / pct * (100 - pct)
                            em, es = divmod(int(eta), 60)
                            eh, em = divmod(em, 60)
                            eta_str = f" ETA {eh}h{em:02d}m{es:02d}s" if eh > 0 else f" ETA {em}m{es:02d}s"
                        else:
                            eta_str = ""
                        self._log(f"  ⏳ 合并中... {cur/1048576:.0f}MB / {expected_bytes/1048576:.0f}MB ({pct:.0f}%){eta_str}")
            mt = threading.Thread(target=_merge_tick, daemon=True)
            mt.start()
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.wait(timeout=7200)
                r = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                r = 1
                self._log("  ❌ 合并超时")
            except Exception as e:
                r = 1
                self._log(f"  ❌ 合并异常: {e}")
            finally:
                _merge_done[0] = True

            if r == 0:
                # 合并后自动检测并修复重复视频流
                self._fix_merged_streams(outpath)
                merged_files.append(outpath)
                self._log(f"  ✅ 合并完成: {out_name}")
            else:
                merged_files.extend(group)

            try: os.remove(list_file)
            except: pass

        return merged_files

    # ═══════════════════════════════════════
    #  配置保存/加载
    # ═══════════════════════════════════════
    def _save_config(self):
        cfg = {
            # 统一视频列表
            "videos": self.videos,
            "folder_groups": self.folder_groups,
            "folder_name": self.folder_name,
            # 套框
            "frame_template": self.frame_template,
            "frame_roi": self.frame_roi,
            "bg_color": getattr(self, 'bg_color', None),
            "output_resolution": getattr(self, 'output_resolution', '1920x1080'),
            # 画中画
            "pip_template": self.pip_template,
            "pip_regions": self.pip_regions,
            "pip_left_files": self.pip_left_files,
            "pip_right_files": self.pip_right_files,
            "pip_enable_left": self.pip_enable_left.get(),
            "pip_enable_center": self.pip_enable_center.get(),
            "pip_enable_right": self.pip_enable_right.get(),
            "pip_enable_left_decor": self.pip_enable_left_decor.get(),
            "pip_enable_right_decor": self.pip_enable_right_decor.get(),
            "batch_episodes": self.batch_episodes_var.get(),
            "enable_intro": self.enable_intro.get() if hasattr(self, 'enable_intro') else True,
            "enable_outro": self.enable_outro.get() if hasattr(self, 'enable_outro') else True,
            # 横转竖
            "rotate_dir": self.rotate_dir.get() if hasattr(self, 'rotate_dir') else "cw",
            # 通用
            "codec": self.codec_var.get(),
            "bitrate": self.bitrate_var.get(),
            "merge_count": self.merge_count.get(),
            "merge": self.merge_var.get(),
            "output_dir": self.out_dir.get(),
            "game_mode": self.game_mode.get(),
            "intro_video": self.intro_video,
            "outro_video": self.outro_video,
            # 片头片尾独立模式
            "io_intro": self.io_intro_var.get(),
            "io_outro": self.io_outro_var.get(),
            "io_fade": self.io_fade_var.get(),
            "io_fade_sec": self.io_fade_sec_var.get(),
            # 流水线
            "pipe_rotate": self.pipe_rotate_var.get() if hasattr(self, 'pipe_rotate_var') else False,
            "pipe_frame": self.pipe_frame_var.get() if hasattr(self, 'pipe_frame_var') else False,
            "pipe_pip": self.pipe_pip_var.get() if hasattr(self, 'pipe_pip_var') else False,
            "pipe_intro_outro": self.pipe_intro_outro_var.get() if hasattr(self, 'pipe_intro_outro_var') else False,
        }
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print(f"[配置] 已保存到 {self._config_path}", flush=True)
        except Exception as e:
            print(f"[配置] 保存失败: {e}", flush=True)

    def _load_config(self):
        if not os.path.exists(self._config_path):
            print("[配置] 无历史配置，使用默认值", flush=True)
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            def win_path(p):
                return p.replace("/", "\\") if p else p

            # 统一视频列表（兼容旧格式）
            if cfg.get("videos"):
                self.videos = [win_path(f) for f in cfg["videos"] if os.path.exists(win_path(f))]
            elif cfg.get("frame_videos"):
                # 旧格式兼容
                self.videos = [win_path(f) for f in cfg["frame_videos"] if os.path.exists(win_path(f))]

            if cfg.get("folder_groups"):
                self.folder_groups = cfg["folder_groups"]
            elif cfg.get("frame_folder_groups"):
                self.folder_groups = cfg["frame_folder_groups"]
            elif cfg.get("center_folder_groups"):
                self.folder_groups = cfg["center_folder_groups"]
            elif cfg.get("rotate_folder_groups"):
                self.folder_groups = cfg["rotate_folder_groups"]

            self.folder_name = cfg.get("folder_name") or cfg.get("frame_folder_name") or cfg.get("pip_folder_name")

            # 刷新视频列表框显示
            if hasattr(self, 'video_listbox'):
                self.video_listbox.delete(0, tk.END)
                for v in self.videos:
                    self.video_listbox.insert(tk.END, os.path.basename(v))
                for g in self.folder_groups:
                    self.video_listbox.insert(tk.END, f"📁 {g['name']} ({len(g['videos'])}个视频)")
                self._update_video_count()

            # 套框
            tpl = win_path(cfg.get("frame_template"))
            if tpl and os.path.exists(tpl):
                self.frame_template = tpl
            if cfg.get("frame_roi"):
                self.frame_roi = tuple(cfg["frame_roi"])
            self.bg_color = cfg.get("bg_color", None)
            self.output_resolution = cfg.get("output_resolution", "1920x1080")

            # 画中画
            pip_tpl = win_path(cfg.get("pip_template"))
            if pip_tpl and os.path.exists(pip_tpl):
                self.pip_template = pip_tpl
            if cfg.get("pip_regions"):
                self.pip_regions = {k: tuple(v) for k, v in cfg["pip_regions"].items()}
            if cfg.get("pip_left_files"):
                self.pip_left_files = [win_path(f) for f in cfg["pip_left_files"] if os.path.exists(win_path(f))]
            if cfg.get("pip_right_files"):
                self.pip_right_files = [win_path(f) for f in cfg["pip_right_files"] if os.path.exists(win_path(f))]
            # 区域/装饰启用开关
            if "pip_enable_left" in cfg:
                self.pip_enable_left.set(cfg["pip_enable_left"])
            if "pip_enable_center" in cfg:
                self.pip_enable_center.set(cfg["pip_enable_center"])
            if "pip_enable_right" in cfg:
                self.pip_enable_right.set(cfg["pip_enable_right"])
            if "pip_enable_left_decor" in cfg:
                self.pip_enable_left_decor.set(cfg["pip_enable_left_decor"])
            if "pip_enable_right_decor" in cfg:
                self.pip_enable_right_decor.set(cfg["pip_enable_right_decor"])
            # 兼容旧格式
            if cfg.get("pip_lists") and not cfg.get("pip_left_files"):
                pl = cfg["pip_lists"]
                if "left" in pl and isinstance(pl["left"], dict) and "files" in pl["left"]:
                    self.pip_left_files = [win_path(f) for f in pl["left"]["files"] if os.path.exists(win_path(f))]
                if "right" in pl and isinstance(pl["right"], dict) and "files" in pl["right"]:
                    self.pip_right_files = [win_path(f) for f in pl["right"]["files"] if os.path.exists(win_path(f))]

            # 片头片尾
            intro = win_path(cfg.get("intro_video"))
            if intro and os.path.exists(intro):
                self.intro_video = intro
                if hasattr(self, 'intro_label'):
                    self._configure_label(self.intro_label, text=os.path.basename(intro), fg=C["text"])
            outro = win_path(cfg.get("outro_video"))
            if outro and os.path.exists(outro):
                self.outro_video = outro
                if hasattr(self, 'outro_label'):
                    self._configure_label(self.outro_label, text=os.path.basename(outro), fg=C["text"])
            
            # 片头片尾独立模式
            if cfg.get("io_intro"):
                io_intro = win_path(cfg["io_intro"])
                if os.path.exists(io_intro):
                    self.io_intro_var.set(io_intro)
            if cfg.get("io_outro"):
                io_outro = win_path(cfg["io_outro"])
                if os.path.exists(io_outro):
                    self.io_outro_var.set(io_outro)
            if "io_fade" in cfg:
                self.io_fade_var.set(cfg["io_fade"])
            if "io_fade_sec" in cfg:
                self.io_fade_sec_var.set(cfg["io_fade_sec"])

            # 通用设置
            if cfg.get("codec"): self.codec_var.set(cfg["codec"])
            if cfg.get("bitrate"): self.bitrate_var.set(cfg["bitrate"])
            if "merge_count" in cfg: self.merge_count.set(cfg["merge_count"])
            if "merge" in cfg:
                self.merge_var.set(cfg["merge"])
                self._toggle_merge()
            if cfg.get("output_dir"): self.out_dir.set(win_path(cfg["output_dir"]))
            if "game_mode" in cfg: self.game_mode.set(cfg["game_mode"])
            if "rotate_dir" in cfg and hasattr(self, 'rotate_dir'): self.rotate_dir.set(cfg["rotate_dir"])

            # 流水线
            if not hasattr(self, 'pipe_rotate_var'):
                self.pipe_rotate_var = tk.BooleanVar(value=cfg.get("pipe_rotate", False))
                self.pipe_frame_var = tk.BooleanVar(value=cfg.get("pipe_frame", False))
                self.pipe_pip_var = tk.BooleanVar(value=cfg.get("pipe_pip", False))
                self.pipe_intro_outro_var = tk.BooleanVar(value=cfg.get("pipe_intro_outro", False))
            if "enable_intro" in cfg:
                self.enable_intro.set(cfg["enable_intro"])
            if "enable_outro" in cfg:
                self.enable_outro.set(cfg["enable_outro"])

            print(f"[配置] 已加载: 套框ROI={self.frame_roi}, 画中画模板={self.pip_template is not None}, 画中画区域={list(self.pip_regions.keys())}", flush=True)
        except Exception as e:
            print(f"[配置] 加载失败: {e}", flush=True)


if __name__ == "__main__":
    try:
        if HAS_DND:
            root = tkinterdnd2.Tk()
        else:
            root = tk.Tk()
        VideoProcessor(root)
        root.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input(f"\n❌ 错误: {e}\n按回车退出...")
