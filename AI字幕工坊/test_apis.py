import urllib.request
import json
import time

print("="*60)
print("🔍 翻译API国内可用性测试")
print("="*60)

results = {}

# 1. 百度翻译 (国内首选)
print("\n📌 百度翻译")
try:
    url = "https://fanyi.baidu.com/sug"
    data = "kw=你好".encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    })
    resp = urllib.request.urlopen(req, timeout=10)
    result = json.loads(resp.read())
    print(f"  ✅ 可用 - sug API正常")
    results['百度翻译'] = True
except Exception as e:
    print(f"  ❌ {e}")
    results['百度翻译'] = False

# 2. 有道翻译
print("\n📌 有道翻译")
try:
    import urllib.parse
    text = urllib.parse.quote("hello")
    url = f"https://fanyi.youdao.com/translate?&doctype=json&type=JA2ZH_CN&i={text}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode('utf-8')
    data = json.loads(raw)
    print(f"  ✅ 可用")
    results['有道翻译'] = True
except Exception as e:
    print(f"  ❌ {e}")
    results['有道翻译'] = False

# 3. 小牛翻译
print("\n📌 小牛翻译")
try:
    import urllib.parse
    text = urllib.parse.quote("hello")
    url = f"https://niutrans.com/NiuTransServer/testalign?from=en&to=zh&src={text}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode('utf-8')
    print(f"  ✅ 可用")
    results['小牛翻译'] = True
except Exception as e:
    print(f"  ❌ {e}")
    results['小牛翻译'] = False

# 4. 腾讯翻译君
print("\n📌 腾讯翻译")
try:
    url = "https://fq.imdada.cn/trans/api"
    data = json.dumps({"from":"ja","to":"zh","src_text":"こんにちは"}).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"  ✅ 可用")
    results['腾讯翻译'] = True
except Exception as e:
    print(f"  ❌ {e}")
    results['腾讯翻译'] = False

# 5. 百度翻译高级版 (需要Key但免费)
print("\n📌 百度翻译API (免费版)")
print("  ℹ️ 需要注册获取AppID和Key，每月5万字符免费")
results['百度翻译API'] = "需要Key"

# 6. MiMo API
print("\n📌 MiMo API")
import os
api_key = os.environ.get('XIAOMI_API_KEY', '')
if api_key:
    print(f"  ✅ 已配置 (Key: {api_key[:8]}...)")
    results['MiMo'] = True
else:
    print("  ⚠️ 未配置环境变量，但可在软件中配置")
    results['MiMo'] = "可配置"

# 7. Ollama本地
print("\n📌 Ollama本地翻译")
try:
    url = "http://localhost:11434/api/tags"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=3)
    print(f"  ✅ Ollama服务运行中")
    results['Ollama'] = True
except Exception as e:
    print(f"  ⚠️ Ollama未运行 (可选安装)")
    results['Ollama'] = "可选"

# 8. Google Translate (备用，国内可能被墙)
print("\n📌 Google Translate")
try:
    import urllib.parse
    text = urllib.parse.quote("hello")
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh&dt=t&q={text}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=5)
    print(f"  ✅ 可用")
    results['Google'] = True
except Exception as e:
    print(f"  ❌ 国内被墙")
    results['Google'] = False

print("\n" + "="*60)
print("📊 测试结果汇总")
print("="*60)
for name, status in results.items():
    if status == True:
        print(f"  ✅ {name}")
    elif status == False:
        print(f"  ❌ {name}")
    else:
        print(f"  ⚠️ {name} ({status})")
