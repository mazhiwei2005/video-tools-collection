#!/usr/bin/env python3
"""稀饭动漫下载器 - B站风格UI"""
import os
import re
import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font
import threading
import queue
import requests
import urllib3
import base64
import subprocess
import json as json_mod
urllib3.disable_warnings()

# 颜色常量 - B站风格
COLORS = {
    "bg": "#F5F7FA",           # 主背景
    "sidebar": "#FFFFFF",      # 侧边栏背景
    "card": "#FFFFFF",         # 卡片背景
    "primary": "#00AEEC",      # B站蓝
    "primary_dark": "#0091D4", # 深蓝
    "primary_light": "#E8F4FD",# 浅蓝背景
    "text": "#333333",         # 主文字
    "text_secondary": "#999999",# 次要文字
    "border": "#E5E5E5",       # 边框
    "success": "#67C23A",      # 成功绿
    "warning": "#E6A23C",      # 警告黄
    "danger": "#F56C6C",       # 危险红
    "hover": "#E8F4FD",        # 悬停背景
}

SITE = "https://anime.xifanacg.com"
ANICH_API = "https://anich.sends.eu.org"

class RoundedFrame(tk.Canvas):
    """圆角卡片"""
    def __init__(self, parent, bg=COLORS["card"], radius=16, **kwargs):
        super().__init__(parent, highlightthickness=0, bg=parent["bg"], **kwargs)
        self.bg = bg
        self.radius = radius
        self.bind("<Configure>", self._draw)
    
    def _draw(self, event=None):
        self.delete("bg")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 1 or h < 1:
            return
        # 绘制圆角矩形
        self.create_round_rect(2, 2, w-2, h-2, self.radius, fill=self.bg, outline=COLORS["border"], tags="bg")
    
    def create_round_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1+radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

class ModernButton(tk.Canvas):
    """现代化按钮"""
    def __init__(self, parent, text="", command=None, style="primary", width=120, height=40, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bg=parent["bg"], **kwargs)
        self.command = command
        self.style = style
        self.text = text
        self.width = width
        self.height = height
        
        self._setup_style()
        self._draw()
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_click)
    
    def _setup_style(self):
        styles = {
            "primary": {"bg": COLORS["primary"], "fg": "#FFFFFF", "hover": COLORS["primary_dark"]},
            "secondary": {"bg": "#F0F0F0", "fg": COLORS["text"], "hover": "#E0E0E0"},
            "danger": {"bg": COLORS["danger"], "fg": "#FFFFFF", "hover": "#E04040"},
            "success": {"bg": COLORS["success"], "fg": "#FFFFFF", "hover": "#5AAP2A"},
        }
        self.style = styles.get(styles, styles["primary"])
    
    def _draw(self, bg=None):
        self.delete("all")
        bg = bg or self.style["bg"]
        self.create_round_rect(0, 0, self.winfo_width(), self.winfo_height(), 10, fill=bg, outline="")
        self.create_text(self.winfo_width()//2, self.winfo_height()//2, text=self.text, fill=self.style["fg"], font=("微软雅黑", 10, "bold"))
    
    def create_round_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
            x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
            x1, y2, x1, y2-radius, x1, y1+radius, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)
    
    def _on_enter(self, e):
        self._draw(self.style["hover"])
    
    def _on_leave(self, e):
        self._draw()
    
    def _on_click(self, e):
        if self.command:
            self.command()

class XifanDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("动漫下载器 - 稀饭 + AniCh")
        self.root.geometry("1100x700")
        self.root.configure(bg=COLORS["bg"])
        
        # 隐藏默认标题栏
        self.root.overrideredirect(False)
        
        self.session = None
        self._downloading = False
        self._cancel = False
        self.download_queue = queue.Queue()
        self.added_anime = set()  # 已添加的动漫ID集合，用于去重
        self.current_page = "download"
        self.last_clipboard = ""  # 用于自动粘贴，记录上次剪贴板内容
        self._current_speed = 0
        self._total_downloaded = 0
        self._current_process = None
        self.stats = {"success": 0, "failed": 0, "downloaded_eps": 0, "failed_eps": 0}
        
        # 数据文件路径（保存在exe同目录）
        self.data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download_list.json")
        
        self.setup_ui()
        self.init_session()
        self.load_download_list()  # 启动时加载历史列表
        self.check_queue()
        
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        # 主容器
        self.main_container = tk.Frame(self.root, bg=COLORS["bg"])
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # 左侧导航栏
        self.setup_sidebar()
        
        # 右侧内容区
        self.content_frame = tk.Frame(self.main_container, bg=COLORS["bg"])
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 顶部标题栏
        self.setup_header()
        
        # 内容区域
        self.setup_content()
        
        # 绑定窗口获焦事件，实现自动粘贴
        self.root.bind("<FocusIn>", self.auto_paste_on_focus)
    
    def setup_sidebar(self):
        """左侧导航栏"""
        sidebar = tk.Frame(self.main_container, bg=COLORS["sidebar"], width=200)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        
        # Logo区域
        logo_frame = tk.Frame(sidebar, bg=COLORS["sidebar"], height=60)
        logo_frame.pack(fill=tk.X, pady=(20, 30))
        tk.Label(logo_frame, text="🍚 稀饭下载器", font=("微软雅黑", 14, "bold"), 
                bg=COLORS["sidebar"], fg=COLORS["primary"]).pack()
        
        # 导航按钮
        nav_items = [
            ("📥", "下载任务", "download"),
            ("📋", "下载列表", "list"),
            ("📜", "历史记录", "history"),
            ("⚙️", "设置选项", "settings"),
            ("ℹ️", "关于软件", "about"),
        ]
        
        self.nav_buttons = {}
        for icon, text, page in nav_items:
            btn_frame = tk.Frame(sidebar, bg=COLORS["sidebar"], cursor="hand2")
            btn_frame.pack(fill=tk.X, padx=10, pady=2)
            
            btn_label = tk.Label(btn_frame, text=f"  {icon}  {text}", font=("微软雅黑", 11),
                               bg=COLORS["sidebar"], fg=COLORS["text"], anchor="w", padx=20, pady=12)
            btn_label.pack(fill=tk.X)
            
            btn_frame.bind("<Enter>", lambda e, f=btn_frame: f.configure(bg=COLORS["hover"]))
            btn_frame.bind("<Leave>", lambda e, f=btn_frame, p=page: f.configure(bg=COLORS["sidebar"] if self.current_page != p else COLORS["primary_light"]))
            btn_frame.bind("<ButtonPress-1>", lambda e, p=page: self.switch_page(p))
            btn_label.bind("<ButtonPress-1>", lambda e, p=page: self.switch_page(p))
            
            self.nav_buttons[page] = btn_frame
        
        # 底部状态
        status_frame = tk.Frame(sidebar, bg=COLORS["sidebar"])
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=20)
        
        self.lbl_download_count = tk.Label(status_frame, text="⬜ 下载中 0", font=("微软雅黑", 10),
                                          bg=COLORS["primary"], fg="#FFFFFF", padx=15, pady=8)
        self.lbl_download_count.pack(fill=tk.X, pady=(0, 5))
        
        self.lbl_wait_count = tk.Label(status_frame, text="⏳ 等待中 0", font=("微软雅黑", 10),
                                       bg=COLORS["text_secondary"], fg="#FFFFFF", padx=15, pady=8)
        self.lbl_wait_count.pack(fill=tk.X)
        
        # 高亮当前页
        self.switch_page("download")
    
    def setup_header(self):
        """顶部标题栏"""
        header = tk.Frame(self.content_frame, bg=COLORS["bg"], height=50)
        header.pack(fill=tk.X, padx=20, pady=(15, 5))
        
        tk.Label(header, text="📥 下载任务", font=("微软雅黑", 16, "bold"),
                bg=COLORS["bg"], fg=COLORS["text"]).pack(side=tk.LEFT)
        
        # 右上角按钮
        btn_frame = tk.Frame(header, bg=COLORS["bg"])
        btn_frame.pack(side=tk.RIGHT)
        
        for text, cmd in [("—", self.root.iconify), ("□", None), ("✕", self.root.destroy)]:
            btn = tk.Label(btn_frame, text=text, font=("微软雅黑", 12), bg=COLORS["bg"], 
                          fg=COLORS["text_secondary"], padx=10, cursor="hand2")
            btn.pack(side=tk.LEFT)
            if cmd:
                btn.bind("<ButtonPress-1>", lambda e, c=cmd: c())
    
    def setup_content(self):
        """内容区域"""
        # 使用Canvas+Scrollbar实现滚动
        canvas = tk.Canvas(self.content_frame, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.content_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=COLORS["bg"])
        
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 输入区域卡片
        self.setup_input_card()
        
        # 解析结果卡片
        self.setup_result_card()
        
        # 输出设置卡片
        self.setup_output_card()
        
        # 下载控制卡片
        self.setup_control_card()
    
    def setup_input_card(self):
        """输入链接区域"""
        card = tk.Frame(self.scrollable_frame, bg=COLORS["card"], relief="flat")
        card.pack(fill=tk.X, pady=(0, 15))
        
        # 标题
        header = tk.Frame(card, bg=COLORS["card"])
        header.pack(fill=tk.X, padx=20, pady=(15, 10))
        tk.Label(header, text="🔗 输入动漫链接（每行一个）", font=("微软雅黑", 12, "bold"),
                bg=COLORS["card"], fg=COLORS["text"]).pack(side=tk.LEFT)
        tk.Label(header, text="支持批量输入多个链接，每行一个", font=("微软雅黑", 9),
                bg=COLORS["card"], fg=COLORS["text_secondary"]).pack(side=tk.RIGHT)
        
        # 输入框
        input_frame = tk.Frame(card, bg=COLORS["card"])
        input_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.link_text = tk.Text(input_frame, height=5, font=("Consolas", 10), 
                                bg="#F8F9FA", fg=COLORS["text"], relief="solid", bd=1,
                                insertbackground=COLORS["primary"])
        self.link_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.link_text.insert("1.0", "https://anich.emmmm.eu.org/b/38184/1")
        
        # 右侧按钮
        btn_frame = tk.Frame(input_frame, bg=COLORS["card"])
        btn_frame.pack(side=tk.RIGHT, padx=(10, 0))
        
        self.create_button(btn_frame, "开始解析", self.parse_all, "primary", 120, 40).pack(pady=(0, 5))
        self.create_button(btn_frame, "删除选中", self.delete_selected, "danger", 120, 35).pack(pady=(0, 5))
        self.create_button(btn_frame, "清空结果", self.clear_results, "danger", 120, 35).pack(pady=(0, 5))
        self.create_button(btn_frame, "清空内容", self.clear_links, "secondary", 120, 35).pack(pady=(0, 5))
        self.create_button(btn_frame, "粘贴链接", self.paste_links, "secondary", 120, 35).pack()
        
        # 示例提示
        tk.Label(card, text="支持：稀饭动漫(xifanacg.com) + AniCh(emmmm.eu.org)（每行一个链接）",
                font=("微软雅黑", 9), bg=COLORS["card"], fg=COLORS["text_secondary"]).pack(anchor="w", padx=20, pady=(0, 5))
        tk.Label(card, text="示例：https://anime.xifanacg.com/bangumi/3235.html 或 https://anich.emmmm.eu.org/b/38184/1",
                font=("微软雅黑", 9), bg=COLORS["card"], fg=COLORS["text_secondary"]).pack(anchor="w", padx=20, pady=(0, 15))
    
    def setup_result_card(self):
        """解析结果区域"""
        card = tk.Frame(self.scrollable_frame, bg=COLORS["card"], relief="flat")
        card.pack(fill=tk.X, pady=(0, 15))
        
        # 标题
        header = tk.Frame(card, bg=COLORS["card"])
        header.pack(fill=tk.X, padx=20, pady=(15, 10))
        tk.Label(header, text="📋 解析结果", font=("微软雅黑", 12, "bold"),
                bg=COLORS["card"], fg=COLORS["text"]).pack(side=tk.LEFT)
        
        # 表格
        columns = ("名称", "集数", "状态", "进度", "链接")
        self.tree = ttk.Treeview(card, columns=columns, show="headings", height=8)
        
        style = ttk.Style()
        style.configure("Treeview", rowheight=35, font=("微软雅黑", 10))
        style.configure("Treeview.Heading", font=("微软雅黑", 10, "bold"))
        
        self.tree.heading("名称", text="动漫名称")
        self.tree.heading("集数", text="总集数")
        self.tree.heading("状态", text="状态")
        self.tree.heading("进度", text="下载进度")
        
        self.tree.column("名称", width=350)
        self.tree.column("集数", width=80, anchor="center")
        self.tree.column("状态", width=100, anchor="center")
        self.tree.column("进度", width=150, anchor="center")
        self.tree.column("链接", width=0, stretch=False)  # 隐藏列，保存原始链接
        
        scrollbar = ttk.Scrollbar(card, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0), pady=(0, 15))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 20), pady=(0, 15))
    
    def setup_output_card(self):
        """输出设置区域"""
        card = tk.Frame(self.scrollable_frame, bg=COLORS["card"], relief="flat")
        card.pack(fill=tk.X, pady=(0, 15))
        
        # 标题
        header = tk.Frame(card, bg=COLORS["card"])
        header.pack(fill=tk.X, padx=20, pady=(15, 10))
        tk.Label(header, text="💾 输出设置", font=("微软雅黑", 12, "bold"),
                bg=COLORS["card"], fg=COLORS["text"]).pack(side=tk.LEFT)
        
        # 保存目录
        dir_frame = tk.Frame(card, bg=COLORS["card"])
        dir_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        tk.Label(dir_frame, text="保存目录：", font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT)
        self.out_dir = tk.StringVar(value=r"G:\测试下载\百合番")
        tk.Entry(dir_frame, textvariable=self.out_dir, font=("微软雅黑", 10), width=50).pack(side=tk.LEFT, padx=5)
        self.create_button(dir_frame, "浏览", self.choose_dir, "secondary", 80, 30).pack(side=tk.LEFT)
        
        # 命名规则
        name_frame = tk.Frame(card, bg=COLORS["card"])
        name_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        tk.Label(name_frame, text="命名规则：", font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT)
        self.name_pattern = tk.StringVar(value="动漫名_集数")
        ttk.Combobox(name_frame, textvariable=self.name_pattern, values=["动漫名_集数", "集数_动漫名", "动漫名/集数"],
                    state="readonly", width=20).pack(side=tk.LEFT, padx=5)
        
        # 同时下载数
        thread_frame = tk.Frame(card, bg=COLORS["card"])
        thread_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        tk.Label(thread_frame, text="同时下载：", font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT)
        self.thread_count = tk.IntVar(value=3)
        tk.Spinbox(thread_frame, from_=1, to=10, textvariable=self.thread_count, width=5, font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=5)
        tk.Label(thread_frame, text="个任务", font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT)
    
    def setup_control_card(self):
        """下载控制区域"""
        card = tk.Frame(self.scrollable_frame, bg=COLORS["card"], relief="flat")
        card.pack(fill=tk.X, pady=(0, 15))
        
        # 标题
        header = tk.Frame(card, bg=COLORS["card"])
        header.pack(fill=tk.X, padx=20, pady=(15, 10))
        tk.Label(header, text="🎮 下载控制", font=("微软雅黑", 12, "bold"),
                bg=COLORS["card"], fg=COLORS["text"]).pack(side=tk.LEFT)
        
        # 按钮区域
        btn_frame = tk.Frame(card, bg=COLORS["card"])
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.create_button(btn_frame, "▶ 全部开始", self.start_download, "success", 120, 40).pack(side=tk.LEFT, padx=(0, 10))
        self.create_button(btn_frame, "⏸ 全部暂停", self.pause_download, "secondary", 120, 40).pack(side=tk.LEFT, padx=(0, 10))
        self.create_button(btn_frame, "⏹ 全部停止", self.stop_download, "danger", 120, 40).pack(side=tk.LEFT)
        
        # 速度显示
        speed_frame = tk.Frame(card, bg=COLORS["card"])
        speed_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        tk.Label(speed_frame, text="当前速度：", font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT)
        self.lbl_speed = tk.Label(speed_frame, text="0 MB/s", font=("微软雅黑", 10, "bold"),
                                 bg=COLORS["card"], fg=COLORS["primary"])
        self.lbl_speed.pack(side=tk.LEFT)
        
        # 统计信息
        stats_frame = tk.Frame(card, bg=COLORS["card"])
        stats_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        self.lbl_stats = tk.Label(stats_frame, text="动漫: 0 | 已下载: 0 | 失败: 0",
                                 font=("微软雅黑", 10), bg=COLORS["card"], fg=COLORS["text_secondary"])
        self.lbl_stats.pack(side=tk.LEFT)
        
        # 状态栏
        self.lbl_status = tk.Label(card, text="就绪", font=("微软雅黑", 10),
                                  bg=COLORS["primary_light"], fg=COLORS["primary"], padx=15, pady=8)
        self.lbl_status.pack(fill=tk.X, padx=20, pady=(0, 15))
    
    def create_button(self, parent, text, command, style="primary", width=120, height=40):
        """创建现代化按钮"""
        colors = {
            "primary": (COLORS["primary"], COLORS["primary_dark"], "#FFFFFF"),
            "secondary": ("#F0F0F0", "#E0E0E0", COLORS["text"]),
            "danger": (COLORS["danger"], "#E04040", "#FFFFFF"),
            "success": (COLORS["success"], "#5AAA2A", "#FFFFFF"),
        }
        bg, hover_bg, fg = colors.get(style, colors["primary"])
        
        btn = tk.Label(parent, text=text, font=("微软雅黑", 10, "bold"),
                      bg=bg, fg=fg, padx=15, pady=8, cursor="hand2", width=width//8)
        btn.pack(side=tk.LEFT, padx=2)
        
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        btn.bind("<ButtonPress-1>", lambda e: command())
        
        return btn
    
    def switch_page(self, page):
        """切换页面"""
        self.current_page = page
        for p, btn in self.nav_buttons.items():
            if p == page:
                btn.configure(bg=COLORS["primary_light"])
            else:
                btn.configure(bg=COLORS["sidebar"])
        
        # 更新标题
        titles = {
            "download": "📥 下载任务",
            "list": "📋 下载列表",
            "history": "📜 历史记录",
            "settings": "⚙️ 设置选项",
            "about": "ℹ️ 关于软件",
        }
        # 这里可以添加页面切换逻辑
    
    def init_session(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        try:
            self.session.get(SITE, verify=False, timeout=15)
        except:
            pass

    def _is_anich_url(self, url):
        """判断是否为AniCh链接"""
        return "anich" in url.lower() or "emmmm.eu.org" in url.lower()

    def _parse_anich_page(self, url):
        """解析AniCh页面，获取bangumi ID和集数列表"""
        # 提取bangumi ID
        m = re.search(r'/b/(\d+)', url)
        if not m:
            return None
        bangumi_id = m.group(1)

        resp = self.session.get(url, verify=False, timeout=30)
        resp.encoding = "utf-8"

        # 从window.$data中提取数据
        data_match = re.search(r'window\.\$data\s*=\s*(\{.*?\})\s*</script>', resp.text, re.DOTALL)
        if not data_match:
            return None

        try:
            data = json.loads(data_match.group(1))
            # 找到bangumi数据
            bangumi_key = f"bangumi-{bangumi_id}"
            if bangumi_key not in data:
                return None

            bangumi_data = data[bangumi_key]
            title = bangumi_data.get('data', {}).get('title', f'AniCh_{bangumi_id}')
            episodes = bangumi_data.get('episodes', [])

            # 只取有资源的集数
            eps = []
            for ep in episodes:
                if ep.get('status', False):
                    eps.append({
                        'sort': ep['sort'],
                        'title': ep.get('title', ''),
                    })

            return {
                'id': bangumi_id,
                'name': title,
                'eps': eps,
                'total': len(episodes),  # 总集数（包括无资源的）
                'site': 'anich',
            }
        except Exception as e:
            return None

    def _get_anich_m3u8(self, bangumi_id, episode):
        """获取AniCh视频URL（优先MP4直链，其次m3u8）"""
        try:
            resp = self.session.get(f"{ANICH_API}/vod/{bangumi_id}/{episode}", verify=False, timeout=30)
            if resp.status_code != 200:
                return None

            data = json_mod.loads(resp.text)
            raw = bytes(data)

            mp4_urls = []
            m3u8_urls = []
            # 提取base64编码的URL（protobuf中嵌套的base64字符串）
            all_b64 = re.findall(rb'[A-Za-z0-9+/]{20,}={0,2}', raw)

            for b64 in all_b64:
                b64_str = b64.decode('ascii')
                # 尝试不同的跳过长度来解码URL（protobuf前缀干扰）
                for skip in range(0, 5):
                    candidate = b64_str[skip:]
                    padded = candidate + '=' * (4 - len(candidate) % 4) if len(candidate) % 4 else candidate
                    try:
                        decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
                        # 修复protobuf前缀干扰（\x1d\x104ps:// → https://）
                        fixed = re.sub(r'[^\x00-\x7f]*\d*ps://', 'https://', decoded)
                        # 收集MP4和m3u8 URL
                        for url_match in re.finditer(r'https?://[a-zA-Z0-9._:/-]+(?:\.mp4|\.m3u8)[^\s"\'<>]*', fixed):
                            url = url_match.group(0)
                            if '.mp4' in url and '.m3u8' not in url:
                                mp4_urls.append(url)
                            elif '.m3u8' in url:
                                m3u8_urls.append(url)
                    except:
                        pass

            # 优先返回MP4直链（更稳定）
            if mp4_urls:
                return mp4_urls[0]
            # 其次返回m3u8
            if m3u8_urls:
                return m3u8_urls[0]
            return None
        except Exception as e:
            return None
    
    def choose_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.out_dir.set(path)
    
    def clear_links(self):
        self.link_text.delete("1.0", tk.END)

    def clear_results(self):
        """清空解析结果和下载队列"""
        # 清空treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
        # 清空下载队列
        while not self.download_queue.empty():
            try:
                self.download_queue.get_nowait()
            except:
                break
        # 清空已添加记录
        self.added_anime.clear()
        self.update_status("🗑️ 已清空所有解析结果")
    
    def delete_selected(self):
        """删除选中的文本"""
        try:
            # 获取选中的范围
            sel_start = self.link_text.index("sel.first")
            sel_end = self.link_text.index("sel.last")
            # 删除选中的文本
            self.link_text.delete(sel_start, sel_end)
        except tk.TclError:
            # 没有选中文本时，删除当前行
            try:
                # 获取当前光标位置
                cursor_pos = self.link_text.index("insert")
                line_num = cursor_pos.split(".")[0]
                # 删除当前行
                self.link_text.delete(f"{line_num}.0", f"{line_num}.end+1c")
            except:
                pass
    
    def paste_links(self):
        try:
            text = self.root.clipboard_get()
            self.link_text.insert(tk.END, text + "\n")
        except:
            pass
    
    def auto_paste_on_focus(self, event=None):
        """当窗口获得焦点时，自动粘贴剪贴板中的URL"""
        try:
            # 获取当前剪贴板内容
            clipboard = self.root.clipboard_get()
            
            # 如果剪贴板内容与上次相同，跳过
            if clipboard == self.last_clipboard:
                return
            
            # 检查是否像URL（以http/https开头）
            if clipboard.startswith(("http://", "https://")):
                # 检查输入框中是否已包含该URL
                current_content = self.link_text.get("1.0", tk.END)
                if clipboard in current_content:
                    return
                
                # 追加到输入框末尾
                self.link_text.insert(tk.END, clipboard + "\n")
                self.last_clipboard = clipboard
                
                # 可选：显示提示
                # messagebox.showinfo("自动粘贴", f"已自动粘贴链接：{clipboard[:50]}...")
        except tk.TclError:
            # 剪贴板为空或非文本内容
            pass
    
    def parse_all(self):
        links = self.link_text.get("1.0", tk.END).strip().split('\n')
        links = [l.strip() for l in links if l.strip()]
        
        if not links:
            messagebox.showwarning("警告", "请输入至少一个链接")
            return
        
        threading.Thread(target=self._parse_links, args=(links,), daemon=True).start()
    
    def _parse_links(self, links):
        total = len(links)
        success = 0
        skipped = 0
        
        for i, link in enumerate(links):
            self.update_status(f"正在解析 [{i+1}/{total}]...")
            
            try:
                # 判断是AniCh还是稀饭动漫
                if self._is_anich_url(link):
                    # AniCh解析
                    info = self._parse_anich_page(link)
                    if not info:
                        continue

                    bangumi_id = info['id']
                    if bangumi_id in self.added_anime:
                        skipped += 1
                        continue

                    self.added_anime.add(bangumi_id)
                    anime_info = {
                        "id": bangumi_id,
                        "name": info['name'],
                        "eps": info['eps'],
                        "total": info['total'],
                        "link": link,
                        "site": "anich",
                    }
                    self.download_queue.put(anime_info)

                    ep_count = len(info['eps'])
                    total_count = info['total']
                    status = f"有{ep_count}集" if ep_count < total_count else f"{total_count}集"
                    self.root.after(0, lambda n=info['name'], t=status, l=link:
                        self.tree.insert("", tk.END, values=(n, t, "待下载", "0%", l)))
                    success += 1
                else:
                    # 稀饭动漫解析
                    match = re.search(r'/watch/(\d+)/', link) or re.search(r'/bangumi/(\d+)', link)
                    if not match:
                        continue

                    vod_id = match.group(1)

                    if vod_id in self.added_anime:
                        skipped += 1
                        self.update_status(f"[{i+1}/{total}] 跳过重复: {vod_id}")
                        continue

                    resp = self.session.get(f"{SITE}/bangumi/{vod_id}.html", verify=False, timeout=30)
                    resp.encoding = "utf-8"

                    title_match = re.search(r'<title>(.*?)</title>', resp.text)
                    if title_match:
                        full_title = title_match.group(1).strip()
                        anime_name = re.split(r'_\w+', full_title)[0].strip()
                        anime_name = re.split(r'\s*[-|]\s*稀饭动漫', anime_name)[0].strip()
                    else:
                        anime_name = f"动漫_{vod_id}"

                    all_eps = re.findall(r'/watch/(\d+)/(\d+)/(\d+)\.html', resp.text)
                    if not all_eps:
                        continue

                    first_line_eps = [(v, s, n) for v, s, n in all_eps if s == "1"]
                    if not first_line_eps:
                        min_line = min(int(s) for _, s, _ in all_eps)
                        first_line_eps = [(v, s, n) for v, s, n in all_eps if int(s) == min_line]

                    eps = sorted(set(first_line_eps), key=lambda x: int(x[2]))

                    anime_info = {"id": vod_id, "name": anime_name, "eps": eps, "total": len(eps), "link": link, "site": "xifan"}
                    self.download_queue.put(anime_info)
                    self.added_anime.add(vod_id)

                    self.root.after(0, lambda n=anime_name, t=len(eps), l=link:
                        self.tree.insert("", tk.END, values=(n, t, "待下载", "0%", l)))
                    success += 1
                
            except Exception as e:
                pass
            
            time.sleep(0.5)
        
        self.update_status(f"✅ 解析完成！成功 {success}/{total} 部动漫，跳过 {skipped} 个重复")
        self.root.after(0, self._update_stats)
    
    def start_download(self):
        if self._downloading:
            return
        
        if self.download_queue.empty():
            messagebox.showinfo("提示", "队列为空，请先添加动漫链接")
            return
        
        self._downloading = True
        self._cancel = False
        self.stats = {"success": 0, "failed": 0, "downloaded_eps": 0, "failed_eps": 0}
        self._current_speed = 0  # 当前下载速度
        self._total_downloaded = 0  # 总下载量
        
        threading.Thread(target=self._download_worker, daemon=True).start()
        threading.Thread(target=self._speed_monitor, daemon=True).start()  # 速度监控线程
    
    def pause_download(self):
        self._cancel = True
    
    def stop_download(self):
        self._cancel = True
        self._downloading = False
    
    def _download_worker(self):
        out_dir = self.out_dir.get()
        
        while not self.download_queue.empty() and not self._cancel:
            try:
                anime = self.download_queue.get(timeout=1)
            except:
                break
            
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
            site = anime.get("site", "xifan")
            
            self.root.after(0, lambda i=current_item: self.tree.set(i, "状态", "检测中"))
            
            anime_dir = os.path.join(out_dir, safe_name)
            
            # 检测已存在的集数
            existing_eps = set()
            if os.path.exists(anime_dir):
                for f in os.listdir(anime_dir):
                    if f.endswith('.mp4'):
                        # 提取集数：第01集.mp4 -> 01
                        ep_match = re.search(r'第(\d+)集', f)
                        if ep_match:
                            existing_eps.add(ep_match.group(1))
            
            # 筛选出需要下载的集数
            eps_to_download = []
            if site == "anich":
                for ep in eps:
                    ep_num = str(ep['sort']).zfill(2)
                    if ep_num not in existing_eps:
                        eps_to_download.append(ep)
            else:
                for v, s, n in eps:
                    ep_num = n.zfill(2)
                    if ep_num not in existing_eps:
                        eps_to_download.append((v, s, n))
            
            # 如果所有集数都已存在，跳过
            if not eps_to_download:
                self.root.after(0, lambda i=current_item: self.tree.set(i, "状态", "✅ 已存在"))
                self.root.after(0, lambda i=current_item: self.tree.set(i, "进度", f"{len(eps)}/{len(eps)}"))
                self.stats["success"] += 1
                self.stats["downloaded_eps"] += len(eps)
                self.root.after(0, self._update_stats)
                continue
            
            # 显示需要补下载的集数
            missing_count = len(eps_to_download)
            self.root.after(0, lambda i=current_item, m=missing_count, t=len(eps): 
                self.tree.set(i, "状态", f"补{m}集"))
            
            os.makedirs(anime_dir, exist_ok=True)
            
            anime_success = len(existing_eps)  # 已存在的集数
            anime_failed = 0
            
            for ep_idx, ep_data in enumerate(eps_to_download):
                if self._cancel:
                    break
                
                if site == "anich":
                    # AniCh下载（MP4直链或m3u8）
                    ep_sort = ep_data['sort']
                    ep_num = str(ep_sort).zfill(2)
                    ep_file = os.path.join(anime_dir, f"第{ep_num}集.mp4")

                    progress = f"{anime_success+ep_idx+1}/{len(eps)}"
                    self.root.after(0, lambda i=current_item, p=progress: self.tree.set(i, "进度", p))

                    try:
                        m3u8_url = self._get_anich_m3u8(anime["id"], ep_sort)
                        if not m3u8_url:
                            anime_failed += 1
                            self.stats["failed_eps"] += 1
                            continue

                        if '.mp4' in m3u8_url and '.m3u8' not in m3u8_url:
                            # MP4直链：用requests下载
                            r = self.session.get(m3u8_url, stream=True, verify=False, timeout=1800)
                            if r.status_code == 200:
                                file_size = 0
                                last_time = time.time()
                                last_size = 0
                                with open(ep_file, 'wb') as f:
                                    for chunk in r.iter_content(8192):
                                        if self._cancel:
                                            break
                                        f.write(chunk)
                                        file_size += len(chunk)
                                        self._total_downloaded += len(chunk)
                                        current_time = time.time()
                                        if current_time - last_time >= 0.5:
                                            speed = (file_size - last_size) / (current_time - last_time)
                                            self._current_speed = speed
                                            last_time = current_time
                                            last_size = file_size
                            else:
                                raise Exception(f"HTTP {r.status_code}")
                        else:
                            # m3u8：用ffmpeg下载
                            cmd = [
                                "ffmpeg", "-y",
                                "-headers", f"User-Agent: Mozilla/5.0\r\nReferer: https://anich.emmmm.eu.org\r\n",
                                "-i", m3u8_url,
                                "-c", "copy",
                                "-movflags", "+faststart",
                                ep_file
                            ]
                            self._current_process = subprocess.Popen(
                                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                            )
                            self._current_process.wait()
                            self._current_process = None

                        if os.path.exists(ep_file) and os.path.getsize(ep_file) > 1024*1024:
                            anime_success += 1
                            self.stats["downloaded_eps"] += 1
                        else:
                            if os.path.exists(ep_file):
                                os.remove(ep_file)
                            anime_failed += 1
                            self.stats["failed_eps"] += 1
                    except Exception as e:
                        anime_failed += 1
                        self.stats["failed_eps"] += 1
                else:
                    # 稀饭动漫下载
                    v, s, n = ep_data
                    ep_num = n.zfill(2)
                    ep_file = os.path.join(anime_dir, f"第{ep_num}集.mp4")

                    progress = f"{anime_success+ep_idx+1}/{len(eps)}"
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
                            file_size = 0
                            last_time = time.time()
                            last_size = 0

                            with open(ep_file, 'wb') as f:
                                for chunk in r2.iter_content(8192):
                                    if self._cancel:
                                        break
                                    f.write(chunk)
                                    file_size += len(chunk)
                                    self._total_downloaded += len(chunk)

                                    current_time = time.time()
                                    if current_time - last_time >= 0.5:
                                        speed = (file_size - last_size) / (current_time - last_time)
                                        self._current_speed = speed
                                        last_time = current_time
                                        last_size = file_size

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

                    except:
                        anime_failed += 1
                        self.stats["failed_eps"] += 1

                    time.sleep(0.3)

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
        self._current_speed = 0
        self.update_status("✅ 下载完成！等待新任务...")
    
    def _speed_monitor(self):
        """速度监控线程，定期更新UI"""
        last_downloaded = 0
        while self._downloading:
            time.sleep(1)
            # 计算平均速度
            speed = self._total_downloaded - last_downloaded
            last_downloaded = self._total_downloaded
            self._current_speed = speed
            
            # 更新UI
            self.root.after(0, self._update_speed_display)
    
    def _update_speed_display(self):
        """更新速度显示"""
        if self._current_speed > 1024*1024:
            speed_str = f"{self._current_speed/1024/1024:.1f} MB/s"
        elif self._current_speed > 1024:
            speed_str = f"{self._current_speed/1024:.1f} KB/s"
        else:
            speed_str = "0 B/s"
        self.lbl_speed.config(text=speed_str)
        
        # 更新总下载量
        if self._total_downloaded > 1024*1024*1024:
            total_str = f"{self._total_downloaded/1024/1024/1024:.2f} GB"
        elif self._total_downloaded > 1024*1024:
            total_str = f"{self._total_downloaded/1024/1024:.1f} MB"
        else:
            total_str = f"{self._total_downloaded/1024:.1f} KB"
        self.lbl_stats.config(text=f"已下载: {self.stats['success']} | 失败: {self.stats['failed']} | 总量: {total_str}")
    
    def _update_stats(self):
        self._update_speed_display()
        self.lbl_download_count.config(text=f"⬜ 下载中 {'1' if self._downloading else '0'}")
        self.lbl_wait_count.config(text=f"⏳ 等待中 {self.download_queue.qsize()}")
        self.save_download_list()  # 每次更新状态时保存列表
    
    def update_status(self, text):
        self.root.after(0, lambda: self.lbl_status.config(text=text))
    
    def check_queue(self):
        # 更新队列状态显示
        self.lbl_wait_count.config(text=f"⏳ 等待中 {self.download_queue.qsize()}")
        self.root.after(1000, self.check_queue)
    
    def save_download_list(self):
        """保存下载列表到文件"""
        try:
            data = {
                "anime_list": [],
                "added_anime": list(self.added_anime),
                "output_dir": self.out_dir.get()
            }
            
            # 从Treeview获取当前列表
            for item in self.tree.get_children():
                values = self.tree.item(item, "values")
                if len(values) >= 5:
                    data["anime_list"].append({
                        "name": values[0],
                        "eps": values[1],
                        "status": values[2],
                        "progress": values[3],
                        "link": values[4]  # 保存原始链接
                    })
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存列表失败: {e}")
    
    def load_download_list(self):
        """从文件加载下载列表"""
        if not os.path.exists(self.data_file):
            return
        
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 恢复输出目录
            if "output_dir" in data and data["output_dir"]:
                self.out_dir.set(data["output_dir"])
            
            # 恢复已添加的动漫ID
            if "added_anime" in data:
                self.added_anime = set(data["added_anime"])
            
            # 恢复列表
            if "anime_list" in data:
                for anime in data["anime_list"]:
                    name = anime.get("name", "")
                    eps = anime.get("eps", "")
                    status = anime.get("status", "待下载")
                    progress = anime.get("progress", "0%")
                    link = anime.get("link", "")
                    
                    # 只恢复未完成的项目
                    if status not in ["✅ 完成", "✅ 已存在"]:
                        self.tree.insert("", tk.END, values=(name, eps, "待下载", progress, link))
                        
                        # 如果有链接，重新解析并加入队列
                        if link:
                            threading.Thread(target=self._parse_links, args=([link],), daemon=True).start()
            
            self.update_status(f"📂 已加载历史列表（{len(data.get('anime_list', []))} 条记录）")
        except Exception as e:
            print(f"加载列表失败: {e}")
    
    def on_closing(self):
        """窗口关闭时保存列表"""
        self.save_download_list()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = XifanDownloader(root)
    root.mainloop()
