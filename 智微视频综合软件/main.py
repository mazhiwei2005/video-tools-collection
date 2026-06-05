#!/usr/bin/env python3
"""智微视频综合软件 v2.0 - 动态高级版 UI"""
import os, sys, math, random, time, colorsys
import tkinter as tk
from tkinter import font as tkfont

# ── 新配色系统 ──
C = {
    "primary":       "#2F7BFF",
    "primary_dark":  "#1A5FCC",
    "primary_light": "#E8F0FF",
    "primary_glow":  "#5A9BFF",
    "bg":            "#F0F2F5",
    "bg_dark":       "#E4E7EB",
    "sidebar":       "#FAFBFC",
    "card":          "#FFFFFF",
    "card_hover":    "#F8FAFF",
    "text":          "#1A1A2E",
    "text2":         "#8B8FA3",
    "text3":         "#B0B4C0",
    "border":        "#E8EBF0",
    "border_glow":   "#2F7BFF40",
    "success":       "#00C48C",
    "warning":       "#FF9F43",
    "danger":        "#FF4757",
    "glow":          "#2F7BFF",
    "particle":      "#C8D8FF",
    "gradient_start":"#2F7BFF",
    "gradient_end":  "#6C5CE7",
}

# ── 粒子系统 ──
class ParticleSystem:
    """背景浮动粒子 + 光斑"""
    def __init__(self, canvas, width, height):
        self.canvas = canvas
        self.w, self.h = width, height
        self.particles = []
        self.lights = []
        self._init_particles()
        self._init_lights()

    def _init_particles(self):
        for _ in range(35):
            self.particles.append({
                "x": random.uniform(0, self.w),
                "y": random.uniform(0, self.h),
                "r": random.uniform(1.5, 3.5),
                "dx": random.uniform(-0.3, 0.3),
                "dy": random.uniform(-0.2, 0.2),
                "alpha": random.uniform(0.15, 0.4),
                "phase": random.uniform(0, math.pi * 2),
            })

    def _init_lights(self):
        for _ in range(3):
            self.lights.append({
                "x": random.uniform(100, self.w - 100),
                "y": random.uniform(100, self.h - 100),
                "r": random.uniform(120, 200),
                "dx": random.uniform(-0.4, 0.4),
                "dy": random.uniform(-0.3, 0.3),
                "alpha": random.uniform(0.03, 0.06),
            })

    def update(self):
        self.canvas.delete("particle")
        t = time.time()
        # 光斑
        for l in self.lights:
            l["x"] += l["dx"]
            l["y"] += l["dy"]
            if l["x"] < -l["r"] or l["x"] > self.w + l["r"]: l["dx"] *= -1
            if l["y"] < -l["r"] or l["y"] > self.h + l["r"]: l["dy"] *= -1
            a = max(0, min(255, int(l["alpha"] * 255 * (1 + 0.3 * math.sin(t * 0.5)))))
            color = f"#{a:02x}{a+20:02x}ff"
            try:
                self.canvas.create_oval(
                    l["x"]-l["r"], l["y"]-l["r"], l["x"]+l["r"], l["y"]+l["r"],
                    fill="", outline=color, width=1, tags="particle")
            except: pass
        # 粒子
        for p in self.particles:
            p["x"] += p["dx"]
            p["y"] += p["dy"] + math.sin(t * 0.8 + p["phase"]) * 0.15
            if p["x"] < -10: p["x"] = self.w + 10
            if p["x"] > self.w + 10: p["x"] = -10
            if p["y"] < -10: p["y"] = self.h + 10
            if p["y"] > self.h + 10: p["y"] = -10
            a = int(p["alpha"] * 255 * (0.7 + 0.3 * math.sin(t * 1.2 + p["phase"])))
            a = max(0, min(255, a))
            color = f"#{0x2F:02x}{0x7B:02x}{min(255, 0xFF+a//3):02x}"
            try:
                self.canvas.create_oval(
                    p["x"]-p["r"], p["y"]-p["r"], p["x"]+p["r"], p["y"]+p["r"],
                    fill=color, outline="", tags="particle")
            except: pass


# ── 发光按钮 ──
class GlowButton(tk.Canvas):
    """带呼吸光 + 水波纹 + 放大效果的按钮"""
    def __init__(self, parent, text="", command=None, style="primary",
                 width=140, height=44, **kw):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bg=parent["bg"], **kw)
        self.cmd = command
        self.text = text
        self.w, self.h = width, height
        self._hover = False
        self._glow_phase = 0
        self._ripple = []
        self._press = False

        styles = {
            "primary":  (C["primary"], C["primary_dark"], "#FFF", C["primary_glow"]),
            "success":  (C["success"], "#00A87A", "#FFF", "#33D4A0"),
            "danger":   (C["danger"],  "#E03040", "#FFF", "#FF6B7A"),
            "secondary":("#E8ECF0", "#D8DCE0", C["text"], "#F0F4F8"),
            "ghost":    ("", "", C["primary"], C["primary_light"]),
        }
        self.bg_n, self.bg_h, self.fg, self.glow = styles.get(style, styles["primary"])

        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self):
        self.delete("all")
        w, h = self.w, self.h
        r = 12  # 圆角

        # 发光效果
        if self._hover and self.glow:
            for i in range(3):
                a = max(0, min(255, int(30 - i*10 + 10*math.sin(self._glow_phase))))
                gc = self.glow
                try:
                    self.create_oval(-i*4, -i*3, w+i*4, h+i*3,
                                     outline=gc, width=1, fill="")
                except: pass

        # 主体
        bg = self.bg_h if self._press else (self.bg_n if not self._hover else self.bg_n)
        if self._hover and bg:
            # 微亮
            bg = self._lighten(bg, 15) if not self._press else bg
        if bg:
            self._round_rect(0, 0, w, h, r, fill=bg, outline="")

        # 涟漪
        for rx, ry, rr, ra in self._ripple:
            if ra > 0:
                try:
                    self.create_oval(rx-rr, ry-rr, rx+rr, ry+rr,
                                     outline=C["primary_glow"], width=1, fill="")
                except: pass

        # 文字
        offset = 1 if self._press else 0
        self.create_text(w//2, h//2 + offset, text=self.text,
                         fill=self.fg, font=("微软雅黑", 10, "bold"))

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
               x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def _lighten(self, hex_color, amount):
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            r = min(255, r + amount)
            g = min(255, g + amount)
            b = min(255, b + amount)
            return f"#{r:02x}{g:02x}{b:02x}"
        except: return hex_color

    def _on_enter(self, e):
        self._hover = True
        self._glow_loop()
        self.configure(cursor="hand2")

    def _on_leave(self, e):
        self._hover = False
        self._draw()

    def _on_press(self, e):
        self._press = True
        self._ripple.append([e.x, e.y, 0, 255])
        self._ripple_anim()
        self._draw()

    def _on_release(self, e):
        self._press = False
        self._draw()
        if self.cmd: self.cmd()

    def _glow_loop(self):
        if not self._hover: return
        self._glow_phase += 0.15
        self._draw()
        self.after(50, self._glow_loop)

    def _ripple_anim(self):
        new = []
        for rx, ry, rr, ra in self._ripple:
            rr += 3
            ra -= 8
            if ra > 0 and rr < max(self.w, self.h):
                new.append([rx, ry, rr, ra])
        self._ripple = new
        self._draw()
        if self._ripple:
            self.after(30, self._ripple_anim)


# ── 流光进度条 ──
class GlowProgress(tk.Canvas):
    """带流光动画的圆角进度条"""
    def __init__(self, parent, width=300, height=22, **kw):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bg=parent["bg"], **kw)
        self.w, self.h = width, height
        self._value = 0
        self._phase = 0
        self._animating = False
        self._draw()

    def set_value(self, v):
        self._value = max(0, min(100, v))
        if self._value > 0 and not self._animating:
            self._animating = True
            self._animate()
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.w, self.h
        r = h // 2

        # 背景轨道
        self._round_rect(0, 0, w, h, r, fill="#E8ECF0", outline="")

        # 填充
        if self._value > 0:
            fw = max(h, int(w * self._value / 100))
            self._round_rect(0, 0, fw, h, r, fill=C["primary"], outline="")

            # 流光效果
            if self._animating:
                gx = int(self._phase * w) % fw
                for i in range(20):
                    px = gx - i * 3
                    if 0 < px < fw:
                        a = max(0, min(255, 180 - i * 9))
                        try:
                            self.create_line(px, 4, px, h-4,
                                             fill=f"#{0xFF:02x}{0xFF:02x}{0xFF:02x}", width=1)
                        except: pass

            # 百分比文字
            self.create_text(w//2, h//2, text=f"{self._value:.0f}%",
                             fill="#FFF", font=("Consolas", 9, "bold"))

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
               x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def _animate(self):
        if self._value <= 0:
            self._animating = False
            return
        self._phase += 0.02
        self._draw()
        self.after(50, self._animate)


# ── 主应用 ──
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("智微视频综合软件 v2.0")
        self.root.geometry("1280x780")
        self.root.minsize(1050, 650)
        self.root.configure(bg=C["bg"])

        self.current_page = None
        self.pages = {}
        self.nav_buttons = {}
        self._nav_animate_idx = 0

        self._setup_ui()
        self._init_pages()
        self._startup_animation()

    def _setup_ui(self):
        # 粒子背景Canvas
        self.bg_canvas = tk.Canvas(self.root, bg=C["bg"], highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.root.update_idletasks()
        self.particles = ParticleSystem(self.bg_canvas, self.root.winfo_width(), self.root.winfo_height())
        self._particle_loop()

        # 主容器（在粒子之上）
        self.container = tk.Frame(self.root, bg=C["bg"])
        self.container.place(x=0, y=0, relwidth=1, relheight=1)

        # ── 左侧导航栏（毛玻璃风格） ──
        self.sidebar = tk.Frame(self.container, bg=C["sidebar"], width=220)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # 侧边栏光条指示器
        self._indicator = tk.Frame(self.sidebar, bg=C["primary"], width=3, height=40)
        self._indicator.place(x=0, y=90)

        # Logo
        logo_f = tk.Frame(self.sidebar, bg=C["sidebar"], height=70)
        logo_f.pack(fill=tk.X, pady=(18, 20))
        logo_f.pack_propagate(False)
        tk.Label(logo_f, text="🎬 智微视频综合软件",
                 font=("微软雅黑", 14, "bold"),
                 bg=C["sidebar"], fg=C["primary"]).pack(expand=True)
        tk.Label(logo_f, text="v2.0 Dynamic Edition",
                 font=("微软雅黑", 8), bg=C["sidebar"], fg=C["text3"]).pack()

        # 导航项
        nav = [
            ("📥", "稀饭下载",    "downloader"),
            ("🎬", "视频处理",    "video_processor"),
            ("🖼️", "视频叠加",    "video_overlay"),
            ("📤", "B站上传",     "bili_uploader"),
            ("🔍", "动漫查询",    "anime_search"),
        ]

        self._nav_frames = []
        for icon, text, pid in nav:
            f = tk.Frame(self.sidebar, bg=C["sidebar"], cursor="hand2", height=48)
            f.pack(fill=tk.X, padx=12, pady=2)
            f.pack_propagate(False)

            lbl = tk.Label(f, text=f"  {icon}  {text}",
                           font=("微软雅黑", 11), bg=C["sidebar"],
                           fg=C["text"], anchor="w", padx=14)
            lbl.pack(fill=tk.BOTH, expand=True)

            for w in (f, lbl):
                w.bind("<Enter>", lambda e, fr=f, p=pid: self._nav_hover(fr, p, True))
                w.bind("<Leave>", lambda e, fr=f, p=pid: self._nav_hover(fr, p, False))
                w.bind("<ButtonPress-1>", lambda e, p=pid: self.switch_page(p))

            self.nav_buttons[pid] = f
            self._nav_frames.append((f, pid))

        # 底部
        tk.Label(self.sidebar, text="© 2026 智微软件",
                 font=("微软雅黑", 8), bg=C["sidebar"], fg=C["text3"]).pack(side=tk.BOTTOM, pady=12)

        # ── 右侧内容区 ──
        self.content = tk.Frame(self.container, bg=C["bg"])
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _particle_loop(self):
        self.particles.w = self.root.winfo_width()
        self.particles.h = self.root.winfo_height()
        self.particles.update()
        self.root.after(60, self._particle_loop)

    def _nav_hover(self, frame, pid, entering):
        if self.current_page == pid: return
        if entering:
            frame.configure(bg=C["primary_light"])
            for child in frame.winfo_children():
                child.configure(bg=C["primary_light"])
        else:
            frame.configure(bg=C["sidebar"])
            for child in frame.winfo_children():
                child.configure(bg=C["sidebar"])

    def _startup_animation(self):
        """启动动画：侧边栏菜单依次滑入"""
        self.sidebar.place(x=-220, y=0, relheight=1)
        self._slide_sidebar(0)

    def _slide_sidebar(self, step):
        if step <= 22:
            x = -220 + int(220 * (step / 22))
            self.sidebar.place(x=x, y=0, relheight=1)
            self.root.after(15, lambda: self._slide_sidebar(step + 1))
        else:
            self.sidebar.place_forget()
            self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
            self.switch_page("downloader")

    def _init_pages(self):
        page_map = {
            "downloader":     ("pages.downloader",     "DownloaderPage"),
            "video_processor":("pages.video_processor", "VideoProcessorPage"),
            "video_overlay":  ("pages.video_overlay",   "VideoOverlayPage"),
            "bili_uploader":  ("pages.bili_uploader",   "BiliUploaderPage"),
            "anime_search":   ("pages.anime_search",    "AnimeSearchPage"),
        }
        for pid, (mod_path, cls_name) in page_map.items():
            try:
                import importlib
                mod = importlib.import_module(mod_path)
                cls = getattr(mod, cls_name)
                page = cls(self.content, C)
                page.frame.place(x=0, y=0, relwidth=1, relheight=1)
                page.frame.lower()
                self.pages[pid] = page
            except Exception as e:
                f = tk.Frame(self.content, bg=C["bg"])
                tk.Label(f, text=f"⚠️ {pid} 加载失败: {e}",
                         font=("微软雅黑", 12), bg=C["bg"], fg=C["danger"]).pack(expand=True)
                self.pages[pid] = type('P', (), {'frame': f, 'show': lambda s: None, 'hide': lambda s: None})()

    def switch_page(self, pid):
        if pid == self.current_page: return

        # 隐藏当前
        if self.current_page and self.current_page in self.pages:
            old = self.pages[self.current_page]
            old.frame.lower()

        # 更新导航高亮
        for nid, btn in self.nav_buttons.items():
            if nid == pid:
                btn.configure(bg=C["primary_light"])
                for child in btn.winfo_children():
                    child.configure(bg=C["primary_light"], fg=C["primary"])
            else:
                btn.configure(bg=C["sidebar"])
                for child in btn.winfo_children():
                    child.configure(bg=C["sidebar"], fg=C["text"])

        # 移动指示器
        if pid in self.nav_buttons:
            btn = self.nav_buttons[pid]
            self._animate_indicator(btn.winfo_y())

        # 显示新页面（带淡入）
        if pid in self.pages:
            self.pages[pid].frame.lift()
            self._fade_in(self.pages[pid].frame, 0)

        self.current_page = pid

    def _animate_indicator(self, target_y):
        """侧边栏蓝色指示器平滑移动"""
        cur = self._indicator.winfo_y()
        diff = target_y - cur
        if abs(diff) < 2:
            self._indicator.place(y=target_y)
            return
        step = diff * 0.25
        new_y = cur + step
        self._indicator.place(y=new_y)
        self.root.after(16, lambda: self._animate_indicator(target_y))

    def _fade_in(self, widget, step):
        """页面淡入动画"""
        if step >= 10:
            return
        # 通过不断raise来模拟淡入（tkinter限制）
        widget.lift()
        if step < 9:
            self.root.after(25, lambda: self._fade_in(widget, step + 1))


if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    root = tk.Tk()
    app = App(root)
    root.mainloop()
