#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用动漫下载器 v4.0 — 浏览器播放 + CDP抓流 + 自动录制
适用于: 伪HLS / MediaSource / JS解密型站点
核心: Playwright打开页面 → 自动播放 → CDP抓真实视频 → 无则录制
"""
import re, json, time, os, subprocess, threading, queue, base64, tempfile, shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BLUE = "#00a1d6"
BLUE_LIGHT = "#e3f2fd"
BLUE_DARK = "#0095c8"
GREEN = "#4caf50"
RED = "#f44336"

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
    return "ffprobe"

def _check_duration(filepath):
    try:
        ffprobe = _find_ffprobe()
        cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", filepath]
        r = subprocess.run(cmd, capture_output=True, timeout=15,
                           encoding="utf-8", errors="replace")
        return float(r.stdout.strip())
    except:
        return None


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
# 浏览器引擎 — Playwright + CDP 抓流/录制
# ================================================================
class BrowserEngine:
    def __init__(self, log_fn=None):
        self.log = log_fn or print
        self._cancel = False
    
    def cancel(self):
        self._cancel = True
    
    def _launch(self, record_video=False, video_dir=None):
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            channel="msedge",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                   "--disable-web-security", "--autoplay-policy=no-user-gesture-required"]
        )
        ctx_kwargs = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
            "locale": "zh-CN",
        }
        if record_video and video_dir:
            ctx_kwargs["record_video_dir"] = video_dir
            ctx_kwargs["record_video_size"] = {"width": 1920, "height": 1080}
        ctx = browser.new_context(**ctx_kwargs)
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            window.chrome = {runtime: {}};

            // ===== 猫抓核心: Hook fetch/XHR/MediaSource =====
            window.__mseLogs = [];
            window.__mseBuffers = [];
            window.__fetchLogs = [];

            // Hook fetch — 拦截所有fetch请求
            const _origFetch = window.fetch;
            window.fetch = async function(...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
                const resp = await _origFetch.apply(this, args);
                try {
                    const ct = resp.headers.get('content-type') || '';
                    const cl = resp.headers.get('content-length') || '0';
                    window.__fetchLogs.push({url: url.substring(0, 200), ct, cl: parseInt(cl)});
                } catch(e) {}
                return resp;
            };

            // Hook XMLHttpRequest — 拦截XHR
            const _origOpen = XMLHttpRequest.prototype.open;
            const _origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                this._hookUrl = url;
                return _origOpen.call(this, method, url, ...rest);
            };
            XMLHttpRequest.prototype.send = function(...args) {
                this.addEventListener('load', function() {
                    try {
                        const ct = this.getResponseHeader('content-type') || '';
                        const cl = this.getResponseHeader('content-length') || '0';
                        window.__fetchLogs.push({url: (this._hookUrl||'').substring(0, 200), ct, cl: parseInt(cl), type: 'xhr'});
                    } catch(e) {}
                });
                return _origSend.apply(this, args);
            };

            // Hook MediaSource.addSourceBuffer + SourceBuffer.appendBuffer
            // 这是猫抓核心: 拦截解密后的真实视频数据
            if (typeof MediaSource !== 'undefined') {
                const _origAddSB = MediaSource.prototype.addSourceBuffer;
                MediaSource.prototype.addSourceBuffer = function(mimeType) {
                    window.__mseLogs.push({event: 'addSourceBuffer', mimeType});
                    const sb = _origAddSB.call(this, mimeType);
                    const _origAppend = SourceBuffer.prototype.appendBuffer;
                    SourceBuffer.prototype.appendBuffer = function(data) {
                        const size = (data && data.byteLength) ? data.byteLength : 0;
                        window.__mseLogs.push({event: 'appendBuffer', size, mimeType});
                        // 保存数据到全局数组 (限制大小避免OOM)
                        if (size > 0 && size < 10*1024*1024) {
                            try {
                                const copy = new Uint8Array(data);
                                window.__mseBuffers.push(copy);
                            } catch(e) {}
                        }
                        return _origAppend.apply(this, arguments);
                    };
                    return sb;
                };
            }
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
        策略: 
        1. 先尝试CDP抓真实视频流 (非m3u8假流)
        2. 尝试从DOM/player对象提取真实URL
        3. 以上都失败 → 返回"record"标记, 走录制路线
        """
        pw, browser, ctx = self._launch()
        page = ctx.new_page()
        
        captured = {"real_video": [], "m3u8": [], "mp4": [], "all_big": []}
        cdp_responses = []
        
        def on_response(response):
            try:
                if response.status != 200:
                    return
                resp_url = response.url
                ct = response.headers.get("content-type", "").lower()
                cl = int(response.headers.get("content-length", "0"))
                
                # 记录所有 >100KB 的响应
                if cl > 100000:
                    entry = {"url": resp_url[:200], "ct": ct, "cl": cl}
                    cdp_responses.append(entry)
                    captured["all_big"].append(entry)
                    if cl > 100000:
                        self.log(f"  大响应: {ct} {cl//1024}KB {resp_url[:80]}")
                
                # 真实视频流 (非.m3u8)
                if cl > 500000:
                    if any(v in ct for v in ["video/mp4", "video/webm", "application/mp4",
                                              "application/octet-stream", "video/iso.segment"]):
                        if resp_url not in [r["url"] for r in captured["real_video"]]:
                            captured["real_video"].append(entry)
                            self.log(f"  ✓ 真实视频: {ct} {cl//1024}KB")
                    
                    # 也抓任何可能是视频的大文件 (排除已知假流)
                    if ".m3u8" not in resp_url and ".png" not in resp_url and ".jpg" not in resp_url:
                        if "javascript" not in ct and "html" not in ct and "css" not in ct:
                            if resp_url not in [r["url"] for r in captured["real_video"]]:
                                captured["real_video"].append(entry)
                                self.log(f"  ? 可能视频: {ct} {cl//1024}KB {resp_url[:60]}")
                
                # m3u8 (仅记录, 不作为下载源)
                if ".m3u8" in resp_url and "blob:" not in resp_url:
                    if resp_url not in [u for u in captured["m3u8"]]:
                        captured["m3u8"].append(resp_url)
                
                # MP4直链
                if ".mp4" in resp_url and "blob:" not in resp_url and cl > 1000000:
                    if resp_url not in [u for u in captured["mp4"]]:
                        captured["mp4"].append(resp_url)
                        self.log(f"  ✓ MP4直链: {cl//1024}KB")
            except:
                pass
        
        page.on("response", on_response)
        
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            for _ in range(2):
                t = page.title()
                if t and "JavaScript" not in t and "请启用" not in t:
                    break
                time.sleep(2)
                page.reload(wait_until="domcontentloaded")
            
            # ===== 分析播放器 =====
            self.log(f"  分析播放器...")
            try:
                player_info = page.evaluate("""() => {
                    let info = {};
                    // 播放器类型
                    info.has_DPlayer = typeof DPlayer !== 'undefined';
                    info.has_DanPlayer = typeof DanPlayer !== 'undefined';
                    info.has_ArtPlayer = typeof Artplayer !== 'undefined';
                    info.has_Hls = typeof Hls !== 'undefined';
                    info.has_flvjs = typeof flvjs !== 'undefined';
                    
                    // MediaSource
                    info.has_MediaSource = typeof MediaSource !== 'undefined';
                    
                    // video元素
                    let videos = document.querySelectorAll('video');
                    info.video_count = videos.length;
                    if (videos.length > 0) {
                        let v = videos[0];
                        info.video_src = (v.src || 'none').substring(0, 200);
                        info.video_currentSrc = (v.currentSrc || 'none').substring(0, 200);
                        info.video_readyState = v.readyState;
                        info.video_paused = v.paused;
                        info.video_ended = v.ended;
                        info.video_duration = v.duration;
                        info.video_error = v.error ? v.error.code : null;
                    }
                    
                    // 检查iframe播放器
                    let iframes = document.querySelectorAll('iframe');
                    info.iframe_count = iframes.length;
                    info.iframe_srcs = Array.from(iframes).map(f => (f.src || '').substring(0, 150));
                    
                    return info;
                }""")
                for k, v in player_info.items():
                    self.log(f"    {k}: {v}")
            except Exception as e:
                self.log(f"    播放器分析失败: {e}")
            
            # ===== 从iframe提取真实m3u8 (关键!) =====
            # 很多站把播放器放在iframe里, url=参数包含真实m3u8
            try:
                iframe_srcs = player_info.get("iframe_srcs", []) if 'player_info' in dir() else []
                for iframe_src in iframe_srcs:
                    # 提取url=参数中的m3u8
                    url_match = re.search(r'[?&]url=(https?[^&"\']+\.m3u8[^&"\']*)', iframe_src)
                    if url_match:
                        from urllib.parse import unquote
                        real_m3u8 = unquote(url_match.group(1))
                        self.log(f"  ★ 从iframe提取到m3u8: {real_m3u8[:80]}")
                        captured["m3u8"].insert(0, real_m3u8)
                    
                    # 也检查iframe页面内是否嵌套了player_aaaa
                    if "artplayer" in iframe_src or "dplayer" in iframe_src:
                        try:
                            iframe_page = ctx.new_page()
                            iframe_page.goto(iframe_src, timeout=15000, wait_until="domcontentloaded")
                            iframe_content = iframe_page.content()
                            # 找嵌套的player_aaaa
                            nested_m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;', iframe_content, re.S)
                            if not nested_m:
                                nested_m = re.search(r'url\s*[:=]\s*["\']?(https?://[^"\']+\.(m3u8|mp4)[^"\']*)', iframe_content)
                            if nested_m and nested_m.lastindex:
                                nested_url = nested_m.group(1) if nested_m.lastindex >= 1 else nested_m.group(0)
                                self.log(f"  ★ iframe内m3u8: {nested_url[:80]}")
                                captured["m3u8"].insert(0, nested_url)
                            iframe_page.close()
                        except Exception as e2:
                            self.log(f"    iframe解析失败: {e2}")
            except Exception as e:
                self.log(f"    iframe提取失败: {e}")
            
            # ★ 关键: 如果从iframe提取到了m3u8, 立即返回, 不等视频加载
            if captured["m3u8"]:
                best = captured["m3u8"][0]
                self.log(f"  → 直接返回m3u8: {best[:80]}")
                # 提取Cookie
                cookies = []
                try:
                    for c in ctx.cookies():
                        cookies.append(f"{c['name']}={c['value']}")
                except:
                    pass
                cookie_str = "; ".join(cookies) if cookies else ""
                browser.close()
                pw.stop()
                return [(best, "m3u8", cookie_str)]
            
            # ===== 以下仅在没有iframe m3u8时执行 =====
            self.log(f"  尝试自动播放...")
            try:
                page.evaluate("""() => {
                    // 尝试点击播放按钮
                    let btns = document.querySelectorAll('.play-btn, .btn-play, .vjs-big-play-button, [class*="play"], [class*="Play"]');
                    for (let b of btns) { try { b.click(); } catch(e) {} }
                    
                    // 尝试直接播放video
                    let videos = document.querySelectorAll('video');
                    for (let v of videos) {
                        try { v.play(); } catch(e) {}
                    }
                }""")
            except:
                pass
            
            # ===== 等待视频加载 (最多30秒) =====
            self.log(f"  等待视频加载...")
            start = time.time()
            video_loaded = False
            while time.time() - start < 30:
                if self._cancel:
                    break
                
                # 检查是否有真实视频被抓到
                if captured["real_video"]:
                    time.sleep(2)
                    video_loaded = True
                    break
                
                # 检查video元素状态
                try:
                    state = page.evaluate("""() => {
                        let v = document.querySelector('video');
                        if (!v) return null;
                        return {
                            readyState: v.readyState,
                            paused: v.paused,
                            duration: v.duration,
                            currentTime: v.currentTime,
                            error: v.error ? v.error.code : null
                        };
                    }""")
                    if state and state.get("readyState", 0) >= 2:
                        self.log(f"    video已就绪 (readyState={state['readyState']}, duration={state.get('duration', '?')}s)")
                        video_loaded = True
                        time.sleep(2)
                        break
                    if state and state.get("error"):
                        self.log(f"    video错误: code={state['error']}")
                except:
                    pass
                
                time.sleep(1)
            
            # ===== 分析所有抓到的响应 =====
            self.log(f"\n  === 网络分析 ({len(cdp_responses)}个大响应) ===")
            
            # 按content-type分组
            ct_groups = {}
            for r in cdp_responses:
                ct = r["ct"].split(";")[0] if r["ct"] else "无"
                if ct not in ct_groups:
                    ct_groups[ct] = []
                ct_groups[ct].append(r)
            
            for ct, items in sorted(ct_groups.items(), key=lambda x: -sum(i["cl"] for i in x[1])):
                total_kb = sum(i["cl"] for i in items) // 1024
                self.log(f"    {ct}: {len(items)}个, 共{total_kb}KB")
            
            # 保存诊断信息
            diag_path = os.path.join(tempfile.gettempdir(), "ani_diag.json")
            with open(diag_path, "w", encoding="utf-8") as f:
                json.dump({"url": url, "player": player_info if 'player_info' in dir() else {},
                           "responses": cdp_responses[:50]}, f, ensure_ascii=False, indent=2)
            self.log(f"  诊断已保存: {diag_path}")
            
            # ===== 猫抓核心: 提取Hook数据 =====
            self.log(f"\n  === 浏览器Hook分析 ===")
            try:
                hook_data = page.evaluate("""() => {
                    return {
                        mseLogs: window.__mseLogs || [],
                        fetchLogs: window.__fetchLogs || [],
                        bufferCount: (window.__mseBuffers || []).length,
                        totalBufferSize: (window.__mseBuffers || []).reduce((s, b) => s + b.byteLength, 0)
                    };
                }""")
                
                # MediaSource日志
                mse_logs = hook_data.get("mseLogs", [])
                self.log(f"  MediaSource事件: {len(mse_logs)}个")
                for entry in mse_logs[:10]:
                    self.log(f"    {entry}")
                
                # Fetch/XHR日志
                fetch_logs = hook_data.get("fetchLogs", [])
                self.log(f"  Fetch/XHR请求: {len(fetch_logs)}个")
                # 找非图片/非JS的大请求
                for fl in fetch_logs:
                    ct = fl.get("ct", "")
                    cl = fl.get("cl", 0)
                    if cl > 100000 and "image" not in ct and "javascript" not in ct and "text" not in ct:
                        self.log(f"    ★ {ct} {cl//1024}KB {fl.get('url', '')[:80]}")
                
                # MSE Buffer数据
                buf_count = hook_data.get("bufferCount", 0)
                buf_size = hook_data.get("totalBufferSize", 0)
                self.log(f"  MSE Buffer: {buf_count}个, 共{buf_size//1024}KB")
                
                if buf_count > 0 and buf_size > 100000:
                    self.log(f"  ★ 捕获到真实视频数据! {buf_size//1024//1024}MB")
                    # 提取数据到临时文件
                    try:
                        # 分批提取避免内存溢出
                        chunk_size = 50  # 每次50个buffer
                        raw_data = bytearray()
                        for start in range(0, buf_count, chunk_size):
                            end = min(start + chunk_size, buf_count)
                            chunk = page.evaluate(f"""() => {{
                                const bufs = window.__mseBuffers.slice({start}, {end});
                                // 转base64
                                return bufs.map(b => {{
                                    let binary = '';
                                    const bytes = new Uint8Array(b);
                                    for (let i = 0; i < bytes.byteLength; i++) {{
                                        binary += String.fromCharCode(bytes[i]);
                                    }}
                                    return btoa(binary);
                                }});
                            }}""")
                            for b64 in chunk:
                                raw_data.extend(base64.b64decode(b64))
                            self.log(f"    提取 {end}/{buf_count} ({len(raw_data)//1024}KB)")
                        
                        # 保存原始数据
                        raw_path = os.path.join(tempfile.gettempdir(), "ani_mse_raw.bin")
                        with open(raw_path, "wb") as f:
                            f.write(raw_data)
                        self.log(f"  原始数据已保存: {raw_path} ({len(raw_data)//1024}KB)")
                        
                        # 检查是否是有效视频
                        if len(raw_data) > 16:
                            if raw_data[:4] == b'\\x00\\x00\\x00\\x1c' or b'ftyp' in bytes(raw_data[:16]):
                                self.log(f"  ★ 数据是fMP4格式! 可直接保存为视频")
                                captured["mse_data"] = raw_path
                            elif raw_data[0] == 0x47:
                                self.log(f"  ★ 数据是MPEG-TS格式!")
                                captured["mse_data"] = raw_path
                            else:
                                hex_head = " ".join(f"{b:02x}" for b in raw_data[:16])
                                self.log(f"  数据头: {hex_head}")
                    except Exception as e:
                        self.log(f"  数据提取失败: {e}")
                elif buf_count > 0:
                    self.log(f"  Buffer数据不足 ({buf_size//1024}KB < 100KB)")
                else:
                    self.log(f"  无MediaSource Buffer — 可能播放器未使用MSE")
                
            except Exception as e:
                self.log(f"  Hook分析失败: {e}")
            
        except Exception as e:
            self.log(f"  浏览器错误: {e}")
        
        # 提取Cookie
        cookies = []
        try:
            for c in ctx.cookies():
                cookies.append(f"{c['name']}={c['value']}")
        except:
            pass
        cookie_str = "; ".join(cookies) if cookies else ""
        
        browser.close()
        pw.stop()
        
        # ===== 决策: 用哪个方案 =====
        
        # 方案0 (最强): MSE Hook捕获了真实视频数据
        if "mse_data" in captured:
            self.log(f"  → 用MSE Hook数据 (猫抓模式)")
            return [(captured["mse_data"], "mse_data", cookie_str)]
        
        # 方案1: 有m3u8 → 用ffmpeg完整下载HLS (比单个ts靠谱)
        if captured["m3u8"]:
            best_m3u8 = captured["m3u8"][0]  # 第一个是iframe提取的(最准)
            self.log(f"  → 用m3u8完整下载: {best_m3u8[:80]}")
            return [(best_m3u8, "m3u8", cookie_str)]
        
        # 方案2: 找到了真实视频流 (单个ts/mp4响应)
        if captured["real_video"]:
            for r in captured["real_video"]:
                if "png" not in r["ct"] and "jpg" not in r["ct"] and "html" not in r["ct"]:
                    self.log(f"  → 用视频流: {r['ct']} {r['cl']//1024}KB")
                    return [(r["url"], "real_video", cookie_str)]
        
        # 方案3: MP4直链
        if captured["mp4"]:
            self.log(f"  → 用MP4直链")
            return [(captured["mp4"][0], "mp4", cookie_str)]
        
        # 方案4: 录制模式
        self.log(f"  → 无直接视频流, 标记为录制模式")
        return [("record:" + url, "record", cookie_str)]
    
    def record_episode(self, url, output_path, log_fn=None):
        """
        录制模式: Playwright播放 + 视频录制
        适用于 MSE/伪HLS 站点
        """
        log = log_fn or self.log
        log(f"  录制模式启动...")
        
        record_dir = tempfile.mkdtemp(prefix="ani_rec_")
        pw, browser, ctx = self._launch(record_video=True, video_dir=record_dir)
        page = ctx.new_page()
        
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            for _ in range(2):
                t = page.title()
                if t and "JavaScript" not in t and "请启用" not in t:
                    break
                time.sleep(2)
                page.reload(wait_until="domcontentloaded")
            
            # 等待页面完全加载
            time.sleep(5)
            
            # 点击播放
            log(f"  点击播放...")
            page.evaluate("""() => {
                let btns = document.querySelectorAll('.play-btn, .btn-play, .vjs-big-play-button, [class*="play"], [class*="Play"]');
                for (let b of btns) { try { b.click(); } catch(e) {} }
                let videos = document.querySelectorAll('video');
                for (let v of videos) { try { v.play(); } catch(e) {} }
            }""")
            
            # 获取视频时长
            time.sleep(3)
            duration = 0
            try:
                duration = page.evaluate("() => { let v = document.querySelector('video'); return v ? v.duration : 0; }")
            except:
                pass
            
            if not duration or duration <= 0:
                duration = 600  # 默认10分钟
                log(f"  无法获取时长, 默认录制{duration}秒")
            else:
                log(f"  视频时长: {duration:.0f}秒")
            
            # 等待视频开始播放
            log(f"  等待播放开始...")
            play_start = time.time()
            while time.time() - play_start < 15:
                try:
                    state = page.evaluate("""() => {
                        let v = document.querySelector('video');
                        return v ? {paused: v.paused, currentTime: v.currentTime, readyState: v.readyState} : null;
                    }""")
                    if state and not state.get("paused") and state.get("currentTime", 0) > 0:
                        log(f"  播放已开始 (currentTime={state['currentTime']:.1f}s)")
                        break
                except:
                    pass
                time.sleep(1)
            
            # 录制: 等待视频播完
            log(f"  录制中... (预计{duration:.0f}秒)")
            last_progress = 0
            while True:
                if self._cancel:
                    log(f"  用户取消录制")
                    break
                
                try:
                    state = page.evaluate("""() => {
                        let v = document.querySelector('video');
                        return v ? {currentTime: v.currentTime, duration: v.duration, paused: v.paused, ended: v.ended} : null;
                    }""")
                    if state:
                        current = state.get("currentTime", 0)
                        total = state.get("duration", duration)
                        
                        # 进度报告
                        if total > 0:
                            pct = current / total * 100
                            if pct - last_progress >= 5:
                                log(f"  录制进度: {pct:.0f}% ({current:.0f}/{total:.0f}s)")
                                last_progress = pct
                        
                        # 播放结束
                        if state.get("ended") or (total > 0 and current >= total - 1):
                            log(f"  播放结束")
                            break
                        
                        # 长时间没进度
                        if current == 0 and time.time() - play_start > 30:
                            log(f"  播放无进度, 停止录制")
                            break
                except:
                    pass
                
                time.sleep(2)
            
            # 停止录制, 获取视频文件
            time.sleep(2)  # 等待Playwright写入视频文件
            
            # 找录制的视频文件
            video_files = []
            for root, dirs, files in os.walk(record_dir):
                for f in files:
                    if f.endswith((".webm", ".mp4")):
                        fp = os.path.join(root, f)
                        video_files.append((fp, os.path.getsize(fp)))
            
            if not video_files:
                log(f"  未找到录制文件")
                return False
            
            # 选最大的文件
            video_files.sort(key=lambda x: -x[1])
            recorded = video_files[0][0]
            recorded_size = video_files[0][1]
            log(f"  录制文件: {recorded_size/1024/1024:.1f}MB")
            
            # 转换为mp4 (Playwright录的是webm)
            if recorded.endswith(".webm"):
                log(f"  转换webm→mp4...")
                ffmpeg = _find_ffmpeg()
                cmd = [ffmpeg, "-y", "-i", recorded, "-c:v", "libx264", "-preset", "fast",
                       "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                       "-hide_banner", "-loglevel", "warning", output_path]
                result = subprocess.run(cmd, capture_output=True, timeout=600,
                                        encoding="utf-8", errors="replace")
                if result.returncode != 0:
                    log(f"  转换失败: {result.stderr[:200]}")
                    return False
            else:
                shutil.copy2(recorded, output_path)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                sz = os.path.getsize(output_path)
                dur = _check_duration(output_path)
                log(f"  完成 {sz/1024/1024:.1f}MB" + (f" {dur:.0f}s" if dur else ""))
                return True
            
            return False
        
        except Exception as e:
            log(f"  录制失败: {e}")
            return False
        finally:
            try:
                browser.close()
                pw.stop()
            except:
                pass
            shutil.rmtree(record_dir, ignore_errors=True)


# ================================================================
# 下载引擎
# ================================================================
class DownloadEngine:
    def __init__(self, log_fn=None):
        self.log = log_fn or print
    
    def download(self, video_url, output_path, referer="", cookie="", engine=None):
        # 录制模式
        if video_url.startswith("record:"):
            actual_url = video_url[7:]
            if engine:
                return engine.record_episode(actual_url, output_path, log_fn=self.log)
            return False
        
        # MSE Hook数据 (猫抓模式: 已在浏览器内捕获)
        if "mse_data" in str(video_url) or (os.path.exists(str(video_url)) and video_url.endswith(".bin")):
            return self._save_mse_data(video_url, output_path)
        
        if "m3u8" in video_url:
            return self._download_m3u8_ffmpeg(video_url, output_path, referer, cookie)
        elif "mp4" in video_url or "real_video" in str(video_url):
            return self._download_direct(video_url, output_path, referer, cookie)
        else:
            return self._download_direct(video_url, output_path, referer, cookie)
    
    def _save_mse_data(self, mse_data_path, output_path):
        """保存MSE Hook捕获的视频数据"""
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
        if not os.path.exists(mse_data_path):
            self.log(f"  MSE数据文件不存在: {mse_data_path}")
            return False
        
        size = os.path.getsize(mse_data_path)
        self.log(f"  MSE数据: {size/1024/1024:.1f}MB")
        
        # 检查数据头判断格式
        with open(mse_data_path, "rb") as f:
            header = f.read(16)
        
        if b'ftyp' in header:
            # fMP4 — 直接重命名为mp4
            self.log(f"  fMP4格式, 直接保存")
            shutil.copy2(mse_data_path, output_path)
        elif header[0] == 0x47:
            # MPEG-TS — 用ffmpeg转mp4
            self.log(f"  MPEG-TS格式, ffmpeg转mp4...")
            ffmpeg = _find_ffmpeg()
            cmd = [ffmpeg, "-y", "-i", mse_data_path, "-c", "copy",
                   "-movflags", "+faststart", "-hide_banner", "-loglevel", "warning", output_path]
            result = subprocess.run(cmd, capture_output=True, timeout=300,
                                    encoding="utf-8", errors="replace")
            if result.returncode != 0:
                self.log(f"  转换失败: {result.stderr[:200]}")
                return False
        else:
            # 未知格式, 尝试ffmpeg
            self.log(f"  未知格式头: {header[:8].hex()}, 尝试ffmpeg...")
            ffmpeg = _find_ffmpeg()
            cmd = [ffmpeg, "-y", "-i", mse_data_path, "-c", "copy",
                   "-movflags", "+faststart", "-hide_banner", "-loglevel", "warning", output_path]
            result = subprocess.run(cmd, capture_output=True, timeout=300,
                                    encoding="utf-8", errors="replace")
            if result.returncode != 0:
                # 尝试重新编码
                cmd = [ffmpeg, "-y", "-i", mse_data_path,
                       "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
                       "-movflags", "+faststart", "-hide_banner", "-loglevel", "warning", output_path]
                result = subprocess.run(cmd, capture_output=True, timeout=600,
                                        encoding="utf-8", errors="replace")
                if result.returncode != 0:
                    self.log(f"  转换失败: {result.stderr[:200]}")
                    return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            sz = os.path.getsize(output_path)
            dur = _check_duration(output_path)
            self.log(f"  完成 {sz/1024/1024:.1f}MB" + (f" {dur:.0f}s" if dur else ""))
            return True
        return False

    def _download_direct(self, url, output_path, referer, cookie=""):
        """直接下载视频URL"""
        import requests as req
        import urllib3
        urllib3.disable_warnings()
        
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": referer,
        }
        if cookie:
            headers["Cookie"] = cookie
        
        try:
            r = req.get(url, headers=headers, verify=False, stream=True, timeout=60)
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
                dur = _check_duration(output_path)
                self.log(f"  完成 {sz/1024/1024:.1f}MB" + (f" {dur:.0f}s" if dur else ""))
                return True
        except Exception as e:
            self.log(f"  下载失败: {e}")
        return False
    
    def _download_m3u8_ffmpeg(self, m3u8_url, output_path, referer, cookie=""):
        """ffmpeg下载m3u8 (传统HLS站点用)"""
        import requests as req
        import urllib3
        urllib3.disable_warnings()
        
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
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
                try:
                    r = s.get(m3u8_url, timeout=10)
                    content = r.text
                except:
                    return False
        
        # 生成clean m3u8
        from urllib.parse import urljoin, urlparse
        lines = content.strip().split("\n")
        clean_lines = []
        ad_count = 0
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("#EXTINF"):
                if i + 1 >= len(lines):
                    break
                seg = lines[i + 1].strip()
                seg_path = urlparse(seg).path.lower()
                if any(seg_path.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                    ad_count += 1
                    i += 2
                    continue
                clean_lines.append(line)
                clean_lines.append(urljoin(m3u8_url, seg))
                i += 2
                continue
            if line.startswith("#EXT-X-MAP") or line.startswith("#EXT-X-KEY"):
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    uri = m.group(1)
                    line = line.replace(uri, urljoin(m3u8_url, uri))
                clean_lines.append(line)
                i += 1
                continue
            clean_lines.append(line)
            i += 1
        
        extinf_count = len([l for l in clean_lines if l.startswith("#EXTINF")])
        self.log(f"  {extinf_count}个segment (过滤{ad_count}个图片)")
        
        tmp = tempfile.mkdtemp(prefix="ani_m3u8_")
        try:
            clean_m3u8 = os.path.join(tmp, "clean.m3u8")
            with open(clean_m3u8, "w", encoding="utf-8") as f:
                f.write("\n".join(clean_lines))
            
            ffmpeg = _find_ffmpeg()
            headers_str = f"Referer: {referer}\r\n"
            if cookie:
                headers_str += f"Cookie: {cookie}\r\n"
            cmd = [
                ffmpeg, "-y",
                "-protocol_whitelist", "file,http,https,tcp,tls",
                "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "-headers", headers_str,
                "-i", clean_m3u8.replace("\\", "/"),
                "-c", "copy", "-movflags", "+faststart",
                "-hide_banner", output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=600,
                                    encoding="utf-8", errors="replace")
            if result.returncode != 0:
                err = result.stderr[-300:] if result.stderr else "unknown"
                self.log(f"  ffmpeg失败: {err[:200]}")
                return False
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                sz = os.path.getsize(output_path)
                dur = _check_duration(output_path)
                self.log(f"  完成 {sz/1024/1024:.1f}MB" + (f" {dur:.0f}s" if dur else ""))
                return True
            return False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ================================================================
# GUI
# ================================================================
class UniversalDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("通用动漫下载器 v4.0 — 浏览器播放 + CDP抓流 + 自动录制")
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
        tk.Label(hd, text="浏览器播放 + CDP抓流 + 自动录制", bg=BLUE, fg="#cce5ff", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=6)
        tk.Label(hd, text="v4.0", bg=BLUE, fg="white", font=("微软雅黑", 8)).pack(side=tk.RIGHT, padx=14)
        
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
                
                # 抓流
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
                
                ok = self.downloader.download(video_url, output, referer, cookie_str, engine=self.engine)
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
