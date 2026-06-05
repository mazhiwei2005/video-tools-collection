#!/usr/bin/env python3
"""翻译引擎 - 支持多引擎翻译 + Ollama本地（优化版 v2）"""
import os, json, time
import urllib.request
import re
from typing import Dict, List, Optional

# 尝试导入translators库
try:
    import translators as ts
    TRANSLATORS_AVAILABLE = True
except:
    TRANSLATORS_AVAILABLE = False

class TranslationEngine:
    def __init__(self):
        self.engines = {
            'sogou': {'name': '搜狗翻译', 'enabled': True, 'priority': 1, 'type': 'translators'},
            'bing': {'name': '必应翻译', 'enabled': True, 'priority': 2, 'type': 'translators'},
            'alibaba': {'name': '阿里翻译', 'enabled': True, 'priority': 3, 'type': 'translators'},
            'youdao': {'name': '有道翻译', 'enabled': True, 'priority': 4, 'type': 'translators'},
            'caiyun': {'name': '彩云小译', 'enabled': True, 'priority': 5, 'type': 'translators'},
            'mimo': {'name': 'MiMo AI', 'enabled': True, 'priority': 6, 'type': 'api'},
            'ollama': {'name': 'Ollama本地', 'enabled': True, 'priority': 7, 'type': 'local'},
        }

        self.cache = {}
        self.stats = {'total': 0, 'success': 0, 'cache_hit': 0, 'engine_stats': {}}

        # 翻译风格prompt（精简版，避免Sakura混乱）
        self.style_prompts = {
            'direct': '请直译以下内容，保持原意。',
            'anime': '你是一名专业动漫字幕组翻译员。请用B站高质量字幕组风格翻译，保留口语化表达，不要机翻腔。',
            'bilibili': '请用B站风格翻译，要接地气。',
            'novel': '请用轻小说风格翻译，要优美。',
            'casual': '请用日常口语风格翻译。',
            '热血番': '热血战斗动漫风格，保持节奏感。',
            '校园番': '校园动漫风格，贴近中国学生表达。',
            '恋爱番': '恋爱动漫风格，保留暧昧语气。',
            '搞笑番': '搞笑动漫风格，允许适当本地化。',
        }

        # 语言映射
        self.lang_map = {
            'ja': 'ja', 'zh': 'zh', 'en': 'en', 'ko': 'ko',
        }

        # 动漫术语库
        self.glossary = {}
        self._load_glossary()

        # 上下文缓存（用于连续翻译）
        self._context_cache = []
        self._context_max = 5

    def _load_glossary(self):
        """加载术语库"""
        glossary_path = os.path.join(os.path.dirname(__file__), '..', 'glossary.json')
        if os.path.exists(glossary_path):
            try:
                with open(glossary_path, 'r', encoding='utf-8') as f:
                    self.glossary.update(json.load(f))
            except: pass

    def _get_config(self) -> dict:
        """读取配置文件"""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def _get_relevant_glossary(self, text: str) -> str:
        """提取文本中相关的术语"""
        if not self.glossary:
            return ""
        relevant = {k: v for k, v in self.glossary.items() if k in text}
        if relevant:
            # 最多返回10个相关术语
            items = list(relevant.items())[:10]
            return "术语参考：" + ", ".join([f"{k}→{v}" for k, v in items])
        return ""

    def translate(self, text: str, source_lang: str = 'ja', target_lang: str = 'zh',
                  engine: str = 'auto', style: str = 'direct',
                  char_settings: str = '', scene_desc: str = '') -> Dict:
        """翻译文本"""
        if not text.strip():
            return {'text': '', 'engine': 'none', 'time': 0, 'success': True}

        # 检查缓存
        cache_key = f"{text}|{source_lang}|{target_lang}|{style}"
        if cache_key in self.cache:
            self.stats['cache_hit'] += 1
            return self.cache[cache_key]

        start_time = time.time()
        result = None

        # 选择引擎
        if engine == 'auto':
            engines_to_try = sorted(self.engines.items(), key=lambda x: x[1]['priority'])
        else:
            engines_to_try = [(engine, self.engines.get(engine, {}))]

        for eng_name, eng_info in engines_to_try:
            if not eng_info.get('enabled', False):
                continue

            try:
                if eng_info.get('type') == 'translators' and TRANSLATORS_AVAILABLE:
                    result = self._translate_translators(text, source_lang, target_lang, eng_name)
                elif eng_name == 'mimo':
                    result = self._translate_mimo(text, source_lang, target_lang, style, char_settings, scene_desc)
                elif eng_name == 'ollama':
                    result = self._translate_ollama(text, source_lang, target_lang, style, char_settings, scene_desc)

                if result and result.get('success'):
                    result['engine'] = eng_name
                    result['engine_name'] = eng_info.get('name', eng_name)
                    result['time'] = round(time.time() - start_time, 2)
                    self.cache[cache_key] = result
                    self.stats['success'] += 1
                    self.stats['total'] += 1
                    if eng_name not in self.stats['engine_stats']:
                        self.stats['engine_stats'][eng_name] = {'success': 0, 'fail': 0}
                    self.stats['engine_stats'][eng_name]['success'] += 1
                    return result
            except Exception as e:
                print(f"[翻译] {eng_name} 失败: {e}")
                if eng_name not in self.stats['engine_stats']:
                    self.stats['engine_stats'][eng_name] = {'success': 0, 'fail': 0}
                self.stats['engine_stats'][eng_name]['fail'] += 1
                continue

        # 所有引擎都失败
        self.stats['total'] += 1
        return {
            'text': f'[翻译失败] {text}',
            'engine': 'none',
            'time': round(time.time() - start_time, 2),
            'success': False,
            'error': '所有翻译引擎都失败'
        }

    def translate_with_context(self, text: str, prev_lines: list = None, next_lines: list = None,
                               source_lang: str = 'ja', target_lang: str = 'zh',
                               engine: str = 'auto', style: str = 'anime',
                               anime_genre: str = '', char_settings: str = '',
                               scene_desc: str = '') -> Dict:
        """上下文感知翻译 - 给模型提供前后句上下文"""
        config = self._get_config()
        if not char_settings:
            char_settings = config.get('character_settings', '')
        if not scene_desc:
            scene_desc = config.get('scene_description', '')

        # 对于Ollama（Sakura），用简单格式避免混乱
        # 对于MiMo等强模型，可以传入上下文
        current_engine = engine
        if engine == 'auto':
            # 自动选择时，优先用MiMo（支持上下文），其次Ollama
            if self.engines.get('mimo', {}).get('enabled'):
                current_engine = 'mimo'
            elif self.engines.get('ollama', {}).get('enabled'):
                current_engine = 'ollama'

        if current_engine == 'ollama':
            # Sakura用简单格式，不传上下文（会混乱）
            return self.translate(text, source_lang, target_lang, 'ollama', style, char_settings, scene_desc)
        else:
            # MiMo等强模型，传入上下文提高翻译质量
            context_str = ""
            if prev_lines:
                context_str += f"前文：{' '.join(prev_lines[-3:])}\n"
            if next_lines:
                context_str += f"后文：{' '.join(next_lines[:2])}\n"
            if char_settings:
                context_str += f"角色设定：{char_settings}\n"
            if scene_desc:
                context_str += f"场景：{scene_desc}\n"

            if context_str:
                # 把上下文作为额外信息传给translate
                enhanced_text = f"{context_str}\n当前台词：{text}"
                return self.translate(enhanced_text, source_lang, target_lang, current_engine, style)
            else:
                return self.translate(text, source_lang, target_lang, current_engine, style)

    def post_process_asr(self, raw_text: str, segments: list = None) -> str:
        """ASR后处理：修正识别错误"""
        text = re.sub(r'(\w)\1{2,}', r'\1', raw_text)
        text = re.sub(r'([。！？])\1+', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 25:
            parts = re.split(r'([，。！？、])', text)
            if len(parts) > 2:
                text = parts[0] + parts[1]
        return text

    def update_glossary(self, term_ja: str, term_zh: str):
        """更新术语库"""
        self.glossary[term_ja] = term_zh
        glossary_path = os.path.join(os.path.dirname(__file__), '..', 'glossary.json')
        try:
            with open(glossary_path, 'w', encoding='utf-8') as f:
                json.dump(self.glossary, f, ensure_ascii=False, indent=2)
        except: pass

    def _translate_translators(self, text: str, src: str, tgt: str, engine: str) -> Dict:
        """使用translators库翻译"""
        try:
            src_lang = self.lang_map.get(src, src)
            tgt_lang = self.lang_map.get(tgt, tgt)
            result = ts.translate_text(text, translator=engine, from_language=src_lang, to_language=tgt_lang)
            if result and result.strip():
                return {'text': result.strip(), 'success': True}
            return {'text': '', 'success': False, 'error': '无结果'}
        except Exception as e:
            return {'text': '', 'success': False, 'error': str(e)}

    def _translate_mimo(self, text: str, src: str, tgt: str, style: str,
                        char_settings: str = '', scene_desc: str = '') -> Dict:
        """MiMo AI翻译（支持上下文）"""
        config = self._get_config()
        api_key = os.environ.get('XIAOMI_API_KEY', '') or config.get('mimo_api_key', '')

        if not api_key:
            return {'text': '', 'success': False, 'error': '未配置API Key'}

        try:
            lang_map = {'ja': '日语', 'zh': '中文', 'en': '英文'}
            src_name = lang_map.get(src, src)
            tgt_name = lang_map.get(tgt, tgt)
            style_prompt = self.style_prompts.get(style, self.style_prompts['direct'])

            # 构建上下文信息
            context_parts = []
            if char_settings:
                context_parts.append(f"【角色设定】{char_settings}")
            if scene_desc:
                context_parts.append(f"（场景：{scene_desc}）")

            # 提取相关术语
            glossary_hint = self._get_relevant_glossary(text)
            if glossary_hint:
                context_parts.append(glossary_hint)

            context_str = "\n".join(context_parts) if context_parts else ""

            prompt = f"""{style_prompt}
{context_str}

请将以下{src_name}内容翻译为{tgt_name}，只返回翻译结果："""

            url = "https://api.xiaomi.com/v1/chat/completions"
            data = json.dumps({
                "model": "mimo-v2.5-pro",
                "messages": [
                    {"role": "system", "content": "你是一个专业的动漫字幕翻译员，擅长将日语动漫台词翻译成自然流畅的中文。"},
                    {"role": "user", "content": f"{prompt}\n{text}"}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }).encode('utf-8')

            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "AI字幕工坊/1.0"
            })
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode('utf-8'))
            translated = result['choices'][0]['message']['content'].strip()

            # 后处理
            translated = self._clean_translation(translated)

            return {'text': translated, 'success': True}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {'text': '', 'success': False, 'error': 'MiMo API Key无效'}
            return {'text': '', 'success': False, 'error': f'MiMo API错误: HTTP {e.code}'}
        except Exception as e:
            return {'text': '', 'success': False, 'error': f'MiMo错误: {str(e)}'}

    def _translate_ollama(self, text: str, src: str, tgt: str, style: str,
                          char_settings: str = '', scene_desc: str = '') -> Dict:
        """Ollama本地翻译（Sakura专用格式）"""
        config = self._get_config()
        model_name = config.get('ollama_model', 'sakura')

        # 从参数或配置获取角色设定和场景描述
        if not char_settings:
            char_settings = config.get('character_settings', '')
        if not scene_desc:
            scene_desc = config.get('scene_description', '')

        try:
            url = "http://localhost:11434/api/generate"

            # 根据模型选择不同的prompt格式
            if 'sakura' in model_name.lower():
                # Sakura专用格式：简单直接，不要复杂prompt
                # 注入角色设定作为system prompt的一部分
                system_parts = ["你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格翻译日文，并能正确处理特殊角色名和专有名词。"]
                if char_settings:
                    system_parts.append(f"角色设定：{char_settings}")
                if scene_desc:
                    system_parts.append(f"场景：{scene_desc}")

                # 提取相关术语
                glossary_hint = self._get_relevant_glossary(text)
                if glossary_hint:
                    system_parts.append(glossary_hint)

                system_prompt = "\n".join(system_parts)

                prompt = f"将下面的日文文本翻译成中文。\n日文：{text}\n中文："
                data = json.dumps({
                    "model": model_name,
                    "system": system_prompt,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1,
                    "repeat_penalty": 1.0
                }).encode('utf-8')
            else:
                # Qwen2.5等其他模型：可以用更详细的prompt
                style_prompt = self.style_prompts.get(style, self.style_prompts['direct'])
                context_parts = []
                if char_settings:
                    context_parts.append(f"【角色设定】{char_settings}")
                if scene_desc:
                    context_parts.append(f"（场景：{scene_desc}）")

                # 提取相关术语
                glossary_hint = self._get_relevant_glossary(text)
                if glossary_hint:
                    context_parts.append(glossary_hint)

                context_str = "\n".join(context_parts) if context_parts else ""

                lang_map = {'ja': '日语', 'zh': '中文', 'en': '英文'}
                src_name = lang_map.get(src, src)
                tgt_name = lang_map.get(tgt, tgt)

                system_prompt = "你是一个专业的动漫字幕翻译员，擅长将日语动漫台词翻译成自然流畅的中文。"

                if context_str:
                    prompt = f"{style_prompt}\n{context_str}\n将以下{src_name}翻译为{tgt_name}：\n{text}\n只返回翻译结果："
                else:
                    prompt = f"{style_prompt}\n将以下{src_name}翻译为{tgt_name}：\n{text}\n只返回翻译结果："
                data = json.dumps({
                    "model": model_name,
                    "system": system_prompt,
                    "prompt": prompt,
                    "stream": False
                }).encode('utf-8')

            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/json"
            })
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read().decode('utf-8'))

            translated = result.get('response', '').strip()
            if translated:
                # 后处理
                translated = self._clean_translation(translated, is_sakura='sakura' in model_name.lower())
                return {'text': translated, 'success': True}
            return {'text': '', 'success': False, 'error': 'Ollama返回空响应'}
        except urllib.error.URLError as e:
            return {'text': '', 'success': False, 'error': f'Ollama连接失败，请确认Ollama已启动 (ollama serve)'}
        except Exception as e:
            return {'text': '', 'success': False, 'error': f'Ollama错误: {str(e)}'}

    def _clean_translation(self, text: str, is_sakura: bool = False) -> str:
        """清理翻译结果"""
        if not text:
            return text

        # 1. 移除常见前缀
        prefixes = ["翻译：", "翻译:", "译文：", "译文:", "中文：", "中文:", "结果：", "结果:",
                     "修正后：", "修正后:", "校对后：", "校对后:", "输出：", "输出:"]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # 2. Sakura特殊处理：移除乱码中文名前缀（2-4个汉字+换行）
        if is_sakura and "\n" in text:
            parts = text.split("\n", 1)
            first_line = parts[0].strip()
            if re.match(r'^[\u4e00-\u9fff]{2,4}$', first_line):
                text = parts[1].strip()

        # 3. 移除开头的引号（如果翻译结果被包裹）
        if text and text[0] in '「『"' and text[-1] in '」』"':
            text = text[1:-1].strip()

        # 4. 检查是否是完全乱码（Sakura偶尔会返回prompt本身）
        if is_sakura and ('日文：' in text or '中文：' in text or '将下面' in text):
            # 可能是prompt被返回了，尝试提取实际翻译
            match = re.search(r'中文[：:]\s*(.+?)(?:\n|$)', text)
            if match:
                text = match.group(1).strip()

        return text

    def proofread_japanese(self, segments: List[Dict], anime_name: str = "",
                           char_settings: str = "", progress_callback=None) -> List[Dict]:
        """日语校对：用Qwen2.5修正Whisper识别错误（带上下文）"""
        config = self._get_config()
        proofread_model = config.get('proofread_model', 'qwen2.5:7b-instruct-q4_K_M')

        try:
            url = "http://localhost:11434/api/generate"
            results = []
            total = len(segments)

            for i, seg in enumerate(segments):
                if progress_callback:
                    progress_callback(i + 1, total)

                text = seg.get('text', '').strip()
                if not text:
                    results.append(seg)
                    continue

                # 获取上下文（前一句和后一句）
                prev_text = segments[i-1].get('text', '') if i > 0 else ''
                next_text = segments[i+1].get('text', '') if i < len(segments)-1 else ''

                # 构建校对prompt（带上下文）
                context_parts = []
                if anime_name:
                    context_parts.append(f"动漫名：{anime_name}")
                if char_settings:
                    context_parts.append(f"角色设定：{char_settings}")

                context_str = "\n".join(context_parts) if context_parts else ""

                prompt = f"""你是一个日语字幕校对专家。请根据对话上下文，修正以下可能含有识别错误的日语台词。

{context_str}

【对话上下文】
（前一句）{prev_text if prev_text else '（无）'}
（当前句）{text}
（后一句）{next_text if next_text else '（无）'}

要求：
1. 纠正同音词错误（例如将「橋」误识别成「端」等）
2. 补全缺失的助词（てにをは）
3. 口语缩略形式保持原样
4. 不改动原本的语气和人设用词
5. 如果没有错误，直接输出原文
6. 只输出修正后的日语，不要添加任何解释"""

                data = json.dumps({
                    "model": proofread_model,
                    "system": "你是一个日语字幕校对专家，专门修正语音识别错误。",
                    "prompt": prompt,
                    "stream": False
                }).encode('utf-8')

                try:
                    req = urllib.request.Request(url, data=data, headers={
                        "Content-Type": "application/json"
                    })
                    resp = urllib.request.urlopen(req, timeout=60)
                    result = json.loads(resp.read().decode('utf-8'))
                    corrected = result.get('response', '').strip()

                    if corrected:
                        # 清理可能的前缀
                        corrected = self._clean_translation(corrected)

                        # 合理性检查：长度差异不超过50%
                        if abs(len(corrected) - len(text)) / max(len(text), 1) < 0.5:
                            seg['text'] = corrected
                            seg['proofread'] = True
                        else:
                            print(f"[校对] 跳过：长度差异过大 ({len(text)} → {len(corrected)})")
                except Exception as e:
                    print(f"[校对] 单句失败: {e}")

                results.append(seg)

            return results
        except Exception as e:
            print(f"[校对] 错误: {e}")
            return segments

    def stop_ollama_model(self, model_name: str):
        """停止Ollama模型，释放显存"""
        try:
            result = os.popen(f'ollama stop {model_name}').read()
            print(f"[Ollama] 已停止模型: {model_name}")
        except: pass

    def warm_up_ollama_model(self, model_name: str):
        """预热Ollama模型"""
        try:
            url = "http://localhost:11434/api/generate"
            data = json.dumps({"model": model_name, "prompt": "hi", "stream": False}).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=60)
            print(f"[Ollama] 模型预热完成: {model_name}")
        except: pass

    def switch_model(self, from_model: str, to_model: str):
        """切换模型"""
        print(f"[Ollama] 切换模型: {from_model} → {to_model}")
        self.stop_ollama_model(from_model)
        time.sleep(2)  # 等待显存释放
        self.warm_up_ollama_model(to_model)
