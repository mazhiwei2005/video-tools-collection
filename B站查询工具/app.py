#!/usr/bin/env python3
"""B站查询工具 - 网页版 (本地匹配 + B站API)"""
import webbrowser, threading, json, os, re
from flask import Flask, request, jsonify, render_template_string
import requests as req

app = Flask(__name__)
session = req.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

# 加载本地B站标题
TITLES_FILE = os.path.join(os.path.expanduser("~"), "bilibili_titles.txt")
TITLES = []
if os.path.exists(TITLES_FILE):
    with open(TITLES_FILE, "r", encoding="utf-8") as f:
        TITLES = [line.strip() for line in f if line.strip()]
print(f"已加载 {len(TITLES)} 条B站动漫标题")

HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>B站查询工具</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#F1F2F3;font-family:"Microsoft YaHei",sans-serif;min-height:100vh}
.header{background:linear-gradient(135deg,#00A1D6,#007BB5);padding:24px 0;text-align:center;color:#fff}
.header h1{font-size:22px;letter-spacing:1px}
.header p{font-size:13px;opacity:.8;margin-top:4px}
.wrap{max-width:720px;margin:20px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);margin-bottom:16px;overflow:hidden}
.card-hd{padding:14px 18px;font-size:15px;font-weight:bold;color:#222;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:8px}
.card-bd{padding:16px 18px}
.row{display:flex;gap:10px;align-items:center}
input[type=text]{flex:1;border:1px solid #E3E5E7;border-radius:6px;padding:9px 14px;font-size:14px;outline:none;transition:.2s}
input:focus{border-color:#00A1D6;box-shadow:0 0 0 2px rgba(0,161,214,.12)}
select{border:1px solid #E3E5E7;border-radius:6px;padding:9px 10px;font-size:14px;outline:none;background:#fff}
.btn{border:none;border-radius:6px;padding:9px 20px;font-size:14px;font-weight:bold;cursor:pointer;transition:.15s}
.btn-blue{background:#00A1D6;color:#fff}
.btn-blue:hover{background:#008FBE}
.btn-gray{background:#F0F0F0;color:#333}
.btn-gray:hover{background:#E0E0E0}
.result{background:#FAFBFC;border:1px solid #F0F0F0;border-radius:8px;padding:14px;min-height:180px;max-height:440px;overflow-y:auto;font-size:13px;line-height:1.9;color:#333;white-space:pre-wrap;word-break:break-all;margin-top:12px}
.tag{display:inline-block;background:#E3F6FD;color:#00A1D6;border-radius:4px;padding:1px 8px;font-size:12px;margin-left:6px}
.tag-g{display:inline-block;background:#E8F5E9;color:#388E3C;border-radius:4px;padding:1px 8px;font-size:12px;margin-left:6px}
.tag-r{display:inline-block;background:#FFEBEE;color:#D32F2F;border-radius:4px;padding:1px 8px;font-size:12px;margin-left:6px}
.status{margin-top:10px;padding:8px 14px;border-radius:6px;font-size:13px;background:#E3F6FD;color:#00A1D6}
.status.hidden{display:none}
.line{padding:6px 0;border-bottom:1px solid #F5F5F5}
.line:last-child{border:none}
.line-title{font-weight:600;color:#222}
.actions{display:flex;gap:8px;margin-top:12px}
</style>
</head>
<body>
<div class="header">
  <h1>🎬 B站查询工具</h1>
  <p>本地 ''' + str(len(TITLES)) + ''' 部B站动漫 · 即时匹配</p>
</div>
<div class="wrap">
  <div class="card">
    <div class="card-hd">🔍 搜索B站动漫</div>
    <div class="card-bd">
      <div class="row">
        <input type="text" id="kw" placeholder="输入动漫名称，如：鬼灭、进击的巨人..." autofocus>
        <button class="btn btn-blue" onclick="doSearch()">搜索</button>
      </div>
      <div id="result" class="result">输入关键词搜索B站是否有该动漫</div>
      <div id="status" class="status hidden"></div>
      <div class="actions">
        <button class="btn btn-gray" onclick="copyResult()">📋 复制结果</button>
        <button class="btn btn-gray" onclick="clearResult()">🗑 清空</button>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-hd">📺 B站番剧索引（实时查询）</div>
    <div class="card-bd">
      <div class="row">
        <label style="white-space:nowrap">年份</label>
        <select id="year"></select>
        <label style="white-space:nowrap">类型</label>
        <select id="stype">
          <option value="1">番剧</option><option value="4">国创</option>
          <option value="2">电影</option><option value="5">电视剧</option>
        </select>
        <button class="btn btn-blue" onclick="doBili()">查询</button>
      </div>
      <div class="row" style="margin-top:8px">
        <label style="white-space:nowrap">名称</label>
        <input type="text" id="bili-kw" placeholder="输入名称筛选，如：鬼灭...（可留空查全部）">
        <button class="btn btn-blue" onclick="doBiliSearch()">名称查询</button>
        <button class="btn btn-gray" onclick="refreshCache()">🔄 刷新缓存</button>
      </div>
      <div id="bili-result" class="result" style="min-height:80px">选择年份和类型查询B站番剧列表</div>
      <div id="bili-status" class="status hidden"></div>
    </div>
  </div>
</div>

<script>
document.getElementById('kw').addEventListener('keydown',e=>{if(e.key==='Enter')doSearch()});
const ys=document.getElementById('year');
const oAll=document.createElement('option');oAll.value='all';oAll.text='所有年份';oAll.selected=true;ys.add(oAll);
for(let y=2026;y>=2000;y--){const o=document.createElement('option');o.value=y;o.text=y+'年';ys.add(o)}

function showStatus(id,msg,show){const s=document.getElementById(id);s.textContent=msg;s.classList.toggle('hidden',!show)}
function setResult(id,html){document.getElementById(id).innerHTML=html}

async function doSearch(){
  const kw=document.getElementById('kw').value.trim();
  if(!kw)return;
  showStatus('status','搜索中...',true);
  try{
    const r=await fetch('/api/search?kw='+encodeURIComponent(kw));
    const d=await r.json();
    let h='';
    if(d.exact&&d.exact.length){
      h+=`<div style="margin-bottom:8px;font-weight:bold;color:#388E3C">✅ 精确匹配 ${d.exact.length} 个</div>`;
      d.exact.forEach(t=>{h+=`<div class="line"><span class="line-title">${t}</span><span class="tag-g">B站有</span></div>`});
    }
    if(d.fuzzy&&d.fuzzy.length){
      h+=`<div style="margin:10px 0 8px;font-weight:bold;color:#00A1D6">🔍 模糊匹配 ${d.fuzzy.length} 个</div>`;
      d.fuzzy.forEach(t=>{h+=`<div class="line"><span class="line-title">${t}</span><span class="tag">相关</span></div>`});
    }
    if(!d.exact.length&&!d.fuzzy.length){
      h=`<div style="color:#D32F2F;font-weight:bold">❌ 未找到「${kw}」</div><div style="color:#999;margin-top:6px">B站可能没有这部动漫，或名称不匹配</div>`;
    }
    setResult('result',h);
    const total=d.exact.length+d.fuzzy.length;
    showStatus('status',`找到 ${total} 个结果 (${d.exact.length} 精确 + ${d.fuzzy.length} 模糊)`,true);
  }catch(e){document.getElementById('result').textContent='搜索失败: '+e;showStatus('status','搜索失败',true)}
}

async function doBili(){
  const y=document.getElementById('year').value;
  const st=document.getElementById('stype').value;
  showStatus('bili-status','查询中...',true);
  try{
    const r=await fetch(`/api/bili?year=${y}&stype=${st}`);
    const d=await r.json();
    if(!d.data||!d.data.length){document.getElementById('bili-result').textContent='无结果';showStatus('bili-status','无结果',true);return}
    let h=`<div style="margin-bottom:6px;color:#666">共 ${d.data.length} 部</div>`;
    d.data.forEach(item=>{
      h+=`<div class="line"><span class="line-title">${item.title}</span><span style="color:#999;font-size:12px;margin-left:8px">${item.order||''}</span></div>`;
    });
    setResult('bili-result',h);
    showStatus('bili-status',`共 ${d.data.length} 部`,true);
  }catch(e){document.getElementById('bili-result').textContent='查询失败: '+e;showStatus('bili-status','查询失败',true)}
}

async function refreshCache(){
  showStatus('bili-status','正在刷新缓存，首次需要几分钟...',true);
  try{
    const r=await fetch('/api/refresh_cache');
    const d=await r.json();
    if(d.success){showStatus('bili-status',`缓存刷新成功！共 ${d.count} 部动漫`,true)}
    else{showStatus('bili-status','刷新失败: '+d.error,true)}
  }catch(e){showStatus('bili-status','刷新失败: '+e,true)}
}

document.getElementById('bili-kw').addEventListener('keydown',e=>{if(e.key==='Enter')doBiliSearch()});
function copyResult(){navigator.clipboard.writeText(document.getElementById('result').textContent);showStatus('status','已复制',true)}
function clearResult(){document.getElementById('result').textContent='';showStatus('status','',false)}

async function doBiliSearch(){
  const kw=document.getElementById('bili-kw').value.trim();
  if(!kw){alert('请输入动漫名称');return}
  const st=document.getElementById('stype').value;
  showStatus('bili-status','正在搜索「'+kw+'」...',true);
  try{
    const r=await fetch(`/api/bili_search?kw=${encodeURIComponent(kw)}&stype=${st}`);
    const d=await r.json();
    if(!d.data||!d.data.length){
      document.getElementById('bili-result').textContent='未找到「'+kw+'」';
      showStatus('bili-status','无结果',true);return
    }
    let h=`<div style="margin-bottom:6px;color:#666">搜索「${kw}」找到 ${d.data.length} 部</div>`;
    d.data.forEach(item=>{
      const url=`https://www.bilibili.com/bangumi/play/ss${item.season_id}`;
      h+=`<div class="line"><a href="${url}" target="_blank" class="line-title" style="color:#00A1D6;text-decoration:none">${item.title}</a><span style="color:#999;font-size:12px;margin-left:8px">${item.order||''} · ${item.index_show||''}</span></div>`;
    });
    setResult('bili-result',h);
    showStatus('bili-status',`找到 ${d.data.length} 部`,true);
  }catch(e){document.getElementById('bili-result').textContent='查询失败: '+e;showStatus('bili-status','查询失败',true)}
}
</script>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/search')
def api_search():
    global TITLES
    kw = request.args.get('kw', '').strip()
    if not kw:
        return jsonify({"exact": [], "fuzzy": []})
    # 每次搜索时检查文件是否更新，自动重载
    if not TITLES and os.path.exists(TITLES_FILE):
        with open(TITLES_FILE, "r", encoding="utf-8") as f:
            TITLES = [line.strip() for line in f if line.strip()]
        print(f"已自动重载 {len(TITLES)} 条B站动漫标题")
    exact = [t for t in TITLES if kw in t]
    fuzzy = [t for t in TITLES if any(c in t for c in kw) and t not in exact][:30]
    return jsonify({"exact": exact[:50], "fuzzy": fuzzy})

@app.route('/api/bili')
def api_bili():
    year = request.args.get('year', '2025')
    stype = int(request.args.get('stype', 1))
    try:
        url = "https://api.bilibili.com/pgc/season/index/result"
        all_items = []
        if year == 'all':
            years = range(2026, 1999, -1)
        else:
            years = [int(year)]
        for y in years:
            params = {"st": 1, "type": 1, "season_type": stype, "year": f"[{y},{y+1})", "pagesize": 50, "page": 1}
            page = 1
            while True:
                params["page"] = page
                resp = session.get(url, params=params, timeout=15)
                data = resp.json()
                items = data.get("data", {}).get("list", [])
                if not items: break
                all_items.extend(items)
                if len(items) < 50: break
                page += 1
        return jsonify({"data": all_items})
    except Exception as e:
        return jsonify({"error": str(e), "data": []})

@app.route('/api/bili_search')
def api_bili_search():
    kw = request.args.get('kw', '').strip()
    stype = int(request.args.get('stype', 1))
    if not kw:
        return jsonify({"data": []})
    try:
        # 优先用缓存
        cache_file = os.path.join(os.path.dirname(__file__), "bili_cache.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("stype") == stype:
                items = cache.get("items", [])
                matched = [i for i in items if kw.lower() in i.get("title", "").lower()]
                return jsonify({"data": matched})
        # 无缓存则实时查询
        url = "https://api.bilibili.com/pgc/season/index/result"
        all_items = []
        for year in range(2000, 2027):
            params = {"st": 1, "type": 1, "season_type": stype, "year": f"[{year},{year+1})", "pagesize": 50, "page": 1}
            page = 1
            while True:
                params["page"] = page
                resp = session.get(url, params=params, timeout=15)
                data = resp.json()
                items = data.get("data", {}).get("list", [])
                if not items: break
                all_items.extend(items)
                if len(items) < 50: break
                page += 1
        # 保存缓存
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"stype": stype, "items": all_items, "count": len(all_items)}, f, ensure_ascii=False)
        matched = [i for i in all_items if kw.lower() in i.get("title", "").lower()]
        # 按 season_id 去重
        seen = set()
        unique = []
        for item in matched:
            sid = item.get("season_id", id(item))
            if sid not in seen:
                seen.add(sid)
                unique.append(item)
        return jsonify({"data": unique})
    except Exception as e:
        return jsonify({"error": str(e), "data": []})

@app.route('/api/refresh_cache')
def api_refresh_cache():
    """刷新缓存"""
    try:
        url = "https://api.bilibili.com/pgc/season/index/result"
        all_items = []
        for year in range(2000, 2027):
            for stype in [1]:  # 番剧
                params = {"st": 1, "type": 1, "season_type": stype, "year": f"[{year},{year+1})", "pagesize": 50, "page": 1}
                page = 1
                while True:
                    params["page"] = page
                    resp = session.get(url, params=params, timeout=15)
                    data = resp.json()
                    items = data.get("data", {}).get("list", [])
                    if not items: break
                    all_items.extend(items)
                    if len(items) < 50: break
                    page += 1
        cache_file = os.path.join(os.path.dirname(__file__), "bili_cache.json")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"stype": 1, "items": all_items, "count": len(all_items)}, f, ensure_ascii=False)
        return jsonify({"success": True, "count": len(all_items)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    port = 8766
    print(f"B站查询工具启动: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
