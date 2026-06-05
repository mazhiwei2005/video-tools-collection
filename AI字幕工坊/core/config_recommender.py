#!/usr/bin/env python3
"""
AI推荐配置系统 - 自动检测GPU并推荐最佳模型配置
"""

import subprocess
import json
import os
from typing import Dict, List

class ConfigRecommender:
    """配置推荐器"""
    
    def __init__(self):
        # GPU信息
        self.gpu_name = ""
        self.gpu_memory = 0  # MB
        self.gpu_memory_used = 0
        self.cpu_cores = 0
        self.system_memory = 0  # GB
        
        # 模型需求表
        self.model_requirements = {
            'whisper': {
                'tiny': {'memory': 1000, 'speed': 'fastest', 'quality': 'low'},
                'base': {'memory': 1500, 'speed': 'fast', 'quality': 'medium'},
                'small': {'memory': 2500, 'speed': 'medium', 'quality': 'good'},
                'medium': {'memory': 5000, 'speed': 'slow', 'quality': 'high'},
                'large-v3': {'memory': 10000, 'speed': 'slowest', 'quality': 'highest'},
            },
            'nllb': {
                '600M': {'memory': 2000, 'speed': 'fast', 'quality': 'good'},
                '1.3B': {'memory': 4000, 'speed': 'medium', 'quality': 'high'},
                '3.3B': {'memory': 8000, 'speed': 'slow', 'quality': 'highest'},
            },
            'qwen': {
                '1.8B': {'memory': 3000, 'speed': 'fast', 'quality': 'good'},
                '7B': {'memory': 12000, 'speed': 'slow', 'quality': 'high'},
                '14B': {'memory': 24000, 'speed': 'slowest', 'quality': 'highest'},
            },
            'ollama': {
                'sakura-7b': {'memory': 5000, 'speed': 'medium', 'quality': 'high'},
                'qwen2.5-7b': {'memory': 5000, 'speed': 'medium', 'quality': 'high'},
            },
        }
        
        # 推荐模式
        self.modes = {
            '极速模式': {
                'description': '适合低配电脑，速度优先',
                'whisper': 'base',
                'translation': 'sogou',  # 在线翻译
                'polish': False,
                'gpu': False,
            },
            '平衡模式': {
                'description': '默认推荐，速度与质量平衡',
                'whisper': 'small',
                'translation': 'ollama',
                'polish': True,
                'gpu': True,
            },
            '高质量模式': {
                'description': '字幕组级别，质量优先',
                'whisper': 'large-v3',
                'translation': 'ollama',
                'polish': True,
                'gpu': True,
            },
            '专业模式': {
                'description': '完全自定义，手动选择模型',
                'whisper': 'large-v3',
                'translation': 'ollama',
                'polish': True,
                'gpu': True,
            },
        }
    
    def detect_gpu(self) -> Dict:
        """检测GPU信息"""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total,memory.used,memory.free', 
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                self.gpu_name = parts[0].strip()
                self.gpu_memory = int(parts[1].strip())
                self.gpu_memory_used = int(parts[2].strip())
                gpu_free = int(parts[3].strip())
                
                return {
                    'name': self.gpu_name,
                    'memory_total': self.gpu_memory,
                    'memory_used': self.gpu_memory_used,
                    'memory_free': gpu_free,
                    'available': True
                }
        except Exception as e:
            pass
        
        return {'name': '未检测到', 'memory_total': 0, 'available': False}
    
    def detect_system(self) -> Dict:
        """检测系统信息"""
        import platform
        
        info = {
            'os': platform.system(),
            'cpu': platform.processor() or 'Unknown',
            'cpu_cores': os.cpu_count() or 1,
            'python': platform.python_version(),
        }
        
        # 检测内存
        try:
            if platform.system() == 'Windows':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                c_ulonglong = ctypes.c_ulonglong
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ('dwLength', ctypes.c_ulong),
                        ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', c_ulonglong),
                        ('ullAvailPhys', c_ulonglong),
                        ('ullTotalPageFile', c_ulonglong),
                        ('ullAvailPageFile', c_ulonglong),
                        ('ullTotalVirtual', c_ulonglong),
                        ('ullAvailVirtual', c_ulonglong),
                        ('ullAvailExtendedVirtual', c_ulonglong),
                    ]
                memoryStatus = MEMORYSTATUSEX()
                memoryStatus.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                kernel32.GlobalMemoryStatusEx(ctypes.byref(memoryStatus))
                self.system_memory = memoryStatus.ullTotalPhys // (1024**3)
                info['memory_gb'] = self.system_memory
        except:
            info['memory_gb'] = 0
        
        return info
    
    def recommend(self, mode: str = '平衡模式') -> Dict:
        """根据GPU推荐配置"""
        gpu = self.detect_gpu()
        system = self.detect_system()
        
        if not gpu['available']:
            # 无GPU，使用极速模式
            mode = '极速模式'
        
        mode_config = self.modes.get(mode, self.modes['平衡模式'])
        
        # 根据GPU显存调整
        available_memory = gpu.get('memory_free', 0)
        
        recommendations = {
            'mode': mode,
            'mode_description': mode_config['description'],
            'gpu': gpu,
            'system': system,
            'config': {},
        }
        
        # Whisper模型推荐
        if available_memory >= 10000:
            whisper_model = 'large-v3'
        elif available_memory >= 5000:
            whisper_model = 'medium'
        elif available_memory >= 2500:
            whisper_model = 'small'
        elif available_memory >= 1500:
            whisper_model = 'base'
        else:
            whisper_model = 'tiny'
        
        recommendations['config']['whisper_model'] = whisper_model
        recommendations['config']['whisper_device'] = 'cuda' if available_memory > 2000 else 'cpu'
        
        # 翻译引擎推荐
        if available_memory >= 5000:
            recommendations['config']['translation'] = 'ollama'
            recommendations['config']['ollama_model'] = 'sakura-7b'
        else:
            recommendations['config']['translation'] = 'sogou'
        
        # 润色推荐
        if available_memory >= 12000:
            recommendations['config']['polish'] = 'qwen-7b'
        elif available_memory >= 5000:
            recommendations['config']['polish'] = 'qwen-1.8b'
        else:
            recommendations['config']['polish'] = False
        
        # 生成推荐文本
        recommendations['summary'] = self._generate_summary(recommendations)
        
        return recommendations
    
    def _generate_summary(self, rec: Dict) -> str:
        """生成推荐文本摘要"""
        gpu = rec['gpu']
        config = rec['config']
        
        lines = [
            f"🎮 GPU: {gpu['name']}",
            f"💾 显存: {gpu.get('memory_total', 0)}MB (空闲: {gpu.get('memory_free', 0)}MB)",
            f"🖥 系统: {rec['system'].get('cpu', 'Unknown')}",
            f"📊 内存: {rec['system'].get('memory_gb', 0)}GB",
            "",
            f"推荐模式: {rec['mode']}",
            f"模式说明: {rec['mode_description']}",
            "",
            "推荐配置:",
            f"  语音识别: Whisper {config['whisper_model']} ({config['whisper_device'].upper()})",
            f"  翻译引擎: {config['translation']}",
        ]
        
        if config.get('polish'):
            lines.append(f"  AI润色: {config['polish']}")
        else:
            lines.append("  AI润色: 不启用（显存不足）")
        
        return '\n'.join(lines)
