#!/usr/bin/env python3
"""
双语字幕系统 - 支持中日/中英/日英双语字幕
"""

class BilingualSubtitle:
    """双语字幕生成器"""
    
    def __init__(self):
        self.supported_pairs = {
            'ja-zh': {'name': '中日双语', 'above': '日语', 'below': '中文'},
            'ja-en': {'name': '日英双语', 'above': '日语', 'below': '英文'},
            'zh-en': {'name': '中英双语', 'above': '中文', 'below': '英文'},
            'ja-zh-en': {'name': '三语字幕', 'above': '日语', 'middle': '中文', 'below': '英文'},
        }
    
    def generate_ass_bilingual(self, subtitles, lang_pair='ja-zh', 
                                style_above=None, style_below=None):
        """生成双语ASS字幕"""
        pair_info = self.supported_pairs.get(lang_pair, self.supported_pairs['ja-zh'])
        
        # 默认样式
        if style_above is None:
            style_above = {
                'font': 'Microsoft YaHei', 'size': 20, 'color': '&H00FFFFFF',
                'outline_color': '&H00000000', 'outline': 2, 'shadow': 1,
                'alignment': 2, 'margin_v': 30
            }
        if style_below is None:
            style_below = {
                'font': 'Microsoft YaHei', 'size': 22, 'color': '&H0000FFFF',
                'outline_color': '&H00000000', 'outline': 2, 'shadow': 1,
                'alignment': 2, 'margin_v': 5
            }
        
        # 生成ASS头部
        ass = self._generate_ass_header(style_above, style_below, lang_pair)
        
        # 生成字幕事件
        ass += "\n[Events]\n"
        ass += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        
        for sub in subtitles:
            start = self._format_time(sub.get('start', 0))
            end = self._format_time(sub.get('end', 0))
            
            original = sub.get('original', sub.get('text', ''))
            translated = sub.get('translated', sub.get('translation', ''))
            
            # 上方字幕（原文）
            ass += f"Dialogue: 0,{start},{end},Original,,0,0,0,,{original}\n"
            # 下方字幕（翻译）
            if translated:
                ass += f"Dialogue: 0,{start},{end},Translation,,0,0,0,,{translated}\n"
        
        return ass
    
    def generate_srt_bilingual(self, subtitles, lang_pair='ja-zh'):
        """生成双语SRT字幕"""
        srt = ""
        for i, sub in enumerate(subtitles, 1):
            start = self._format_srt_time(sub.get('start', 0))
            end = self._format_srt_time(sub.get('end', 0))
            
            original = sub.get('original', sub.get('text', ''))
            translated = sub.get('translated', sub.get('translation', ''))
            
            srt += f"{i}\n{start} --> {end}\n"
            if translated:
                srt += f"{original}\n{translated}\n\n"
            else:
                srt += f"{original}\n\n"
        
        return srt
    
    def _generate_ass_header(self, style_above, style_below, lang_pair):
        """生成ASS文件头部"""
        header = """[Script Info]
Title: AI字幕工坊 - 双语字幕
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
"""
        # 上方样式（原文）
        header += f"Style: Original,{style_above['font']},{style_above['size']},{style_above['color']},&H000000FF,{style_above['outline_color']},&H80000000,-1,0,0,0,100,100,0,0,1,{style_above['outline']},{style_above['shadow']},{style_above['alignment']},20,20,{style_above['margin_v']},1\n"
        
        # 下方样式（翻译）
        header += f"Style: Translation,{style_below['font']},{style_below['size']},{style_below['color']},&H000000FF,{style_below['outline_color']},&H80000000,-1,0,0,0,100,100,0,0,1,{style_below['outline']},{style_below['shadow']},{style_below['alignment']},20,20,{style_below['margin_v']},1\n"
        
        return header
    
    def _format_time(self, seconds):
        """格式化为ASS时间"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{ms:02d}"
    
    def _format_srt_time(self, seconds):
        """格式化为SRT时间"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
