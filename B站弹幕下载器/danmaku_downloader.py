#!/usr/bin/env python3
"""B站弹幕下载工具 - B站风格UI"""
import os
import re
import sys
import json
import time
import struct
import zlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import requests
import xml.etree.ElementTree as ET

# 颜色常量 - B站风格
COLORS = {
    "bg": "#F5F7FA",
    "sidebar": "#FFFFFF",
    "card": "#FFFFFF",
    "primary": "#00AEEC",
    "primary_dark": "#0091D4",
    "primary_light": "#E8F4FD",
    "text": "#333333",
    "text_secondary": "#999999",
    "border": "#E5E5E5",
    "success": "#67C23A",
    "warning": "#E6A23C",
    "danger": "#F56C6C",
    "hover": "#E8F4FD",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


class DanmakuDownloader:
    """B站弹幕下载器"""

    def __init__(self, root):
        self.root = root
        self.root.title("B站弹幕下载工具")
        self.root.geometry("700x550")
        self.root.configure(bg=COLORS["bg"])
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.setup_ui()

    def setup_ui(self):
        # 主容器
        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 标题
        tk.Label(main, text="📺 B站弹幕下载工具", font=("微软雅黑", 16, "bold"),
                 bg=COLORS["bg"], fg=COLORS["primary"]).pack(anchor="w", pady=(0, 15))

        # 输入卡片
        card1 = tk.Frame(main, bg=COLORS["card"], relief="flat", bd=1)
        card1.pack(fill=tk.X, pady=(0, 10))

        inner1 = tk.Frame(card1, bg=COLORS["card"])
        inner1.pack(fill=tk.X, padx=20, pady=15)

        tk.Label(inner1, text="🔗 视频链接：", font=("微软雅黑", 11),
                 bg=COLORS["card"]).pack(side=tk.LEFT)
        self.url_var = tk.StringVar()
        tk.Entry(inner1, textvariable=self.url_var, font=("微软雅黑", 11), width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(inner1, text="📋 粘贴", font=("微软雅黑", 9),
                  command=self.paste_url, bg=COLORS["border"], relief="flat").pack(side=tk.LEFT, padx=2)

        # 选项卡片
        card2 = tk.Frame(main, bg=COLORS["card"], relief="flat", bd=1)
        card2.pack(fill=tk.X, pady=(0, 10))

        inner2 = tk.Frame(card2, bg=COLORS["card"])
        inner2.pack(fill=tk.X, padx=20, pady=15)

        tk.Label(inner2, text="📁 保存目录：", font=("微软雅黑", 11),
                 bg=COLORS["card"]).pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        tk.Entry(inner2, textvariable=self.dir_var, font=("微软雅黑", 10), width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(inner2, text="浏览", font=("微软雅黑", 9),
                  command=self.choose_dir, bg=COLORS["border"], relief="flat").pack(side=tk.LEFT)

        # 格式选择
        fmt_frame = tk.Frame(main, bg=COLORS["card"], relief="flat", bd=1)
        fmt_frame.pack(fill=tk.X, pady=(0, 10))

        inner3 = tk.Frame(fmt_frame, bg=COLORS["card"])
        inner3.pack(fill=tk.X, padx=20, pady=15)

        tk.Label(inner3, text="📄 输出格式：", font=("微软雅黑", 11),
                 bg=COLORS["card"]).pack(side=tk.LEFT)
        self.fmt_var = tk.StringVar(value="xml")
        for fmt, label in [("xml", "XML（原始弹幕）"), ("ass", "ASS（字幕文件）"), ("srt", "SRT（字幕文件）"), ("txt", "TXT（纯文本）")]:
            tk.Radiobutton(inner3, text=label, variable=self.fmt_var, value=fmt,
                           font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT, padx=10)

        # 附加选项
        opt_frame = tk.Frame(main, bg=COLORS["card"], relief="flat", bd=1)
        opt_frame.pack(fill=tk.X, pady=(0, 10))

        inner_opt = tk.Frame(opt_frame, bg=COLORS["card"])
        inner_opt.pack(fill=tk.X, padx=20, pady=10)

        self.font_size_var = tk.IntVar(value=25)
        tk.Label(inner_opt, text="字号：", font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT)
        tk.Spinbox(inner_opt, from_=12, to=60, textvariable=self.font_size_var,
                   width=5, font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=(0, 15))

        self.duration_var = tk.DoubleVar(value=8.0)
        tk.Label(inner_opt, text="显示时长(秒)：", font=("微软雅黑", 10), bg=COLORS["card"]).pack(side=tk.LEFT)
        tk.Spinbox(inner_opt, from_=3.0, to=20.0, increment=0.5, textvariable=self.duration_var,
                   width=5, font=("微软雅黑", 10)).pack(side=tk.LEFT)

        # 按钮
        btn_frame = tk.Frame(main, bg=COLORS["bg"])
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_download = tk.Button(btn_frame, text="⬇️ 下载弹幕", font=("微软雅黑", 12, "bold"),
                                       bg=COLORS["primary"], fg="white", relief="flat",
                                       padx=30, pady=8, command=self.start_download)
        self.btn_download.pack(side=tk.LEFT)

        # 状态
        self.status_var = tk.StringVar(value="就绪 - 输入B站视频链接即可下载弹幕")
        tk.Label(main, textvariable=self.status_var, font=("微软雅黑", 10),
                 bg=COLORS["bg"], fg=COLORS["text_secondary"], anchor="w").pack(fill=tk.X, pady=(5, 0))

        # 进度条
        self.progress = ttk.Progressbar(main, mode="determinate", length=400)
        self.progress.pack(fill=tk.X, pady=(5, 0))

        # 弹幕预览
        preview_card = tk.Frame(main, bg=COLORS["card"], relief="flat", bd=1)
        preview_card.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        tk.Label(preview_card, text="📋 弹幕预览（前20条）", font=("微软雅黑", 10, "bold"),
                 bg=COLORS["card"], fg=COLORS["text"]).pack(anchor="w", padx=15, pady=(10, 5))

        self.preview_text = tk.Text(preview_card, height=6, font=("Consolas", 9),
                                     bg="#F8F9FA", relief="flat", state="disabled")
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

    def paste_url(self):
        try:
            clip = self.root.clipboard_get()
            self.url_var.set(clip)
        except:
            pass

    def choose_dir(self):
        d = filedialog.askdirectory(title="选择保存目录")
        if d:
            self.dir_var.set(d)

    def extract_bvid(self, url):
        """从URL提取BV号或AV号"""
        # BV号
        m = re.search(r'(BV[\w]{10})', url)
        if m:
            return m.group(1)
        # AV号
        m = re.search(r'(av\d+)', url, re.I)
        if m:
            return m.group(1)
        # 纯BV号
        if re.match(r'^BV[\w]{10}$', url.strip()):
            return url.strip()
        return None

    def get_video_info(self, bvid):
        """获取视频信息（标题、cid列表）"""
        if bvid.lower().startswith("av"):
            aid = bvid.lower().replace("av", "")
            api_url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
        else:
            api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"

        resp = self.session.get(api_url, timeout=15)
        data = resp.json()

        if data.get("code") != 0:
            raise Exception(f"API错误: {data.get('message', '未知错误')}")

        info = data["data"]
        title = info.get("title", "未知")
        pages = info.get("pages", [])
        cid_list = [(p["page"], p["part"], p["cid"]) for p in pages]

        return title, cid_list

    def get_danmaku_xml(self, cid):
        """获取弹幕XML"""
        url = f"https://comment.bilibili.com/{cid}.xml"
        resp = self.session.get(url, timeout=30)
        resp.encoding = "utf-8"
        return resp.text

    def parse_danmaku_xml(self, xml_text):
        """解析弹幕XML"""
        danmakus = []
        try:
            root = ET.fromstring(xml_text)
            for d in root.findall("d"):
                text = d.text or ""
                attrs = d.get("p", "")
                # attrs: time,mode,size,color,timestamp,pool,userhash,dmid
                parts = attrs.split(",")
                if len(parts) >= 4:
                    time_pos = float(parts[0])
                    mode = int(parts[1])
                    size = int(parts[2])
                    color = int(parts[3])
                    danmakus.append({
                        "text": text,
                        "time": time_pos,
                        "mode": mode,
                        "size": size,
                        "color": color,
                    })
        except Exception as e:
            raise Exception(f"解析弹幕失败: {e}")
        return danmakus

    def danmaku_to_ass(self, danmakus, video_width=1920, video_height=1080):
        """弹幕转ASS字幕"""
        font_size = self.font_size_var.get()
        duration = self.duration_var.get()

        ass_lines = []
        ass_lines.append("[Script Info]")
        ass_lines.append("Title: Bilibili Danmaku")
        ass_lines.append(f"PlayResX: {video_width}")
        ass_lines.append(f"PlayResY: {video_height}")
        ass_lines.append("ScriptType: v4.00+")
        ass_lines.append("")
        ass_lines.append("[V4+ Styles]")
        ass_lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
        ass_lines.append(f"Style: Danmaku,Microsoft YaHei,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,8,0,0,0,1")
        ass_lines.append("")
        ass_lines.append("[Events]")
        ass_lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

        import random
        for dm in danmakus:
            t = dm["time"]
            start_h = int(t // 3600)
            start_m = int((t % 3600) // 60)
            start_s = t % 60

            end_t = t + duration
            end_h = int(end_t // 3600)
            end_m = int((end_t % 3600) // 60)
            end_s = end_t % 60

            start_str = f"{start_h}:{start_m:02d}:{start_s:05.2f}"
            end_str = f"{end_h}:{end_m:02d}:{end_s:05.2f}"

            color = dm["color"]
            r = color & 0xFF
            g = (color >> 8) & 0xFF
            b = (color >> 16) & 0xFF
            ass_color = f"&H00{b:02X}{g:02X}{r:02X}"

            mode = dm["mode"]
            if mode == 4:  # 底部
                pos = f"\\an2\\pos({video_width//2},{video_height - 50})"
            elif mode == 5:  # 顶部
                pos = f"\\an8\\pos({video_width//2},50)"
            else:  # 滚动
                y = random.randint(20, video_height - 80)
                pos = f"\\move({video_width + 100},{y},{-200},{y})"

            text = dm["text"].replace("\n", "\\N")
            line = f"Dialogue: 0,{start_str},{end_str},Danmaku,,0,0,0,,{{\\c{ass_color}{pos}}}{text}"
            ass_lines.append(line)

        return "\n".join(ass_lines)

    def danmaku_to_srt(self, danmakus):
        """弹幕转SRT字幕"""
        srt_lines = []
        for i, dm in enumerate(danmakus, 1):
            t = dm["time"]
            end_t = t + 3.0  # 每条弹幕显示3秒

            def format_time(seconds):
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = seconds % 60
                return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

            srt_lines.append(str(i))
            srt_lines.append(f"{format_time(t)} --> {format_time(end_t)}")
            srt_lines.append(dm["text"])
            srt_lines.append("")

        return "\n".join(srt_lines)

    def danmaku_to_txt(self, danmakus):
        """弹幕转纯文本"""
        lines = []
        for dm in danmakus:
            t = dm["time"]
            m = int(t // 60)
            s = t % 60
            lines.append(f"[{m:02d}:{s:05.2f}] {dm['text']}")
        return "\n".join(lines)

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入B站视频链接")
            return
        self.btn_download.config(state="disabled")
        threading.Thread(target=self._download_thread, daemon=True).start()

    def _download_thread(self):
        try:
            url = self.url_var.get().strip()
            save_dir = self.dir_var.get().strip()
            fmt = self.fmt_var.get()

            # 1. 提取BV号
            self.status_var.set("🔍 正在解析链接...")
            bvid = self.extract_bvid(url)
            if not bvid:
                raise Exception("无法识别链接中的BV号/AV号，请检查链接格式")

            # 2. 获取视频信息
            self.status_var.set("📡 正在获取视频信息...")
            title, cid_list = self.get_video_info(bvid)

            if not cid_list:
                raise Exception("未找到视频分P信息")

            total = len(cid_list)
            self.progress["maximum"] = total

            # 3. 创建保存目录
            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:80]
            save_path = os.path.join(save_dir, f"{safe_title}_弹幕")
            os.makedirs(save_path, exist_ok=True)

            # 4. 逐P下载弹幕
            for idx, (page, part, cid) in enumerate(cid_list):
                self.status_var.set(f"⬇️ 正在下载第{page}P弹幕 ({idx+1}/{total})...")
                self.progress["value"] = idx

                xml_text = self.get_danmaku_xml(cid)
                danmakus = self.parse_danmaku_xml(xml_text)

                if not danmakus:
                    self.status_var.set(f"⚠️ 第{page}P没有弹幕")
                    continue

                # 文件名
                if total == 1:
                    filename_base = safe_title
                else:
                    safe_part = re.sub(r'[<>:"/\\|?*]', '', part)[:60]
                    filename_base = f"P{page:02d}_{safe_part}"

                # 保存
                if fmt == "xml":
                    filepath = os.path.join(save_path, f"{filename_base}.xml")
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(xml_text)
                elif fmt == "ass":
                    filepath = os.path.join(save_path, f"{filename_base}.ass")
                    content = self.danmaku_to_ass(danmakus)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                elif fmt == "srt":
                    filepath = os.path.join(save_path, f"{filename_base}.srt")
                    content = self.danmaku_to_srt(danmakus)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                elif fmt == "txt":
                    filepath = os.path.join(save_path, f"{filename_base}.txt")
                    content = self.danmaku_to_txt(danmakus)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)

                # 预览
                if idx == 0:
                    preview = "\n".join([f"[{dm['time']:.1f}s] {dm['text']}" for dm in danmakus[:20]])
                    self.root.after(0, lambda p=preview: self._update_preview(p))

                time.sleep(0.3)

            self.progress["value"] = total
            self.status_var.set(f"✅ 完成！共下载 {total} 个弹幕文件 → {save_path}")
            messagebox.showinfo("完成", f"弹幕已保存到：\n{save_path}\n\n共 {total} 个文件")

        except Exception as e:
            self.status_var.set(f"❌ 错误: {str(e)}")
            messagebox.showerror("错误", str(e))
        finally:
            self.root.after(0, lambda: self.btn_download.config(state="normal"))

    def _update_preview(self, text):
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", text)
        self.preview_text.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = DanmakuDownloader(root)
    root.mainloop()
