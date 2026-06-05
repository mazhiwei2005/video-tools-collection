#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番薯动漫爬取器
使用Playwright绕过滑块验证，解析视频URL
"""
import re, json, time, os, sys

def test_playwright():
    """测试Playwright是否可用"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception as e:
        print(f"Playwright不可用: {e}")
        return False

def scrape_fsdm(url):
    """爬取番薯动漫页面，返回解析结果"""
    from playwright.sync_api import sync_playwright
    
    result = {"error": "未知错误"}
    
    with sync_playwright() as p:
        # 用系统Edge浏览器
        browser = p.chromium.launch(
            headless=True,
            channel="msedge",  # 使用Windows Edge
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            print(f"加载页面: {url}")
            page.goto(url, timeout=30000)
            
            # 等待guard验证完成（自动滑块或等待）
            print("等待验证...")
            time.sleep(5)
            
            # 检查是否还在guard页面
            content = page.content()
            if '_guard' in content and len(content) < 200:
                print("仍在验证页面，尝试自动滑块...")
                # 尝试模拟滑块操作
                try:
                    slider = page.query_selector('.slider-handle')
                    if slider:
                        box = slider.bounding_box()
                        if box:
                            # 从左滑到右
                            page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                            page.mouse.down()
                            for i in range(20):
                                page.mouse.move(box['x'] + box['width']/2 + (i+1)*15, box['y'] + box['height']/2)
                                time.sleep(0.05)
                            page.mouse.up()
                            time.sleep(3)
                            content = page.content()
                except Exception as e:
                    print(f"滑块操作失败: {e}")
            
            # 再等一下
            time.sleep(2)
            content = page.content()
            print(f"页面内容: {len(content)}字节")
            
            if len(content) < 500:
                result = {"error": f"页面内容过短({len(content)}字节), 验证可能未通过"}
                return result
            
            # 提取标题
            title = page.title()
            print(f"标题: {title}")
            
            # 提取player数据
            player_match = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;', content, re.S)
            if player_match:
                try:
                    d = json.loads(player_match.group(1))
                    raw_url = d.get('url', '')
                    
                    # 解码URL
                    if d.get('encrypt', 0) == 1:
                        from urllib.parse import unquote
                        raw_url = unquote(raw_url)
                    
                    print(f"视频URL: {raw_url[:150]}")
                    result = {
                        "success": True,
                        "site": "fsdm",
                        "anime_name": title.split('-')[0].strip() if '-' in title else title,
                        "url": raw_url,
                        "is_m3u8": "m3u8" in raw_url,
                        "is_mp4": "mp4" in raw_url,
                    }
                except json.JSONDecodeError:
                    result = {"error": "JSON解析失败"}
            else:
                # 试试其他播放器格式
                video_urls = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', content)
                video_urls += re.findall(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', content)
                if video_urls:
                    result = {
                        "success": True,
                        "site": "fsdm",
                        "anime_name": title,
                        "url": video_urls[0],
                        "is_m3u8": "m3u8" in video_urls[0],
                        "is_mp4": "mp4" in video_urls[0],
                    }
                else:
                    result = {"error": f"未找到视频URL (页面{len(content)}字节)"}
            
            # 提取集数信息
            ep_links = re.findall(r'href="([^"]*vodplay/[^"]*)"', content)
            if ep_links:
                result["episode_count"] = len(set(ep_links))
            
        except Exception as e:
            result = {"error": str(e)}
        finally:
            browser.close()
    
    return result


def scrape_fsdm_episodes(url):
    """爬取番薯动漫，提取所有集数链接"""
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="msedge",
            args=["--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(url, timeout=30000)
            time.sleep(5)
            
            content = page.content()
            
            # 提取所有集数链接
            # 格式: /vodplay/xxx-sid-ep.html
            ep_pattern = re.findall(r'href="([^"]*vodplay/[^"]*-([\d]+)-([\d]+)\.html)"', content)
            
            episodes = []
            seen = set()
            for full_url, sid, nid in ep_pattern:
                key = f"{sid}-{nid}"
                if key not in seen:
                    seen.add(key)
                    episodes.append({
                        "sid": int(sid),
                        "nid": int(nid),
                        "url": full_url if full_url.startswith("http") else f"https://www.fsdm02.com{full_url}"
                    })
            
            episodes.sort(key=lambda x: (x["sid"], x["nid"]))
            return episodes
        finally:
            browser.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        print(f"测试爬取: {url}")
        result = scrape_fsdm(url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法: python fsdm_scraper.py <url>")
        print("测试Playwright...")
        if test_playwright():
            print("✅ Playwright可用")
        else:
            print("❌ Playwright不可用")
