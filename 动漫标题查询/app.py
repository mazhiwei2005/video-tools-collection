#!/usr/bin/env python3
"""动漫标题查询工具 v1.0
功能: 搜索动漫 → 获取每集标题 → 保存TXT → 批量命名文件
数据源: B站 + AniList + MAL(Jikan)
"""

import os, re, json, time
from flask import Flask, render_template, request, jsonify
import urllib.request, urllib.parse

app = Flask(__name__)

# ========== 中文→日文名映射 ==========
CN_JP_MAP = {
    "进击的巨人": "進撃の巨人", "名侦探光之美少女": "名探偵プリキュア",
    "鬼灭之刃": "鬼滅の刃", "咒术回战": "呪術廻戦",
    "间谍过家家": "スパイファミリー", "电锯人": "チェンソーマン",
    "我的英雄学院": "僕のヒーローアカデミア", "刀剑神域": "ソードアート・オンライン",
    "一拳超人": "ワンパンマン", "东京喰种": "東京喰種",
    "从零开始的异世界生活": "Re:ゼロから始める異世界生活",
    "关于我转生变成史莱姆这档事": "転生したらスライムだった件",
    "无职转生": "無職転生", "约会大作战": "デート・ア・ライブ",
    "辉夜大小姐想让我告白": "かぐや様は告らせたい", "五等分的新娘": "五等分の花嫁",
    "我推的孩子": "推しの子", "葬送的芙莉莲": "葬送のフリーレン",
    "药屋少女的呢喃": "薬屋のひとりごと", "蓝色监狱": "ブルーロック",
    "排球少年": "ハイキュー!!", "黑子的篮球": "黒子のバスケ",
    "灌篮高手": "スラムダンク", "海贼王": "ONE PIECE",
    "火影忍者": "NARUTO", "龙珠": "ドラゴンボール",
    "名侦探柯南": "名探偵コナン", "哆啦A梦": "ドラえもん",
    "蜡笔小新": "クレヨンしんちゃん", "银魂": "銀魂",
    "死神": "BLEACH", "新世纪福音战士": "新世紀エヴァンゲリオン",
    "EVA": "エヴァンゲリオン", "拜托偶像公主": "アイドルプリンセスにお願い",
    "孤独摇滚": "ぼっち・ざ・ろっこ！", "赛马娘": "ウマ娘",
    "莉可丽丝": "リコリス・リコイル", "别当欧尼酱了": "お兄ちゃんはおしまい！",
    "芙莉莲": "葬送のフリーレン", "药屋少女": "薬屋のひとりごと",
    "迷宫饭": "ダンジョン飯", "吹响上低音号": "響け！ユーフォニアム",
    "青春猪头少年": "青春ブタ野郎", "86": "86―エイティシックス―",
    "国王排名": "王様ランキング", "间谍过家家": "SPY×FAMILY",
    "派对浪客诸葛孔明": "パリピ孔明", "辉夜姬": "かぐや様は告らせたい",
    "擅长捉弄的高木同学": "からかい上手の高木さん", "玉子市场": "たまこまーけっと",
    "中二病也要谈恋爱": "中二病でも恋がしたい！", "紫罗兰永恒花园": "ヴァイオレット・エヴァーガーデン",
    "命运石之门": "シュタインズ・ゲート", "心理测量者": "PSYCHO-PASS",
    "物语系列": "物語シリーズ", "魔法少女小圆": "魔法少女まどか☆マギカ",
    "天元突破": "天元突破グレンラガン", "反叛的鲁路修": "コードギアス",
}


def _get_bili_jp_title(season_id):
    """从B站番剧详情获取日文原名"""
    try:
        url = f"https://api.bilibili.com/pgc/view/web/season?season_id={season_id}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            if data.get("code") == 0:
                info = data.get("result", {})
                return info.get("jp_title", ""), info.get("alias", ""), info
    except:
        pass
    return "", "", {}


def search_bilibili(keyword):
    """搜索B站番剧"""
    try:
        # 用番剧搜索API
        url = f"https://api.bilibili.com/pgc/search/web?keyword={urllib.parse.quote(keyword)}&page=1&season_type=1"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com",
            "Cookie": "buvid3=abc123"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if isinstance(data, dict) and data.get("code") == 0:
                media_list = data.get("data", {}).get("media_list", [])
                results = []
                for item in media_list[:5]:
                    title = re.sub(r"<.*?>", "", item.get("title", ""))
                    results.append({
                        "season_id": item.get("season_id"),
                        "title": title,
                        "cover": item.get("cover", ""),
                        "ep_size": item.get("ep_size"),
                        "areas": item.get("areas", ""),
                        "score": item.get("order_score", ""),
                    })
                return results
    except Exception as e:
        print(f"B站搜索失败: {e}")

    # Fallback: 用search/type API
    try:
        url = f"https://api.bilibili.com/web/web-interface/search/type?keyword={urllib.parse.quote(keyword)}&search_type=media_bangumi"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://search.bilibili.com"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("code") == 0:
                items = data.get("data", {}).get("result", [])
                results = []
                for item in items[:5]:
                    title = re.sub(r"<.*?>", "", item.get("title", ""))
                    results.append({
                        "season_id": item.get("season_id"),
                        "title": title,
                        "cover": item.get("cover", ""),
                        "ep_size": item.get("eps_count"),
                        "areas": item.get("areas", ""),
                    })
                return results
    except:
        pass
    return []


def get_bili_episodes(season_id):
    """获取B站番剧集数"""
    try:
        url = f"https://api.bilibili.com/pgc/view/web/season?season_id={season_id}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("code") != 0:
                return None
            info = data.get("result", {})
            episodes = []
            for ep in info.get("episodes", []):
                idx = ep.get("title", "?")
                long_title = ep.get("long_title", "")
                episodes.append({
                    "episode": idx,
                    "title": f"{idx} - {long_title}" if long_title else idx,
                    "badge": ep.get("badge", ""),
                })
            return {
                "title": info.get("title", ""),
                "jp_title": info.get("jp_title", ""),
                "alias": info.get("alias", ""),
                "cover": info.get("cover", ""),
                "evaluate": info.get("evaluate", "")[:200],
                "episodes": episodes,
                "total": info.get("total", len(episodes)),
            }
    except:
        return None


def anilist_search(keyword):
    """搜索AniList"""
    query = """query($search:String){Page(page:1,perPage:5){media(search:$search,type:ANIME,sort:POPULARITY_DESC){
      id title{romaji native english} episodes status season seasonYear coverImage{large} genres
    }}}"""
    try:
        req = urllib.request.Request(
            "https://graphql.anilist.co",
            data=json.dumps({"query": query, "variables": {"search": keyword}}).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = json.loads(resp.read()).get("data", {}).get("Page", {}).get("media", [])
            return [{
                "id": m["id"],
                "title_romaji": m["title"].get("romaji", ""),
                "title_native": m["title"].get("native", ""),
                "title_english": m["title"].get("english", ""),
                "episodes": m.get("episodes"),
                "status": m.get("status", ""),
                "season": f"{m.get('season','')} {m.get('seasonYear','')}".strip(),
                "cover": m.get("coverImage", {}).get("large", ""),
                "genres": m.get("genres", []),
            } for m in items]
    except:
        return []


def anilist_detail(aid):
    """获取AniList详情"""
    query = """query($id:Int){Media(id:$id,type:ANIME){
      id title{romaji native english} episodes status season seasonYear coverImage{large}
      genres description(asHtml:false) streamingEpisodes{title url site}
      relations{edges{node{id type title{romaji native}episodes}relationType}}
    }}"""
    try:
        req = urllib.request.Request(
            "https://graphql.anilist.co",
            data=json.dumps({"query": query, "variables": {"id": aid}}).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            m = json.loads(resp.read()).get("data", {}).get("Media")
            if not m:
                return None
            eps = []
            for i, ep in enumerate(m.get("streamingEpisodes") or []):
                raw = ep.get("title", "")
                match = re.match(r"Episode\s+(\d+)\s*-\s*(.*)", raw, re.I)
                eps.append({
                    "episode": match.group(1) if match else str(i + 1),
                    "title": match.group(2).strip() if match else raw,
                })
            related = []
            for e in (m.get("relations", {}) or {}).get("edges", []):
                n = e.get("node", {})
                if n.get("type") == "ANIME":
                    related.append({
                        "id": n.get("id"),
                        "title": n.get("title", {}).get("native", ""),
                        "relation": e.get("relationType", ""),
                        "episodes": n.get("episodes"),
                    })
            desc = re.sub(r"<.*?>", "", m.get("description", "") or "")
            return {
                "id": m["id"],
                "title": m["title"].get("native", "") or m["title"].get("romaji", ""),
                "title_romaji": m["title"].get("romaji", ""),
                "title_english": m["title"].get("english", ""),
                "episodes": eps,
                "ep_count": m.get("episodes"),
                "status": m.get("status", ""),
                "season": f"{m.get('season','')} {m.get('seasonYear','')}".strip(),
                "cover": m.get("coverImage", {}).get("large", ""),
                "genres": m.get("genres", []),
                "evaluate": desc[:300],
                "related": related,
            }
    except:
        return None


def jikan_search(keyword):
    """搜索MAL(Jikan)"""
    try:
        url = f"https://api.jikan.moe/v4/anime?q={urllib.parse.quote(keyword)}&limit=5"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            items = json.loads(resp.read()).get("data", [])
            return [{
                "mal_id": a["mal_id"],
                "title": a.get("title", ""),
                "title_japanese": a.get("title_japanese", ""),
                "title_english": a.get("title_english", ""),
                "episodes": a.get("episodes"),
                "status": a.get("status", ""),
                "score": a.get("score"),
                "season": f"{a.get('season','')} {a.get('year','')}".strip(),
                "images": a.get("images", {}).get("jpg", {}).get("large_image_url", ""),
                "genres": [g.get("name", "") for g in a.get("genres", [])],
            } for a in items]
    except:
        return []


def jikan_detail(mal_id):
    """获取MAL详情"""
    try:
        req = urllib.request.Request(f"https://api.jikan.moe/v4/anime/{mal_id}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read()).get("data")
            if not data:
                return None
        # 获取集数
        eps = []
        try:
            time.sleep(0.3)
            req2 = urllib.request.Request(f"https://api.jikan.moe/v4/anime/{mal_id}/episodes?page=1", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                for e in json.loads(resp2.read()).get("data", []):
                    eps.append({
                        "episode": str(e.get("mal_id", "?")),
                        "title": e.get("title", ""),
                    })
        except:
            pass
        desc = data.get("synopsis", "") or ""
        return {
            "mal_id": data["mal_id"],
            "title": data.get("title", ""),
            "title_japanese": data.get("title_japanese", ""),
            "title_english": data.get("title_english", ""),
            "episodes": eps,
            "ep_count": data.get("episodes"),
            "status": data.get("status", ""),
            "score": data.get("score"),
            "season": f"{data.get('season','')} {data.get('year','')}".strip(),
            "cover": data.get("images", {}).get("jpg", {}).get("large_image_url", ""),
            "genres": [g.get("name", "") for g in data.get("genres", [])],
            "evaluate": desc[:300],
        }
    except:
        return None


# ========== 智能搜索（中日英一起搜）==========
def smart_search(keyword):
    """同时用中文、日文、英文搜索所有数据源"""
    results = {"bilibili": [], "anilist": [], "mal": [], "translated": False, "jp_name": ""}

    # 1. 先用中文直接搜所有源
    results["bilibili"] = search_bilibili(keyword)
    results["anilist"] = anilist_search(keyword)
    results["mal"] = jikan_search(keyword)

    # 2. 如果AniList/MAL没结果，翻译后再搜
    if not results["anilist"] and not results["mal"]:
        jp_name = CN_JP_MAP.get(keyword)
        if jp_name:
            results["translated"] = True
            results["jp_name"] = jp_name
            results["anilist"] = anilist_search(jp_name)
            results["mal"] = jikan_search(jp_name)

        # 去掉常见后缀再试
        if not results["anilist"] and not results["mal"]:
            for suffix in ["！", "!", " 第一季", " 第二季", " 第三季", " 最终季", " 剧场版", " TV"]:
                trimmed = keyword.replace(suffix, "").strip()
                if trimmed and trimmed != keyword:
                    jp2 = CN_JP_MAP.get(trimmed)
                    if jp2:
                        results["anilist"] = anilist_search(jp2)
                        results["mal"] = jikan_search(jp2)
                        if results["anilist"] or results["mal"]:
                            results["translated"] = True
                            results["jp_name"] = jp2
                            break
                    # 也用中文去AniList试（部分中国动漫有中文条目）
                    al = anilist_search(trimmed)
                    if al:
                        results["anilist"] = al
                        results["translated"] = True
                        results["jp_name"] = trimmed
                        break

    # 3. 如果B站有结果但AniList/MAL没有，用B站的日文名/别名再搜
    if (not results["anilist"] or not results["mal"]) and results["bilibili"]:
        sid = results["bilibili"][0].get("season_id")
        if sid:
            jp_title, alias, info = _get_bili_jp_title(sid)
            if jp_title and not results["anilist"]:
                al = anilist_search(jp_title)
                if al:
                    results["anilist"] = al
                    results["translated"] = True
                    results["jp_name"] = jp_title
            if jp_title and not results["mal"]:
                mal = jikan_search(jp_title)
                if mal:
                    results["mal"] = mal
            if alias and not results["anilist"]:
                for a in alias.split("\n"):
                    a = a.strip()
                    if a and a != keyword:
                        al = anilist_search(a)
                        if al:
                            results["anilist"] = al
                            results["translated"] = True
                            results["jp_name"] = a
                            break

    return results


# ========== Routes ==========
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(force=True)
    keyword = data.get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "请输入动漫名称"})
    return jsonify(smart_search(keyword))


@app.route("/api/bili_episodes", methods=["POST"])
def api_bili_episodes():
    data = request.get_json(force=True)
    sid = data.get("season_id")
    if not sid:
        return jsonify({"error": "缺少 season_id"})
    return jsonify(get_bili_episodes(sid) or {"error": "获取失败"})


@app.route("/api/anilist/<int:aid>")
def api_anilist(aid):
    info = anilist_detail(aid)
    return jsonify(info or {"error": "AniList 查询失败"})


@app.route("/api/mal/<int:mal_id>")
def api_mal(mal_id):
    info = jikan_detail(mal_id)
    return jsonify(info or {"error": "MAL 查询失败"})


@app.route("/api/save_txt", methods=["POST"])
def api_save_txt():
    """保存集数标题为TXT"""
    data = request.get_json(force=True)
    title = data.get("title", "anime")
    episodes = data.get("episodes", [])
    save_dir = data.get("save_dir", "")

    safe_name = re.sub(r'[<>:"/\\|?*]', '', title).strip() or "anime"
    content = f"# {title}\n# 共{len(episodes)}集\n\n"
    for ep in episodes:
        ep_num = ep.get("episode", "?")
        ep_title = ep.get("title", "")
        content += f"第{str(ep_num).zfill(2)}集 {ep_title}\n"

    if save_dir and os.path.isdir(save_dir):
        filepath = os.path.join(save_dir, f"{safe_name}_集数标题.txt")
    else:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = os.path.join(desktop, f"{safe_name}_集数标题.txt")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"success": True, "path": filepath, "count": len(episodes)})


@app.route("/api/browse")
def api_browse():
    """浏览文件夹"""
    path = request.args.get("path", "")
    if not path:
        # 返回磁盘列表
        drives = []
        for d in "CDEFGH":
            p = f"{d}:\\"
            if os.path.isdir(p):
                drives.append({"name": f"{d}盘", "path": p, "is_dir": True})
        return jsonify({"current": "", "items": drives})

    if not os.path.isdir(path):
        return jsonify({"error": f"路径不存在: {path}"})

    items = []
    parent = os.path.dirname(path.rstrip("\\/"))
    if parent and parent != path:
        items.append({"name": ".. 返回上级", "path": parent, "is_dir": True})
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full):
                items.append({"name": name, "path": full, "is_dir": True})
    except PermissionError:
        return jsonify({"error": "无权限"})
    return jsonify({"current": path, "items": items})


@app.route("/api/rename", methods=["POST"])
def api_rename():
    """批量重命名视频文件"""
    data = request.get_json(force=True)
    folder = data.get("folder", "")
    episodes = data.get("episodes", [])

    if not folder or not os.path.isdir(folder):
        return jsonify({"error": "文件夹不存在"})

    video_exts = {".mp4", ".mkv", ".avi", ".flv", ".mov", ".wmv", ".ts", ".rmvb"}
    files = sorted([f for f in os.listdir(folder)
                    if os.path.splitext(f)[1].lower() in video_exts])

    if not files:
        return jsonify({"error": "没有找到视频文件"})

    ep_map = {}
    for ep in episodes:
        num = str(ep.get("episode", "")).strip()
        title = ep.get("title", "").strip()
        if num and title:
            # 尝试提取纯标题（去掉前面的"X - "）
            clean = re.sub(r"^\d+\s*[-–—]\s*", "", title)
            ep_map[num] = clean

    renamed = []
    errors = []
    for i, filename in enumerate(files):
        ext = os.path.splitext(filename)[1]
        old_path = os.path.join(folder, filename)

        # 尝试从文件名提取集数
        num_match = re.search(r"(?:第|EP|ep|E)(\d+)", filename)
        ep_num = num_match.group(1) if num_match else str(i + 1)

        title = ep_map.get(ep_num, "")
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title).strip()
        if safe_title:
            new_name = f"第{ep_num.zfill(2)}集 {safe_title}{ext}"
        else:
            new_name = f"第{ep_num.zfill(2)}集{ext}"

        new_path = os.path.join(folder, new_name)
        if new_path != old_path:
            try:
                os.rename(old_path, new_path)
                renamed.append({"old": filename, "new": new_name})
            except Exception as e:
                errors.append({"file": filename, "error": str(e)})

    return jsonify({"success": True, "renamed": renamed, "errors": errors, "total": len(files)})


if __name__ == "__main__":
    print("=" * 50)
    print("  🎬 动漫标题查询工具 v1.0")
    print("  B站 + AniList + MAL · 中日英三语搜索")
    print("  http://127.0.0.1:5010")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5010, debug=False)
