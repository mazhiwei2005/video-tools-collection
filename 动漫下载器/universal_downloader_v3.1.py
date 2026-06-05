#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用动漫下载器 v3.1 — Playwright抓流 + ffmpeg直下 + TS内容诊断
核心: Playwright只负责抓真实m3u8, ffmpeg负责下载+解密+合并
新增: TS内容诊断(打印headers+hex), 增强媒体流捕获
"""
import re, json, time, os, subprocess, threading, queue, struct
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BLUE = "#00a1d6"
BLUE_LIGHT = "#e3f2fd"
BLUE_DARK = "#0095c8"
GREEN = "#4caf50"
RED = "#f44336"
GRAY = "#999"

def _find_ffmpeg():
    import shutil
    f = shutil.which("ffmpeg")
    if f:
        return f
    for p in [r"C:\Program Files\FFmpeg\ffmpeg.exe",
              r"C:\ffmpeg\bin\ffmpeg.exe",
              os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe")]:
        if os.path.exists(p):
            return p
    return "ffmpeg"

def _find_ffprobe():
    import shutil
    f = shutil.which("ffprobe")
    if f:
        return f
    ff = _find_ffmpeg()
    probe = ff.replace("ffmpeg", "ffprobe").replace("FFmpeg", "ffprobe")
    if os.path.exists(probe):
        return probe
    for p in [r"C:\Program Files\FFmpeg\ffprobe.exe"]:
        if os.path.exists(p):
            return p
    return "ffprobe"


# ================================================================
# 站点识别
# ================================================================
def detect_site(url):
    url_lower = url.lower()
    if "bimiacg" in url_lower:
        return "bimiacg"
    if "omofun" in url_lower:
        return "omofun"
    if "xifan" in url_lower or "稀饭" in url_lower:
        return "稀饭"
    if "661dm" in url_lower:
        return "661dm"
    return "通用"


# ================================================================
# TS内容诊断 — 判断.ts文件到底是什么
# ================================================================
def diagnose_ts(ts_url, referer="", cookie="", log_fn=print):
    """
    下载.ts文件的前128字节, 打印headers + hex + 内容类型
    返回: "ts" | "fmp4" | "html" | "json" | "png" | "encrypted" | "unknown"
    """
    import requests as req
    import urllib3
    urllib3.disable_warnings()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": referer,
        "Range": "bytes=0-511",  # 只下载前512字节
    }
    if cookie:
        headers["Cookie"] = cookie
    
    try:
        r = req.get(ts_url, headers=headers, timeout=10, verify=False, stream=False)
        log_fn(f"  [诊断] HTTP {r.status_code}")
        log_fn(f"  [诊断] Headers:")
        for k in ["content-type", "content-length", "content-encoding",
                   "x-cache", "cf-cache-status", "server", "accept-ranges"]:
            v = r.headers.get(k, "")
            if v:
                log_fn(f"    {k}: {v}")
        
        data = r.content[:512]
        log_fn(f"  [诊断] 实际获取: {len(r.content)}字节 (前512)")
        log_fn(f"  [诊断] Hex前64字节:")
        hex_lines = []
        for i in range(0, min(64, len(data)), 16):
            chunk = data[i:i+16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            hex_lines.append(f"    {i:04x}: {hex_part:<48s} {ascii_part}")
        for line in hex_lines:
            log_fn(line)
        
        # 判断类型
        if not data:
            log_fn(f"  [诊断] 结论: 空数据")
            return "empty"
        
        # 检查前几个字节
        if data[:4] == b'\x89PNG':
            log_fn(f"  [诊断] 结论: PNG图片(广告)")
            return "png"
        if data[:3] == b'\xff\xd8\xff':
            log_fn(f"  [诊断] 结论: JPEG图片(广告)")
            return "jpeg"
        if data[:4] == b'GIF8':
            log_fn(f"  [诊断] 结论: GIF图片(广告)")
            return "gif"
        if data[:4] == b'<htm' or data[:5] == b'<!DOC':
            log_fn(f"  [诊断] 结论: HTML页面(防盗链/拦截)")
            return "html"
        if data[0] == 0x1f and data[1] == 0x8b:
            log_fn(f"  [诊断] 结论: gzip压缩数据")
            return "gzipped"
        if data[0] == 0x47:
            log_fn(f"  [诊断] 结论: 真正MPEG-TS (0x47同步字节)")
            return "ts"
        if b'ftyp' in data[:16]:
            log_fn(f"  [诊断] 结论: fMP4/ISOM (ftyp box)")
            return "fmp4"
        if b'moof' in data[:32] or b'mdat' in data[:32]:
            log_fn(f"  [诊断] 结论: fMP4片段 (moof/mdat)")
            return "fmp4"
        if data[0] == 0x7b or data[:1] == b'{':
            text = data.decode("utf-8", errors="replace")[:100]
            log_fn(f"  [诊断] 结论: JSON/文本数据: {text[:80]}")
            return "json"
        
        # 未知二进制
        log_fn(f"  [诊断] 结论: 未知二进制数据 (非TS/MP4/HTML/图片)")
        return "encrypted"
    
    except Exception as e:
        log_fn(f"  [诊断] 请求失败: {e}")
        return "error"


# ================================================================
# 浏览器引擎 — Playwright只负责抓流
# ================================================================
class BrowserEngine:
    def __init__(self, log_fn=None):
        self.log = log_fn or print
        self._cancel = False
    
    def cancel(self):
        self._cancel = True
    
    def _launch(self):
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            channel="msedge",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                   "--disable-web-security"]
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            window.chrome = {runtime: {}};
        """)
        return pw, browser, ctx
    
    def extract_episodes(self, url):
        """从播放页提取全集列表"""
        pw, browser, ctx = self._launch()
        page = ctx.new_page()
        
        try:
            self.log(f"加载页面...")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            for _ in range(4):
                title = page.title()
                if title and "JavaScript" not in title and "请启用" not in title:
                    break
                time.sleep(3)
                page.reload(wait_until="domcontentloaded")
            
            content = page.content()
            title = page.title()
            name = self._extract_name(title, content)
            
            episodes = self._extract_ep_links(content, url)
            if not episodes:
                nid = 1
                sid = 1
                player_m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;', content, re.S)
                if not player_m:
                    player_m = re.search(r'window\.player_\d+\s*=\s*(\{.*?\})\s*;', content, re.S)
                if player_m:
                    try:
                        d = json.loads(player_m.group(1))
                        nid = d.get("nid", 1)
                        sid = d.get("sid", 1)
                    except:
                        pass
                episodes = [{"sid": sid, "nid": nid, "url": url}]
            
            self.log(f"{name} - {len(episodes)}集")
            return {"success": True, "name": name, "episodes": episodes}
        except Exception as e:
            return {"error": str(e)}
        finally:
            browser.close()
            pw.stop()
    
    def _extract_name(self, title, content=""):
        if content:
            h1_m = re.search(r'<h1[^>]*>([^<]{2,60})</h1>', content)
            if h1_m:
                n = h1_m.group(1).strip()
                n = re.sub(r'\s*第\d+[集话].*$', '', n)
                if len(n) >= 2:
                    return n
            tt_m = re.search(r'<title>([^<]+)</title>', content)
            if tt_m:
                title = tt_m.group(1)
        if not title:
            return "未知动漫"
        name = title.split('|')[0].split('-')[0].split('_')[0].strip()
        name = name.split('——')[0].split('—')[0].strip()
        name = re.sub(r'\s*第\d+[集话]\s*$', '', name)
        return name if len(name) >= 2 else "未知动漫"
    
    def _extract_ep_links(self, content, base_url):
        episodes = []
        seen = set()
        patterns = [
            (r'href="([^"]*?(?:sid|source)/(\d+)/(?:nid|ep)/(\d+)[^"]*\.html)"', 1),
            (r'href="([^"]*-(\d+)-(\d+)\.html)"', 1),
            (r'href="([^"]*?/play/(\d+)/(\d+)/?[^"]*)"', 1),
        ]
        for pattern, sid_idx in patterns:
            matches = re.findall(pattern, content)
            for full_url, sid, nid in matches:
                key = f"{sid}-{nid}"
                if key not in seen:
                    seen.add(key)
                    ep_url = full_url if full_url.startswith("http") else self._make_absolute(full_url, base_url)
                    episodes.append({"sid": int(sid), "nid": int(nid), "url": ep_url})
            if episodes:
                break
        episodes.sort(key=lambda x: (x["sid"], x["nid"]))
        return episodes
    
    def _make_absolute(self, path, base_url):
        if path.startswith("//"):
            return "https:" + path
        from urllib.parse import urljoin
        return urljoin(base_url, path)
    
    def grab_video_url(self, url, timeout=25):
        """
        核心: 打开页面 → 收集所有m3u8候选 → TS内容诊断 → 选最优
        每次调用都创建新浏览器, 不复用
        """
        pw, browser, ctx = self._launch()
        page = ctx.new_page()
        
        captured_urls = []
        captured_media = []  # 直接抓取的视频响应
        all_responses = []   # 记录所有响应 (诊断用)
        
        def on_response(response):
            try:
                if response.status != 200:
                    return
                resp_url = response.url
                ct = response.headers.get("content-type", "").lower()
                cl = int(response.headers.get("content-length", "0"))
                
                # 记录所有响应 (诊断用)
                all_responses.append({"url": resp_url[:150], "ct": ct, "cl": cl})
                
                # 1. 抓m3u8 (用于解析)
                if ".m3u8" in resp_url and "blob:" not in resp_url:
                    if resp_url not in [u for u, t in captured_urls]:
                        captured_urls.append((resp_url, "m3u8"))
                
                # 2. 抓真实视频响应 (按content-type)
                if cl > 100000 and any(v in ct for v in ["video", "octet-stream", "mp2t"]):
                    if resp_url not in [u for u, _ in captured_media]:
                        captured_media.append((resp_url, "media"))
                        self.log(f"  抓到视频流: {ct} {cl//1024}KB")
                
                # 3. 也抓其他可能的大文件 (诊断用)
                if cl > 500000 and "image" not in ct and "text" not in ct and "javascript" not in ct:
                    if resp_url not in [u for u, _ in captured_media] and resp_url not in [u for u, _ in captured_urls]:
                        captured_media.append((resp_url, "unknown_media"))
                        self.log(f"  抓到未知大文件: {ct} {cl//1024}KB {resp_url[:80]}")
                
                # 4. 抓MP4直链
                if ".mp4" in resp_url and "blob:" not in resp_url and cl > 500000:
                    if resp_url not in [u for u, _ in captured_urls]:
                        captured_urls.append((resp_url, "mp4"))
            except:
                pass
        
        page.on("response", on_response)
        
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            for _ in range(4):
                t = page.title()
                if t and "JavaScript" not in t and "请启用" not in t:
                    break
                time.sleep(3)
                page.reload(wait_until="domcontentloaded")
            
            # 等待播放器加载 (最多25秒)
            start = time.time()
            while time.time() - start < 25:
                if self._cancel:
                    break
                # 有真实视频响应 → 立即用
                if captured_media:
                    time.sleep(2)
                    break
                # 有m3u8 → 多等几秒看有没有真实视频
                m3u8s = [u for u, t in captured_urls if t == "m3u8"]
                if m3u8s and time.time() - start > 8:
                    time.sleep(3)
                    break
                mp4s = [u for u, t in captured_urls if t == "mp4"]
                if mp4s and time.time() - start > 3:
                    time.sleep(2)
                    break
                time.sleep(1)
            
            # ===== 诊断: 打印所有网络响应 =====
            self.log(f"  === 网络诊断 ({len(all_responses)}个响应) ===")
            ct_counts = {}
            for r in all_responses:
                ct_short = r["ct"].split(";")[0] if r["ct"] else "无"
                ct_counts[ct_short] = ct_counts.get(ct_short, 0) + 1
            for ct, cnt in sorted(ct_counts.items(), key=lambda x: -x[1])[:10]:
                self.log(f"    {ct}: {cnt}个")
            
            # 打印所有大文件响应 (>100KB)
            big_files = [r for r in all_responses if r["cl"] > 100000]
            if big_files:
                self.log(f"  大文件(>100KB): {len(big_files)}个")
                for r in big_files[:5]:
                    self.log(f"    {r['ct']} {r['cl']//1024}KB {r['url']}")
            else:
                self.log(f"  大文件(>100KB): 0个 !!!!")
            
            # DOM提取 (最稳定的方式)
            content = page.content()
            player_m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;', content, re.S)
            if not player_m:
                player_m = re.search(r'window\.player_\d+\s*=\s*(\{.*?\})\s*;', content, re.S)
            if player_m:
                try:
                    d = json.loads(player_m.group(1))
                    raw = d.get("url", "")
                    if d.get("encrypt", 0) == 1:
                        from urllib.parse import unquote
                        raw = unquote(raw)
                    elif d.get("encrypt", 0) == 2:
                        import base64
                        raw = unquote(base64.b64decode(raw).decode())
                    if raw and ("m3u8" in raw or "mp4" in raw):
                        captured_urls.insert(0, (raw, "m3u8" if "m3u8" in raw else "mp4"))
                except:
                    pass
            
            # ===== 关键诊断: 下载第一个.ts内容看看到底是什么 =====
            m3u8_list = [u for u, t in captured_urls if t == "m3u8"]
            if m3u8_list:
                test_m3u8 = m3u8_list[0]
                self.log(f"\n  === TS内容诊断 (m3u8: {test_m3u8[:80]}) ===")
                try:
                    import requests as req
                    import urllib3
                    urllib3.disable_warnings()
                    s = req.Session()
                    s.verify = False
                    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    
                    # 获取m3u8内容
                    r = s.get(test_m3u8, timeout=10)
                    m3u8_text = r.text
                    
                    # 找到第一个.ts URL
                    from urllib.parse import urljoin
                    for line in m3u8_text.strip().split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            test_ts = urljoin(test_m3u8, line)
                            self.log(f"  测试下载: {test_ts[:100]}")
                            diagnose_ts(test_ts, referer=url, log_fn=self.log)
                            break
                except Exception as e:
                    self.log(f"  诊断失败: {e}")
            
            # ===== JS诊断: 检查播放器是否用MediaSource =====
            self.log(f"\n  === JS播放器诊断 ===")
            try:
                has_ms = page.evaluate("""() => {
                    let info = {};
                    info.has_MediaSource = typeof MediaSource !== 'undefined';
                    info.has_SourceBuffer = typeof SourceBuffer !== 'undefined';
                    // 检查video元素
                    let videos = document.querySelectorAll('video');
                    info.video_count = videos.length;
                    if (videos.length > 0) {
                        let v = videos[0];
                        info.video_src = v.src || 'none';
                        info.video_currentSrc = v.currentSrc || 'none';
                        info.video_readyState = v.readyState;
                        // 检查是否有blob URL
                        info.has_blob_src = (v.src || '').startsWith('blob:');
                    }
                    // 检查是否有DPlayer/DanPlayer等播放器对象
                    info.has_dplayer = typeof DPlayer !== 'undefined';
                    info.has_danplayer = typeof DanPlayer !== 'undefined';
                    info.has_hls = typeof Hls !== 'undefined';
                    return info;
                }""")
                for k, v in has_ms.items():
                    self.log(f"    {k}: {v}")
            except Exception as e:
                self.log(f"    JS诊断失败: {e}")
            
        except Exception as e:
            self.log(f"  浏览器: {e}")
        
        # 提取Cookie (关键: ffmpeg需要Cookie才能下载ts)
        cookies = []
        try:
            for c in ctx.cookies():
                cookies.append(f"{c['name']}={c['value']}")
        except:
            pass
        cookie_str = "; ".join(cookies) if cookies else ""
        
        browser.close()
        pw.stop()
        
        if not captured_urls and not captured_media:
            return []
        
        # 优先用抓到的真实视频流 (比m3u8可靠)
        if captured_media:
            seen = set()
            unique = []
            for u, t in captured_media:
                if u not in seen:
                    seen.add(u)
                    if t == "media":
                        unique.insert(0, (u, t, cookie_str))  # 真视频排前面
                    else:
                        unique.append((u, t, cookie_str))
            if unique:
                self.log(f"  直接抓到{len(unique)}个视频流")
                return unique
        
        # 没有真实视频流, 用m3u8
        seen = set()
        unique = []
        for u, t in captured_urls:
            if u not in seen:
                seen.add(u)
                unique.append((u, t))
        
        # 验证m3u8: 下载内容, 数TS数量, 过滤假流, 选最优
        import requests as req
        import urllib3
        urllib3.disable_warnings()
        s = req.Session()
        s.verify = False
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        referer_m = re.search(r'(https?://[^/]+)', url)
        if referer_m:
            s.headers["Referer"] = referer_m.group(1) + "/"
        
        best_url = None
        best_count = 0
        best_type = "m3u8"
        
        for u, t in unique:
            if t == "m3u8":
                try:
                    r = s.get(u, timeout=8)
                    text = r.text
                    ts_count = text.count(".ts")
                    if ts_count >= 10 and ts_count > best_count:
                        best_count = ts_count
                        best_url = u
                        self.log(f"  m3u8: {ts_count}个TS")
                except:
                    pass
            elif t == "mp4" and not best_url:
                best_url = u
                best_type = "mp4"
        
        if best_url:
            if best_type == "m3u8":
                self.log(f"  选中m3u8 ({best_count}个TS)")
            else:
                self.log(f"  选中MP4直链")
            return [(best_url, best_type, cookie_str)]
        
        # 兜底
        if unique:
            self.log(f"  兜底: {unique[0][0][:50]}...")
            return [(unique[0][0], unique[0][1], cookie_str)]
        return []


# ================================================================
# 下载引擎 — ffmpeg直下 (不手动拼TS)
# ================================================================
class DownloadEngine:
    def __init__(self, log_fn=None):
        self.log = log_fn or print
    
    def download(self, video_url, output_path, referer="", cookie=""):
        if "m3u8" in video_url:
            return self._download_m3u8_ffmpeg(video_url, output_path, referer, cookie)
        elif "mp4" in video_url:
            return self._download_mp4(video_url, output_path, referer)
        else:
            self.log(f"  未知格式: {video_url[:80]}")
            return False
    
    def _download_m3u8_ffmpeg(self, m3u8_url, output_path, referer, cookie=""):
        """ffmpeg直接从m3u8下载 — 带完整headers(含Cookie)"""
        import requests as req
        import urllib3
        urllib3.disable_warnings()
        
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
        # 先解析master playlist取子流
        s = req.Session()
        s.verify = False
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": referer,
        })
        try:
            r = s.get(m3u8_url, timeout=10)
            content = r.text
        except Exception as e:
            self.log(f"  m3u8获取失败: {e}")
            return False
        
        # master → 子流
        if "#EXT-X-STREAM-INF" in content:
            streams = []
            lines = content.strip().split("\n")
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF"):
                    bw = re.search(r"BANDWIDTH=(\d+)", line)
                    bw_val = int(bw.group(1)) if bw else 0
                    if i + 1 < len(lines):
                        sub = lines[i + 1].strip()
                        if not sub.startswith("http"):
                            from urllib.parse import urljoin
                            sub = urljoin(m3u8_url, sub)
                        streams.append((bw_val, sub))
            if streams:
                streams.sort(key=lambda x: x[0], reverse=True)
                m3u8_url = streams[0][1]
                self.log(f"  master→子流({len(streams)}条)")
                # 关键: 重新下载子m3u8内容!
                try:
                    r = s.get(m3u8_url, timeout=10)
                    content = r.text
                    self.log(f"  子m3u8已获取 ({len(content)}字节)")
                except Exception as e:
                    self.log(f"  子m3u8获取失败: {e}")
                    return False
        
        # 解析segment
        lines = content.strip().split("\n")
        if not lines or "#EXTM3U" not in lines[0]:
            self.log(f"  不是有效m3u8")
            return False
        
        # 稳定过滤: 保留原始m3u8结构, 只去广告图片+转绝对URL
        import re
        from urllib.parse import urljoin, urlparse
        clean_lines = []
        ad_count = 0
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # EXTINF + segment 成对处理
            if line.startswith("#EXTINF"):
                if i + 1 >= len(lines):
                    break
                seg = lines[i + 1].strip()
                # 只检查URL路径部分是否是图片广告
                seg_path = urlparse(seg).path.lower()
                if any(seg_path.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                    ad_count += 1
                    i += 2
                    continue
                
                # 保留: 转绝对URL
                full_url = urljoin(m3u8_url, seg)
                clean_lines.append(line)
                clean_lines.append(full_url)
                i += 2
                continue
            
            # MAP/KEY: URI转绝对URL, 永远保留
            if line.startswith("#EXT-X-MAP") or line.startswith("#EXT-X-KEY"):
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    uri = m.group(1)
                    full = urljoin(m3u8_url, uri)
                    line = line.replace(uri, full)
                clean_lines.append(line)
                i += 1
                continue
            
            # 其他所有行原样保留
            clean_lines.append(line)
            i += 1
        
        extinf_count = len([l for l in clean_lines if l.startswith("#EXTINF")])
        self.log(f"  {extinf_count}个segment (过滤{ad_count}个图片广告)")
        
        # 生成干净m3u8
        import tempfile
        tmp = tempfile.mkdtemp(prefix="ani_m3u8_")
        try:
            clean_m3u8 = os.path.join(tmp, "clean.m3u8")
            with open(clean_m3u8, "w", encoding="utf-8") as f:
                f.write("\n".join(clean_lines))
            
            # ffmpeg下载 (带完整headers含Cookie)
            ffmpeg = _find_ffmpeg()
            headers = f"Referer: {referer}\r\n"
            if cookie:
                headers += f"Cookie: {cookie}\r\n"
            cmd = [
                ffmpeg, "-y",
                "-protocol_whitelist", "file,http,https,tcp,tls",
                "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "-headers", headers,
                "-i", clean_m3u8.replace("\\", "/"),
                "-c", "copy", "-movflags", "+faststart",
                "-hide_banner", output_path
            ]
            
            self.log(f"  ffmpeg下载中...")
            result = subprocess.run(cmd, capture_output=True, timeout=600,
                                    encoding="utf-8", errors="replace")
            
            if result.returncode != 0:
                err = result.stderr[-300:] if result.stderr else "unknown"
                self.log(f"  ffmpeg失败: {err[:200]}")
                return False
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                sz = os.path.getsize(output_path)
                duration = self._check_duration(output_path)
                if duration and duration < 10:
                    self.log(f"  时长异常({duration:.1f}s)")
                    os.remove(output_path)
                    return False
                self.log(f"  完成 {sz/1024/1024:.1f}MB" + (f" {duration:.0f}s" if duration else ""))
                return True
            
            self.log(f"  ffmpeg输出为空")
            return False
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    
    def _check_duration(self, filepath):
        """用ffprobe检测视频时长"""
        try:
            ffprobe = _find_ffprobe()
            cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1:nokey=1", filepath]
            r = subprocess.run(cmd, capture_output=True, timeout=15,
                               encoding="utf-8", errors="replace")
            return float(r.stdout.strip())
        except:
            return None
    
    def _download_mp4(self, mp4_url, output_path, referer):
        import requests as req
        import urllib3
        urllib3.disable_warnings()
        
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
        try:
            r = req.get(mp4_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": referer,
            }, verify=False, stream=True, timeout=30)
            r.raise_for_status()
            
            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            last_update = time.time()
            
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_update >= 3:
                            last_update = now
                            if total > 0:
                                self.log(f"  下载 {downloaded/1024/1024:.1f}/{total/1024/1024:.1f}MB ({downloaded/total*100:.0f}%)")
            
            if os.path.getsize(output_path) > 10000:
                sz = os.path.getsize(output_path)
                self.log(f"  完成 {sz/1024/1024:.1f}MB")
                return True
        except Exception as e:
            self.log(f"  下载失败: {e}")
        return False


# ================================================================
# GUI
# ================================================================
class UniversalDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("通用动漫下载器 v3.1 — Playwright抓流 + ffmpeg直下 + TS诊断")
        self.root.geometry("950x700")
        self.root.minsize(850, 580)
        
        self.engine = BrowserEngine(log_fn=self._log)
        self.downloader = DownloadEngine(log_fn=self._log)
        self.msg_queue = queue.Queue()
        self._downloading = False
        self._cancel = False
        self.tasks = []
        
        self._setup_style()
        self._setup_ui()
        self._poll_queue()
    
    def _setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TFrame", background="#f4f5f7")
        s.configure("TLabel", background="#f4f5f7", font=("微软雅黑", 9))
        s.configure("TButton", font=("微软雅黑", 9))
        s.configure("TLabelframe", background="#f4f5f7", font=("微软雅黑", 9, "bold"))
        s.configure("TLabelframe.Label", background="#f4f5f7", font=("微软雅黑", 9, "bold"))
        s.configure("Blue.TButton", background=BLUE, foreground="white", font=("微软雅黑", 9, "bold"))
        s.map("Blue.TButton", background=[("active", BLUE_DARK)])
        s.configure("Green.TButton", background=GREEN, foreground="white", font=("微软雅黑", 9, "bold"))
        s.map("Green.TButton", background=[("active", "#43a047")])
        s.configure("Red.TButton", background=RED, foreground="white", font=("微软雅黑", 9))
        s.map("Red.TButton", background=[("active", "#d32f2f")])
        s.configure("Treeview", font=("微软雅黑", 9), rowheight=24)
        s.configure("Treeview.Heading", font=("微软雅黑", 9, "bold"), background=BLUE_LIGHT)
    
    def _setup_ui(self):
        hd = tk.Frame(self.root, bg=BLUE, height=44)
        hd.pack(fill=tk.X)
        tk.Label(hd, text="通用动漫下载器", bg=BLUE, fg="white", font=("微软雅黑", 14, "bold")).pack(side=tk.LEFT, padx=14, pady=6)
        tk.Label(hd, text="Playwright抓流 + ffmpeg直下 + TS诊断", bg=BLUE, fg="#cce5ff", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=6)
        tk.Label(hd, text="v3.1", bg=BLUE, fg="white", font=("微软雅黑", 8)).pack(side=tk.RIGHT, padx=14)
        
        f1 = ttk.Frame(self.root)
        f1.pack(fill=tk.X, padx=10, pady=(8, 2))
        ttk.Label(f1, text="播放页链接:").pack(side=tk.LEFT)
        self.link_var = tk.StringVar()
        e = ttk.Entry(f1, textvariable=self.link_var, width=70)
        e.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        e.bind("<Return>", lambda _: self._parse())
        self.site_label = tk.StringVar(value="站点: 自动")
        ttk.Label(f1, textvariable=self.site_label).pack(side=tk.LEFT, padx=8)
        ttk.Button(f1, text="解析", style="Blue.TButton", command=self._parse).pack(side=tk.LEFT, padx=2)
        
        f2 = ttk.Frame(self.root)
        f2.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(f2, text="保存到:").pack(side=tk.LEFT)
        self.out_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop", "动漫下载"))
        ttk.Entry(f2, textvariable=self.out_dir, width=60).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ttk.Button(f2, text="浏览", command=self._browse).pack(side=tk.LEFT, padx=2)
        
        cols = ("name", "site", "eps", "status", "done")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=8)
        for c, w, t in [("name", 280, "动漫名"), ("site", 60, "站点"), ("eps", 60, "集数"),
                         ("status", 70, "状态"), ("done", 100, "进度")]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill=tk.BOTH, padx=10, pady=4, expand=True)
        
        f3 = ttk.Frame(self.root)
        f3.pack(fill=tk.X, padx=10, pady=4)
        ttk.Button(f3, text="开始下载", style="Green.TButton", command=self._start).pack(side=tk.LEFT, padx=4)
        ttk.Button(f3, text="停止", style="Red.TButton", command=self._stop).pack(side=tk.LEFT, padx=4)
        ttk.Button(f3, text="清空", command=self._clear).pack(side=tk.LEFT, padx=4)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(f3, textvariable=self.status_var).pack(side=tk.RIGHT, padx=8)
        
        lf = ttk.LabelFrame(self.root, text="日志")
        lf.pack(fill=tk.BOTH, padx=10, pady=(2, 8), expand=True)
        self.log_text = tk.Text(lf, height=8, font=("Consolas", 9), state=tk.DISABLED, wrap=tk.WORD)
        sb = ttk.Scrollbar(lf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)
    
    def _log(self, msg):
        self.msg_queue.put(("log", msg))
    
    def _parse(self):
        url = self.link_var.get().strip()
        if not url:
            return
        site = detect_site(url)
        self.site_label.set(f"站点: {site}")
        self._log(f"[{site}] 解析: {url}")
        threading.Thread(target=self._parse_worker, args=(url, site), daemon=True).start()
    
    def _parse_worker(self, url, site):
        result = self.engine.extract_episodes(url)
        if "error" in result:
            self._log(f"错误: {result['error']}")
            return
        
        name = result["name"]
        episodes = result["episodes"]
        task = {
            "name": name, "site": site, "episodes": episodes,
            "status": "等待", "done": "", "first_url": url,
        }
        self.tasks.append(task)
        self.msg_queue.put(("add_task", task))
        self._log(f"{name} — {len(episodes)}集 [{site}]")
    
    def _start(self):
        if self._downloading:
            return
        pending = [t for t in self.tasks if t["status"] in ("等待", "失败")]
        if not pending:
            messagebox.showinfo("提示", "没有待下载的任务")
            return
        self._downloading = True
        self._cancel = False
        threading.Thread(target=self._worker, args=(pending,), daemon=True).start()
    
    def _stop(self):
        self._cancel = True
        self.engine.cancel()
        self._downloading = False
        self._log("已停止")
    
    def _clear(self):
        if self._downloading:
            return
        self.tasks.clear()
        self.msg_queue.put(("refresh_tree",))
    
    def _worker(self, tasks):
        total_ok = total_fail = 0
        
        for task in tasks:
            if self._cancel:
                break
            task["status"] = "下载中"
            self.msg_queue.put(("refresh_tree",))
            
            name = task["name"].replace("/", "_").replace("\\", "_")
            save_path = os.path.join(self.out_dir.get(), name)
            os.makedirs(save_path, exist_ok=True)
            eps = task["episodes"]
            site = task["site"]
            
            self._log(f">> {name} ({len(eps)}集) [{site}]")
            
            for i, ep in enumerate(eps):
                if self._cancel:
                    break
                
                nid = ep["nid"]
                ep_url = ep.get("url", task.get("first_url", ""))
                
                task["done"] = f"{i+1}/{len(eps)}"
                self.msg_queue.put(("refresh_tree",))
                
                self._log(f"  [{i+1}/{len(eps)}] 第{nid:02d}集 抓流中...")
                
                # 每集独立浏览器抓流
                urls = self.engine.grab_video_url(ep_url, timeout=25)
                
                if not urls:
                    self._log(f"  第{nid:02d}集: 未抓到视频")
                    task["done"] = f"{i+1}/{len(eps)} X"
                    total_fail += 1
                    self.msg_queue.put(("refresh_tree",))
                    continue
                
                video_url = urls[0][0]
                fmt = urls[0][1]
                cookie_str = urls[0][2] if len(urls[0]) > 2 else ""
                self._log(f"  第{nid:02d}集: {fmt.upper()}")
                
                output = os.path.join(save_path, f"第{nid:02d}集.mp4")
                
                # 跳过已下载
                if os.path.exists(output) and os.path.getsize(output) > 100000:
                    self._log(f"  第{nid:02d}集: 已存在, 跳过")
                    task["done"] = f"{i+1}/{len(eps)} ok"
                    total_ok += 1
                    self.msg_queue.put(("refresh_tree",))
                    continue
                
                referer_m = re.search(r'(https?://[^/]+)', ep_url)
                referer = referer_m.group(1) + "/" if referer_m else ""
                
                ok = self.downloader.download(video_url, output, referer, cookie_str)
                if ok:
                    self._log(f"  第{nid:02d}集: 完成")
                    task["done"] = f"{i+1}/{len(eps)} ok"
                    total_ok += 1
                else:
                    self._log(f"  第{nid:02d}集: 失败")
                    task["done"] = f"{i+1}/{len(eps)} X"
                    total_fail += 1
                
                self.msg_queue.put(("refresh_tree",))
                time.sleep(1)
            
            task["status"] = "完成" if not self._cancel else "已停止"
            self.msg_queue.put(("refresh_tree",))
        
        self._downloading = False
        self._log(f"完成! ok={total_ok} fail={total_fail}")
        self.status_var.set(f"完成 — 成功{total_ok} 失败{total_fail}")
    
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "log":
                    self.log_text.configure(state=tk.NORMAL)
                    self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg[1]}\n")
                    self.log_text.see(tk.END)
                    self.log_text.configure(state=tk.DISABLED)
                elif msg[0] == "add_task":
                    t = msg[1]
                    self.tree.insert("", tk.END, values=(t["name"], t["site"], f"{len(t['episodes'])}集", t["status"], ""), iid=str(id(t)))
                elif msg[0] == "refresh_tree":
                    for t in self.tasks:
                        try:
                            self.tree.item(str(id(t)), values=(t["name"], t["site"], f"{len(t['episodes'])}集", t["status"], t.get("done", "")))
                        except:
                            pass
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = UniversalDownloader(root)
    root.mainloop()
