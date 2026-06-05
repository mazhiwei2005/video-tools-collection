#!/usr/bin/env python3
"""B站弹幕发射器 - 完整版 (WBI签名 + SQLite历史 + 断点续传 + 爆发模式)"""
import json, os, re, ssl, sys, time, hashlib, sqlite3, urllib.parse, urllib.request, random as _rand
from http.server import HTTPServer, SimpleHTTPRequestHandler

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "danmaku_history.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS sent_danmaku (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bvid TEXT, cid INTEGER, msg TEXT, progress INTEGER,
        mode INTEGER, fontsize INTEGER, color INTEGER,
        dmid TEXT DEFAULT '', status INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime')))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fp ON sent_danmaku(bvid,cid,msg,progress,mode,fontsize,color)")
    conn.commit(); conn.close()

def db_add(bv,cid,msg,prog,mode,fs,color,dmid=''):
    c=sqlite3.connect(DB_PATH);c.execute("INSERT INTO sent_danmaku(bvid,cid,msg,progress,mode,fontsize,color,dmid,status) VALUES(?,?,?,?,?,?,?,?,0)",(bv,cid,msg,prog,mode,fs,color,dmid));c.commit();c.close()
def db_check(bv,cid,msg,prog,mode,fs,color):
    c=sqlite3.connect(DB_PATH);r=c.execute("SELECT COUNT(*) FROM sent_danmaku WHERE bvid=? AND cid=? AND msg=? AND progress=? AND mode=? AND fontsize=? AND color=? AND status IN (0,1)",(bv,cid,msg,prog,mode,fs,color)).fetchone();c.close();return r[0] if r else 0
def db_stats():
    c=sqlite3.connect(DB_PATH)
    r={"total":c.execute("SELECT COUNT(*) FROM sent_danmaku").fetchone()[0],
       "pending":c.execute("SELECT COUNT(*) FROM sent_danmaku WHERE status=0").fetchone()[0],
       "alive":c.execute("SELECT COUNT(*) FROM sent_danmaku WHERE status=1").fetchone()[0],
       "lost":c.execute("SELECT COUNT(*) FROM sent_danmaku WHERE status=2").fetchone()[0]}
    c.close();return r
def db_clear():
    c=sqlite3.connect(DB_PATH);c.execute("DELETE FROM sent_danmaku");c.commit();c.close()
def db_pending(cid):
    c=sqlite3.connect(DB_PATH);rows=c.execute("SELECT dmid,msg FROM sent_danmaku WHERE cid=? AND status=0 AND dmid!=\'\'",(cid,)).fetchall();c.close();return rows
def db_update(dmid,status):
    c=sqlite3.connect(DB_PATH);c.execute("UPDATE sent_danmaku SET status=? WHERE dmid=?",(status,dmid));c.commit();c.close()

_TAB=[46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]
_wbi={"k":None,"t":0}
def _mixin(o):return"".join(o[i]for i in _TAB)[:32]
def _keys():
    n=time.time()
    if _wbi["k"]and n-_wbi["t"]<86400:return _wbi["k"]
    ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
    req=urllib.request.Request("https://api.bilibili.com/x/web-interface/nav");req.add_header("User-Agent","Mozilla/5.0")
    with urllib.request.urlopen(req,context=ctx,timeout=10)as r:d=json.loads(r.read())
    ik=d["data"]["wbi_img"]["img_url"].rsplit("/",1)[1].split(".")[0]
    sk=d["data"]["wbi_img"]["sub_url"].rsplit("/",1)[1].split(".")[0]
    _wbi["k"]=(ik,sk);_wbi["t"]=n;return(ik,sk)
def sign_wbi(params):
    ik,sk=_keys();mk=_mixin(ik+sk);wts=round(time.time());p=dict(params);p["wts"]=wts
    p=dict(sorted(p.items()));p={k:"".join(c for c in str(v)if c not in"!\'()*")for k,v in p.items()}
    q=urllib.parse.urlencode(p);params["w_rid"]=hashlib.md5((q+mk).encode()).hexdigest();params["wts"]=wts;return params

BH={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36","Referer":"https://www.bilibili.com"}
init_db()

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>B站弹幕发射器</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Microsoft YaHei',sans-serif;background:#f5f5f5;color:#333;font-size:14px}
.top-nav{background:#fff;border-bottom:1px solid #e0e0e0;padding:0 24px;display:flex;align-items:center;height:48px}
.top-nav .logo{font-size:16px;font-weight:bold;color:#00a1d6;margin-right:32px}
.top-nav .ni{display:flex}
.top-nav .ni div{padding:12px 18px;cursor:pointer;font-size:13px;color:#666;border-bottom:2px solid transparent}
.top-nav .ni div:hover{color:#333}
.top-nav .ni div.on{color:#00a1d6;border-bottom-color:#00a1d6}
.status-bar{background:#fff;border-bottom:1px solid #e0e0e0;padding:6px 24px;font-size:12px;color:#999;display:flex;justify-content:space-between}
.status-bar .left{display:flex;gap:16px;align-items:center}
.dot{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:4px}
.dot.ok{background:#67c23a}.dot.err{background:#f56c6c}
.main{display:flex;gap:16px;padding:16px 24px;max-width:1200px;margin:0 auto}
.cp{width:420px;flex-shrink:0}
.pc{background:#fff;border:1px solid #e0e0e0;border-radius:4px;margin-bottom:12px}
.ph{display:flex;border-bottom:1px solid #e0e0e0}
.pt{padding:10px 20px;cursor:pointer;font-size:13px;color:#666;border-bottom:2px solid transparent}
.pt:hover{color:#333}.pt.on{color:#00a1d6;border-bottom-color:#00a1d6}
.pb{padding:16px}.pb.hid{display:none}
.fr{display:flex;align-items:center;margin-bottom:12px;gap:8px}
.fl{width:100px;font-size:13px;color:#666;text-align:right;flex-shrink:0}
.fl .r{color:#f56c6c;margin-left:2px}
.fi{flex:1;min-width:0}
.fi input,.fi select,.fi textarea{width:100%;padding:6px 10px;border:1px solid #dcdfe6;border-radius:3px;font-size:13px;outline:none}
.fi input:focus,.fi select:focus,.fi textarea:focus{border-color:#00a1d6}
.fi .h{font-size:11px;color:#999;margin-top:3px}
.fi .ri{display:flex;gap:8px;align-items:center}
.fi .ri span{font-size:12px;color:#999}
.br{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}
.btn{padding:7px 18px;border:1px solid #dcdfe6;border-radius:3px;cursor:pointer;font-size:13px;background:#fff;color:#606266}
.btn:hover{border-color:#00a1d6;color:#00a1d6}
.btn.pri{background:#00a1d6;color:#fff;border-color:#00a1d6}.btn.pri:hover{background:#0091c4}
.btn.dng{color:#f56c6c;border-color:#f56c6c}.btn.dng:hover{background:#f56c6c;color:#fff}
.btn:disabled{opacity:.5;cursor:not-allowed}
.lp{flex:1;min-width:0}
.lc{background:#fff;border:1px solid #e0e0e0;border-radius:4px;height:calc(100vh - 80px);display:flex;flex-direction:column}
.lh{padding:12px 16px;border-bottom:1px solid #e0e0e0;font-size:14px;font-weight:bold;display:flex;justify-content:space-between;align-items:center}
.lh button{font-size:12px;color:#999;cursor:pointer;border:none;background:none}.lh button:hover{color:#f56c6c}
.lb{flex:1;overflow-y:auto;padding:12px 16px;font-family:Consolas,monospace;font-size:12px;line-height:1.8}
.ll{padding:2px 0}.ll.s{color:#67c23a}.ll.e{color:#f56c6c}.ll.i{color:#00a1d6}.ll.w{color:#e6a23c}.ll .tm{color:#999;margin-right:6px}
.tc{display:none}.tc.on{display:block}
.cl{display:flex;align-items:center;gap:6px}.cl label{font-size:13px;color:#666;cursor:pointer}.cl input{cursor:pointer}
.fu{display:flex;align-items:center;gap:8px}.fu .fn{font-size:12px;color:#999;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fu input[type="file"]{display:none}.fu .ub{padding:5px 12px;border:1px solid #dcdfe6;border-radius:3px;cursor:pointer;font-size:12px;background:#fff}.fu .ub:hover{border-color:#00a1d6;color:#00a1d6}
.cg{display:flex;align-items:center;gap:6px}.cg input[type="color"]{width:28px;height:28px;border:1px solid #dcdfe6;border-radius:3px;cursor:pointer;padding:0;background:none}
.sr{display:flex;gap:16px;padding:8px 16px;background:#fafafa;border-radius:4px;margin-bottom:12px;font-size:12px}
.sr span{color:#666}.sr .val{font-weight:bold;color:#00a1d6}
</style>
</head>
<body>
<div class="top-nav">
<div class="logo">&#127909; B站弹幕发射器</div>
<div class="ni">
<div class="on" onclick="stab(this,'xml')">发送XML弹幕文件</div>
<div onclick="stab(this,'lrc')">发送弹幕歌词</div>
<div onclick="stab(this,'single')">发送单条弹幕</div>
<div onclick="stab(this,'batch')">发送批量弹幕</div>
<div onclick="stab(this,'fetch')">弹幕获取</div>
<div onclick="stab(this,'verify')">弹幕校验</div>
</div></div>
<div class="status-bar"><div class="left"><span><span class="dot" id="ld"></span><span id="lt">未登录</span></span><span id="vs">未选择视频</span></div><span>本地代理 · WBI签名 · SQLite历史</span></div>
<div class="main">
<div class="cp">
<div class="pc"><div class="ph"><div class="pt on" onclick="ptab(this,'basic')">基本配置</div><div class="pt" onclick="ptab(this,'adv')">更多配置</div><div class="pt" onclick="ptab(this,'delay')">延迟策略</div></div>
<div class="pb" id="p-basic">
<div class="fr"><span class="fl">账号缓存值1<span class="r">*</span></span><div class="fi"><input id="sess" placeholder="SESSDATA"></div></div>
<div class="fr"><span class="fl">账号缓存值2<span class="r">*</span></span><div class="fi"><input id="jct" placeholder="bili_jct"></div></div>
<div class="fr"><span class="fl">视频BV号<span class="r">*</span></span><div class="fi"><input id="bv" placeholder="请输入BV号或链接" oninput="debounce()"><div class="h">支持BV号、AV号或完整链接</div></div></div>
<div class="fr"><span class="fl">分P号</span><div class="fi"><div class="ri"><input type="number" id="pg" value="1" min="1"><span id="phint">共1P</span></div></div></div>
<div class="fr"><span class="fl">发送模式</span><div class="fi"><select id="sm"><option value="1">正式发送弹幕</option><option value="0">测试发送模式</option></select><div class="h">测试模式仅预览不实际发送</div></div></div>
<div class="fr"><span class="fl">弹幕池</span><div class="fi"><select id="pool"><option value="0">普通池</option><option value="1">字幕池</option></select></div></div>
<div class="fr"><span class="fl">颜色格式</span><div class="fi"><label class="cl"><input type="checkbox" id="hexc" checked> 兼容16进制颜色发送</label></div></div>
</div>
<div class="pb hid" id="p-adv">
<div class="fr"><span class="fl">首句时间</span><div class="fi"><input type="number" id="ft" placeholder="非必填，调整时间轴(秒)" step="0.1"></div></div>
<div class="fr"><span class="fl">开始句</span><div class="fi"><input type="number" id="sl" value="1" min="1"></div></div>
<div class="fr"><span class="fl">时间补偿值</span><div class="fi"><div class="ri"><input type="number" id="toff" value="0" step="100"><span>毫秒</span></div><div class="h">可正负数</div></div></div>
<div class="fr"><span class="fl">字号</span><div class="fi"><select id="fs"><option value="25">标准(25)</option><option value="18">小(18)</option><option value="36">大(36)</option></select></div></div>
<div class="fr"><span class="fl">弹幕模式</span><div class="fi"><select id="dm"><option value="1">滚动</option><option value="4">底部</option><option value="5">顶部</option></select></div></div>
<div class="fr"><span class="fl">颜色</span><div class="fi"><div class="cg"><input type="color" id="dcp" value="#ffffff" onchange="document.getElementById('dc').value=this.value.slice(1)"><input type="text" id="dc" value="FFFFFF" style="width:90px" oninput="document.getElementById('dcp').value='#'+this.value"></div></div></div>
</div>
<div class="pb hid" id="p-delay">
<div style="background:#f0f9ff;border:1px solid #b3d8ff;border-radius:4px;padding:10px 12px;margin-bottom:14px">
<div style="font-size:12px;color:#409eff;font-weight:bold;margin-bottom:8px">&#128161; 推荐配置（点击应用）</div>
<div style="display:flex;gap:6px;flex-wrap:wrap">
<button class="btn" onclick="setDelay(3,5,0,0,0)" style="font-size:11px;padding:4px 10px">自己视频 (3-5秒)</button>
<button class="btn" onclick="setDelay(5,8,0,0,0)" style="font-size:11px;padding:4px 10px">别人视频 (5-8秒)</button>
<button class="btn" onclick="setDelay(5,10,10,15,30)" style="font-size:11px;padding:4px 10px">大批量 (5-10秒+爆发)</button>
<button class="btn" onclick="setDelay(8,15,0,0,0)" style="font-size:11px;padding:4px 10px">安全保守 (8-15秒)</button>
</div>
</div>
<div class="fr"><span class="fl">普通间隔</span><div class="fi"><div class="ri"><input type="number" id="dmin" value="3" min="0.5" step="0.1" style="width:60px"><span>-</span><input type="number" id="dmax" value="5" min="0.5" step="0.1" style="width:60px"><span>秒</span></div></div></div>
<div class="fr"><span class="fl">爆发模式</span><div class="fi"><div class="ri"><span>每</span><input type="number" id="bsz" value="0" min="0" style="width:50px"><span>条后休息</span></div><div class="h">设为0禁用爆发模式</div></div></div>
<div class="fr"><span class="fl">休息时间</span><div class="fi"><div class="ri"><input type="number" id="rmin" value="10" min="1" style="width:50px"><span>-</span><input type="number" id="rmax" value="30" min="1" style="width:50px"><span>秒</span></div></div></div>
<div class="fr"><span class="fl">最大发送数</span><div class="fi"><input type="number" id="maxn" value="100" min="1"><div class="h">防止发送过多被风控</div></div></div>
<div class="sr"><span>数据库: </span><span class="val" id="st-t">0</span><span>条 | 待验证:</span><span class="val" id="st-p">0</span><span>| 已存活:</span><span class="val" id="st-a">0</span><span>| 已丢失:</span><span class="val" id="st-l">0</span></div>
<div class="br"><button class="btn" onclick="loadStats()">刷新统计</button><button class="btn dng" onclick="clearDb()">清空历史</button></div>
</div></div>
<div class="tc on" id="t-xml"><div class="pc"><div class="pb">
<div class="fr"><span class="fl">上传xml文件</span><div class="fi"><div class="fu"><label class="ub" for="xf">选择文件</label><input type="file" id="xf" accept=".xml" onchange="xfile(event)"><span class="fn" id="xfn">未选择文件</span></div></div></div>
<div class="br"><button class="btn" onclick="pxml()">预览信息</button><button class="btn pri" onclick="sxml()">发送弹幕</button><button class="btn dng" onclick="stp()">停止发送</button><button class="btn" onclick="retryFailed()" id="btn-retry1" style="display:none;color:#e6a23c;border-color:#e6a23c">重试失败</button></div>
</div></div></div>
<div class="tc" id="t-lrc"><div class="pc"><div class="pb">
<div class="fr"><span class="fl">上传歌词</span><div class="fi"><div class="fu"><label class="ub" for="lf">选择文件</label><input type="file" id="lf" accept=".lrc,.ass,.srt" onchange="lfile(event)"><span class="fn" id="lfn">未选择文件</span></div><div class="h">支持 .lrc / .ass / .srt</div></div></div>
<div class="br"><button class="btn" onclick="plrc()">预览</button><button class="btn pri" onclick="slrc()">发送</button><button class="btn dng" onclick="stp()">停止</button></div>
</div></div></div>
<div class="tc" id="t-single"><div class="pc"><div class="pb">
<div class="fr"><span class="fl">弹幕内容<span class="r">*</span></span><div class="fi"><input id="stxt" placeholder="输入弹幕内容" maxlength="100"></div></div>
<div class="fr"><span class="fl">发送时间</span><div class="fi"><div class="ri"><input type="number" id="stm" value="0" min="0" step="0.1"><span>秒</span></div></div></div>
<div class="br"><button class="btn pri" onclick="ssingle()">发送</button></div>
</div></div></div>
<div class="tc" id="t-batch"><div class="pc"><div class="pb">
<div class="fr"><span class="fl">弹幕列表</span><div class="fi"><textarea id="btxt" rows="8" style="resize:vertical;font-family:inherit" placeholder="每行一条，格式：时间(秒) 内容&#10;或只写内容（自动分配时间）"></textarea></div></div>
<div class="br"><button class="btn" onclick="pbatch()">预览</button><button class="btn pri" onclick="sbatch()">发送</button><button class="btn dng" onclick="stp()">停止</button></div>
</div></div></div>
<div class="tc" id="t-verify"><div class="pc"><div class="pb">
<div class="h" style="margin-bottom:12px">检测当前视频的弹幕存活状态，与B站在线弹幕比对</div>
<div class="br"><button class="btn pri" onclick="doVerify()">检测存活</button><button class="btn" onclick="loadStats()">刷新统计</button></div>
</div></div></div>
<div class="tc" id="t-fetch"><div class="pc">
<div class="ph"><div class="pt on" onclick="ftab(this,'fbili')">B站视频</div><div class="pt" onclick="ftab(this,'furl')">XML链接</div></div>
<div class="pb" id="ff-bili">
<div class="h" style="margin-bottom:12px">从其他B站视频抓取弹幕，加载到当前工具发送</div>
<div class="fr"><span class="fl">视频链接<span class="r">*</span></span><div class="fi"><input id="fsrc" placeholder="BV号或完整链接" oninput="debounce2()"><div class="h">输入后自动解析视频信息</div></div></div>
<div class="fr"><span class="fl">选择分P</span><div class="fi"><div class="ri"><select id="fpg" style="flex:1"><option>请先输入视频链接</option></select></div></div></div>
<div id="fpreview" style="background:#f5f7fa;border-radius:4px;padding:10px 12px;margin-bottom:12px;font-size:12px;color:#666;display:none">
<div style="margin-bottom:6px"><b>弹幕预览：</b><span id="fpcnt">0</span> 条</div>
<div id="fpcontent" style="max-height:120px;overflow-y:auto;font-family:Consolas,monospace;line-height:1.6"></div>
</div>
<div class="br">
<button class="btn" onclick="fetchBili()">获取弹幕</button>
<button class="btn pri" onclick="fetchAndLoad()">获取并加载</button>
</div>
</div>
<div class="pb hid" id="ff-url">
<div class="h" style="margin-bottom:12px">从URL加载弹幕XML文件</div>
<div class="fr"><span class="fl">XML地址<span class="r">*</span></span><div class="fi"><input id="furl" placeholder="https://example.com/danmaku.xml"></div></div>
<div class="br">
<button class="btn pri" onclick="fetchUrl()">获取并加载</button>
</div>
</div>
</div></div>
</div>
<div class="lp"><div class="lc"><div class="lh"><span>发送日志显示区域</span><button onclick="document.getElementById('log').innerHTML=''">清空日志</button></div><div class="lb" id="log"></div></div></div>
</div>
<script>
let vi=null,xd=[],ld=[],running=false,failedDms=[];
(function(){try{const c=JSON.parse(localStorage.getItem('bdm_c')||'{}');$('sess').value=c.s||'';$('jct').value=c.j||'';}catch(e){}updSt();loadStats();})();
function $(id){return document.getElementById(id);}
function stab(el,n){document.querySelectorAll('.top-nav .ni div').forEach(t=>t.classList.remove('on'));el.classList.add('on');document.querySelectorAll('.tc').forEach(t=>t.classList.remove('on'));$('t-'+n).classList.add('on');}
function ptab(el,n){el.parentElement.querySelectorAll('.pt').forEach(t=>t.classList.remove('on'));el.classList.add('on');['basic','adv','delay'].forEach(x=>$('p-'+x).classList.add('hid'));$('p-'+n).classList.remove('hid');}
function g(id){return $(id).value.trim();}
function log(m,t='i'){const el=$('log');const n=new Date();const ts=n.getHours().toString().padStart(2,'0')+':'+n.getMinutes().toString().padStart(2,'0')+':'+n.getSeconds().toString().padStart(2,'0');el.innerHTML+='<div class="ll '+t+'"><span class="tm">['+ts+']</span>'+m.replace(/</g,'&lt;')+'</div>';el.scrollTop=el.scrollHeight;}
function updSt(){const s=g('sess'),j=g('jct');if(s&&j){$('ld').className='dot ok';$('lt').textContent='Cookie已设置';}else{$('ld').className='dot err';$('lt').textContent='未设置Cookie';}}
function auth(){const s=g('sess'),j=g('jct');if(!s||!j){log('请先填写SESSDATA和bili_jct','e');return null;}return{cookie:'SESSDATA='+decodeURIComponent(s)+'; bili_jct='+decodeURIComponent(j),csrf:decodeURIComponent(j)};}
function slp(ms){return new Promise(r=>setTimeout(r,ms));}
function setDelay(dmin,dmax,bsz,rmin,rmax){$('dmin').value=dmin;$('dmax').value=dmax;$('bsz').value=bsz;$('rmin').value=rmin;$('rmax').value=rmax;log('&#9989; 已应用推荐配置: '+dmin+'-'+dmax+'秒'+(bsz>1?' +爆发模式':''),'s');}
let dt=null;function debounce(){clearTimeout(dt);dt=setTimeout(gvi,800);}
async function gvi(){
  const url=g('bv');if(!url)return;const bv=ebv(url);if(!bv)return log('无法识别链接','e');
  localStorage.setItem('bdm_c',JSON.stringify({s:g('sess'),j:g('jct')}));updSt();
  try{const r=await fetch('/api/api.bilibili.com/x/web-interface/view?'+(bv.startsWith('BV')?'bvid':'aid')+'='+bv);const d=await r.json();if(d.code!==0)throw new Error(d.message);
  const v=d.data,pages=v.pages||[];vi={aid:v.aid,cid:v.cid,bvid:v.bvid,title:v.title,pages};
  $('vs').textContent='&#127916; '+(v.title||'')+(pages.length>1?' ('+pages.length+'P)':'');
  $('phint').textContent=pages.length>1?'共'+pages.length+'P':'共1P';
  log('&#9989; 已解析: '+(v.title||'')+(pages.length>1?' ('+pages.length+'P)':'')+' cid:'+v.cid,'s');
  try{await fetch('/api/api.bilibili.com/x/web-interface/nav',{headers:{'X-Bili-Cookie':'SESSDATA='+decodeURIComponent(g('sess'))}}).then(r=>r.json()).then(d=>{if(d.code===0&&d.data&&d.data.isLogin){$('ld').className='dot ok';$('lt').textContent=d.data.uname;log('&#9989; 登录: '+d.data.uname,'s');}else log('&#9888; 未登录','w');});}catch(e){}
  }catch(e){log('&#10060; '+e.message,'e');}
}
function ebv(u){let m=u.match(/(BV[\\w]{10})/);if(m)return m[1];m=u.match(/av(\\d+)/i);if(m)return m[1];if(/^BV[\\w]{10}$/i.test(u.trim()))return u.trim();if(/^\\d+$/.test(u.trim()))return u.trim();return null;}
function cid(){if(!vi)return null;const p=vi.pages||[];if(p.length<=1)return vi.cid;const i=Math.max(0,Math.min((parseInt(g('pg'))||1)-1,p.length-1));return p[i].cid;}
function xfile(e){const f=e.target.files[0];if(!f)return;$('xfn').textContent=f.name;const r=new FileReader();r.onload=function(ev){xd=pxml2(ev.target.result);log('&#128194; '+f.name+' ('+xd.length+' 条)','i');};r.readAsText(f);}
function pxml2(xml){const doc=new DOMParser().parseFromString(xml,'text/xml'),dms=[];doc.querySelectorAll('d').forEach(d=>{const p=(d.getAttribute('p')||'').split(',');if(p.length>=4)dms.push({time:parseFloat(p[0]),mode:parseInt(p[1]),size:parseInt(p[2]),color:parseInt(p[3]),text:d.textContent||''});});return dms.sort((a,b)=>a.time-b.time);}
function pxml(){if(!xd.length)return log('请先上传XML','w');log('&#128203; 预览(前20条):','i');xd.slice(0,20).forEach(d=>{const m=Math.floor(d.time/60),s=(d.time%60).toFixed(1);log('  ['+m.toString().padStart(2,'0')+':'+s.padStart(4,'0')+'] '+d.text);});if(xd.length>20)log('  ... 共'+xd.length+'条');}
async function sxml(){if(!xd.length)return log('请先上传XML','w');if(!vi)return log('请先解析视频','w');const c=cid();if(!c)return log('无法获取cid','e');const mx=parseInt(g('maxn'))||100;log('&#128640; 发送 '+Math.min(xd.length,mx)+' 条...','i');await dosend(xd.slice(0,mx));}
function lfile(e){const f=e.target.files[0];if(!f)return;$('lfn').textContent=f.name;const r=new FileReader();r.onload=function(ev){const ext=f.name.split('.').pop().toLowerCase();if(ext==='lrc')ld=plrc2(ev.target.result);else if(ext==='srt')ld=psrt(ev.target.result);else if(ext==='ass')ld=pas(ev.target.result);else{log('不支持: '+ext,'e');return;}log('&#128194; '+f.name+' ('+ld.length+'条)','i');};r.readAsText(f);}
function plrc2(t){const lines=t.split('\\n'),dms=[];const off=parseFloat(g('ft'))||0;lines.forEach(l=>{const m=l.match(/\\[(\\d+):(\\d+\\.?\\d*)\\](.*)/);if(m)dms.push({time:parseInt(m[1])*60+parseFloat(m[2])+off,mode:parseInt(g('dm')||'1'),size:parseInt(g('fs')||'25'),color:parseInt(g('dc')||'FFFFFF',16),text:m[3].trim()});});return dms.sort((a,b)=>a.time-b.time);}
function psrt(t){const dms=[];t.split(/\\n\\s*\\n/).forEach(b=>{const ls=b.trim().split('\\n');if(ls.length<3)return;const tm=ls[1].match(/(\\d+):(\\d+):(\\d+)[,.](\\d+)\\s*-->/);if(!tm)return;const time=parseInt(tm[1])*3600+parseInt(tm[2])*60+parseInt(tm[3])+parseInt(tm[4])/1000;dms.push({time,mode:parseInt(g('dm')||'1'),size:parseInt(g('fs')||'25'),color:parseInt(g('dc')||'FFFFFF',16),text:ls.slice(2).join(' ')});});return dms.sort((a,b)=>a.time-b.time);}
function pas(t){const dms=[];t.split('\\n').forEach(l=>{if(!l.startsWith('Dialogue:'))return;const p=l.split(',',9);if(p.length<10)return;const tm=p[1].trim().match(/(\\d+):(\\d+):(\\d+)\\.(\\d+)/);if(!tm)return;const time=parseInt(tm[1])*3600+parseInt(tm[2])*60+parseInt(tm[3])+parseInt(tm[4])/100;const text=p[9].replace(/\\{[^}]*\\}/g,'').replace(/\\\\N/g,' ').replace(/\\\\n/g,' ').trim();if(text)dms.push({time,mode:parseInt(g('dm')||'1'),size:parseInt(g('fs')||'25'),color:parseInt(g('dc')||'FFFFFF',16),text});});return dms.sort((a,b)=>a.time-b.time);}
function plrc(){if(!ld.length)return log('请先上传','w');log('&#128203; 歌词预览(前20):','i');ld.slice(0,20).forEach(d=>{const m=Math.floor(d.time/60),s=(d.time%60).toFixed(1);log('  ['+m.toString().padStart(2,'0')+':'+s.padStart(4,'0')+'] '+d.text);});}
async function slrc(){if(!ld.length)return log('请先上传','w');if(!vi)return log('请先解析','w');log('&#128640; 发送 '+ld.length+' 条...','i');await dosend(ld);}
async function ssingle(){const text=g('stxt').trim();if(!text)return log('请输入内容','w');if(!vi)return log('请先解析','w');const c=cid();if(!c)return log('cid错误','e');const time=parseFloat(g('stm'))||0;log('&#128640; 发送: "'+text+'"','i');await dosend([{time,mode:parseInt(g('dm')||'1'),size:parseInt(g('fs')||'25'),color:parseInt(g('dc')||'FFFFFF',16),text}]);}
function pbp(raw){const lines=raw.split('\\n').filter(l=>l.trim()),dms=[];let t=0;const dm=parseInt(g('dm')||'1'),fs=parseInt(g('fs')||'25'),c=parseInt(g('dc')||'FFFFFF',16);for(const l of lines){const m=l.match(/^([\\d.]+)\\s+(.+)$/);if(m){dms.push({time:parseFloat(m[1]),mode:dm,size:fs,color:c,text:m[2].trim()});t=parseFloat(m[1])+1;}else{dms.push({time:t,mode:dm,size:fs,color:c,text:l.trim()});t+=1;}}return dms;}
function pbatch(){const raw=g('btxt').trim();if(!raw)return log('请输入','w');const dms=pbp(raw);log('&#128203; 批量预览('+dms.length+'条):','i');dms.slice(0,20).forEach(d=>{const m=Math.floor(d.time/60),s=(d.time%60).toFixed(1);log('  ['+m.toString().padStart(2,'0')+':'+s.padStart(4,'0')+'] '+d.text);});}
async function sbatch(){const raw=g('btxt').trim();if(!raw)return log('请输入','w');if(!vi)return log('请先解析','w');const dms=pbp(raw);log('&#128640; 发送 '+dms.length+' 条...','i');await dosend(dms);}
async function dosend(dms){
  const au=auth();if(!au)return;const c=cid();if(!c)return log('cid错误','e');
  const test=g('sm')==='0';const dmin=parseFloat(g('dmin'))||1.5,dmax=parseFloat(g('dmax'))||3.0;
  const bsz=parseInt(g('bsz'))||0,rmin=parseFloat(g('rmin'))||10,rmax=parseFloat(g('rmax'))||30;
  const toff=(parseFloat(g('toff'))||0)/1000;const pool=parseInt(g('pool'))||0;
  running=true;let ok=0,fail=0,skip=0,cnt=0;failedDms=[];
  for(let i=0;i<dms.length;i++){
    if(!running){log('&#9209; 已停止','w');break;}
    const dm=dms[i];const time=Math.max(0,dm.time+toff);
    const color=dm.color||parseInt(g('dc')||'FFFFFF',16);const mode=dm.mode||parseInt(g('dm')||'1');
    const fs=dm.size||parseInt(g('fs')||'25');
    try{const cr=await fetch('/api/history/check?'+new URLSearchParams({bvid:vi.bvid,cid:String(c),msg:dm.text,progress:String(Math.round(time*1000)),mode:String(mode),fontsize:String(fs),color:String(color)}));
    const cd=await cr.json();if(cd.count>0){skip++;log('&#9197; 跳过: "'+dm.text+'" (已发送)','w');continue;}}catch(e){}
    if(test){const m=Math.floor(time/60),s=(time%60).toFixed(1);log('  [测试] ['+m.toString().padStart(2,'0')+':'+s.padStart(4,'0')+'] '+dm.text);ok++;cnt++;}
    else{
      const rnd=Math.floor(Date.now()*1000+Math.random()*1000);
      try{const sr=await fetch('/api/wbi/sign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'1',oid:String(c),msg:dm.text,bvid:vi.bvid,progress:String(Math.round(time*1000)),mode:String(mode),fontsize:String(fs),color:String(color),pool:String(pool),rnd:String(rnd)})});const params=await sr.json();
      let retries=0;while(retries<3){
      try{const r=await fetch('/api/api.bilibili.com/x/v2/dm/post',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','X-Bili-Cookie':au.cookie},body:new URLSearchParams(Object.assign({},params,{csrf:au.csrf})).toString()});
      const d=await r.json();
      if(d.code===0){ok++;cnt++;const dmid=d.data?(d.data.dmid_str||d.data.dmid||''):'';
      const mm=Math.floor(time/60),ss=(time%60).toFixed(1);log('&#10004; ['+mm.toString().padStart(2,'0')+':'+ss.padStart(4,'0')+'] "'+dm.text+'"'+(dmid?' [ID:'+dmid.substring(0,8)+']':''),'s');
      try{await fetch('/api/history/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bvid:vi.bvid,cid:c,msg:dm.text,progress:Math.round(time*1000),mode,fontsize:fs,color,dmid})});}catch(e){}break;}
      else if(d.code===36703){retries++;log('&#9888; 频率过快，等10秒后重试 ('+retries+'/3)','w');await slp(10000);continue;}
      else if(d.code===36715){failedDms.push(dm);fail++;log('&#10060; "'+dm.text+'" &rarr; 当日发送数量已达上限','e');break;}
      else if(d.code===36701){failedDms.push(dm);fail++;log('&#10060; "'+dm.text+'" &rarr; 弹幕内容被禁止','e');break;}
      else if(d.code===36702){failedDms.push(dm);fail++;log('&#10060; "'+dm.text+'" &rarr; 弹幕长度超过100字','e');break;}
      else if(d.code===-101||d.code===-111){fail++;log('&#10060; 登录失效，请重新填写SESSDATA和bili_jct','e');running=false;break;}
      else{failedDms.push(dm);fail++;log('&#10060; "'+dm.text+'" &rarr; ['+d.code+'] '+(d.message||JSON.stringify(d)),'e');break;}
      }catch(e){failedDms.push(dm);fail++;log('&#10060; "'+dm.text+'" &rarr; '+e.message,'e');break;}
      retries++;}
      if(retries>=3){failedDms.push(dm);fail++;log('&#10060; "'+dm.text+'" 重试3次仍频率过快','e');}
      }catch(e){failedDms.push(dm);fail++;log('&#10060; 签名失败: '+e.message,'e');}
    }
    cnt++;
    if(i<dms.length-1&&running){
      let delay=dmin+Math.random()*(dmax-dmin);
      if(bsz>1&&cnt%bsz===0){delay=rmin+Math.random()*(rmax-rmin);log('&#9889; 爆发休息 '+delay.toFixed(1)+'秒...','w');}
      else log('&#9203; 等待 '+delay.toFixed(1)+'秒...','i');
      await slp(delay*1000);
    }
  }
  const retryBtn=$('btn-retry1');
  if(retryBtn)retryBtn.style.display=failedDms.length?'inline-block':'none';
  log('&#9989; 完成: 成功'+ok+' 跳过'+skip+(fail?' 失败'+fail+(failedDms.length?' (可重试)':''):''),'s');running=false;loadStats();
}
function stp(){running=false;log('&#9209; 正在停止...','w');}
async function retryFailed(){
  if(!failedDms.length)return log('没有失败的弹幕可重试','w');
  if(running)return log('正在发送中，请等待完成','w');
  const dms=[...failedDms];failedDms=[];
  log('&#128260; 重试 '+dms.length+' 条失败弹幕...','i');
  await dosend(dms);
}
async function doVerify(){
  if(!vi)return log('请先解析视频','w');const c=cid();if(!c)return;
  log('&#128269; 检测存活...','i');
  try{const r=await fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cid:c})});
  const d=await r.json();log('&#9989; 检测完成: 存活'+d.alive+' 丢失'+d.lost,'s');loadStats();}catch(e){log('&#10060; '+e.message,'e');}
}
async function loadStats(){try{const r=await fetch('/api/history/stats');const d=await r.json();$('st-t').textContent=d.total;$('st-p').textContent=d.pending;$('st-a').textContent=d.alive;$('st-l').textContent=d.lost;}catch(e){}}
async function clearDb(){if(!confirm('确定清空所有历史记录？'))return;await fetch('/api/history/clear',{method:'POST'});log('&#128465; 历史已清空','w');loadStats();}

// === 弹幕获取功能 ===
let fdm=[],fvi=null;
function ftab(el,n){el.parentElement.querySelectorAll('.pt').forEach(t=>t.classList.remove('on'));el.classList.add('on');['fbili','furl'].forEach(x=>$('ff-'+x).classList.add('hid'));$('ff-'+n).classList.remove('hid');}
let dt2=null;function debounce2(){clearTimeout(dt2);dt2=setTimeout(fetchInfo,800);}
async function fetchInfo(){
  const url=g('fsrc');if(!url)return;const bv=ebv(url);if(!bv)return log('无法识别链接','e');
  try{const r=await fetch('/api/api.bilibili.com/x/web-interface/view?'+(bv.startsWith('BV')?'bvid':'aid')+'='+bv);const d=await r.json();if(d.code!==0)throw new Error(d.message);
  const v=d.data,pages=v.pages||[];fvi={aid:v.aid,bvid:v.bvid,title:v.title,pages};
  const sel=$('fpg');sel.innerHTML='';
  pages.forEach((p,i)=>{const opt=document.createElement('option');opt.value=p.cid;opt.textContent='P'+p.page+': '+p.part+(p.duration?' ('+Math.floor(p.duration/60)+':'+(p.duration%60).toString().padStart(2,'0')+')':'');sel.appendChild(opt);});
  log('&#9989; 已解析: '+v.title+' ('+pages.length+'P)','s');
  }catch(e){log('&#10060; '+e.message,'e');}
}
async function fetchBili(){
  const sel=$('fpg');const cid=sel.value;if(!cid||isNaN(cid)){log('请先输入视频链接并选择分P','w');return null;}
  log('&#128640; 获取弹幕 CID:'+cid+'...','i');
  try{const r=await fetch('/api/fetch/bili',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cid:parseInt(cid)})});
  const d=await r.json();if(d.error)throw new Error(d.error);
  fdm=d.dms||[];$('fpcnt').textContent=fdm.length;
  const preview=fdm.slice(0,20).map(dm=>{const m=Math.floor(dm.time/60),s=(dm.time%60).toFixed(1);return '['+m.toString().padStart(2,'0')+':'+s.padStart(4,'0')+'] '+dm.text;}).join('<br>');
  $('fpcontent').innerHTML=preview+(fdm.length>20?'<br>... 共'+fdm.length+'条':'');
  $('fpreview').style.display='block';
  log('&#9989; 获取成功: '+fdm.length+' 条弹幕','s');
  return fdm;
  }catch(e){log('&#10060; '+e.message,'e');return null;}
}
async function fetchAndLoad(){
  const dms=await fetchBili();if(!dms||!dms.length)return;
  xd=dms;log('&#128194; 已加载 '+xd.length+' 条弹幕到发送队列','s');
  stab(document.querySelector('.top-nav .ni div:nth-child(1)'),'xml');
  log('&#128073; 已切换到「发送XML弹幕文件」页面，点击「发送弹幕」即可','i');
}
async function fetchUrl(){
  const url=g('furl').trim();if(!url)return log('请输入XML链接','w');
  log('&#128640; 获取: '+url,'i');
  try{const r=await fetch('/api/fetch/url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
  const d=await r.json();if(d.error)throw new Error(d.error);
  xd=d.dms||[];log('&#9989; 获取成功: '+xd.length+' 条弹幕','s');
  stab(document.querySelector('.top-nav .ni div:nth-child(1)'),'xml');
  }catch(e){log('&#10060; '+e.message,'e');}
}
</script>
</body>
</html>"""

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type, X-Bili-Cookie")
        super().end_headers()
    def do_OPTIONS(self):self.send_response(200);self.end_headers()
    def do_GET(self):
        if self.path=="/"or self.path=="/index.html":
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
        elif self.path.startswith("/api/history/check"):
            self.handle_history_check()
        elif self.path.startswith("/api/history/stats"):
            self.respond_json(db_stats())
        elif self.path.startswith("/api/"):
            self.proxy("GET")
        else:super().do_GET()
    def do_POST(self):
        if self.path=="/api/history/add":
            self.handle_history_add()
        elif self.path=="/api/history/clear":
            db_clear();self.respond_json({"ok":True})
        elif self.path=="/api/verify":
            self.handle_verify()
        elif self.path=="/api/wbi/sign":
            self.handle_wbi_sign()
        elif self.path=="/api/fetch/bili":
            self.handle_fetch_bili()
        elif self.path=="/api/fetch/url":
            self.handle_fetch_url()
        elif self.path.startswith("/api/"):
            self.proxy("POST")
        else:super().do_POST()
    def respond_json(self,data):
        self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    def handle_history_check(self):
        qs=urllib.parse.urlparse(self.path).query
        p=dict(urllib.parse.parse_qsl(qs))
        count=db_check(p.get("bvid",""),int(p.get("cid",0)),p.get("msg",""),int(p.get("progress",0)),int(p.get("mode",0)),int(p.get("fontsize",0)),int(p.get("color",0)))
        self.respond_json({"count":count})
    def handle_history_add(self):
        length=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(length))if length else{}
        db_add(body.get("bvid",""),body.get("cid",0),body.get("msg",""),body.get("progress",0),body.get("mode",0),body.get("fontsize",0),body.get("color",0),body.get("dmid",""))
        self.respond_json({"ok":True})
    def handle_wbi_sign(self):
        length=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(length))if length else{}
        signed=sign_wbi(body)
        self.respond_json(signed)
    def handle_fetch_bili(self):
        """Fetch danmaku from B站 video"""
        import zlib
        length=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(length))if length else{}
        cid=body.get("cid",0)
        if not cid:self.respond_json({"error":"no cid"});return
        ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
        try:
            req=urllib.request.Request(f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}")
            req.add_header("User-Agent","Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            req.add_header("Referer","https://www.bilibili.com/")
            with urllib.request.urlopen(req,context=ctx,timeout=20)as r:raw=r.read()
            # Try zlib decompression (B站 uses raw deflate)
            try:xml_text=zlib.decompress(raw,-zlib.MAX_WBITS).decode("utf-8","ignore")
            except:
                try:xml_text=zlib.decompress(raw).decode("utf-8","ignore")
                except:xml_text=raw.decode("utf-8","ignore")
            # Parse and convert to our format
            ET=__import__("xml.etree.ElementTree",fromlist=["ElementTree"])
            root=ET.fromstring(xml_text)
            dms=[]
            for d in root.findall("d"):
                p=(d.get("p") or "").split(",")
                if len(p)>=4:
                    dms.append({
                        "time":float(p[0]),
                        "mode":int(p[1]),
                        "size":int(p[2]),
                        "color":int(p[3]),
                        "text":(d.text or "").strip()
                    })
            dms.sort(key=lambda x:x["time"])
            self.respond_json({"ok":True,"count":len(dms),"dms":dms,"title":f"CID {cid}"})
        except Exception as e:
            self.respond_json({"error":str(e)})
    def handle_fetch_url(self):
        """Fetch danmaku XML from a URL"""
        import zlib
        length=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(length))if length else{}
        url=body.get("url","")
        if not url:self.respond_json({"error":"no url"});return
        ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
        try:
            req=urllib.request.Request(url)
            req.add_header("User-Agent","Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            with urllib.request.urlopen(req,context=ctx,timeout=20)as r:raw=r.read()
            # Try various decompression
            for attempt in [
                lambda: zlib.decompress(raw,-zlib.MAX_WBITS),
                lambda: zlib.decompress(raw),
                lambda: __import__('gzip').decompress(raw),
                lambda: raw
            ]:
                try:xml_text=attempt().decode("utf-8","ignore");break
                except:continue
            else:xml_text=raw.decode("utf-8","ignore")
            # Parse XML
            ET=__import__("xml.etree.ElementTree",fromlist=["ElementTree"])
            root=ET.fromstring(xml_text)
            dms=[]
            for d in root.findall("d"):
                p=(d.get("p") or "").split(",")
                if len(p)>=4:
                    dms.append({
                        "time":float(p[0]),
                        "mode":int(p[1]),
                        "size":int(p[2]),
                        "color":int(p[3]),
                        "text":(d.text or "").strip()
                    })
            dms.sort(key=lambda x:x["time"])
            self.respond_json({"ok":True,"count":len(dms),"dms":dms})
        except Exception as e:
            self.respond_json({"error":str(e)})
    def handle_verify(self):
        length=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(length))if length else{}
        cid=body.get("cid",0)
        if not cid:self.respond_json({"error":"no cid"});return
        ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
        req=urllib.request.Request(f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}")
        req.add_header("User-Agent","Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        req.add_header("Referer","https://www.bilibili.com/")
        with urllib.request.urlopen(req,context=ctx,timeout=30)as r:raw=r.read()
        try:
            import gzip;xml_text=gzip.decompress(raw).decode("utf-8","ignore")
        except:
            try:import zlib;xml_text=zlib.decompress(raw,-zlib.MAX_WBITS).decode("utf-8","ignore")
            except:
                try:xml_text=zlib.decompress(raw).decode("utf-8","ignore")
                except:xml_text=raw.decode("utf-8","ignore")
        doc=__import__("xml.etree.ElementTree",fromlist=["ElementTree"]).fromstring(xml_text)
        online_dmids=set()
        for d in doc.findall("d"):
            attrs=d.get("p","").split(",")
            if len(attrs)>=8:online_dmids.add(attrs[7])
        pending=db_pending(cid);alive=0;lost=0
        for dmid,msg in pending:
            if dmid in online_dmids:db_update(dmid,1);alive+=1
            else:db_update(dmid,2);lost+=1
        self.respond_json({"alive":alive,"lost":lost,"online":len(online_dmids)})
    def proxy(self,method):
        try:
            target=self.path[5:]
            if not target.startswith("http"):target="https://"+target
            length=int(self.headers.get("Content-Length",0))
            body=self.rfile.read(length)if length else None
            req=urllib.request.Request(target,data=body,method=method)
            if "X-Bili-Cookie" in self.headers:req.add_header("Cookie",self.headers["X-Bili-Cookie"])
            if "Content-Type" in self.headers:req.add_header("Content-Type",self.headers["Content-Type"])
            for k,v in BH.items():req.add_header(k,v)
            ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
            with urllib.request.urlopen(req,context=ctx,timeout=30)as resp:data=resp.read()
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(data)
        except Exception as e:
            self.send_response(500);self.send_header("Content-Type","application/json");self.end_headers()
            self.wfile.write(json.dumps({"error":str(e)}).encode())

if __name__=="__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port=8765
    server=HTTPServer(("127.0.0.1",port),Handler)
    print(f"")
    print(f"  ✅ B站弹幕发射器已启动！")
    print(f"  📺 请在浏览器打开: http://localhost:{port}")
    print(f"  🛑 按 Ctrl+C 停止")
    print(f"  💾 历史数据库: {DB_PATH}")
    print(f"")
    server.serve_forever()
