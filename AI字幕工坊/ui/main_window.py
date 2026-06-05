#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI字幕工坊 - 主窗口 v3
专业级AI动漫字幕工作站
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import json
import threading
import time
import subprocess

# 尝试导入拖拽支持
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

# 导入核心模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.translator import TranslationEngine
from core.speech_recognizer import SpeechRecognizer
from core.bilingual import BilingualSubtitle
from core.quality_scorer import SubtitleQualityScorer
from core.speaker_identifier import SpeakerIdentifier
from core.ass_editor import ASSStyleEditor
from core.config_recommender import ConfigRecommender

class ModernButton(tk.Button):
    """现代风格按钮"""
    def __init__(self, parent, text="", command=None, style="primary", **kwargs):
        colors = {
            'primary': {'bg': '#00A1D6', 'fg': 'white', 'hover': '#0088B4'},
            'success': {'bg': '#52C41A', 'fg': 'white', 'hover': '#45A817'},
            'danger': {'bg': '#FF4D4F', 'fg': 'white', 'hover': '#E04345'},
            'warning': {'bg': '#FAAD14', 'fg': 'white', 'hover': '#E09A12'},
            'ghost': {'bg': '#2B2D30', 'fg': '#00A1D6', 'hover': '#3A3D40'},
        }
        c = colors.get(style, colors['primary'])
        super().__init__(parent, text=text, command=command,
                        bg=c['bg'], fg=c['fg'],
                        activebackground=c['hover'],
                        relief='flat', font=('Microsoft YaHei UI', 10),
                        cursor='hand2', padx=15, pady=6, **kwargs)
        self.bind('<Enter>', lambda e: self.config(bg=c['hover']))
        self.bind('<Leave>', lambda e: self.config(bg=c['bg']))

class AI字幕工坊:
    """AI动漫字幕工坊主窗口"""
    
    def __init__(self):
        # 使用TkinterDnD支持拖拽
        if HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
        
        self.root.title("AI动漫字幕工坊 v1.0")
        self.root.geometry("1400x900")
        self.root.configure(bg='#18191C')
        
        # 初始化引擎
        self.translator = TranslationEngine()
        self.recognizer = None
        
        # 状态变量
        self.current_file = None
        self.video_list = []  # 视频列表 [(path, name, status)]
        self.subtitles = []
        self.is_playing = False
        self.current_time = 0
        self.zoom_level = 1.0
        
        # 创建UI
        self._create_styles()
        self._create_menu()
        self._create_toolbar()
        self._create_main_area()
        self._create_timeline()
        self._create_log_panel()
        self._create_statusbar()
        
        # 绑定快捷键
        self._bind_shortcuts()
        
        # 添加主窗口拖拽支持
        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self._on_drop)
        
        # 初始化完成
        self.status_label.config(text="就绪 - 请导入视频或字幕文件")
        self._log("AI动漫字幕工坊已启动")
    
    def _create_styles(self):
        """创建样式"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.style.configure('TNotebook', background='#18191C')
        self.style.configure('TNotebook.Tab', background='#2B2D30', foreground='white',
                           padding=[15, 8], font=('Microsoft YaHei UI', 10))
        self.style.map('TNotebook.Tab',
                      background=[('selected', '#00A1D6')],
                      foreground=[('selected', 'white')])
        
        self.style.configure('TProgressbar', troughcolor='#2B2D30', background='#00A1D6')
        
        self.style.configure('Treeview', background='#1E1F22', foreground='white',
                           fieldbackground='#1E1F22', font=('Microsoft YaHei UI', 9))
        self.style.configure('Treeview.Heading', background='#2B2D30', foreground='white',
                           font=('Microsoft YaHei UI', 10, 'bold'))
    
    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root, bg='#2B2D30', fg='white', 
                         activebackground='#00A1D6', relief='flat')
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0, bg='#2B2D30', fg='white')
        file_menu.add_command(label="打开视频", command=self.open_video, accelerator="Ctrl+O")
        file_menu.add_command(label="打开文件夹", command=self.open_folder)
        file_menu.add_command(label="打开字幕", command=self.open_subtitle, accelerator="Ctrl+Shift+O")
        file_menu.add_separator()
        file_menu.add_command(label="保存字幕", command=self.save_subtitle, accelerator="Ctrl+S")
        file_menu.add_command(label="导出", command=self.export_menu)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=file_menu)
        
        # AI工具菜单
        ai_menu = tk.Menu(menubar, tearoff=0, bg='#2B2D30', fg='white')
        ai_menu.add_command(label="AI生成字幕", command=self.ai_generate_subtitle)
        ai_menu.add_command(label="AI翻译", command=self.ai_translate)
        ai_menu.add_command(label="AI润色", command=self.ai_polish)
        ai_menu.add_separator()
        ai_menu.add_command(label="🌐 双语字幕", command=self.ai_bilingual_subtitle)
        ai_menu.add_command(label="👤 人物识别", command=self.ai_identify_speakers)
        ai_menu.add_command(label="📊 质量评分", command=self.ai_quality_score)
        ai_menu.add_command(label="🎨 字幕样式", command=self.ai_style_editor)
        ai_menu.add_separator()
        ai_menu.add_command(label="⏰ 字幕时间校正", command=self.adjust_subtitle_timing)
        ai_menu.add_command(label="批量处理", command=self.batch_process)
        menubar.add_cascade(label="AI工具", menu=ai_menu)
        
        # 视频菜单
        video_menu = tk.Menu(menubar, tearoff=0, bg='#2B2D30', fg='white')
        video_menu.add_command(label="▶ 预览视频", command=self.preview_video)
        video_menu.add_command(label="▶ 预览+字幕", command=self.preview_with_subtitle)
        video_menu.add_separator()
        video_menu.add_command(label="🎬 烧录字幕到视频", command=self.burn_subtitle_to_video)
        video_menu.add_command(label="📦 导出带字幕视频(软字幕)", command=self.export_with_soft_subtitle)
        menubar.add_cascade(label="视频", menu=video_menu)
        
        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0, bg='#2B2D30', fg='white')
        settings_menu.add_command(label="翻译设置", command=self.translation_settings)
        settings_menu.add_command(label="模型管理", command=self.model_manager)
        settings_menu.add_command(label="GPU配置", command=self.gpu_settings)
        settings_menu.add_separator()
        settings_menu.add_command(label="🎮 AI推荐配置", command=self.show_recommend_config)
        menubar.add_cascade(label="设置", menu=settings_menu)
        
        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0, bg='#2B2D30', fg='white')
        help_menu.add_command(label="使用帮助", command=self.show_help)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = tk.Frame(self.root, bg='#2B2D30', height=50)
        toolbar.pack(fill='x', padx=5, pady=2)
        
        # 按钮容器 - 使用grid布局让按钮可以拉伸
        btn_frame = tk.Frame(toolbar, bg='#2B2D30')
        btn_frame.pack(fill='x', padx=5, pady=5)
        
        # 配置列权重，让按钮可以拉伸
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)
        btn_frame.columnconfigure(3, weight=1)
        btn_frame.columnconfigure(4, weight=1)
        btn_frame.columnconfigure(5, weight=1)
        
        ModernButton(btn_frame, text="📁 打开视频", command=self.open_video, style="ghost").grid(row=0, column=0, padx=2, sticky='ew')
        ModernButton(btn_frame, text="📂 打开文件夹", command=self.open_folder, style="ghost").grid(row=0, column=1, padx=2, sticky='ew')
        ModernButton(btn_frame, text="📄 打开字幕", command=self.open_subtitle, style="ghost").grid(row=0, column=2, padx=2, sticky='ew')
        ModernButton(btn_frame, text="🤖 AI生成字幕", command=self.ai_generate_subtitle, style="primary").grid(row=0, column=3, padx=2, sticky='ew')
        ModernButton(btn_frame, text="▶ 实时字幕", command=self.realtime_subtitle, style="danger").grid(row=0, column=4, padx=2, sticky='ew')
        ModernButton(btn_frame, text="📋 批量处理", command=self.batch_process_folder, style="warning").grid(row=0, column=5, padx=2, sticky='ew')
        ModernButton(btn_frame, text="🌐 AI翻译", command=self.ai_translate, style="success").grid(row=0, column=6, padx=2, sticky='ew')
        ModernButton(btn_frame, text="✨ AI润色", command=self.ai_polish, style="warning").grid(row=0, column=7, padx=2, sticky='ew')
        
        # GPU状态
        self.gpu_label = tk.Label(btn_frame, text="🎮 GPU: 检测中...", 
                                 bg='#2B2D30', fg='#52C41A', font=('Consolas', 10))
        self.gpu_label.grid(row=0, column=8, padx=10)
        
        self._detect_gpu()
    
    def _create_main_area(self):
        """创建主区域"""
        main_frame = tk.Frame(self.root, bg='#18191C')
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 左侧面板 - 视频列表 + 字幕列表
        left_panel = tk.Frame(main_frame, bg='#1E1F22', width=300)
        left_panel.pack(side='left', fill='y', padx=(0,5))
        left_panel.pack_propagate(False)
        
        # 视频列表标题
        video_header = tk.Frame(left_panel, bg='#1E1F22')
        video_header.pack(fill='x', padx=5, pady=5)
        
        tk.Label(video_header, text="📹 视频列表", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 12, 'bold')).pack(side='left')
        
        self.video_count_label = tk.Label(video_header, text="(0个)", bg='#1E1F22', fg='#888',
                                         font=('Microsoft YaHei UI', 10))
        self.video_count_label.pack(side='right')
        
        # 视频列表
        self.video_listbox = tk.Listbox(left_panel, bg='#2B2D30', fg='white',
                                       font=('Microsoft YaHei UI', 9),
                                       selectbackground='#00A1D6', selectforeground='white',
                                       height=8)
        self.video_listbox.pack(fill='x', padx=5, pady=5)
        self.video_listbox.bind('<<ListboxSelect>>', self._on_video_select)
        
        # 添加拖拽支持
        if HAS_DND:
            self.video_listbox.drop_target_register(DND_FILES)
            self.video_listbox.dnd_bind('<<Drop>>', self._on_drop)
        
        # 视频列表按钮
        video_btn_frame = tk.Frame(left_panel, bg='#1E1F22')
        video_btn_frame.pack(fill='x', padx=5, pady=2)
        
        ModernButton(video_btn_frame, text="➕ 添加视频", command=self.open_video, style="ghost").pack(side='left', padx=2)
        ModernButton(video_btn_frame, text="➖ 移除选中", command=self._remove_selected_video, style="ghost").pack(side='left', padx=2)
        ModernButton(video_btn_frame, text="🗑 清空列表", command=self._clear_video_list, style="ghost").pack(side='left', padx=2)
        
        # 分隔线
        ttk.Separator(left_panel, orient='horizontal').pack(fill='x', padx=5, pady=5)
        
        # 字幕列表标题
        subtitle_header = tk.Frame(left_panel, bg='#1E1F22')
        subtitle_header.pack(fill='x', padx=5, pady=5)
        
        tk.Label(subtitle_header, text="📋 字幕列表", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 12, 'bold')).pack(side='left')
        
        self.subtitle_count_label = tk.Label(subtitle_header, text="(0条)", bg='#1E1F22', fg='#888',
                                            font=('Microsoft YaHei UI', 10))
        self.subtitle_count_label.pack(side='right')
        
        # 字幕列表
        self.subtitle_list = ttk.Treeview(left_panel, columns=('time', 'text', 'trans'), 
                                         show='headings', height=12)
        self.subtitle_list.heading('time', text='时间')
        self.subtitle_list.heading('text', text='原文')
        self.subtitle_list.heading('trans', text='翻译')
        self.subtitle_list.column('time', width=70)
        self.subtitle_list.column('text', width=100)
        self.subtitle_list.column('trans', width=100)
        self.subtitle_list.pack(fill='both', expand=True, padx=5, pady=5)
        self.subtitle_list.bind('<<TreeviewSelect>>', self._on_subtitle_select)
        
        # 字幕编辑区 - 加大高度
        edit_frame = tk.Frame(left_panel, bg='#1E1F22')
        edit_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 时间显示标签
        self.time_label = tk.Label(edit_frame, text="时间: --:--.--- → --:--.---", 
                                  bg='#1E1F22', fg='#00A1D6', font=('Consolas', 10))
        self.time_label.pack(anchor='w', pady=(0, 5))
        
        tk.Label(edit_frame, text="原文:", bg='#1E1F22', fg='#AAA').pack(anchor='w')
        self.edit_original = tk.Text(edit_frame, height=4, bg='#2B2D30', fg='white',
                                    font=('Microsoft YaHei UI', 11), insertbackground='white')
        self.edit_original.pack(fill='both', expand=True, pady=2)
        
        tk.Label(edit_frame, text="翻译:", bg='#1E1F22', fg='#AAA').pack(anchor='w')
        self.edit_translation = tk.Text(edit_frame, height=4, bg='#2B2D30', fg='white',
                                       font=('Microsoft YaHei UI', 11), insertbackground='white')
        self.edit_translation.pack(fill='both', expand=True, pady=2)
        
        ModernButton(edit_frame, text="💾 保存修改", command=self._save_subtitle_edit, style="primary").pack(fill='x', pady=5)
        
        # 中间 - 视频预览
        center_panel = tk.Frame(main_frame, bg='#000000')
        center_panel.pack(side='left', fill='both', expand=True, padx=5)
        
        self.video_canvas = tk.Canvas(center_panel, bg='#000000', highlightthickness=0)
        self.video_canvas.pack(fill='both', expand=True)
        
        self.video_canvas.create_text(400, 200, text="🎬", font=('Arial', 60), fill='#333')
        self.video_canvas.create_text(400, 280, text="导入视频开始使用", 
                                     fill='#666', font=('Microsoft YaHei UI', 16))
        self.video_canvas.create_text(400, 320, text="支持 MP4/MKV/AVI/MOV 格式", 
                                     fill='#444', font=('Microsoft YaHei UI', 10))
        
        # 视频控制栏
        video_controls = tk.Frame(center_panel, bg='#1E1F22', height=40)
        video_controls.pack(fill='x', side='bottom')
        
        self.time_display = tk.Label(video_controls, text="00:00:00 / 00:00:00", 
                                    bg='#1E1F22', fg='#00A1D6', font=('Consolas', 12))
        self.time_display.pack(side='left', padx=10)
        
        # 右侧面板 - 翻译设置
        right_panel = tk.Frame(main_frame, bg='#1E1F22', width=280)
        right_panel.pack(side='right', fill='y', padx=(5,0))
        right_panel.pack_propagate(False)
        
        # 翻译设置标题
        tk.Label(right_panel, text="🌐 翻译设置", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 12, 'bold')).pack(pady=10)
        
        # 翻译引擎选择
        engine_frame = tk.LabelFrame(right_panel, text="翻译引擎", bg='#1E1F22', fg='#AAA',
                                     font=('Microsoft YaHei UI', 10))
        engine_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(engine_frame, text="选择引擎:", bg='#1E1F22', fg='#AAA',
                font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=10, pady=(5,0))
        
        self.engine_var = tk.StringVar(value='auto')
        engine_combo = ttk.Combobox(engine_frame, textvariable=self.engine_var, state='readonly', width=15)
        engine_combo['values'] = [
            'auto - 自动选择',
            'sogou - 搜狗翻译',
            'bing - 必应翻译',
            'alibaba - 阿里翻译',
            'youdao - 有道翻译',
            'caiyun - 彩云小译',
            'mimo - MiMo AI',
            'ollama - Ollama本地',
        ]
        engine_combo.set('auto - 自动选择')
        engine_combo.pack(padx=10, pady=5)
        
        # 翻译风格
        style_frame = tk.LabelFrame(right_panel, text="翻译风格", bg='#1E1F22', fg='#AAA',
                                    font=('Microsoft YaHei UI', 10))
        style_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(style_frame, text="选择风格:", bg='#1E1F22', fg='#AAA',
                font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=10, pady=(5,0))
        
        self.style_var = tk.StringVar(value='anime')
        style_combo = ttk.Combobox(style_frame, textvariable=self.style_var, state='readonly', width=15)
        style_combo['values'] = [
            'anime - 动漫字幕组',
            'direct - 直译',
            'bilibili - B站风格',
            'novel - 轻小说',
            'casual - 日常口语',
        ]
        style_combo.set('anime - 动漫字幕组')
        style_combo.pack(padx=10, pady=5)
        
        # 翻译统计
        stats_frame = tk.LabelFrame(right_panel, text="翻译统计", bg='#1E1F22', fg='#AAA',
                                   font=('Microsoft YaHei UI', 10))
        stats_frame.pack(fill='x', padx=10, pady=5)
        
        self.stats_label = tk.Label(stats_frame, text="总翻译: 0\n成功: 0\n缓存: 0",
                                   bg='#1E1F22', fg='#52C41A', font=('Microsoft YaHei UI', 9),
                                   justify='left')
        self.stats_label.pack(fill='x', padx=10, pady=5)
        
        # 快速翻译区
        quick_frame = tk.LabelFrame(right_panel, text="快速翻译", bg='#1E1F22', fg='#AAA',
                                   font=('Microsoft YaHei UI', 10))
        quick_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(quick_frame, text="输入文本:", bg='#1E1F22', fg='#AAA').pack(anchor='w', padx=5)
        self.quick_input = tk.Text(quick_frame, height=3, bg='#2B2D30', fg='white',
                                  font=('Microsoft YaHei UI', 10), insertbackground='white')
        self.quick_input.pack(fill='x', padx=5, pady=2)
        
        ModernButton(quick_frame, text="🌐 翻译", command=self._quick_translate, style="success").pack(fill='x', padx=5, pady=5)
        
        tk.Label(quick_frame, text="结果:", bg='#1E1F22', fg='#AAA').pack(anchor='w', padx=5)
        self.quick_output = tk.Text(quick_frame, height=3, bg='#2B2D30', fg='#52C41A',
                                   font=('Microsoft YaHei UI', 10), state='disabled')
        self.quick_output.pack(fill='x', padx=5, pady=2)
    
    def _create_timeline(self):
        """创建时间轴"""
        timeline_frame = tk.Frame(self.root, bg='#1E1F22', height=180)
        timeline_frame.pack(fill='x', padx=5, pady=5)
        timeline_frame.pack_propagate(False)
        
        # 时间轴控制栏
        control_frame = tk.Frame(timeline_frame, bg='#1E1F22')
        control_frame.pack(fill='x', padx=5, pady=5)
        
        # 播放控制
        play_frame = tk.Frame(control_frame, bg='#1E1F22')
        play_frame.pack(side='left')
        
        self.play_btn = ModernButton(play_frame, text="▶", command=self.toggle_play, style="ghost")
        self.play_btn.pack(side='left', padx=2)
        
        ModernButton(play_frame, text="⏮", command=self.prev_subtitle, style="ghost").pack(side='left', padx=2)
        ModernButton(play_frame, text="⏭", command=self.next_subtitle, style="ghost").pack(side='left', padx=2)
        ModernButton(play_frame, text="⏹", command=self.stop_play, style="ghost").pack(side='left', padx=2)
        
        # 时间显示
        self.timeline_time = tk.Label(control_frame, text="00:00.000", 
                                     bg='#1E1F22', fg='#00A1D6', font=('Consolas', 14, 'bold'))
        self.timeline_time.pack(side='left', padx=20)
        
        # 缩放控制
        zoom_frame = tk.Frame(control_frame, bg='#1E1F22')
        zoom_frame.pack(side='right')
        
        ModernButton(zoom_frame, text="🔍+", command=self.zoom_in, style="ghost").pack(side='left', padx=2)
        ModernButton(zoom_frame, text="🔍-", command=self.zoom_out, style="ghost").pack(side='left', padx=2)
        ModernButton(zoom_frame, text="适配", command=self.zoom_fit, style="ghost").pack(side='left', padx=2)
        
        # 时间轴画布
        canvas_frame = tk.Frame(timeline_frame, bg='#141517')
        canvas_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.waveform_canvas = tk.Canvas(canvas_frame, bg='#141517', height=40,
                                        highlightthickness=0)
        self.waveform_canvas.pack(fill='x')
        
        self.timeline_canvas = tk.Canvas(canvas_frame, bg='#141517', height=80,
                                        highlightthickness=0)
        self.timeline_canvas.pack(fill='both', expand=True)
        
        self._draw_timeline()
    
    def _create_log_panel(self):
        """创建日志面板"""
        log_frame = tk.Frame(self.root, bg='#1E1F22', height=120)
        log_frame.pack(fill='x', padx=5, pady=(0,2))
        log_frame.pack_propagate(False)
        
        # 日志标题
        log_header = tk.Frame(log_frame, bg='#1E1F22')
        log_header.pack(fill='x', padx=5, pady=2)
        
        tk.Label(log_header, text="📋 处理日志", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 10, 'bold')).pack(side='left')
        
        ModernButton(log_header, text="清空", command=self._clear_log, style="ghost").pack(side='right')
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, height=5, bg='#141517', fg='#00FF00',
                                                  font=('Consolas', 9), insertbackground='white',
                                                  state='disabled')
        self.log_text.pack(fill='both', expand=True, padx=5, pady=2)
    
    def _log(self, message):
        """添加日志"""
        self.log_text.config(state='normal')
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert('end', f"[{timestamp}] {message}\n")
        self.log_text.see('end')
        self.log_text.config(state='disabled')
    
    def _clear_log(self):
        """清空日志"""
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.config(state='disabled')
    
    def _create_statusbar(self):
        """创建状态栏"""
        statusbar = tk.Frame(self.root, bg='#2B2D30', height=30)
        statusbar.pack(fill='x', side='bottom')
        
        self.status_label = tk.Label(statusbar, text="就绪", bg='#2B2D30', fg='#AAA',
                                    font=('Microsoft YaHei UI', 9))
        self.status_label.pack(side='left', padx=10)
        
        self.progress = ttk.Progressbar(statusbar, length=200, mode='determinate')
        self.progress.pack(side='right', padx=10, pady=5)
        
        self.engine_status = tk.Label(statusbar, text="引擎: 搜狗翻译", bg='#2B2D30', fg='#52C41A',
                                     font=('Microsoft YaHei UI', 9))
        self.engine_status.pack(side='right', padx=10)
    
    def _detect_gpu(self):
        """检测GPU"""
        def detect():
            try:
                import subprocess
                result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used', 
                                       '--format=csv,noheader'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    gpu_info = result.stdout.strip().split(',')
                    gpu_name = gpu_info[0].strip()
                    self.gpu_label.config(text=f"🎮 {gpu_name}")
                else:
                    self.gpu_label.config(text="🎮 GPU: 未检测到", fg='#FF4D4F')
            except:
                self.gpu_label.config(text="🎮 GPU: 未检测到", fg='#FF4D4F')
        
        threading.Thread(target=detect, daemon=True).start()
    
    def _bind_shortcuts(self):
        """绑定快捷键"""
        self.root.bind('<Control-o>', lambda e: self.open_video())
        self.root.bind('<Control-s>', lambda e: self.save_subtitle())
        self.root.bind('<space>', lambda e: self.toggle_play())
        self.root.bind('<Left>', lambda e: self.prev_subtitle())
        self.root.bind('<Right>', lambda e: self.next_subtitle())
    
    def _draw_timeline(self):
        """绘制时间轴"""
        self.timeline_canvas.delete('all')
        w = self.timeline_canvas.winfo_width()
        h = self.timeline_canvas.winfo_height()
        
        if not self.subtitles:
            return
        
        # 计算总时长（毫秒）
        max_time = max(end for _, end, _, _ in self.subtitles)
        if max_time <= 0:
            return
        
        # 绘制时间刻度
        # 每100像素对应的时间（毫秒）
        time_per_100px = max_time / (w / 100) if w > 0 else 1000
        
        # 绘制网格线和时间标签
        for i in range(0, w, 100):
            self.timeline_canvas.create_line(i, 0, i, h, fill='#2B2D30', tags='grid')
            # 计算对应的时间
            time_ms = i * time_per_100px / 100
            time_str = f"{int(time_ms//60000):02d}:{int((time_ms%60000)//1000):02d}"
            self.timeline_canvas.create_text(i+2, 5, text=time_str, anchor='nw',
                                           fill='#888', font=('Consolas', 7), tags='time_label')
        
        # 绘制字幕块
        for i, (start, end, text, trans) in enumerate(self.subtitles):
            # 将时间转换为像素位置
            x1 = start / max_time * w
            x2 = end / max_time * w
            
            # 确保最小宽度
            if x2 - x1 < 2:
                x2 = x1 + 2
            
            color = '#00A1D6' if i % 2 == 0 else '#52C41A'
            self.timeline_canvas.create_rectangle(x1, 15, x2, 55, fill=color, 
                                                 outline='#FFF', tags=f'sub_{i}')
            
            # 显示字幕文本（截取前5个字符）
            display_text = text[:5] + '...' if len(text) > 5 else text
            self.timeline_canvas.create_text((x1+x2)/2, 35, text=display_text, 
                                           fill='white', font=('Microsoft YaHei UI', 8),
                                           tags=f'sub_text_{i}')
    
    # ==================== 视频列表功能 ====================
    
    def open_video(self):
        """打开视频"""
        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self._add_video_to_list(file_path)
            self._load_video(file_path)
    
    def open_folder(self):
        """打开文件夹"""
        folder_path = filedialog.askdirectory(title="选择视频文件夹")
        if folder_path:
            video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv')
            count = 0
            for file in os.listdir(folder_path):
                if file.lower().endswith(video_exts):
                    full_path = os.path.join(folder_path, file)
                    self._add_video_to_list(full_path)
                    count += 1
            
            if count > 0:
                self.status_label.config(text=f"已添加 {count} 个视频")
                # 自动选中第一个
                self.video_listbox.selection_set(0)
                self._load_video(self.video_list[0][0])
            else:
                messagebox.showinfo("提示", "文件夹中没有找到视频文件")
    
    def _add_video_to_list(self, file_path):
        """添加视频到列表"""
        # 检查是否已存在
        for path, name, status in self.video_list:
            if path == file_path:
                return
        
        name = os.path.basename(file_path)
        self.video_list.append((file_path, name, "待处理"))
        self.video_listbox.insert(tk.END, name)
        self.video_count_label.config(text=f"({len(self.video_list)}个)")
    
    def _load_video(self, file_path):
        """加载视频"""
        self.current_file = file_path
        name = os.path.basename(file_path)
        self.status_label.config(text=f"当前: {name}")
        
        # 不再清空字幕，保留已生成的字幕
        # 只更新显示
        self._draw_timeline()
    
    def _post_process_subtitle_timing(self):
        """后处理字幕时间，使其更准确"""
        if not self.subtitles:
            return
        
        # 调整字幕时间，使其更符合实际说话时间
        for i in range(len(self.subtitles)):
            start, end, text, trans = self.subtitles[i]
            
            # 1. 确保字幕时长合理（至少1秒，最多10秒）
            duration = end - start
            if duration < 1000:  # 少于1秒
                # 延长到至少1秒
                end = start + 1000
            elif duration > 10000:  # 超过10秒
                # 缩短到10秒
                end = start + 10000
            
            # 2. 确保字幕之间有适当间隔（至少100ms）
            if i > 0:
                prev_start, prev_end, _, _ = self.subtitles[i-1]
                if start < prev_end + 100:
                    start = prev_end + 100
                    # 确保结束时间仍然合理
                    if end < start + 1000:
                        end = start + 1000
            
            # 3. 根据文本长度调整显示时间
            # 日语每秒大约显示5-8个字符
            char_count = len(text)
            min_duration = max(1000, char_count * 150)  # 每个字符至少150ms
            if end - start < min_duration:
                end = start + min_duration
            
            self.subtitles[i] = (start, end, text, trans)
        
        # 记录日志
        self._log(f"字幕时间后处理完成，共 {len(self.subtitles)} 条")
    
    def _on_drop(self, event):
        """拖拽文件处理"""
        if event.data:
            # 处理拖拽的文件路径
            # tkinterdnd2返回的路径可能用{}包裹
            files = self.root.tk.splitlist(event.data)
            video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.ts')
            
            added_count = 0
            for file_path in files:
                file_path = file_path.strip()
                if os.path.isfile(file_path) and file_path.lower().endswith(video_exts):
                    self._add_video_to_list(file_path)
                    added_count += 1
                elif os.path.isdir(file_path):
                    # 如果是文件夹，添加文件夹内的所有视频
                    for f in os.listdir(file_path):
                        if f.lower().endswith(video_exts):
                            full_path = os.path.join(file_path, f)
                            self._add_video_to_list(full_path)
                            added_count += 1
            
            if added_count > 0:
                self._log(f"拖拽添加了 {added_count} 个视频")
                # 自动选中第一个
                if not self.current_file and self.video_list:
                    self.video_listbox.selection_set(0)
                    self._load_video(self.video_list[0][0])
    
    def _on_video_select(self, event):
        """视频选中事件"""
        selection = self.video_listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.video_list):
                file_path, name, status = self.video_list[idx]
                self._load_video(file_path)
    
    def _remove_selected_video(self):
        """移除选中的视频"""
        selection = self.video_listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.video_list):
                self.video_list.pop(idx)
                self.video_listbox.delete(idx)
                self.video_count_label.config(text=f"({len(self.video_list)}个)")
    
    def _clear_video_list(self):
        """清空视频列表"""
        if self.video_list:
            if messagebox.askyesno("确认", "确定要清空视频列表吗？"):
                self.video_list.clear()
                self.video_listbox.delete(0, tk.END)
                self.video_count_label.config(text="(0个)")
                self.current_file = None
                self.subtitles = []
                self._refresh_subtitle_list()
                self._draw_timeline()
    
    # ==================== 字幕功能 ====================
    
    def open_subtitle(self):
        """打开字幕"""
        file_path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[
                ("字幕文件", "*.srt *.ass *.vtt"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self._load_subtitle(file_path)
    
    def _load_subtitle(self, file_path):
        """加载字幕文件"""
        try:
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext == '.srt':
                self._load_srt(file_path)
            elif ext == '.ass':
                self._load_ass(file_path)
            elif ext == '.vtt':
                self._load_vtt(file_path)
            
            self._refresh_subtitle_list()
            self._draw_timeline()
            self.status_label.config(text=f"已加载字幕: {len(self.subtitles)} 条")
            self.subtitle_count_label.config(text=f"({len(self.subtitles)}条)")
        except Exception as e:
            messagebox.showerror("错误", f"加载字幕失败: {e}")
    
    def _load_srt(self, file_path):
        """加载SRT字幕"""
        import re
        self.subtitles = []
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                time_parts = lines[1].split(' --> ')
                start = self._srt_time_to_ms(time_parts[0].strip())
                end = self._srt_time_to_ms(time_parts[1].strip())
                # 过滤掉随机ID行（20位左右的字母数字组合）
                text_lines = []
                for line in lines[2:]:
                    # 跳过看起来像ID的行（纯字母数字，15-25位）
                    if re.match(r'^[a-z0-9]{15,25}$', line.strip()):
                        continue
                    text_lines.append(line)
                text = '\n'.join(text_lines)
                if text.strip():  # 只添加非空字幕
                    self.subtitles.append((start, end, text, ''))
    
    def _load_ass(self, file_path):
        """加载ASS字幕"""
        self.subtitles = []
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        import re
        for line in content.split('\n'):
            if line.startswith('Dialogue:'):
                parts = line.split(',', 9)
                if len(parts) >= 10:
                    start = self._ass_time_to_ms(parts[1])
                    end = self._ass_time_to_ms(parts[2])
                    text = parts[9].replace('\\N', '\n').replace('\\n', '\n')
                    text = re.sub(r'\{[^}]*\}', '', text)
                    self.subtitles.append((start, end, text, ''))
    
    def _load_vtt(self, file_path):
        """加载VTT字幕"""
        pass
    
    def _srt_time_to_ms(self, time_str):
        """SRT时间转毫秒"""
        parts = time_str.replace(',', '.').split(':')
        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
        return int((h * 3600 + m * 60 + s) * 1000)
    
    def _ass_time_to_ms(self, time_str):
        """ASS时间转毫秒"""
        parts = time_str.split(':')
        h, m = int(parts[0]), int(parts[1])
        s_parts = parts[2].split('.')
        s = int(s_parts[0])
        cs = int(s_parts[1]) if len(s_parts) > 1 else 0
        return (h * 3600 + m * 60 + s) * 1000 + cs * 10
    
    def _refresh_subtitle_list(self):
        """刷新字幕列表"""
        self.subtitle_list.delete(*self.subtitle_list.get_children())
        for i, (start, end, text, trans) in enumerate(self.subtitles):
            # 显示完整时间格式：MM:SS.mmm
            time_str = f"{start//60000:02d}:{(start%60000)//1000:02d}.{start%1000:03d}"
            self.subtitle_list.insert('', 'end', iid=str(i), 
                                     values=(time_str, text[:30], trans[:30] if trans else ''))
        self.subtitle_count_label.config(text=f"({len(self.subtitles)}条)")
    
    def _on_subtitle_select(self, event):
        """字幕选中事件"""
        selection = self.subtitle_list.selection()
        if selection:
            idx = int(selection[0])
            if idx < len(self.subtitles):
                start, end, text, trans = self.subtitles[idx]
                self.edit_original.delete('1.0', 'end')
                self.edit_original.insert('1.0', text)
                self.edit_translation.delete('1.0', 'end')
                self.edit_translation.insert('1.0', trans)
    
    def _save_subtitle_edit(self):
        """保存字幕修改"""
        selection = self.subtitle_list.selection()
        if selection:
            idx = int(selection[0])
            if idx < len(self.subtitles):
                start, end, _, _ = self.subtitles[idx]
                original = self.edit_original.get('1.0', 'end-1c')
                translation = self.edit_translation.get('1.0', 'end-1c')
                self.subtitles[idx] = (start, end, original, translation)
                self._refresh_subtitle_list()
                self._draw_timeline()
                self.status_label.config(text="字幕已更新")
    
    def save_subtitle(self):
        """保存字幕"""
        if not self.subtitles:
            messagebox.showwarning("警告", "没有字幕可保存")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="保存字幕",
            defaultextension=".srt",
            filetypes=[("SRT字幕", "*.srt"), ("ASS字幕", "*.ass")]
        )
        
        if file_path:
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == '.srt':
                    self._save_srt(file_path)
                elif ext == '.ass':
                    self._save_ass(file_path)
                self.status_label.config(text=f"已保存: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}")
    
    def _save_srt(self, file_path):
        """保存SRT字幕"""
        with open(file_path, 'w', encoding='utf-8') as f:
            for i, (start, end, text, trans) in enumerate(self.subtitles):
                f.write(f"{i+1}\n")
                f.write(f"{self._ms_to_srt_time(start)} --> {self._ms_to_srt_time(end)}\n")
                if trans:
                    f.write(f"{text}\n{trans}\n\n")
                else:
                    f.write(f"{text}\n\n")
    
    def _ms_to_srt_time(self, ms):
        """毫秒转SRT时间"""
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        ms_part = ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms_part:03d}"
    
    def _save_ass(self, file_path):
        """保存ASS字幕"""
        pass
    
    def export_menu(self):
        """导出菜单"""
        pass
    
    # ==================== AI功能 ====================
    
    def ai_generate_subtitle(self):
        """AI生成字幕 - 3步流水线：Whisper识别 → 日语校对 → 保存"""
        if not self.current_file:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        
        if self.subtitles:
            if not messagebox.askyesno("确认", "已有字幕将被替换，是否继续？"):
                return
        
        # 弹出设置对话框
        settings = self._show_proofread_settings()
        if settings is None:
            return  # 用户取消
        
        anime_name = settings.get('anime_name', '')
        enable_proofread = settings.get('enable_proofread', True)
        initial_prompt = settings.get('initial_prompt', '')
        
        # 保存到config
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                config['anime_name'] = anime_name
                config['initial_prompt'] = initial_prompt
                config['character_settings'] = settings.get('character_settings', '')
                config['scene_description'] = settings.get('scene_description', '')
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
        except:
            pass
        
        def generate_thread():
            try:
                self.root.after(0, lambda: self._log("=" * 40))
                self.root.after(0, lambda: self._log("开始AI字幕生成（3步流水线）"))
                
                # ========== 第1步：Whisper语音识别 ==========
                self.root.after(0, lambda: self._log("【第1步】Whisper语音识别..."))
                self.root.after(0, lambda: self.status_label.config(text="第1步：正在加载语音识别模型..."))
                
                recognizer = SpeechRecognizer(model_size="large-v3")
                
                def progress_callback(status, progress):
                    self.root.after(0, lambda: self.status_label.config(text=f"第1步: {status}"))
                    self.root.after(0, lambda: self.progress.config(value=progress * 0.4))  # 0-40%
                    if progress % 20 == 0:
                        self.root.after(0, lambda: self._log(f"识别进度: {progress}%"))
                
                if not recognizer.load_model(progress_callback):
                    self.root.after(0, lambda: self._log("错误: 模型加载失败!"))
                    self.root.after(0, lambda: messagebox.showerror("错误", "语音识别模型加载失败"))
                    return
                
                self.root.after(0, lambda: self._log("模型加载完成"))
                self.root.after(0, lambda: self._log("正在提取音频..."))
                
                import subprocess
                import tempfile
                
                audio_path = tempfile.mktemp(suffix='.wav')
                
                ffmpeg_cmd = [
                    'ffmpeg', '-i', self.current_file,
                    '-vn', '-acodec', 'pcm_s16le',
                    '-ar', '16000', '-ac', '1',
                    '-y', audio_path
                ]
                
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    self.root.after(0, lambda: self._log("错误: 音频提取失败!"))
                    self.root.after(0, lambda: messagebox.showerror("错误", "音频提取失败"))
                    return
                
                self.root.after(0, lambda: self._log("音频提取完成"))
                self.root.after(0, lambda: self._log("正在识别日语语音..."))
                
                # 传入initial_prompt（番剧专有名词）
                result = recognizer.transcribe(
                    audio_path, language="ja", 
                    progress_callback=progress_callback,
                    initial_prompt=initial_prompt
                )
                
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                
                if not result['success']:
                    error_msg = result['error']
                    self.root.after(0, lambda: self._log(f"错误: {error_msg}"))
                    self.root.after(0, lambda: messagebox.showerror("错误", f"识别失败: {error_msg}"))
                    return
                
                # 保存识别结果
                raw_segments = result['segments']
                count = len(raw_segments)
                duration = result['duration']
                elapsed = result['elapsed']
                
                self.root.after(0, lambda: self._log(f"识别完成! 共 {count} 条字幕 ({elapsed:.1f}秒)"))
                
                # ========== 第2步：日语校对（可选） ==========
                if enable_proofread and count > 0:
                    self.root.after(0, lambda: self._log("【第2步】日语校对（Qwen2.5）..."))
                    self.root.after(0, lambda: self.status_label.config(text="第2步：正在校对日语..."))
                    
                    def proofread_progress(status, progress):
                        self.root.after(0, lambda: self.status_label.config(text=f"第2步: {status}"))
                        self.root.after(0, lambda: self.progress.config(value=40 + progress * 0.3))  # 40-70%
                    
                    translator = TranslationEngine()
                    corrected_segments = translator.proofread_japanese(
                        raw_segments, 
                        anime_name=anime_name,
                        progress_callback=proofread_progress
                    )
                    
                    # 统修正数量
                    corrected_count = sum(1 for a, b in zip(raw_segments, corrected_segments) 
                                        if a['text'] != b['text'])
                    self.root.after(0, lambda: self._log(f"校对完成! 修正了 {corrected_count} 条字幕"))
                    
                    # 模型热切换：释放Qwen2.5显存，预热Sakura
                    self.root.after(0, lambda: self._log("正在切换模型（释放显存→加载Sakura）..."))
                    self.root.after(0, lambda: self.status_label.config(text="切换模型中..."))
                    proofread_model = "qwen2.5:7b-instruct-q4_K_M"
                    sakura_model = "sakura"
                    try:
                        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
                        if os.path.exists(config_path):
                            with open(config_path, 'r') as f:
                                cfg = json.load(f)
                                proofread_model = cfg.get('proofread_model', proofread_model)
                                sakura_model = cfg.get('ollama_model', sakura_model)
                    except:
                        pass
                    translator.switch_model(proofread_model, sakura_model)
                    self.root.after(0, lambda: self._log("模型切换完成"))
                else:
                    self.root.after(0, lambda: self._log("【第2步】跳过日语校对"))
                    corrected_segments = raw_segments
                
                # ========== 第2.5步：断句优化 ==========
                self.root.after(0, lambda: self._log("【断句优化】合并短句/拆分长句..."))
                before_count = len(corrected_segments)
                translator2 = TranslationEngine()
                corrected_segments = translator2.optimize_subtitle_segments(corrected_segments)
                after_count = len(corrected_segments)
                if before_count != after_count:
                    self.root.after(0, lambda: self._log(f"断句优化: {before_count} → {after_count} 条"))
                
                # ========== 第3步：保存结果 ==========
                self.root.after(0, lambda: self._log("【第3步】保存字幕..."))
                self.root.after(0, lambda: self.status_label.config(text="第3步：保存字幕..."))
                self.root.after(0, lambda: self.progress.config(value=80))
                
                self.subtitles = []
                for seg in corrected_segments:
                    start_ms = int(seg['start'] * 1000)
                    end_ms = int(seg['end'] * 1000)
                    text = seg['text']
                    self.subtitles.append((start_ms, end_ms, text, ''))
                
                # 后处理字幕时间
                self._post_process_subtitle_timing()
                
                self.root.after(0, self._refresh_subtitle_list)
                self.root.after(0, self._draw_timeline)
                self.root.after(0, lambda: self.progress.config(value=100))
                
                # 完成
                self.root.after(0, lambda: self._log("=" * 40))
                self.root.after(0, lambda: self._log(f"全部完成! 共 {count} 条字幕"))
                if enable_proofread:
                    self.root.after(0, lambda: self._log(f"校对修正: {corrected_count} 条"))
                self.root.after(0, lambda: self._log(f"视频时长: {duration:.1f}秒"))
                self.root.after(0, lambda: self.status_label.config(text=f"完成! 共 {count} 条字幕"))
                self.root.after(100, lambda: messagebox.showinfo("完成", 
                    f"AI字幕生成完成!\n\n"
                    f"字幕数量: {count}\n"
                    f"校对修正: {corrected_count if enable_proofread else '未启用'}\n"
                    f"视频时长: {duration:.1f}秒"))
                    
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._log(f"异常: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("错误", f"处理失败: {error_msg}"))
                self.root.after(0, lambda: self.status_label.config(text="处理失败"))
        
        threading.Thread(target=generate_thread, daemon=True).start()
    
    def _show_proofread_settings(self):
        """显示校对设置对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("AI字幕生成设置")
        dialog.geometry("520x520")
        dialog.configure(bg='#1E1F22')
        dialog.transient(self.root)
        dialog.grab_set()
        
        result = {}
        
        # 标题
        tk.Label(dialog, text="🎬 AI字幕生成", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)
        
        # 读取config
        config_data = {}
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
        except:
            pass
        
        # 动漫名称
        frame1 = tk.Frame(dialog, bg='#1E1F22')
        frame1.pack(fill='x', padx=20, pady=3)
        tk.Label(frame1, text="动漫名称（传给Whisper提高识别率）:", bg='#1E1F22', fg='#888',
                font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        name_entry = tk.Entry(frame1, bg='#2B2D30', fg='white', font=('Microsoft YaHei UI', 11),
                             insertbackground='white')
        name_entry.pack(fill='x', pady=3)
        name_entry.insert(0, config_data.get('anime_name', ''))
        
        # 专有名词
        frame2 = tk.Frame(dialog, bg='#1E1F22')
        frame2.pack(fill='x', padx=20, pady=3)
        tk.Label(frame2, text="专有名词（人名/地名/术语，空格分隔）:", bg='#1E1F22', fg='#888',
                font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        prompt_entry = tk.Entry(frame2, bg='#2B2D30', fg='white', font=('Microsoft YaHei UI', 11),
                               insertbackground='white')
        prompt_entry.pack(fill='x', pady=3)
        prompt_entry.insert(0, config_data.get('initial_prompt', ''))
        
        # 角色设定
        frame3 = tk.Frame(dialog, bg='#1E1F22')
        frame3.pack(fill='x', padx=20, pady=3)
        tk.Label(frame3, text="角色设定（传给校对和翻译模型）:", bg='#1E1F22', fg='#888',
                font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        char_entry = tk.Entry(frame3, bg='#2B2D30', fg='white', font=('Microsoft YaHei UI', 11),
                             insertbackground='white')
        char_entry.pack(fill='x', pady=3)
        char_entry.insert(0, config_data.get('character_settings', ''))
        
        # 场景描述
        frame4 = tk.Frame(dialog, bg='#1E1F22')
        frame4.pack(fill='x', padx=20, pady=3)
        tk.Label(frame4, text="场景描述（传给Sakura翻译时使用）:", bg='#1E1F22', fg='#888',
                font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        scene_entry = tk.Entry(frame4, bg='#2B2D30', fg='white', font=('Microsoft YaHei UI', 11),
                              insertbackground='white')
        scene_entry.pack(fill='x', pady=3)
        scene_entry.insert(0, config_data.get('scene_description', ''))
        
        # 启用校对
        proofread_var = tk.BooleanVar(value=True)
        tk.Checkbutton(dialog, text="启用日语校对（Qwen2.5修正识别错误）", 
                      variable=proofread_var,
                      bg='#1E1F22', fg='#00A1D6', selectcolor='#2B2D30',
                      activebackground='#1E1F22', activeforeground='#00A1D6',
                      font=('Microsoft YaHei UI', 11)).pack(pady=8)
        
        # 说明
        tk.Label(dialog, text="💡 流程：Whisper识别 → Qwen2.5校对 → 断句优化 → 保存\n动漫名和专有名词→Whisper，角色设定和场景→校对+翻译",
                bg='#1E1F22', fg='#666', font=('Microsoft YaHei UI', 9)).pack(pady=5)
        
        # 按钮
        def on_confirm():
            result['anime_name'] = name_entry.get().strip()
            result['initial_prompt'] = prompt_entry.get().strip()
            result['character_settings'] = char_entry.get().strip()
            result['scene_description'] = scene_entry.get().strip()
            result['enable_proofread'] = proofread_var.get()
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        btn_frame = tk.Frame(dialog, bg='#1E1F22')
        btn_frame.pack(pady=15)
        ModernButton(btn_frame, text="开始生成", command=on_confirm, style="primary").pack(side='left', padx=10)
        ModernButton(btn_frame, text="取消", command=on_cancel, style="ghost").pack(side='left', padx=10)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        
        return result if result else None
    
    def ai_translate(self):
        """AI翻译"""
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕可翻译")
            return
        
        # 从Combobox值中提取引擎代码
        engine_str = self.engine_var.get()
        engine = engine_str.split(' - ')[0] if ' - ' in engine_str else engine_str
        
        style_str = self.style_var.get()
        style = style_str.split(' - ')[0] if ' - ' in style_str else style_str
        
        self._log(f"开始翻译，引擎: {engine}，风格: {style}")
        self._log(f"共 {len(self.subtitles)} 条字幕待翻译")
        
        def translate_thread():
            try:
                total = len(self.subtitles)
                self.root.after(0, lambda: self.progress.config(maximum=total))
                self.root.after(0, lambda: self.status_label.config(text="翻译中..."))
                
                for i, (start, end, text, _) in enumerate(self.subtitles):
                    try:
                        result = self.translator.translate(text, 'ja', 'zh', engine=engine, style=style)
                        self.subtitles[i] = (start, end, text, result['text'])
                        
                        self.root.after(0, lambda v=i+1: self.progress.config(value=v))
                        self.root.after(0, lambda v=i+1, t=total: self.status_label.config(text=f"翻译中... {v}/{t}"))
                        
                        # 每10条记录一次日志
                        if (i + 1) % 10 == 0:
                            self.root.after(0, lambda v=i+1: self._log(f"已翻译 {v} 条"))
                        
                        # 更新统计
                        stats = self.translator.get_engine_status()['stats']
                        self.root.after(0, lambda s=stats: self.stats_label.config(
                            text=f"总翻译: {s['total']}\n成功: {s['success']}\n缓存: {s['cache_hit']}"))
                        
                        engine_name = result.get('engine_name', result['engine'])
                        self.root.after(0, lambda n=engine_name: self.engine_status.config(text=f"引擎: {n}"))
                        
                    except Exception as e:
                        self.root.after(0, lambda err=str(e), idx=i: self._log(f"翻译第{idx+1}条失败: {err}"))
                        continue
                
                self.root.after(0, self._refresh_subtitle_list)
                self.root.after(0, self._draw_timeline)
                self.root.after(0, lambda: self._log(f"翻译完成! 共 {total} 条"))
                self.root.after(0, lambda: self.status_label.config(text=f"翻译完成! 共 {total} 条"))
                self.root.after(100, lambda: messagebox.showinfo("完成", f"翻译完成! 共处理 {total} 条字幕"))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._log(f"翻译异常: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("错误", f"翻译失败: {error_msg}"))
        
        threading.Thread(target=translate_thread, daemon=True).start()
    
    def adjust_subtitle_timing(self):
        """字幕时间校正"""
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕可校正")
            return
        
        # 创建校正对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("字幕时间校正")
        dialog.geometry("400x300")
        dialog.configure(bg='#1E1F22')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 校正选项
        tk.Label(dialog, text="字幕时间校正", bg='#1E1F22', fg='white', 
                font=('Microsoft YaHei UI', 12, 'bold')).pack(pady=10)
        
        # 全局时间偏移
        offset_frame = tk.Frame(dialog, bg='#1E1F22')
        offset_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(offset_frame, text="全局时间偏移(毫秒):", bg='#1E1F22', fg='#AAA').pack(anchor='w')
        offset_var = tk.StringVar(value="0")
        tk.Entry(offset_frame, textvariable=offset_var, bg='#2B2D30', fg='white', 
                font=('Consolas', 10)).pack(fill='x', pady=5)
        
        # 说明
        tk.Label(dialog, text="正数=字幕延后，负数=字幕提前", bg='#1E1F22', fg='#888',
                font=('Microsoft YaHei UI', 9)).pack(pady=5)
        
        # 按钮
        btn_frame = tk.Frame(dialog, bg='#1E1F22')
        btn_frame.pack(fill='x', padx=20, pady=20)
        
        def apply_offset():
            try:
                offset_ms = int(offset_var.get())
                for i in range(len(self.subtitles)):
                    start, end, text, trans = self.subtitles[i]
                    self.subtitles[i] = (start + offset_ms, end + offset_ms, text, trans)
                
                self._refresh_subtitle_list()
                self._draw_timeline()
                self._log(f"已应用全局时间偏移: {offset_ms}ms")
                dialog.destroy()
                messagebox.showinfo("完成", f"已调整 {len(self.subtitles)} 条字幕的时间")
            except ValueError:
                messagebox.showerror("错误", "请输入有效的数字")
        
        ModernButton(btn_frame, text="应用", command=apply_offset, style="primary").pack(side='left', padx=5)
        ModernButton(btn_frame, text="取消", command=dialog.destroy, style="ghost").pack(side='left', padx=5)
    
    def ai_polish(self):
        """AI润色"""
        messagebox.showinfo("提示", "AI润色功能开发中...")
    
    def batch_process(self):
        """批量处理"""
        if not self.video_list:
            messagebox.showwarning("提示", "请先添加视频到列表")
            return
        
        messagebox.showinfo("提示", f"批量处理功能开发中...\n\n当前列表: {len(self.video_list)} 个视频")
    
    def _quick_translate(self):
        """快速翻译"""
        text = self.quick_input.get('1.0', 'end-1c').strip()
        if not text:
            return
        
        # 从Combobox值中提取引擎代码
        engine_str = self.engine_var.get()
        engine = engine_str.split(' - ')[0] if ' - ' in engine_str else engine_str
        
        style_str = self.style_var.get()
        style = style_str.split(' - ')[0] if ' - ' in style_str else style_str
        
        def do_translate():
            result = self.translator.translate(text, 'ja', 'zh', engine=engine, style=style)
            self.quick_output.config(state='normal')
            self.quick_output.delete('1.0', 'end')
            self.quick_output.insert('1.0', result['text'])
            self.quick_output.config(state='disabled')
            
            stats = self.translator.get_engine_status()['stats']
            self.stats_label.config(text=f"总翻译: {stats['total']}\n成功: {stats['success']}\n缓存: {stats['cache_hit']}")
        
        threading.Thread(target=do_translate, daemon=True).start()
    
    def translation_settings(self):
        """翻译设置"""
        messagebox.showinfo("翻译设置", "设置功能开发中...")
    
    def model_manager(self):
        """模型管理"""
        messagebox.showinfo("模型管理", "模型管理功能开发中...")
    
    def gpu_settings(self):
        """GPU配置"""
        messagebox.showinfo("GPU配置", "GPU配置功能开发中...")

    def show_recommend_config(self):
        """AI推荐配置"""
        recommender = ConfigRecommender()
        rec = recommender.recommend()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("AI推荐配置")
        dialog.geometry("500x450")
        dialog.configure(bg='#1E1F22')
        dialog.transient(self.root)
        
        tk.Label(dialog, text="🎮 AI推荐配置", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)
        
        # GPU信息
        gpu = rec['gpu']
        info_text = f"""🎮 GPU: {gpu['name']}
💾 显存: {gpu.get('memory_total', 0)}MB (空闲: {gpu.get('memory_free', 0)}MB)
🖥 系统: {rec['system'].get('cpu', 'Unknown')}
📊 内存: {rec['system'].get('memory_gb', 0)}GB

推荐模式: {rec['mode']}
模式说明: {rec['mode_description']}

推荐配置:
  语音识别: Whisper {rec['config']['whisper_model']} ({rec['config']['whisper_device'].upper()})
  翻译引擎: {rec['config']['translation']}
  AI润色: {rec['config'].get('polish', '不启用')}"""
        
        text_widget = tk.Text(dialog, bg='#2B2D30', fg='#52C41A',
                            font=('Consolas', 10), height=15)
        text_widget.pack(fill='both', expand=True, padx=20, pady=10)
        text_widget.insert('1.0', info_text)
        text_widget.config(state='disabled')
        
        ModernButton(dialog, text="关闭", command=dialog.destroy, style="ghost").pack(pady=10)

    def ai_bilingual_subtitle(self):
        """生成双语字幕"""
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕，请先生成或加载字幕")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("双语字幕设置")
        dialog.geometry("400x300")
        dialog.configure(bg='#1E1F22')
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="🌐 双语字幕生成", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)

        # 语言对选择
        tk.Label(dialog, text="选择语言对:", bg='#1E1F22', fg='#AAA').pack(anchor='w', padx=20)
        pair_var = tk.StringVar(value='ja-zh')
        pairs = [
            ('ja-zh', '中日双语（原文日语，翻译中文）'),
            ('ja-en', '日英双语（原文日语，翻译英文）'),
            ('zh-en', '中英双语（原文中文，翻译英文）'),
        ]
        for val, label in pairs:
            tk.Radiobutton(dialog, text=label, variable=pair_var, value=val,
                          bg='#1E1F22', fg='#AAA', selectcolor='#2B2D30',
                          activebackground='#1E1F22').pack(anchor='w', padx=30)

        def generate():
            bilingual = BilingualSubtitle()
            subs = []
            for start, end, text, trans in self.subtitles:
                subs.append({
                    'start': start / 1000, 'end': end / 1000,
                    'original': text, 'translated': trans
                })
            
            ass_content = bilingual.generate_ass_bilingual(subs, pair_var.get())
            
            file_path = filedialog.asksaveasfilename(
                title="保存双语字幕",
                defaultextension=".ass",
                filetypes=[("ASS字幕", "*.ass"), ("SRT字幕", "*.srt")]
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(ass_content)
                self._log(f"双语字幕已保存: {file_path}")
                messagebox.showinfo("完成", f"双语字幕已保存到:\n{file_path}")
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg='#1E1F22')
        btn_frame.pack(pady=15)
        ModernButton(btn_frame, text="生成", command=generate, style="primary").pack(side='left', padx=10)
        ModernButton(btn_frame, text="取消", command=dialog.destroy, style="ghost").pack(side='left', padx=10)

    def ai_identify_speakers(self):
        """AI人物识别"""
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕，请先生成或加载字幕")
            return

        identifier = SpeakerIdentifier()
        subs = []
        for start, end, text, trans in self.subtitles:
            subs.append({'start': start/1000, 'end': end/1000, 'original': text, 'translated': trans})

        self._log("开始AI人物识别...")
        result = identifier.identify_speakers(subs)

        # 更新字幕
        for i, sub in enumerate(result):
            start, end, _, trans = self.subtitles[i]
            speaker = sub.get('speaker_label', '')
            if speaker:
                text = sub.get('original', '')
                self.subtitles[i] = (start, end, text, trans)

        stats = identifier.get_speaker_stats(result)
        stats_text = "识别结果:\n"
        for speaker, info in stats.items():
            stats_text += f"  {speaker}: {info['count']}条 ({info['gender']})\n"

        self._refresh_subtitle_list()
        self._log(stats_text)
        messagebox.showinfo("完成", f"人物识别完成!\n\n{stats_text}")

    def ai_quality_score(self):
        """AI字幕质量评分"""
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕，请先生成或加载字幕")
            return

        scorer = SubtitleQualityScorer()
        subs = []
        for start, end, text, trans in self.subtitles:
            subs.append({'start': start/1000, 'end': end/1000, 'original': text, 'translated': trans})

        self._log("开始字幕质量评分...")
        result = scorer.score_subtitles(subs)

        dialog = tk.Toplevel(self.root)
        dialog.title("字幕质量评分")
        dialog.geometry("450x400")
        dialog.configure(bg='#1E1F22')
        dialog.transient(self.root)

        tk.Label(dialog, text="📊 字幕质量评分", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)

        overall = result['overall']
        color = '#52C41A' if overall >= 80 else '#FAAD14' if overall >= 60 else '#FF4D4F'
        tk.Label(dialog, text=f"综合评分: {overall}分", bg='#1E1F22', fg=color,
                font=('Microsoft YaHei UI', 20, 'bold')).pack(pady=5)

        details = result['details']
        detail_text = f"""翻译准确率: {details['accuracy']}分
翻译自然度: {details['naturalness']}分
时间轴精准度: {details['timing']}分
字幕长度合理性: {details['length']}分

字幕总数: {result['count']}条
发现问题: {len(result['issues'])}个"""

        text_widget = tk.Text(dialog, bg='#2B2D30', fg='#AAA',
                            font=('Consolas', 10), height=10)
        text_widget.pack(fill='both', expand=True, padx=20, pady=10)
        text_widget.insert('1.0', detail_text)

        if result['issues']:
            text_widget.insert('end', '\n\n问题列表:\n')
            for issue in result['issues'][:10]:
                text_widget.insert('end', f"  {issue['message']}\n")

        text_widget.config(state='disabled')

        ModernButton(dialog, text="关闭", command=dialog.destroy, style="ghost").pack(pady=10)

    def ai_style_editor(self):
        """ASS样式编辑器"""
        editor = ASSStyleEditor()
        presets = editor.get_all_presets()

        dialog = tk.Toplevel(self.root)
        dialog.title("字幕样式编辑器")
        dialog.geometry("500x500")
        dialog.configure(bg='#1E1F22')
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="🎨 字幕样式编辑器", bg='#1E1F22', fg='white',
                font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)

        # 预设选择
        tk.Label(dialog, text="选择预设风格:", bg='#1E1F22', fg='#AAA').pack(anchor='w', padx=20)
        preset_var = tk.StringVar(value='bilibili')
        preset_combo = ttk.Combobox(dialog, textvariable=preset_var, state='readonly', width=25)
        preset_combo['values'] = [f"{k} - {v}" for k, v in presets.items()]
        preset_combo.set('bilibili - B站字幕组风格')
        preset_combo.pack(padx=20, pady=5)

        # 特效选择
        tk.Label(dialog, text="选择特效:", bg='#1E1F22', fg='#AAA').pack(anchor='w', padx=20)
        effect_var = tk.StringVar(value='fade_both')
        effects = [
            ('fade_both', '淡入淡出'),
            ('fade_in', '淡入'),
            ('fade_out', '淡出'),
            ('glow', '发光'),
            ('typewriter', '打字机'),
            ('zoom_in', '缩放'),
        ]
        effect_combo = ttk.Combobox(dialog, textvariable=effect_var, state='readonly', width=25)
        effect_combo['values'] = [f"{k} - {v}" for k, v in effects]
        effect_combo.set('fade_both - 淡入淡出')
        effect_combo.pack(padx=20, pady=5)

        # 预览区域
        tk.Label(dialog, text="预览:", bg='#1E1F22', fg='#AAA').pack(anchor='w', padx=20)
        preview_text = tk.Text(dialog, bg='#000000', fg='#FFFFFF',
                              font=('Microsoft YaHei UI', 16), height=3)
        preview_text.pack(fill='x', padx=20, pady=5)
        preview_text.insert('1.0', '这是字幕预览效果\nThis is subtitle preview')
        preview_text.config(state='disabled')

        def apply_style():
            if not self.subtitles:
                messagebox.showwarning("提示", "没有字幕")
                return

            preset_name = preset_var.get().split(' - ')[0]
            effect_name = effect_var.get().split(' - ')[0]

            subs = []
            for start, end, text, trans in self.subtitles:
                subs.append({'start': start/1000, 'end': end/1000,
                           'original': text, 'translated': trans or text})

            ass_content = editor.generate_full_ass(subs, preset=preset_name, effect=effect_name)

            file_path = filedialog.asksaveasfilename(
                title="保存ASS字幕",
                defaultextension=".ass",
                filetypes=[("ASS字幕", "*.ass")]
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(ass_content)
                self._log(f"ASS字幕已保存: {file_path}")
                messagebox.showinfo("完成", f"ASS字幕已保存到:\n{file_path}")
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg='#1E1F22')
        btn_frame.pack(pady=15)
        ModernButton(btn_frame, text="应用并保存", command=apply_style, style="primary").pack(side='left', padx=10)
        ModernButton(btn_frame, text="取消", command=dialog.destroy, style="ghost").pack(side='left', padx=10)
    
    def show_help(self):
        """显示帮助"""
        help_text = """AI动漫字幕工坊 - 使用帮助

快捷键:
  Ctrl+O - 打开视频
  Ctrl+S - 保存字幕
  空格 - 播放/暂停
  左/右箭头 - 上/下一条字幕

功能:
  - 视频列表管理
  - AI语音识别生成字幕
  - 多引擎翻译
  - 字幕编辑
  - 时间轴预览

翻译引擎:
  - 搜狗翻译/必应翻译/阿里翻译/有道翻译/彩云小译: 免费
  - MiMo AI: 需要配置API Key
  - Ollama本地: 需要安装Ollama

翻译风格:
  - 动漫字幕组: 自然流畅
  - 直译: 保持原意
  - B站风格: 接地气
  - 轻小说: 优美文艺
  - 日常口语: 自然随意
"""
        messagebox.showinfo("使用帮助", help_text)
    
    def show_about(self):
        """显示关于"""
        about_text = """AI动漫字幕工坊 v1.0

专业级AI动漫字幕工作站

功能:
  - 视频列表管理
  - AI字幕生成 (Faster-Whisper large-v3)
  - AI多引擎翻译
  - AI智能润色
  - 时间轴编辑
  - 批量处理

支持格式:
  - 视频: MP4/MKV/AVI/MOV
  - 字幕: SRT/ASS/VTT
"""
        messagebox.showinfo("关于", about_text)
    
    # ==================== 播放控制 ====================
    
    def toggle_play(self):
        """切换播放/暂停"""
        self.is_playing = not self.is_playing
        self.play_btn.config(text="⏸" if self.is_playing else "▶")
    
    def stop_play(self):
        """停止播放"""
        self.is_playing = False
        self.play_btn.config(text="▶")
        self.current_time = 0
    
    def prev_subtitle(self):
        """上一条字幕"""
        selection = self.subtitle_list.selection()
        if selection:
            idx = int(selection[0])
            if idx > 0:
                self.subtitle_list.selection_set(str(idx - 1))
                self.subtitle_list.see(str(idx - 1))
                self._on_subtitle_select(None)
    
    def next_subtitle(self):
        """下一条字幕"""
        selection = self.subtitle_list.selection()
        if selection:
            idx = int(selection[0])
            if idx < len(self.subtitles) - 1:
                self.subtitle_list.selection_set(str(idx + 1))
                self.subtitle_list.see(str(idx + 1))
                self._on_subtitle_select(None)
    
    def zoom_in(self):
        """放大时间轴"""
        self.zoom_level = min(5.0, self.zoom_level * 1.2)
        self._draw_timeline()
    
    def zoom_out(self):
        """缩小时间轴"""
        self.zoom_level = max(0.1, self.zoom_level / 1.2)
        self._draw_timeline()
    
    def zoom_fit(self):
        """适配时间轴"""
        if self.subtitles:
            max_time = max(end for _, end, _, _ in self.subtitles)
            w = self.timeline_canvas.winfo_width()
            self.zoom_level = w / (max_time / 100) if max_time > 0 else 1.0
        else:
            self.zoom_level = 1.0
        self._draw_timeline()
    
    # ==================== 视频预览和烧录 ====================
    
    def preview_video(self):
        """预览视频（使用FFplay）"""
        if not self.current_file:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        
        import subprocess
        self._log(f"预览视频: {os.path.basename(self.current_file)}")
        # 使用FFplay播放视频
        subprocess.Popen(['ffplay', '-i', self.current_file, '-autoexit'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    def preview_with_subtitle(self):
        """预览视频+字幕（使用FFplay加载字幕）"""
        if not self.current_file:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕可显示")
            return
        
        import subprocess
        import tempfile
        
        # 先导出临时SRT文件
        srt_path = tempfile.mktemp(suffix='.srt')
        self._export_srt(srt_path)
        
        self._log(f"预览视频+字幕: {os.path.basename(self.current_file)}")
        # 使用FFplay播放视频并加载字幕
        subprocess.Popen(['ffplay', '-i', self.current_file, 
                        '-vf', f'subtitles={srt_path}',
                        '-autoexit'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    def burn_subtitle_to_video(self):
        """烧录字幕到视频（硬字幕）"""
        if not self.current_file:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕可烧录")
            return
        
        # 选择输出文件
        output_path = filedialog.asksaveasfilename(
            title="保存带字幕视频",
            defaultextension=".mp4",
            filetypes=[("MP4视频", "*.mp4")],
            initialfile=f"{os.path.splitext(os.path.basename(self.current_file))[0]}_字幕.mp4"
        )
        
        if not output_path:
            return
        
        import subprocess
        import tempfile
        import threading
        
        # 先导出临时SRT文件
        srt_path = tempfile.mktemp(suffix='.srt')
        self._export_srt(srt_path)
        
        def burn_thread():
            try:
                self.root.after(0, lambda: self._log(f"开始烧录字幕..."))
                self.root.after(0, lambda: self.status_label.config(text="烧录字幕中..."))
                
                # 使用FFmpeg烧录字幕
                cmd = [
                    'ffmpeg', '-y',
                    '-i', self.current_file,
                    '-vf', f'subtitles={srt_path}',
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
                    '-c:a', 'copy',
                    '-movflags', '+faststart',
                    output_path
                ]
                
                self._log(f"CMD: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # 等待完成
                stdout, stderr = process.communicate()
                
                # 清理临时文件
                try:
                    os.remove(srt_path)
                except:
                    pass
                
                if process.returncode == 0:
                    self.root.after(0, lambda: self._log(f"✅ 烧录完成: {output_path}"))
                    self.root.after(0, lambda: self.status_label.config(text="烧录完成!"))
                    self.root.after(100, lambda: messagebox.showinfo("完成", 
                        f"字幕已烧录到视频!\n\n输出: {output_path}"))
                else:
                    error_msg = stderr[-500:] if stderr else "未知错误"
                    self.root.after(0, lambda: self._log(f"❌ 烧录失败: {error_msg}"))
                    self.root.after(0, lambda: messagebox.showerror("错误", f"烧录失败: {error_msg}"))
                    
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._log(f"异常: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("错误", f"烧录失败: {error_msg}"))
        
        threading.Thread(target=burn_thread, daemon=True).start()
    
    def export_with_soft_subtitle(self):
        """导出带软字幕的视频"""
        if not self.current_file:
            messagebox.showwarning("提示", "请先打开视频文件")
            return
        
        if not self.subtitles:
            messagebox.showwarning("提示", "没有字幕可导出")
            return
        
        # 选择输出文件
        output_path = filedialog.asksaveasfilename(
            title="保存带软字幕视频",
            defaultextension=".mkv",
            filetypes=[("MKV视频", "*.mkv"), ("MP4视频", "*.mp4")],
            initialfile=f"{os.path.splitext(os.path.basename(self.current_file))[0]}_软字幕.mkv"
        )
        
        if not output_path:
            return
        
        import subprocess
        import tempfile
        import threading
        
        # 先导出临时SRT文件
        srt_path = tempfile.mktemp(suffix='.srt')
        self._export_srt(srt_path)
        
        def export_thread():
            try:
                self.root.after(0, lambda: self._log(f"开始导出软字幕视频..."))
                self.root.after(0, lambda: self.status_label.config(text="导出中..."))
                
                # 使用FFmpeg添加软字幕
                cmd = [
                    'ffmpeg', '-y',
                    '-i', self.current_file,
                    '-i', srt_path,
                    '-c', 'copy',
                    '-c:s', 'srt',
                    '-map', '0:v', '-map', '0:a', '-map', '1:0',
                    '-metadata:s:s:0', 'language=jpn',
                    output_path
                ]
                
                self._log(f"CMD: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # 等待完成
                stdout, stderr = process.communicate()
                
                # 清理临时文件
                try:
                    os.remove(srt_path)
                except:
                    pass
                
                if process.returncode == 0:
                    self.root.after(0, lambda: self._log(f"✅ 导出完成: {output_path}"))
                    self.root.after(0, lambda: self.status_label.config(text="导出完成!"))
                    self.root.after(100, lambda: messagebox.showinfo("完成", 
                        f"软字幕视频已导出!\n\n输出: {output_path}\n\n播放时可在播放器中选择/关闭字幕"))
                else:
                    error_msg = stderr[-500:] if stderr else "未知错误"
                    self.root.after(0, lambda: self._log(f"❌ 导出失败: {error_msg}"))
                    self.root.after(0, lambda: messagebox.showerror("错误", f"导出失败: {error_msg}"))
                    
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._log(f"异常: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("错误", f"导出失败: {error_msg}"))
        
        threading.Thread(target=export_thread, daemon=True).start()
    
    def _export_srt(self, output_path):
        """导出SRT字幕文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, (start, end, text, trans) in enumerate(self.subtitles):
                # 使用翻译文本（如果有），否则使用原文
                display_text = trans if trans else text
                f.write(f"{i+1}\n")
                f.write(f"{self._ms_to_srt_time(start)} --> {self._ms_to_srt_time(end)}\n")
                f.write(f"{display_text}\n\n")
    
    def _ms_to_srt_time(self, ms):
        """毫秒转SRT时间格式"""
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        millis = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
    
    def realtime_subtitle(self):
        """实时字幕 - 播放视频同时生成字幕"""
        if not self.current_file:
            messagebox.showinfo("提示", "请先导入视频文件")
            return
        
        # 选择输出SRT路径
        srt_path = self.current_file.rsplit('.', 1)[0] + '.srt'
        
        # 创建实时字幕窗口
        rt_win = tk.Toplevel(self.root)
        rt_win.title("▶ 实时字幕生成中")
        rt_win.geometry("800x300")
        rt_win.configure(bg='#18191C')
        
        # 字幕显示区域
        subtitle_label = tk.Label(rt_win, text="等待识别...", 
                                  bg='#18191C', fg='#00D4FF',
                                  font=('Microsoft YaHei UI', 18, 'bold'),
                                  wraplength=750, justify='center')
        subtitle_label.pack(expand=True, fill='both', padx=20, pady=10)
        
        # 状态栏
        status_label = tk.Label(rt_win, text="准备中...", 
                                bg='#2B2D30', fg='#888',
                                font=('Consolas', 10))
        status_label.pack(fill='x', padx=5, pady=5)
        
        # 进度条
        progress = ttk.Progressbar(rt_win, length=780, mode='determinate')
        progress.pack(fill='x', padx=10, pady=5)
        
        # 存储识别结果
        all_segments = []
        
        def run_realtime():
            import subprocess
            import tempfile
            
            # 步骤1: 提取音频
            status_label.config(text="正在提取音频...")
            audio_path = tempfile.mktemp(suffix='.wav')
            
            try:
                subprocess.run([
                    'ffmpeg', '-y', '-i', self.current_file,
                    '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                    audio_path
                ], capture_output=True, timeout=300)
            except Exception as e:
                rt_win.after(0, lambda: status_label.config(text=f"音频提取失败: {e}"))
                return
            
            # 步骤2: 用Whisper识别（逐段处理）
            status_label.config(text="正在加载模型...")
            
            try:
                from faster_whisper import WhisperModel
                model = WhisperModel("large-v3", device="cuda", compute_type="float16")
                
                status_label.config(text="正在识别...")
                
                segments, info = model.transcribe(
                    audio_path,
                    language="ja",
                    beam_size=5,
                    best_of=3,
                    patience=1.0,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=200,
                        speech_pad_ms=50,
                        threshold=0.5,
                        min_speech_duration_ms=250,
                        max_speech_duration_s=7,
                    ),
                    word_timestamps=True,
                    condition_on_previous_text=False,
                    initial_prompt="以下是一段日语动漫对话。",
                )
                
                total_duration = info.duration if info.duration > 0 else 1
                
                for i, seg in enumerate(segments):
                    start_s = seg.start
                    end_s = seg.end
                    text = seg.text.strip()
                    
                    if text:
                        # 转换为毫秒
                        start_ms = int(start_s * 1000)
                        end_ms = int(end_s * 1000)
                        all_segments.append((start_ms, end_ms, text, ''))
                        
                        # 更新UI
                        rt_win.after(0, lambda t=text: subtitle_label.config(text=t))
                        rt_win.after(0, lambda s=start_s, e=end_s, t=text: 
                            status_label.config(text=f"[{s:.1f}s → {e:.1f}s] {t}"))
                        rt_win.after(0, lambda p=min(95, int(end_s/total_duration*100)): 
                            progress.config(value=p))
                
                # 保存SRT
                with open(srt_path, 'w', encoding='utf-8') as f:
                    for idx, (start_ms, end_ms, text, _) in enumerate(all_segments):
                        f.write(f"{idx+1}\n")
                        sh = start_ms // 3600000
                        sm = (start_ms % 3600000) // 60000
                        ss = (start_ms % 60000) // 1000
                        sms = start_ms % 1000
                        eh = end_ms // 3600000
                        em = (end_ms % 3600000) // 60000
                        es = (end_ms % 60000) // 1000
                        ems = end_ms % 1000
                        f.write(f"{sh:02d}:{sm:02d}:{ss:02d},{sms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}\n")
                        f.write(f"{text}\n\n")
                
                # 加载字幕到编辑器
                self.subtitles = [(s, e, t, tr) for s, e, t, tr in all_segments]
                self.root.after(0, self._refresh_subtitle_list)
                
                rt_win.after(0, lambda: subtitle_label.config(text="✅ 识别完成！"))
                rt_win.after(0, lambda: status_label.config(
                    text=f"共 {len(all_segments)} 条字幕，已保存到 {os.path.basename(srt_path)}"))
                rt_win.after(0, lambda: progress.config(value=100))
                
                # 清理临时文件
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                    
            except Exception as e:
                rt_win.after(0, lambda: status_label.config(text=f"识别失败: {e}"))
                import traceback
                traceback.print_exc()
        
        # 同时启动视频播放和识别
        threading.Thread(target=run_realtime, daemon=True).start()
        
        # 启动FFplay播放视频
        try:
            subprocess.Popen(['ffplay', '-i', self.current_file, '-autoexit'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            messagebox.showerror("错误", f"FFplay启动失败: {e}")

    def batch_process_folder(self):
        """批量处理文件夹中的所有视频"""
        folder = filedialog.askdirectory(title="选择包含视频的文件夹")
        if not folder:
            return
        
        # 扫描视频文件
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts', '.m4v')
        video_files = []
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(video_exts):
                video_files.append(os.path.join(folder, f))
        
        if not video_files:
            messagebox.showinfo("提示", "文件夹中没有找到视频文件")
            return
        
        # 弹出设置对话框
        settings = self._show_proofread_settings()
        if settings is None:
            return
        
        anime_name = settings.get('anime_name', '')
        enable_proofread = settings.get('enable_proofread', True)
        initial_prompt = settings.get('initial_prompt', '')
        
        # 创建批量处理窗口
        batch_win = tk.Toplevel(self.root)
        batch_win.title(f"📋 批量处理 - {len(video_files)} 个视频")
        batch_win.geometry("700x400")
        batch_win.configure(bg='#18191C')
        
        # 标题
        tk.Label(batch_win, text=f"📋 批量处理 {len(video_files)} 个视频", 
                bg='#18191C', fg='white', font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)
        
        # 当前处理状态
        current_label = tk.Label(batch_win, text="等待开始...", 
                                bg='#18191C', fg='#00D4FF', font=('Microsoft YaHei UI', 12))
        current_label.pack(pady=5)
        
        # 日志区域
        log_text = scrolledtext.ScrolledText(batch_win, bg='#1E1F22', fg='#888',
                                             font=('Consolas', 10), height=10)
        log_text.pack(fill='both', expand=True, padx=10, pady=5)
        
        # 总进度
        total_progress = ttk.Progressbar(batch_win, length=680, mode='determinate')
        total_progress.pack(fill='x', padx=10, pady=5)
        
        # 统计
        stats_label = tk.Label(batch_win, text="完成: 0 / 0", 
                              bg='#2B2D30', fg='#888', font=('Consolas', 10))
        stats_label.pack(fill='x', padx=10, pady=5)
        
        def log(msg):
            log_text.insert('end', msg + '\n')
            log_text.see('end')
        
        def run_batch():
            completed = 0
            failed = 0
            
            for idx, video_path in enumerate(video_files):
                video_name = os.path.basename(video_path)
                batch_win.after(0, lambda: current_label.config(
                    text=f"[{idx+1}/{len(video_files)}] {video_name}"))
                batch_win.after(0, lambda: log(f"\n{'='*40}"))
                batch_win.after(0, lambda: log(f"开始处理: {video_name}"))
                
                try:
                    # 第1步：Whisper识别
                    batch_win.after(0, lambda: log("【第1步】Whisper识别..."))
                    
                    recognizer = SpeechRecognizer(model_size="large-v3")
                    
                    def prog_cb(status, progress):
                        pass  # 静默
                    
                    if not recognizer.load_model(prog_cb):
                        batch_win.after(0, lambda: log("❌ 模型加载失败"))
                        failed += 1
                        continue
                    
                    import subprocess
                    import tempfile
                    
                    audio_path = tempfile.mktemp(suffix='.wav')
                    subprocess.run([
                        'ffmpeg', '-y', '-i', video_path,
                        '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                        audio_path
                    ], capture_output=True, timeout=600)
                    
                    result = recognizer.transcribe(
                        audio_path, language="ja",
                        progress_callback=prog_cb,
                        initial_prompt=initial_prompt
                    )
                    
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                    
                    if not result['success']:
                        batch_win.after(0, lambda: log(f"❌ 识别失败: {result['error']}"))
                        failed += 1
                        continue
                    
                    raw_segments = result['segments']
                    batch_win.after(0, lambda: log(f"识别完成: {len(raw_segments)} 条"))
                    
                    # 第2步：校对（可选）
                    if enable_proofread and raw_segments:
                        batch_win.after(0, lambda: log("【第2步】日语校对..."))
                        translator = TranslationEngine()
                        corrected = translator.proofread_japanese(
                            raw_segments, anime_name=anime_name)
                        corrected_count = sum(1 for a, b in zip(raw_segments, corrected) 
                                            if a['text'] != b['text'])
                        batch_win.after(0, lambda: log(f"校对修正: {corrected_count} 条"))
                        
                        # 模型热切换
                        proofread_model = "qwen2.5:7b-instruct-q4_K_M"
                        sakura_model = "sakura"
                        try:
                            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
                            if os.path.exists(config_path):
                                with open(config_path, 'r') as f:
                                    cfg = json.load(f)
                                    proofread_model = cfg.get('proofread_model', proofread_model)
                                    sakura_model = cfg.get('ollama_model', sakura_model)
                        except:
                            pass
                        translator.switch_model(proofread_model, sakura_model)
                    else:
                        corrected = raw_segments
                    
                    # 断句优化
                    translator2 = TranslationEngine()
                    corrected = translator2.optimize_subtitle_segments(corrected)
                    
                    # 保存SRT
                    srt_path = video_path.rsplit('.', 1)[0] + '.srt'
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        for i, seg in enumerate(corrected):
                            start_ms = int(seg['start'] * 1000)
                            end_ms = int(seg['end'] * 1000)
                            f.write(f"{i+1}\n")
                            sh = start_ms // 3600000
                            sm = (start_ms % 3600000) // 60000
                            ss = (start_ms % 60000) // 1000
                            sms = start_ms % 1000
                            eh = end_ms // 3600000
                            em = (end_ms % 3600000) // 60000
                            es = (end_ms % 60000) // 1000
                            ems = end_ms % 1000
                            f.write(f"{sh:02d}:{sm:02d}:{ss:02d},{sms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}\n")
                            f.write(f"{seg['text']}\n\n")
                    
                    completed += 1
                    batch_win.after(0, lambda: log(f"✅ 完成! 保存到 {os.path.basename(srt_path)}"))
                    
                except Exception as e:
                    failed += 1
                    batch_win.after(0, lambda: log(f"❌ 处理失败: {str(e)}"))
                
                # 更新总进度
                progress_val = int((idx + 1) / len(video_files) * 100)
                batch_win.after(0, lambda: total_progress.config(value=progress_val))
                batch_win.after(0, lambda: stats_label.config(
                    text=f"完成: {completed} / 失败: {failed} / 总计: {len(video_files)}"))
            
            # 完成
            batch_win.after(0, lambda: current_label.config(text="✅ 全部处理完成!"))
            batch_win.after(0, lambda: log(f"\n{'='*40}"))
            batch_win.after(0, lambda: log(f"全部完成! 成功: {completed}, 失败: {failed}"))
            batch_win.after(0, lambda: messagebox.showinfo("完成", 
                f"批量处理完成!\n\n成功: {completed}\n失败: {failed}\n总计: {len(video_files)}"))
        
        threading.Thread(target=run_batch, daemon=True).start()

    def run(self):
        """运行应用"""
        self.root.mainloop()


def launch_app():
    """启动应用"""
    app = AI字幕工坊()
    app.run()


if __name__ == "__main__":
    launch_app()
