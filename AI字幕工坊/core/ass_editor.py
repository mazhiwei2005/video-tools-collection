#!/usr/bin/env python3
"""
ASS样式编辑器 - 字幕样式和特效系统
支持多种预设风格、自定义样式、特效
"""

from typing import Dict, List, Tuple

class ASSStyleEditor:
    """ASS样式编辑器"""
    
    def __init__(self):
        # 预设风格
        self.presets = {
            'bilibili': {
                'name': 'B站字幕组风格',
                'font': 'Microsoft YaHei', 'size': 22,
                'color': '&H00FFFFFF',  # 白色
                'outline_color': '&H00000000',  # 黑色描边
                'outline': 2, 'shadow': 1,
                'bold': True, 'italic': False,
                'alignment': 2, 'margin_v': 20,
            },
            'netflix': {
                'name': 'Netflix风格',
                'font': 'Arial', 'size': 20,
                'color': '&H00FFFFFF',
                'outline_color': '&H00000000',
                'outline': 3, 'shadow': 0,
                'bold': False, 'italic': False,
                'alignment': 2, 'margin_v': 30,
            },
            'galgame': {
                'name': 'Galgame风格',
                'font': 'MS Gothic', 'size': 24,
                'color': '&H00FFFFFF',
                'outline_color': '&H00800080',  # 紫色描边
                'outline': 2, 'shadow': 2,
                'bold': False, 'italic': False,
                'alignment': 2, 'margin_v': 10,
            },
            'anime_movie': {
                'name': '动漫电影风格',
                'font': 'SimHei', 'size': 26,
                'color': '&H00FFFFFF',
                'outline_color': '&H00000000',
                'outline': 3, 'shadow': 2,
                'bold': True, 'italic': False,
                'alignment': 2, 'margin_v': 25,
            },
            'classic': {
                'name': '黑边经典字幕',
                'font': 'SimSun', 'size': 20,
                'color': '&H00FFFFFF',
                'outline_color': '&H00000000',
                'outline': 4, 'shadow': 0,
                'bold': False, 'italic': False,
                'alignment': 2, 'margin_v': 20,
            },
            'minimal': {
                'name': '简约白字',
                'font': 'Microsoft YaHei', 'size': 18,
                'color': '&H00FFFFFF',
                'outline_color': '&H00000000',
                'outline': 1, 'shadow': 0,
                'bold': False, 'italic': False,
                'alignment': 2, 'margin_v': 15,
            },
            'karaoke': {
                'name': '卡拉OK风格',
                'font': 'Microsoft YaHei', 'size': 28,
                'color': '&H0000FFFF',  # 黄色
                'outline_color': '&H00000000',
                'outline': 2, 'shadow': 1,
                'bold': True, 'italic': False,
                'alignment': 8, 'margin_v': 20,  # 居中上方
            },
            'bilibili_blue': {
                'name': 'B站蓝白风格',
                'font': 'Microsoft YaHei', 'size': 22,
                'color': '&H00FFD700',  # B站蓝
                'outline_color': '&H00FFFFFF',  # 白色描边
                'outline': 3, 'shadow': 1,
                'bold': True, 'italic': False,
                'alignment': 2, 'margin_v': 20,
            },
        }
        
        # 特效模板
        self.effects = {
            'fade_in': 'fade(300,0)',  # 淡入
            'fade_out': 'fade(0,300)',  # 淡出
            'fade_both': 'fade(300,300)',  # 淡入淡出
            'typewriter': r'{\t(0,50,\fscx100)}',  # 打字机效果
            'glow': r'{\blur5\3c&H00FFFF&}',  # 发光效果
            'shake': r'{\t(0,500,\pos($X,$Y))}',  # 震动效果
            'zoom_in': r'{\t(0,300,\fscx120\fscy120)}',  # 缩放
        }
    
    def get_preset(self, preset_name: str) -> Dict:
        """获取预设风格"""
        return self.presets.get(preset_name, self.presets['bilibili']).copy()
    
    def get_all_presets(self) -> Dict:
        """获取所有预设"""
        return {k: v['name'] for k, v in self.presets.items()}
    
    def generate_ass_style_line(self, style_name: str, style: Dict) -> str:
        """生成ASS样式行"""
        bold = -1 if style.get('bold', False) else 0
        italic = -1 if style.get('italic', False) else 0
        
        return (f"Style: {style_name},"
                f"{style.get('font', 'Arial')},{style.get('size', 20)},"
                f"{style.get('color', '&H00FFFFFF')},&H000000FF,"
                f"{style.get('outline_color', '&H00000000')},&H80000000,"
                f"{bold},{italic},0,0,100,100,0,0,"
                f"{1 if style.get('outline', 2) > 0 else 3},"
                f"{style.get('outline', 2)},{style.get('shadow', 1)},"
                f"{style.get('alignment', 2)},20,20,"
                f"{style.get('margin_v', 20)},1")
    
    def apply_effect(self, text: str, effect: str) -> str:
        """对字幕文本应用特效"""
        if effect == 'fade_in':
            return r'{\fad(300,0)}' + text
        elif effect == 'fade_out':
            return r'{\fad(0,300)}' + text
        elif effect == 'fade_both':
            return r'{\fad(300,300)}' + text
        elif effect == 'glow':
            return r'{\blur3\3c&H00FFFF&}' + text
        elif effect == 'typewriter':
            return r'{\t(0,500,\fscx100\fscy100)}' + text
        elif effect == 'shake':
            return r'{\move(960,540,962,538,0,500)}' + text
        elif effect == 'zoom_in':
            return r'{\t(0,300,\fscx110\fscy110)}' + text
        else:
            return text
    
    def generate_full_ass(self, subtitles: List[Dict], 
                          preset: str = 'bilibili',
                          effect: str = 'fade_both',
                          resolution: Tuple[int, int] = (1920, 1080)) -> str:
        """生成完整的ASS字幕文件"""
        style = self.get_preset(preset)
        
        # 头部
        ass = f"""[Script Info]
Title: AI字幕工坊 - {style['name']}
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {resolution[0]}
PlayResY: {resolution[1]}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{self.generate_ass_style_line('Default', style)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # 字幕事件
        for sub in subtitles:
            start = self._format_time(sub.get('start', 0))
            end = self._format_time(sub.get('end', 0))
            text = sub.get('translated', sub.get('text', ''))
            
            # 应用特效
            text = self.apply_effect(text, effect)
            
            ass += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
        
        return ass
    
    def _format_time(self, seconds: float) -> str:
        """格式化为ASS时间"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
