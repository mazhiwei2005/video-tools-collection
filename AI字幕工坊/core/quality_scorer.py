#!/usr/bin/env python3
"""
AI字幕质量评分系统
自动分析字幕准确率、翻译自然度、时间轴精准度
"""

import re
from typing import Dict, List

class SubtitleQualityScorer:
    """字幕质量评分器"""
    
    def __init__(self):
        self.weights = {
            'accuracy': 0.4,      # 翻译准确率
            'naturalness': 0.3,   # 翻译自然度
            'timing': 0.2,        # 时间轴精准度
            'length': 0.1,        # 字幕长度合理性
        }
    
    def score_subtitles(self, subtitles: List[Dict]) -> Dict:
        """批量评分字幕"""
        if not subtitles:
            return {'overall': 0, 'details': {}}
        
        scores = {
            'accuracy': [],
            'naturalness': [],
            'timing': [],
            'length': [],
        }
        
        for sub in subtitles:
            s = self._score_single(sub)
            for k in scores:
                scores[k].append(s[k])
        
        # 计算平均分
        avg_scores = {}
        for k, v in scores.items():
            avg_scores[k] = round(sum(v) / len(v), 1) if v else 0
        
        # 加权总分
        overall = sum(avg_scores[k] * self.weights[k] for k in avg_scores)
        
        return {
            'overall': round(overall, 1),
            'details': avg_scores,
            'count': len(subtitles),
            'issues': self._find_issues(subtitles)
        }
    
    def _score_single(self, sub: Dict) -> Dict:
        """单条字幕评分"""
        original = sub.get('original', sub.get('text', ''))
        translated = sub.get('translated', sub.get('translation', ''))
        start = sub.get('start', 0)
        end = sub.get('end', 0)
        
        return {
            'accuracy': self._score_accuracy(original, translated),
            'naturalness': self._score_naturalness(translated),
            'timing': self._score_timing(start, end),
            'length': self._score_length(translated),
        }
    
    def _score_accuracy(self, original: str, translated: str) -> float:
        """翻译准确率评分"""
        if not translated or not original:
            return 0
        
        score = 100.0
        
        # 检查是否有机翻标记
        machine_flags = ['[翻译失败]', '[ERROR]', '翻译错误', 'None', 'null']
        for flag in machine_flags:
            if flag in translated:
                score -= 50
        
        # 检查是否包含原文（未翻译）
        jp_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', original))
        if jp_chars > 3:
            remaining_jp = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF]', translated))
            if remaining_jp > jp_chars * 0.5:
                score -= 20  # 翻译不完整
        
        # 检查长度比例
        if original and translated:
            ratio = len(translated) / max(len(original), 1)
            if ratio < 0.3:
                score -= 15  # 翻译太短
            elif ratio > 3:
                score -= 10  # 翻译太长
        
        return max(0, min(100, score))
    
    def _score_naturalness(self, translated: str) -> float:
        """翻译自然度评分"""
        if not translated:
            return 0
        
        score = 100.0
        
        # 检查机翻腔
        machine_phrases = [
            '的的', '了了', '是是', '在在',
            '这是一个', '这是个', '它是一个',
            '我可以', '我能够', '我将要',
        ]
        for phrase in machine_phrases:
            if phrase in translated:
                score -= 10
        
        # 检查重复词
        if re.search(r'(.{2,})\1{2,}', translated):
            score -= 15
        
        # 检查标点符号
        if translated and translated[-1] not in '。！？…～）」』':
            score -= 5  # 缺少结尾标点
        
        # 检查长度是否合理
        length = len(translated)
        if length > 50:
            score -= 10  # 太长
        elif length < 2:
            score -= 20  # 太短
        
        return max(0, min(100, score))
    
    def _score_timing(self, start: float, end: float) -> float:
        """时间轴精准度评分"""
        if end <= start:
            return 0
        
        score = 100.0
        duration = end - start
        
        # 太短（<0.5秒）
        if duration < 0.5:
            score -= 40
        # 太长（>10秒）
        elif duration > 10:
            score -= 20
        # 理想范围 1-5秒
        elif 1 <= duration <= 5:
            score = 100
        
        return max(0, min(100, score))
    
    def _score_length(self, translated: str) -> float:
        """字幕长度合理性评分"""
        if not translated:
            return 0
        
        length = len(translated)
        
        # 理想长度: 10-30字符
        if 10 <= length <= 30:
            return 100
        elif 5 <= length < 10:
            return 85
        elif 30 < length <= 50:
            return 80
        elif length > 50:
            return 60
        elif length < 5:
            return 50
        
        return 70
    
    def _find_issues(self, subtitles: List[Dict]) -> List[Dict]:
        """找出问题字幕"""
        issues = []
        for i, sub in enumerate(subtitles):
            original = sub.get('original', sub.get('text', ''))
            translated = sub.get('translated', sub.get('translation', ''))
            start = sub.get('start', 0)
            end = sub.get('end', 0)
            
            # 未翻译
            if original and not translated:
                issues.append({
                    'index': i, 'type': 'missing_translation',
                    'message': f'第{i+1}条: 未翻译',
                    'severity': 'high'
                })
            
            # 翻译失败
            if translated and '[翻译失败]' in translated:
                issues.append({
                    'index': i, 'type': 'translation_failed',
                    'message': f'第{i+1}条: 翻译失败',
                    'severity': 'high'
                })
            
            # 时间轴问题
            if end <= start:
                issues.append({
                    'index': i, 'type': 'timing_error',
                    'message': f'第{i+1}条: 结束时间≤开始时间',
                    'severity': 'high'
                })
            
            # 太长
            if translated and len(translated) > 50:
                issues.append({
                    'index': i, 'type': 'too_long',
                    'message': f'第{i+1}条: 字幕过长({len(translated)}字符)',
                    'severity': 'medium'
                })
            
            # 太短显示时间
            duration = end - start
            if 0 < duration < 0.5:
                issues.append({
                    'index': i, 'type': 'too_short_timing',
                    'message': f'第{i+1}条: 显示时间过短({duration:.2f}秒)',
                    'severity': 'medium'
                })
        
        return issues[:20]  # 最多返回20个问题
