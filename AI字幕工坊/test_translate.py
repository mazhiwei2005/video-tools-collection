# Windows端测试翻译API
import urllib.request
import urllib.parse
import json
import time

def test_baidu_web():
    """百度翻译网页版接口"""
    print("测试百度翻译网页版...")
    try:
        # 使用百度翻译的API
        url = "https://fanyi.baidu.com/#ja/zh/こんにちは"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        print(f"  ✅ 百度翻译网页可达")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False

def test_edge_translate():
    """Edge浏览器翻译接口"""
    print("测试Edge翻译接口...")
    try:
        # Edge翻译是免费的
        url = "https://api-edge.cognitive.microsofttranslator.com/translate?api-version=3.0&from=ja&to=zh-Hans"
        data = json.dumps([{"text":"こんにちは"}]).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode('utf-8'))
        print(f"  ✅ Edge翻译可用 - {result[0]['translations'][0]['text']}")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False

def test_reverso():
    """Reverso翻译"""
    print("测试Reverso翻译...")
    try:
        url = "https://api.reverso.net/translate/v1/translation"
        data = json.dumps({
            "format": "text",
            "from": "jpn",
            "to": "chi",
            "input": "こんにちは",
            "options": {"sentenceSplitter": True, "origin": "translation.web"}
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode('utf-8'))
        print(f"  ✅ Reverso可用 - {result['translation'][0]}")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False

def test_google_web():
    """Google翻译网页"""
    print("测试Google翻译...")
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl=zh-CN&dt=t&q=こんにちは"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read().decode('utf-8'))
        print(f"  ✅ Google可用 - {result[0][0][0]}")
        return True
    except Exception as e:
        print(f"  ❌ 国内被墙")
        return False

if __name__ == "__main__":
    print("="*50)
    print("翻译API测试 (Windows网络环境)")
    print("="*50)
    
    results = {}
    results['baidu'] = test_baidu_web()
    results['edge'] = test_edge_translate()
    results['reverso'] = test_reverso()
    results['google'] = test_google_web()
    
    print("\n" + "="*50)
    print("结果汇总:")
    for k, v in results.items():
        print(f"  {k}: {'✅' if v else '❌'}")
