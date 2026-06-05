#!/usr/bin/env python3
"""动漫集数标题查询器 v6 - AniCh + AniList + MAL
支持中文自动翻译为日文搜索，国产动漫通过AniCh查询
"""

import json, re, time, os, struct
from flask import Flask, render_template_string, request, jsonify
import requests
import urllib3
urllib3.disable_warnings()

app = Flask(__name__)

# ═══════════════════════════════════════
#  常见动漫中文→日文名映射
# ═══════════════════════════════════════
CN_JP_MAP = {
    "进击的巨人": "進撃の巨人", "名侦探光之美少女": "名探偵プリキュア",
    "光之美少女": "プリキュア", "鬼灭之刃": "鬼滅の刃", "咒术回战": "呪術廻戦",
    "间谍过家家": "スパイファミリー", "电锯人": "チェンソーマン",
    "我的英雄学院": "僕のヒーローアカデミア", "刀剑神域": "ソードアート・オンライン",
    "一拳超人": "ワンパンマン", "东京喰种": "東京喰種",
    "命运之夜": "Fate/stay night", "从零开始的异世界生活": "Re:ゼロから始める異世界生活",
    "关于我转生变成史莱姆这档事": "転生したらスライムだった件",
    "无职转生": "無職転生", "约会大作战": "デート・ア・ライブ",
    "辉夜大小姐想让我告白": "かぐや様は告らせたい", "五等分的新娘": "五等分の花嫁",
    "我推的孩子": "推しの子", "葬送的芙莉莲": "葬送のフリーレン",
    "药屋少女的呢喃": "薬屋のひとりごと", "蓝色监狱": "ブルーロック",
    "排球少年": "ハイキュー!!", "黑子的篮球": "黒子のバスケ",
    "灌篮高手": "スラムダンク", "海贼王": "ONE PIECE",
    "火影忍者": "NARUTO", "龙珠": "ドラゴンボール",
    "名侦探柯南": "名探偵コナン", "哆啦A梦": "ドラえもん",
    "蜡笔小新": "クレヨンしんちゃん", "银魂": "銀魂", "死神": "BLEACH",
    "新世纪福音战士": "新世紀エヴァンゲリオン", "EVA": "エヴァンゲリオン",
    "租借女友": "彼女、お借りします", "转生成史莱姆": "転生したらスライムだった件",
    "孤独摇滚": "ぼっち・ざ・ろっく！", "莉可丽丝": "リコリス・リコイル",
    "赛马娘": "ウマ娘", "辉夜": "かぐや様は告らせたい",
}

ANICH_API = "https://anich.sends.eu.org"
ANICH_SITE = "https://anich.emmmm.eu.org"

# ═══════════════════════════════════════
#  AniCh 搜索
# ═══════════════════════════════════════
def _read_varint(data, pos):
    val, shift = 0, 0
    while pos < len(data) and data[pos] & 0x80:
        val |= (data[pos] & 0x7f) << shift; shift += 7; pos += 1
    if pos < len(data): val |= (data[pos] & 0x7f) << shift; pos += 1
    return val, pos

def anich_search(keyword):
    """搜索AniCh，返回bangumi列表"""
    try:
        resp = requests.get(f"{ANICH_API}/bangumi/search",
                          params={"keyword": keyword}, timeout=15, verify=False)
        data = resp.content
        entries = []
        i = 0
        while i < len(data):
            if data[i] == 0x0a:
                i += 1
                length, i = _read_varint(data, i)
                end = i + length
                bangumi_id, title = 0, ''
                j = i
                while j < end:
                    tag = data[j]; fn, wt = tag >> 3, tag & 7; j += 1
                    if wt == 0:
                        val, j = _read_varint(data, j)
                        if fn == 1: bangumi_id = val
                    elif wt == 2:
                        slen, j = _read_varint(data, j)
                        if fn == 2: title = data[j:j+slen].decode('utf-8', errors='replace')
                        j += slen
                    else: break
                if bangumi_id and title:
                    entries.append({"id": bangumi_id, "title": title})
                i = end
            else: i += 1
        return entries
    except:
        return []

def anich_detail(bangumi_id):
    """获取AniCh番剧详情和集数"""
    try:
        resp = requests.get(f"{ANICH_SITE}/b/{bangumi_id}/1", timeout=20, verify=False)
        resp.encoding = 'utf-8'
        dm = re.search(r'window\.\$data\s*=\s*(\{.*?\})\s*</script>', resp.text, re.DOTALL)
        if not dm: return None
        data = json.loads(dm.group(1))
        key = f"bangumi-{bangumi_id}"
        if key not in data: return None
        bd = data[key]
        title = bd.get('data', {}).get('title', '')
        cover = bd.get('data', {}).get('cover', '')
        episodes = []
        for ep in bd.get('episodes', []):
            episodes.append({
                "index": str(ep.get('sort', '?')),
                "long_title": ep.get('title', ''),
                "status": ep.get('status', False),
            })
        return {
            "source": "anich", "id": bangumi_id, "title": title,
            "cover": cover, "episodes": episodes,
            "available": len([e for e in episodes if e['status']]),
        }
    except:
        return None

# ═══════════════════════════════════════
#  B站搜索 (直接HTTP)
# ═══════════════════════════════════════
BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}

def search_bilibili(keyword):
    """搜索B站番剧"""
    try:
        resp = requests.get("https://api.bilibili.com/pgc/search/web",
                          params={"keyword": keyword, "page": 1},
                          headers=BILI_HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0: return []
        results = []
        for item in data.get("data", {}).get("result", []):
            if item.get("type") != "bangumi": continue
            results.append({
                "season_id": item.get("season_id"),
                "title": re.sub(r'<.*?>', '', item.get("title", "")),
                "cover": item.get("cover", ""),
                "ep_size": item.get("ep_size", ""),
                "rating": item.get("order_score", ""),
            })
        return results
    except:
        return []

def get_bili_episodes(season_id):
    """获取B站番剧集数"""
    try:
        resp = requests.get("https://api.bilibili.com/pgc/view/web/season",
                          params={"season_id": season_id}, headers=BILI_HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0: return None
        info = data.get("result", {})
        episodes = []
        for ep in info.get("episodes", []):
            episodes.append({
                "index": ep.get("title", "?"),
                "long_title": ep.get("long_title", ""),
                "badge": ep.get("badge", ""),
            })
        return {
            "source": "bilibili", "title": info.get("title", ""),
            "jp_title": info.get("jp_title", ""), "alias": info.get("alias", ""),
            "cover": info.get("cover", ""), "evaluate": info.get("evaluate", ""),
            "episodes": episodes, "season_id": season_id,
        }
    except:
        return None

# ═══════════════════════════════════════
#  AniList
# ═══════════════════════════════════════
ANILIST_Q = 'query($s:String){Page(page:1,perPage:5){media(search:$s,type:ANIME,sort:POPULARITY_DESC){id title{romaji native english}episodes status season seasonYear coverImage{large}genres}}}'
ANILIST_DET = 'query($id:Int){Media(id:$id,type:ANIME){id title{romaji native english}episodes status season seasonYear coverImage{large}genres description(asHtml:false)streamingEpisodes{title url site}relations{edges{node{id type title{romaji native}episodes}relationType}}}}'

def anilist_search(keyword):
    try:
        resp = requests.post("https://graphql.anilist.co",
                           json={"query": ANILIST_Q, "variables": {"s": keyword}}, timeout=10)
        items = resp.json().get("data", {}).get("Page", {}).get("media", [])
        return [{
            "id": m["id"], "title_romaji": m["title"].get("romaji",""),
            "title_native": m["title"].get("native",""), "title_english": m["title"].get("english",""),
            "episodes": m.get("episodes"), "status": m.get("status",""),
            "season": f"{m.get('season','')} {m.get('seasonYear','')}".strip(),
            "cover": m.get("coverImage",{}).get("large",""), "genres": m.get("genres",[]),
        } for m in items]
    except: return []

def anilist_detail(aid):
    try:
        resp = requests.post("https://graphql.anilist.co",
                           json={"query": ANILIST_DET, "variables": {"id": aid}}, timeout=10)
        m = resp.json().get("data",{}).get("Media")
        if not m: return None
        eps = []
        for i, ep in enumerate(m.get("streamingEpisodes") or []):
            raw = ep.get("title","")
            match = re.match(r'Episode\s+(\d+)\s*-\s*(.*)', raw, re.I)
            eps.append({"index": match.group(1) if match else str(i+1),
                       "long_title": match.group(2).strip() if match else raw})
        return {
            "source": "anilist", "id": m["id"],
            "title": m["title"].get("native","") or m["title"].get("romaji",""),
            "title_english": m["title"].get("english",""),
            "episodes": eps, "ep_count": m.get("episodes"),
            "status": m.get("status",""), "cover": m.get("coverImage",{}).get("large",""),
            "genres": m.get("genres",[]),
        }
    except: return None

# ═══════════════════════════════════════
#  Jikan (MAL)
# ═══════════════════════════════════════
def jikan_search(keyword):
    try:
        resp = requests.get("https://api.jikan.moe/v4/anime",
                          params={"q": keyword, "limit": 5}, timeout=15)
        items = resp.json().get("data", [])
        return [{
            "mal_id": a["mal_id"], "title": a.get("title",""),
            "title_japanese": a.get("title_japanese",""), "title_english": a.get("title_english",""),
            "episodes": a.get("episodes"), "status": a.get("status",""), "score": a.get("score"),
            "season": f"{a.get('season','')} {a.get('year','')}".strip(),
            "images": a.get("images",{}).get("jpg",{}).get("large_image_url",""),
            "genres": [g.get("name","") for g in a.get("genres",[])],
        } for a in items]
    except: return []

def jikan_detail(mal_id):
    try:
        resp = requests.get(f"https://api.jikan.moe/v4/anime/{mal_id}", timeout=15)
        data = resp.json().get("data")
        if not data: return None
        eps = []
        try:
            resp2 = requests.get(f"https://api.jikan.moe/v4/anime/{mal_id}/episodes", timeout=15)
            for e in resp2.json().get("data", []):
                eps.append({"index": str(e.get("mal_id","?")), "long_title": e.get("title",""),
                           "title_japanese": e.get("title_japanese","")})
        except: pass
        return {
            "source": "jikan", "mal_id": data["mal_id"],
            "title": data.get("title",""), "title_japanese": data.get("title_japanese",""),
            "title_english": data.get("title_english",""),
            "episodes": eps, "ep_count": data.get("episodes"),
            "status": data.get("status",""), "score": data.get("score"),
            "cover": data.get("images",{}).get("jpg",{}).get("large_image_url",""),
            "genres": [g.get("name","") for g in data.get("genres",[])],
        }
    except: return None

# ═══════════════════════════════════════
#  智能搜索（中文→日文翻译）
# ═══════════════════════════════════════
def smart_translate_search(keyword):
    """尝试中文→日文翻译搜索"""
    jp = CN_JP_MAP.get(keyword)
    if jp:
        al = anilist_search(jp)
        mal = jikan_search(jp)
        if al or mal: return al, mal

    for suffix in ["！", "！", " 第一季", " 第二季", " 第三季", " 最终季", " 剧场版", " TV版", " TV"]:
        trimmed = keyword.replace(suffix, "").strip()
        if trimmed and trimmed != keyword:
            jp2 = CN_JP_MAP.get(trimmed)
            if jp2:
                al = anilist_search(jp2)
                mal = jikan_search(jp2)
                if al or mal: return al, mal
            al = anilist_search(trimmed)
            mal = jikan_search(trimmed)
            if al or mal: return al, mal
    return [], []

# ═══════════════════════════════════════
#  Flask Routes
# ═══════════════════════════════════════
@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(force=True)
    keyword = data.get("keyword","").strip()
    if not keyword: return jsonify({"anich":[], "results":[], "anilist":[], "mal":[], "videos":[]})

    # 1. AniCh（优先，国产动漫也能搜）
    anich = anich_search(keyword)

    # 2. AniList + MAL
    anilist = anilist_search(keyword)
    mal = jikan_search(keyword)

    # 3. 中文→日文翻译
    if not anilist and not mal:
        al2, mal2 = smart_translate_search(keyword)
        if al2: anilist = al2
        if mal2: mal = mal2

    # 4. B站
    bili = search_bilibili(keyword)

    # 5. 如果B站有结果但AniList/MAL没有，用B站的日文名再搜
    if (not anilist or not mal) and bili:
        sid = bili[0].get("season_id")
        if sid:
            info = get_bili_episodes(sid)
            if info:
                jp = info.get("jp_title","")
                alias = info.get("alias","")
                if jp and not anilist: anilist = anilist_search(jp)
                if jp and not mal: mal = jikan_search(jp)

    return jsonify({"anich": anich, "results": bili, "anilist": anilist, "mal": mal})

@app.route("/api/anich/<int:bid>")
def api_anich(bid):
    info = anich_detail(bid)
    if not info: return jsonify({"error": "AniCh查询失败"})
    return jsonify(info)

@app.route("/api/episodes", methods=["POST"])
def api_episodes():
    data = request.get_json(force=True)
    sid = data.get("season_id")
    if not sid: return jsonify({"error": "缺少season_id"})
    info = get_bili_episodes(sid)
    if not info: return jsonify({"error": "获取失败"})
    return jsonify(info)

@app.route("/api/anilist/<int:aid>")
def api_anilist(aid):
    info = anilist_detail(aid)
    if not info: return jsonify({"error": "AniList查询失败"})
    return jsonify(info)

@app.route("/api/mal/<int:mal_id>")
def api_mal(mal_id):
    info = jikan_detail(mal_id)
    if not info: return jsonify({"error": "MAL查询失败"})
    return jsonify(info)

@app.route("/api/save", methods=["POST"])
def api_save():
    """保存集数标题为TXT"""
    data = request.get_json(force=True)
    title = data.get("title", "anime")
    episodes = data.get("episodes", [])
    safe = re.sub(r'[<>:"/\\|?*]', '', title).strip() or "anime"
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{safe}_集数标题.txt")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n# 共{len(episodes)}集\n\n")
        for ep in episodes:
            idx = ep.get('index', '?')
            name = ep.get('long_title', '') or ep.get('title', '')
            f.write(f"第{str(idx).zfill(2)}集 {name}\n")
    return jsonify({"success": True, "path": filepath, "count": len(episodes)})

# ═══════════════════════════════════════
#  HTML
# ═══════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>动漫集数标题查询器</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei",sans-serif;background:#f1f2f3;color:#18191c;min-height:100vh}
.hdr{background:linear-gradient(135deg,#00a1d6,#0088cc);padding:20px 0;box-shadow:0 2px 8px rgba(0,161,214,.3)}
.hdr-i{max-width:960px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}
.hdr h1{color:#fff;font-size:22px;font-weight:600}
.hdr .logo{font-size:32px}
.hdr .sub{color:rgba(255,255,255,.8);font-size:13px;margin-top:2px}
.sb{max-width:960px;margin:24px auto;padding:0 20px}
.sf{display:flex;gap:10px}
.si{flex:1;height:44px;border:2px solid #e3e5e7;border-radius:8px;padding:0 16px;font-size:15px;outline:none;background:#fff}
.si:focus{border-color:#00a1d6}
.btn{height:44px;padding:0 28px;background:#00a1d6;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:500;cursor:pointer}
.btn:hover{background:#0088cc}.btn:disabled{background:#94d7ee;cursor:not-allowed}
.ra{max-width:960px;margin:0 auto;padding:0 20px 40px}
.card{background:#fff;border-radius:10px;padding:16px;display:flex;align-items:center;gap:16px;cursor:pointer;border:2px solid transparent;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.05);margin-bottom:10px}
.card:hover{border-color:#00a1d6;box-shadow:0 2px 8px rgba(0,161,214,.15);transform:translateY(-1px)}
.cv{width:60px;height:80px;border-radius:6px;object-fit:cover;background:#e3e5e7;flex-shrink:0}
.cinf{flex:1}.cinf h3{font-size:16px;font-weight:600;margin-bottom:6px}
.cinf .mt{font-size:13px;color:#9499a0;display:flex;gap:16px;flex-wrap:wrap}
.sec-t{font-size:15px;font-weight:600;color:#18191c;margin:20px 0 12px;padding-bottom:8px;border-bottom:2px solid #00a1d6;display:flex;align-items:center;gap:8px}
.det{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:20px}
.ban{background:linear-gradient(135deg,#00a1d6,#0088cc);padding:24px;color:#fff;display:flex;gap:20px;align-items:flex-start}
.ban .po{width:100px;height:133px;border-radius:8px;object-fit:cover;flex-shrink:0;box-shadow:0 4px 12px rgba(0,0,0,.3)}
.ban .ta{flex:1}.ban .ta h2{font-size:22px;font-weight:700;margin-bottom:6px}
.ban .ta .jp{font-size:14px;opacity:.85;margin-bottom:10px}
.ban .ta .tags{display:flex;gap:8px;flex-wrap:wrap}
.ban .ta .tag{background:rgba(255,255,255,.2);padding:3px 10px;border-radius:12px;font-size:12px}
.ev{padding:16px 24px;font-size:13px;color:#61666d;line-height:1.8;border-bottom:1px solid #e3e5e7}
.act{padding:12px 24px;display:flex;gap:10px;border-bottom:1px solid #e3e5e7;flex-wrap:wrap}
.ab{padding:6px 16px;border:1px solid #e3e5e7;border-radius:6px;background:#fff;color:#18191c;font-size:13px;cursor:pointer}.ab:hover{border-color:#00a1d6;color:#00a1d6}
table{width:100%;border-collapse:collapse}
th{background:#f6f7f8;padding:10px 16px;text-align:left;font-size:13px;font-weight:600;color:#61666d;border-bottom:1px solid #e3e5e7;position:sticky;top:0}
td{padding:10px 16px;font-size:14px;border-bottom:1px solid #f1f2f3}
tr:hover{background:#f6f7f8}
.epn{font-weight:600;color:#00a1d6;width:70px;white-space:nowrap}
.ebd{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500;margin-left:8px}
.ebf{background:#e8f5e9;color:#2e7d32}.ebv{background:#fff3e0;color:#e65100}
.stb{padding:10px 24px;background:#f6f7f8;font-size:12px;color:#9499a0;display:flex;justify-content:space-between}
.bb{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;background:#fff;border:1px solid #e3e5e7;border-radius:6px;color:#61666d;font-size:13px;cursor:pointer;margin-bottom:16px}.bb:hover{border-color:#00a1d6;color:#00a1d6}
.ld{text-align:center;padding:40px;color:#9499a0}
.sp{display:inline-block;width:32px;height:32px;border:3px solid #e3e5e7;border-top-color:#00a1d6;border-radius:50%;animation:spin .8s linear infinite;margin-bottom:12px}
@keyframes spin{to{transform:rotate(360deg)}}
.toast{position:fixed;bottom:30px;left:50%;transform:translateX(-50%) translateY(20px);background:rgba(0,0,0,.75);color:#fff;padding:10px 24px;border-radius:8px;font-size:14px;opacity:0;transition:all .3s;pointer-events:none;z-index:999}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;margin-left:8px}
.badge-anich{background:#ff6b9d;color:#fff}
.badge-ali{background:#f0e6ff;color:#7c3aed}
.badge-mal{background:#e8f5e9;color:#2e7d32}
.badge-bili{background:#e8f4fd;color:#00a1d6}
.jp-sub{font-size:12px;color:#61666d;margin-bottom:4px}
.auto-note{background:#fff3e0;border-radius:8px;padding:10px 16px;font-size:12px;color:#e65100;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.no-r{background:#fff;border-radius:12px;padding:30px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.no-r h3{font-size:16px;margin-bottom:12px;color:#61666d}
@media(max-width:640px){.ban{flex-direction:column;align-items:center;text-align:center}.card{flex-direction:column;text-align:center}}
</style>
</head>
<body>
<div class="hdr"><div class="hdr-i"><span class="logo">🎬</span><div><h1>动漫集数标题查询器</h1><div class="sub">AniCh + B站 + AniList + MAL · 中文自动翻译 · 支持国产动漫</div></div></div></div>
<div class="sb"><form class="sf" onsubmit="doSearch(event)"><input class="si" id="kw" placeholder="输入动漫名称（中文/日文/英文均可）..." autocomplete="off"><button class="btn" id="sbtn" type="submit">🔍 搜索</button></form></div>
<div class="ra" id="ra"></div>
<div class="toast" id="toast">✓ 已复制</div>

<script>
const ra=document.getElementById('ra'),kw=document.getElementById('kw'),sb=document.getElementById('sbtn');
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000)}
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'):''}

async function doSearch(e){
  if(e)e.preventDefault();const k=kw.value.trim();if(!k)return;
  sb.disabled=true;sb.textContent='搜索中...';
  ra.innerHTML='<div class="ld"><div class="sp"></div><div>正在搜索 AniCh + B站 + AniList + MAL...</div></div>';
  try{const r=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:k})});
  const d=await r.json();renderSearch(d,k)}
  catch(err){ra.innerHTML='<div class="ld">❌ '+esc(err.message)+'</div>'}
  sb.disabled=false;sb.textContent='🔍 搜索';
}

function renderSearch(d,kw_text){
  const anich=d.anich||[],bg=d.results||[],al=d.anilist||[],mal=d.mal||[];
  let h='<button class="bb" onclick="ra.innerHTML=\'\';kw.focus()">← 新搜索</button>';
  const hasCn=/[\u4e00-\u9fff]/.test(kw_text);
  const foundJP=al.length||mal.length;
  if(hasCn&&foundJP&&bg.length===0&&anich.length===0)
    h+=`<div class="auto-note">🔄 已自动将中文「${esc(kw_text)}」转换为日文搜索</div>`;

  // AniCh结果
  if(anich.length){
    h+='<div class="sec-t">🇯🇵 AniCh</div>';
    for(const r of anich){
      h+=`<div class="card" onclick="loadAniCh(${r.id})"><div class="cinf"><h3>${esc(r.title)}</h3><div class="mt"><span>AniCh ID: ${r.id}</span></div></div><span class="badge badge-anich">AniCh</span><span style="color:#00a1d6;font-size:20px">→</span></div>`;
    }
  }

  // B站结果
  if(bg.length){
    h+='<div class="sec-t">📺 B站番剧</div>';
    for(const r of bg){
      const c=r.cover?(r.cover.startsWith('//')?'https:'+r.cover:r.cover):'';
      const m=[];if(r.ep_size)m.push('📺 '+r.ep_size+'集');if(r.rating)m.push('⭐ '+r.rating);
      h+=`<div class="card" onclick="loadBili(${r.season_id})">${c?`<img class="cv" src="${c}" onerror="this.style.display='none'">`:''}<div class="cinf"><h3>${esc(r.title)}</h3><div class="mt">${m.map(x=>'<span>'+x+'</span>').join('')}</div></div><span class="badge badge-bili">B站</span><span style="color:#00a1d6;font-size:20px">→</span></div>`;
    }
  }

  // AniList结果
  if(al.length){
    h+='<div class="sec-t">🌐 AniList</div>';
    for(const r of al){
      const c=r.cover||'';const title=r.title_native||r.title_romaji;
      const sub=[];if(r.title_english&&r.title_english!==title)sub.push(r.title_english);
      const m=[];if(r.episodes)m.push('📺 '+r.episodes+'集');if(r.season)m.push('📅 '+r.season);if(r.status)m.push('📊 '+r.status);
      h+=`<div class="card" onclick="loadAniList(${r.id})">${c?`<img class="cv" src="${c}" onerror="this.style.display='none'">`:''}<div class="cinf"><h3>${esc(title)}</h3>${sub.length?`<div class="jp-sub">${sub.map(esc).join(' / ')}</div>`:''}<div class="mt">${m.map(x=>'<span>'+x+'</span>').join('')}</div></div><span class="badge badge-ali">AniList</span><span style="color:#00a1d6;font-size:20px">→</span></div>`;
    }
  }

  // MAL结果
  if(mal.length){
    h+='<div class="sec-t">📚 MyAnimeList</div>';
    for(const r of mal){
      const c=r.images||'';const title=r.title_japanese||r.title;
      const sub=[];if(r.title_english&&r.title_english!==title)sub.push(r.title_english);
      const m=[];if(r.episodes)m.push('📺 '+r.episodes+'集');if(r.season)m.push('📅 '+r.season);if(r.score)m.push('⭐ '+r.score);
      h+=`<div class="card" onclick="loadMAL(${r.mal_id})">${c?`<img class="cv" src="${c}" onerror="this.style.display='none'">`:''}<div class="cinf"><h3>${esc(title)}</h3>${sub.length?`<div class="jp-sub">${sub.map(esc).join(' / ')}</div>`:''}<div class="mt">${m.map(x=>'<span>'+x+'</span>').join('')}</div></div><span class="badge badge-mal">MAL</span><span style="color:#00a1d6;font-size:20px">→</span></div>`;
    }
  }

  if(!anich.length&&!bg.length&&!al.length&&!mal.length){
    h+=`<div class="no-r"><h3>😔 没有找到「${esc(kw_text)}」</h3><p>尝试：日文原名、英文名、简短关键词</p></div>`;
  }
  ra.innerHTML=h;
}

async function loadAniCh(bid){
  ra.innerHTML='<div class="ld"><div class="sp"></div><div>获取AniCh集数...</div></div>';
  try{const r=await fetch('/api/anich/'+bid);const d=await r.json();if(d.error){ra.innerHTML='<div class="ld">❌ '+esc(d.error)+'</div>';return}renderAniCh(d)}catch(e){ra.innerHTML='<div class="ld">❌ '+esc(e.message)+'</div>'}
}
async function loadBili(sid){
  ra.innerHTML='<div class="ld"><div class="sp"></div><div>获取B站集数...</div></div>';
  try{const r=await fetch('/api/episodes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({season_id:sid})});const d=await r.json();if(d.error){ra.innerHTML='<div class="ld">❌ '+esc(d.error)+'</div>';return}renderBili(d)}catch(e){ra.innerHTML='<div class="ld">❌ '+esc(e.message)+'</div>'}
}
async function loadAniList(id){
  ra.innerHTML='<div class="ld"><div class="sp"></div><div>获取AniList集数...</div></div>';
  try{const r=await fetch('/api/anilist/'+id);const d=await r.json();if(d.error){ra.innerHTML='<div class="ld">❌ '+esc(d.error)+'</div>';return}renderAniList(d)}catch(e){ra.innerHTML='<div class="ld">❌ '+esc(e.message)+'</div>'}
}
async function loadMAL(id){
  ra.innerHTML='<div class="ld"><div class="sp"></div><div>获取MAL集数...</div></div>';
  try{const r=await fetch('/api/mal/'+id);const d=await r.json();if(d.error){ra.innerHTML='<div class="ld">❌ '+esc(d.error)+'</div>';return}renderMAL(d)}catch(e){ra.innerHTML='<div class="ld">❌ '+esc(e.message)+'</div>'}
}

function renderAniCh(d){
  let h='<button class="bb" onclick="doSearch()">← 返回</button><div class="det">';
  h+=`<div class="ban"><div class="ta"><h2>${esc(d.title)}</h2><div class="tags"><span class="tag">📺 ${d.episodes.length}集</span><span class="tag">✅ ${d.available}集可用</span><span class="tag">来源: AniCh</span></div></div></div>`;
  h+=mkAct();
  h+='<table><thead><tr><th>集数</th><th>标题</th><th>状态</th></tr></thead><tbody>';
  for(const e of d.episodes){
    const st=e.status?'<span class="ebd ebf">✅ 可用</span>':'<span class="ebd ebv">❌ 待更新</span>';
    h+=`<tr><td class="epn">第${esc(e.index).padStart(2,'0')}集</td><td>${esc(e.long_title||'(无标题)')}</td><td>${st}</td></tr>`;
  }
  h+='</tbody></table>';
  h+=`<div class="stb"><span>AniCh ID: ${d.id}</span><span>${d.episodes.length}集</span></div></div>`;
  ra.innerHTML=h;window._d=d;
}

function renderBili(d){
  const c=d.cover?(d.cover.startsWith('//')?'https:'+d.cover:d.cover):'';
  let h='<button class="bb" onclick="doSearch()">← 返回</button><div class="det">';
  h+=`<div class="ban">${c?`<img class="po" src="${c}">`:''}<div class="ta"><h2>${esc(d.title)}</h2>${d.jp_title?`<div class="jp">${esc(d.jp_title)}</div>`:''}<div class="tags"><span class="tag">📺 ${d.episodes.length}集</span><span class="tag">来源: B站</span></div></div></div>`;
  if(d.evaluate)h+=`<div class="ev">${esc(d.evaluate.length>200?d.evaluate.slice(0,200)+'...':d.evaluate)}</div>`;
  h+=mkAct();h+=mkTbl(d.episodes);
  h+=`<div class="stb"><span>B站 season_id=${d.season_id}</span><span>${d.episodes.length}集</span></div></div>`;
  ra.innerHTML=h;window._d=d;
}

function renderAniList(d){
  const c=d.cover||'';const title=d.title||d.title_romaji;
  let h='<button class="bb" onclick="doSearch()">← 返回</button><div class="det">';
  h+=`<div class="ban">${c?`<img class="po" src="${c}">`:''}<div class="ta"><h2>${esc(title)}</h2>`;
  if(d.title_english&&d.title_english!==title)h+=`<div class="jp">${esc(d.title_english)}</div>`;
  const tg=[];if(d.ep_count)tg.push('📺 '+d.ep_count+'集');if(d.season)tg.push('📅 '+d.season);if(d.status)tg.push('📊 '+d.status);tg.push('来源: AniList');
  h+=`<div class="tags">${tg.map(x=>'<span class="tag">'+x+'</span>').join('')}</div></div></div>`;
  h+=mkAct();
  if(d.episodes&&d.episodes.length){h+='<table><thead><tr><th>集数</th><th>标题</th></tr></thead><tbody>';
  for(const e of d.episodes)h+=`<tr><td class="epn">EP${esc(e.index)}</td><td>${esc(e.long_title||'')}</td></tr>`;h+='</tbody></table>';}
  else h+='<div style="padding:30px;text-align:center;color:#9499a0">暂无集数标题</div>';
  h+=`<div class="stb"><span>AniList ID: ${d.id}</span><span>${d.episodes?d.episodes.length+'集':''}</span></div></div>`;
  ra.innerHTML=h;window._d=d;
}

function renderMAL(d){
  const c=d.cover||'';const title=d.title_japanese||d.title;
  let h='<button class="bb" onclick="doSearch()">← 返回</button><div class="det">';
  h+=`<div class="ban">${c?`<img class="po" src="${c}">`:''}<div class="ta"><h2>${esc(title)}</h2>`;
  if(d.title_english&&d.title_english!==title)h+=`<div class="jp">${esc(d.title_english)}</div>`;
  if(d.title&&d.title!==title&&d.title!==d.title_english)h+=`<div class="jp" style="opacity:.7">${esc(d.title)}</div>`;
  const tg=[];if(d.ep_count)tg.push('📺 '+d.ep_count+'集');if(d.season)tg.push('📅 '+d.season);if(d.score)tg.push('⭐ '+d.score);tg.push('来源: MAL');
  h+=`<div class="tags">${tg.map(x=>'<span class="tag">'+x+'</span>').join('')}</div></div></div>`;
  h+=mkAct();
  if(d.episodes&&d.episodes.length){h+='<table><thead><tr><th>集数</th><th>英文标题</th><th>日文标题</th></tr></thead><tbody>';
  for(const e of d.episodes)h+=`<tr><td class="epn">EP${esc(e.index)}</td><td>${esc(e.long_title||'')}</td><td style="font-size:13px;color:#61666d">${esc(e.title_japanese||'')}</td></tr>`;h+='</tbody></table>';}
  else h+='<div style="padding:30px;text-align:center;color:#9499a0">暂无集数标题</div>';
  h+=`<div class="stb"><span>MAL ID: ${d.mal_id}</span><span>${d.episodes?d.episodes.length+'集':''}</span></div></div>`;
  ra.innerHTML=h;window._d=d;
}

function mkAct(){return '<div class="act"><button class="ab" onclick="copyAll()">📋 复制全部</button><button class="ab" onclick="copyList()">📝 简洁列表</button><button class="ab" onclick="saveTxt()">💾 保存TXT</button></div>'}
function mkTbl(eps){let h='<table><thead><tr><th>集数</th><th>标题</th></tr></thead><tbody>';for(const e of eps){const bd=e.badge?`<span class="ebd ebf">${esc(e.badge)}</span>`:'';h+=`<tr><td class="epn">EP${esc(e.index)}</td><td>${esc(e.long_title||'')}${bd}</td></tr>`;}return h+'</tbody></table>'}
function cp(t){navigator.clipboard?navigator.clipboard.writeText(t):(()=>{const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a)})()}
function copyAll(){const d=window._d;if(!d)return;let t=(d.title||'')+'\n';for(const e of d.episodes)t+=`第${String(e.index).padStart(2,'0')}集 ${e.long_title||''}\n`;cp(t);toast('✓ 已复制全部')}
function copyList(){const d=window._d;if(!d)return;let t='';for(const e of d.episodes)t+=`${e.index}. ${e.long_title||''}\n`;cp(t);toast('✓ 已复制列表')}
async function saveTxt(){const d=window._d;if(!d)return;try{const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:d.title,episodes:d.episodes})});const j=await r.json();if(j.success)toast('✓ 已保存: '+j.path);else toast('保存失败')}catch(e){toast('保存失败: '+e.message)}}
kw.focus();
</script>
</body>
</html>"""

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("="*50)
    print("  动漫集数标题查询器 v6")
    print("  AniCh + B站 + AniList + MAL")
    print("  http://127.0.0.1:5020")
    print("="*50)
    app.run(host="0.0.0.0", port=5020, debug=False)
