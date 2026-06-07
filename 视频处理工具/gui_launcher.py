"""
VideoCraft GUI Launcher — 启动Web版视频处理工具的桌面客户端
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading, subprocess, time, os, sys, webbrowser

# ─── 配色 ───
C = {
    "bg": "#0a0e14",
    "bg2": "#131920",
    "bg3": "#1a2332",
    "card": "#1a2332",
    "border": "#2a3545",
    "accent": "#4c9aff",
    "accent_glow": "#1a3a5c",
    "coral": "#ff6b6b",
    "green": "#4ecdc4",
    "amber": "#f0a500",
    "text": "#e8edf3",
    "text2": "#7a8a9e",
    "text3": "#4a5568",
}

class VideoCraftGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("VideoCraft — 视频处理工具")
        self.root.configure(bg=C["bg"])
        self.root.resizable(False, False)

        # 窗口居中
        w, h = 480, 520
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self.server_running = False
        self.server_thread = None
        self.server_process = None
        self.port = 8765

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ─── Header ───
        header = tk.Frame(self.root, bg=C["bg"])
        header.pack(fill=tk.X, padx=20, pady=(20, 0))

        # Logo
        logo_frame = tk.Frame(header, bg=C["bg"])
        logo_frame.pack(fill=tk.X)

        icon_lbl = tk.Label(logo_frame, text="🎬", font=("", 36), bg=C["bg"], fg=C["accent"])
        icon_lbl.pack(side=tk.LEFT, padx=(0, 12))

        title_frame = tk.Frame(logo_frame, bg=C["bg"])
        title_frame.pack(side=tk.LEFT)

        tk.Label(title_frame, text="VideoCraft", font=("Microsoft YaHei UI", 20, "bold"),
                 bg=C["bg"], fg=C["text"]).pack(anchor="w")
        tk.Label(title_frame, text="视频处理工具 · Web版", font=("Microsoft YaHei UI", 10),
                 bg=C["bg"], fg=C["text3"]).pack(anchor="w")

        # ─── Divider ───
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill=tk.X, padx=20, pady=16)

        # ─── Server Status Card ───
        card1 = tk.Frame(self.root, bg=C["card"], highlightbackground=C["border"],
                         highlightthickness=1, padx=16, pady=14)
        card1.pack(fill=tk.X, padx=20, pady=(0, 12))

        status_header = tk.Frame(card1, bg=C["card"])
        status_header.pack(fill=tk.X)

        self.status_icon = tk.Label(status_header, text="⏸", font=("", 16), bg=C["card"], fg=C["text3"])
        self.status_icon.pack(side=tk.LEFT)

        status_text = tk.Frame(status_header, bg=C["card"])
        status_text.pack(side=tk.LEFT, padx=10)

        self.status_title = tk.Label(status_text, text="服务未启动", font=("Microsoft YaHei UI", 12, "bold"),
                                      bg=C["card"], fg=C["text"])
        self.status_title.pack(anchor="w")

        self.status_desc = tk.Label(status_text, text="点击下方按钮启动服务",
                                     font=("Microsoft YaHei UI", 9), bg=C["card"], fg=C["text3"])
        self.status_desc.pack(anchor="w")

        # URL
        self.url_frame = tk.Frame(card1, bg=C["card"])
        self.url_frame.pack(fill=tk.X, pady=(10, 0))

        self.url_lbl = tk.Label(self.url_frame, text=f"http://localhost:{self.port}",
                                 font=("Consolas", 11), bg=C["bg2"], fg=C["accent"],
                                 padx=10, pady=6, cursor="hand2")
        self.url_lbl.pack(fill=tk.X)
        self.url_lbl.bind("<Button-1>", lambda e: self._open_browser())
        self.url_frame.pack_forget()  # Hide initially

        # ─── Progress ───
        self.progress_frame = tk.Frame(card1, bg=C["card"])
        self.progress_frame.pack(fill=tk.X, pady=(8, 0))
        self.progress_frame.pack_forget()

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Horizontal.TProgressbar",
                        background=C["accent"], troughcolor=C["bg2"],
                        borderwidth=0, lightcolor=C["accent"], darkcolor=C["accent"])

        self.progress = ttk.Progressbar(self.progress_frame, style="Custom.Horizontal.TProgressbar",
                                         mode="indeterminate", length=200)
        self.progress.pack(fill=tk.X)

        # ─── Buttons ───
        btn_frame = tk.Frame(self.root, bg=C["bg"])
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 12))

        self.btn_start = tk.Button(btn_frame, text="🚀  启动服务", font=("Microsoft YaHei UI", 12, "bold"),
                                    bg=C["accent"], fg="#fff", relief="flat", cursor="hand2",
                                    padx=20, pady=10, command=self._toggle_server)
        self.btn_start.pack(fill=tk.X)

        self.btn_browser = tk.Button(btn_frame, text="🌐  打开浏览器", font=("Microsoft YaHei UI", 10),
                                      bg=C["bg3"], fg=C["text2"], relief="flat", cursor="hand2",
                                      padx=16, pady=8, command=self._open_browser, state=tk.DISABLED)
        self.btn_browser.pack(fill=tk.X, pady=(8, 0))

        # ─── Features ───
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill=tk.X, padx=20, pady=8)

        features_frame = tk.Frame(self.root, bg=C["bg"])
        features_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 16))

        tk.Label(features_frame, text="功能模块", font=("Microsoft YaHei UI", 10, "bold"),
                 bg=C["bg"], fg=C["text2"]).pack(anchor="w", pady=(0, 8))

        features = [
            ("🖼️", "套框", "将视频嵌入模板指定区域"),
            ("📐", "画中画", "多视频叠加到模板背景"),
            ("📱", "横转竖", "16:9 → 9:16 竖屏旋转"),
            ("🔄", "格式转换", "H264/H265/VP9 编码转换"),
            ("💻", "命令预览", "FFmpeg 命令实时预览"),
        ]

        for icon, title, desc in features:
            row = tk.Frame(features_frame, bg=C["bg"])
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=icon, font=("", 14), bg=C["bg"], fg=C["accent"], width=3).pack(side=tk.LEFT)
            tk.Label(row, text=title, font=("Microsoft YaHei UI", 10, "bold"),
                     bg=C["bg"], fg=C["text"], width=8, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=desc, font=("Microsoft YaHei UI", 9),
                     bg=C["bg"], fg=C["text3"]).pack(side=tk.LEFT, padx=(4, 0))

        # ─── Footer ───
        footer = tk.Frame(self.root, bg=C["bg2"], padx=16, pady=8)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(footer, text="RTX 3070 · NVENC Ready · Flask + FFmpeg",
                 font=("Consolas", 9), bg=C["bg2"], fg=C["text3"]).pack()

    def _toggle_server(self):
        if self.server_running:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        self.btn_start.config(text="⏳  启动中...", bg=C["amber"], state=tk.DISABLED)
        self.progress_frame.pack(fill=tk.X, pady=(8, 0))
        self.progress.start(15)
        self.status_title.config(text="正在启动...")
        self.status_desc.config(text="加载 Flask 服务中，请稍候")

        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

        # Check status after delay
        self.root.after(2000, self._check_server)

    def _run_server(self):
        """Run Flask server in background thread"""
        app_dir = os.path.dirname(os.path.abspath(__file__))
        web_dir = os.path.join(app_dir, "web版")

        if not os.path.exists(os.path.join(web_dir, "app.py")):
            # Try current directory
            web_dir = app_dir

        try:
            # Import and run Flask app
            sys.path.insert(0, web_dir)
            os.chdir(web_dir)

            from app import app
            app.run(host="0.0.0.0", port=self.port, debug=False, threaded=True)
        except Exception as e:
            print(f"Server error: {e}")

    def _check_server(self):
        """Check if server is running"""
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"http://localhost:{self.port}", timeout=2)
            if resp.status == 200:
                self._on_server_started()
                return
        except:
            pass

        # Still starting, check again
        if self.btn_start["state"] == tk.DISABLED:
            self.root.after(1000, self._check_server)

    def _on_server_started(self):
        self.server_running = True
        self.progress.stop()
        self.progress_frame.pack_forget()

        self.btn_start.config(text="⏹  停止服务", bg=C["coral"], state=tk.NORMAL)
        self.btn_browser.config(state=tk.NORMAL)

        self.status_icon.config(text="✅", fg=C["green"])
        self.status_title.config(text="服务运行中", fg=C["green"])
        self.status_desc.config(text=f"端口 {self.port} · 可通过浏览器访问")

        self.url_frame.pack(fill=tk.X, pady=(10, 0))

        # Auto open browser
        self.root.after(500, self._open_browser)

    def _stop_server(self):
        self.server_running = False
        # Kill the server process
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{self.port}/shutdown", timeout=1)
        except:
            pass

        # Force kill via port
        try:
            if os.name == "nt":
                subprocess.run(f"netstat -ano | findstr :{self.port}", shell=True,
                              capture_output=True, timeout=5)
                # Get PID and kill
                result = subprocess.run(
                    ["powershell", "-Command",
                     f"(Get-NetTCPConnection -LocalPort {self.port} -ErrorAction SilentlyContinue).OwningProcess"],
                    capture_output=True, text=True, timeout=5)
                if result.stdout.strip():
                    for pid in result.stdout.strip().split("\n"):
                        pid = pid.strip()
                        if pid and pid != "0":
                            subprocess.run(["taskkill", "/F", "/PID", pid],
                                          capture_output=True, timeout=5)
        except:
            pass

        self.btn_start.config(text="🚀  启动服务", bg=C["accent"], state=tk.NORMAL)
        self.btn_browser.config(state=tk.DISABLED)

        self.status_icon.config(text="⏸", fg=C["text3"])
        self.status_title.config(text="服务已停止", fg=C["text"])
        self.status_desc.config(text="点击上方按钮重新启动")

        self.url_frame.pack_forget()

    def _open_browser(self):
        webbrowser.open(f"http://localhost:{self.port}")

    def _on_close(self):
        if self.server_running:
            if messagebox.askyesno("退出", "服务正在运行中，是否停止并退出？"):
                self._stop_server()
                self.root.after(500, self.root.destroy)
            return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = VideoCraftGUI()
    app.run()
