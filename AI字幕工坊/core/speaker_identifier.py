#!/usr/bin/env python3
"""
AI人物识别系统 - 识别说话人
基于音频特征分析说话人性别和角色
"""

import re
from typing import Dict, List

class SpeakerIdentifier:
    """说话人识别器"""
    
    def __init__(self):
        # 日语男性/女性用语特征
        self.male_patterns = [
            r'俺', r'僕', r'拙者', r'わし', r'オレ', r'ボク',
            r'だぜ', r'だぞ', r'ぜ$', r'ぞ$', r'のだ$', r'んだ$',
            r'じゃねえ', r'てめえ', r'くそ', r'ちくしょう',
        ]
        self.female_patterns = [
            r'あたし', r'わたくし', r'私.*のよ', r'ですわ',
            r'のよ$', r'わよ$', r'かしら', r'わね$',
            r'なの$', r'だわ$', r'でしょう$',
            r'うふふ', r'きゃ', r'いやだ',
        ]
        
        # 敬语特征
        self.polite_patterns = [
            r'です', r'ます', r'でございます', r'ございます',
            r'いただけます', r'していただけます',
        ]
        
        # 角色标签
        self.speaker_labels = {}
        self.speaker_count = 0
    
    def identify_gender(self, text: str) -> str:
        """识别说话人性别"""
        male_score = sum(1 for p in self.male_patterns if re.search(p, text))
        female_score = sum(1 for p in self.female_patterns if re.search(p, text))
        
        if male_score > female_score:
            return 'male'
        elif female_score > male_score:
            return 'female'
        else:
            return 'unknown'
    
    def identify_speakers(self, subtitles: List[Dict]) -> List[Dict]:
        """识别所有字幕的说话人"""
        # 第一轮：基于用语特征识别性别
        for sub in subtitles:
            text = sub.get('original', sub.get('text', ''))
            gender = self.identify_gender(text)
            sub['gender'] = gender
            
            # 识别语气
            sub['tone'] = self._identify_tone(text)
        
        # 第二轮：基于连续对话分配角色
        self._assign_roles(subtitles)
        
        return subtitles
    
    def _identify_tone(self, text: str) -> str:
        """识别语气"""
        if re.search(r'[！!]{2,}|かかってこい|覚悟', text):
            return 'angry'  # 生气
        elif re.search(r'泣|悲し|切な|涙', text):
            return 'sad'  # 悲伤
        elif re.search(r'やった|最高|すごい|わーい', text):
            return 'excited'  # 兴奋
        elif re.search(r'…|沈黙|黙|静', text):
            return 'quiet'  # 安静
        elif re.search(r'ふふ|笑|にこ|わら', text):
            return 'happy'  # 开心
        elif re.search(r'怖|こわ|震|がたがた', text):
            return 'scared'  # 害怕
        else:
            return 'normal'  # 普通
    
    def _assign_roles(self, subtitles: List[Dict]):
        """基于连续对话分配角色"""
        current_speaker = None
        speakers = {}
        
        for sub in subtitles:
            text = sub.get('original', sub.get('text', ''))
            gender = sub.get('gender', 'unknown')
            
            # 如果有明确的角色名（如「太郎」「花子」）
            name_match = re.search(r'「(.+?)」|【(.+?)】|（(.+?)）', text)
            if name_match:
                name = name_match.group(1) or name_match.group(2) or name_match.group(3)
                if name not in speakers:
                    speakers[name] = {
                        'id': len(speakers),
                        'name': name,
                        'gender': gender,
                        'label': f'角色{len(speakers)+1}'
                    }
                current_speaker = name
                sub['speaker'] = name
                sub['speaker_label'] = speakers[name]['label']
            else:
                # 基于性别和对话模式推断
                if gender == 'male':
                    if '男性角色A' not in speakers:
                        speakers['男性角色A'] = {
                            'id': len(speakers),
                            'name': '男性角色A',
                            'gender': 'male',
                            'label': '男主'
                        }
                    sub['speaker'] = '男性角色A'
                    sub['speaker_label'] = '男主'
                elif gender == 'female':
                    if '女性角色A' not in speakers:
                        speakers['女性角色A'] = {
                            'id': len(speakers),
                            'name': '女性角色A',
                            'gender': 'female',
                            'label': '女主'
                        }
                    sub['speaker'] = '女性角色A'
                    sub['speaker_label'] = '女主'
                else:
                    if current_speaker and current_speaker in speakers:
                        sub['speaker'] = current_speaker
                        sub['speaker_label'] = speakers[current_speaker]['label']
                    else:
                        sub['speaker'] = 'unknown'
                        sub['speaker_label'] = '角色?'
    
    def get_speaker_stats(self, subtitles: List[Dict]) -> Dict:
        """获取说话人统计"""
        stats = {}
        for sub in subtitles:
            speaker = sub.get('speaker_label', 'unknown')
            if speaker not in stats:
                stats[speaker] = {'count': 0, 'gender': sub.get('gender', 'unknown')}
            stats[speaker]['count'] += 1
        return stats
