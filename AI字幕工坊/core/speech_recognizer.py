#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI字幕工坊 - 语音识别引擎 v2
使用 Faster-Whisper 进行语音识别
"""

import os
import sys
import time
import json
import traceback
from typing import Optional, Dict, List, Callable

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError as e:
    print(f"[SpeechRecognizer] faster-whisper not available: {e}")
    WHISPER_AVAILABLE = False

class SpeechRecognizer:
    """语音识别引擎"""
    
    def __init__(self, model_size: str = "large-v3", device: str = "auto", compute_type: str = "float16"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.is_loaded = False
        
        self.vram_requirements = {
            "tiny": 1,
            "base": 1,
            "small": 2,
            "medium": 5,
            "large-v2": 6,
            "large-v3": 6,
        }
    
    def load_model(self, progress_callback: Callable = None) -> bool:
        """加载模型"""
        if not WHISPER_AVAILABLE:
            msg = "faster-whisper 未安装，请运行: pip install faster-whisper"
            print(f"[SpeechRecognizer] {msg}")
            if progress_callback:
                progress_callback(msg, 0)
            return False
        
        try:
            if progress_callback:
                progress_callback(f"正在加载模型 {self.model_size}...", 10)
            
            print(f"[SpeechRecognizer] Loading model: {self.model_size}")
            
            # 自动选择设备
            if self.device == "auto":
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.device = "cuda"
                        vram = torch.cuda.get_device_properties(0).total_mem / 1024**3
                        required = self.vram_requirements.get(self.model_size, 6)
                        if vram < required:
                            self.compute_type = "int8"
                        print(f"[SpeechRecognizer] Using CUDA, VRAM: {vram:.1f}GB")
                    else:
                        self.device = "cpu"
                        self.compute_type = "int8"
                        print("[SpeechRecognizer] CUDA not available, using CPU")
                except Exception as e:
                    self.device = "cpu"
                    self.compute_type = "int8"
                    print(f"[SpeechRecognizer] Error detecting GPU: {e}, using CPU")
            
            if progress_callback:
                progress_callback(f"设备: {self.device}, 计算类型: {self.compute_type}", 30)
            
            print(f"[SpeechRecognizer] Device: {self.device}, Compute: {self.compute_type}")
            
            # 检查本地缓存
            import platform
            if platform.system() == "Windows":
                cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            else:
                # WSL中使用Windows的缓存
                cache_dir = "/mnt/c/Users/Lenovo/.cache/huggingface/hub"
            
            model_dir = os.path.join(cache_dir, f"models--Systran--faster-whisper-{self.model_size}")
            
            if os.path.exists(model_dir):
                # 使用本地缓存
                snapshots_dir = os.path.join(model_dir, "snapshots")
                if os.path.exists(snapshots_dir):
                    snapshots = os.listdir(snapshots_dir)
                    if snapshots:
                        local_path = os.path.join(snapshots_dir, snapshots[0])
                        print(f"[SpeechRecognizer] Using local cache: {local_path}")
                        if progress_callback:
                            progress_callback("使用本地缓存模型...", 50)
                        
                        self.model = WhisperModel(
                            local_path,
                            device=self.device,
                            compute_type=self.compute_type
                        )
                        self.is_loaded = True
                        if progress_callback:
                            progress_callback("模型加载完成!", 100)
                        print("[SpeechRecognizer] Model loaded from local cache")
                        return True
            
            # 在线下载
            if progress_callback:
                progress_callback("正在下载模型（首次需要下载约3GB）...", 50)
            
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
            
            self.is_loaded = True
            
            if progress_callback:
                progress_callback("模型加载完成!", 100)
            
            print("[SpeechRecognizer] Model loaded successfully")
            return True
            
        except Exception as e:
            error_msg = f"模型加载失败: {str(e)}"
            print(f"[SpeechRecognizer] {error_msg}")
            print(traceback.format_exc())
            if progress_callback:
                progress_callback(error_msg, 0)
            return False
    
    def transcribe(self, audio_path: str, language: str = "ja", 
                   progress_callback: Callable = None, initial_prompt: str = None) -> Dict:
        """转录音频"""
        if not self.is_loaded:
            if not self.load_model(progress_callback):
                return {'success': False, 'segments': [], 'text': '', 'error': '模型未加载'}
        
        try:
            if progress_callback:
                progress_callback("开始识别...", 0)
            
            print(f"[SpeechRecognizer] Transcribing: {audio_path}")
            start_time = time.time()
            
            # 构建initial_prompt：基础提示 + 用户自定义专有名词
            base_prompt = "以下是一段日语动漫对话。"
            if initial_prompt:
                final_prompt = f"{base_prompt} 片中可能出现的专有名词：{initial_prompt}"
            else:
                final_prompt = base_prompt
            
            # 转录 - 优化参数提高准确率和时间同步
            segments, info = self.model.transcribe(
                audio_path,
                language=language,
                beam_size=5,
                best_of=3,
                patience=1.0,
                length_penalty=1.0,
                repetition_penalty=1.1,
                no_repeat_ngram_size=3,
                temperature=[0.0, 0.2, 0.4],
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=200,
                    speech_pad_ms=50,
                    threshold=0.5,
                    min_speech_duration_ms=250,
                    max_speech_duration_s=7,
                ),
                word_timestamps=True,
                condition_on_previous_text=False,
                initial_prompt=final_prompt,
            )
            
            # 收集结果
            result_segments = []
            full_text = ""
            
            for i, segment in enumerate(segments):
                # 使用更精确的时间戳
                start_time_seg = segment.start
                end_time_seg = segment.end
                
                # 如果有单词级别时间戳，使用更精确的时间
                if hasattr(segment, 'words') and segment.words:
                    # 使用第一个和最后一个单词的时间
                    start_time_seg = segment.words[0].start
                    end_time_seg = segment.words[-1].end
                
                result_segments.append({
                    'start': start_time_seg,
                    'end': end_time_seg,
                    'text': segment.text.strip(),
                })
                full_text += segment.text + " "
                
                progress = min(90, int(segment.end / info.duration * 100) if info.duration > 0 else 0)
                if progress_callback:
                    progress_callback(f"识别中... 第{i+1}段", progress)
                
                print(f"[SpeechRecognizer] Segment {i+1}: {start_time_seg:.1f}s-{end_time_seg:.1f}s {segment.text[:30]}")
            
            elapsed = time.time() - start_time
            
            if progress_callback:
                progress_callback(f"识别完成! {len(result_segments)} 段, 耗时 {elapsed:.1f}s", 100)
            
            print(f"[SpeechRecognizer] Done: {len(result_segments)} segments in {elapsed:.1f}s")
            
            return {
                'success': True,
                'segments': result_segments,
                'text': full_text.strip(),
                'language': info.language,
                'duration': info.duration,
                'elapsed': elapsed,
            }
            
        except Exception as e:
            error_msg = f"识别失败: {str(e)}"
            print(f"[SpeechRecognizer] {error_msg}")
            print(traceback.format_exc())
            return {'success': False, 'segments': [], 'text': '', 'error': error_msg}
    
    def get_status(self) -> Dict:
        """获取引擎状态"""
        return {
            'available': WHISPER_AVAILABLE,
            'loaded': self.is_loaded,
            'model_size': self.model_size,
            'device': self.device,
            'compute_type': self.compute_type,
            'vram_required': self.vram_requirements.get(self.model_size, 6),
        }


# 测试
if __name__ == "__main__":
    print("="*60)
    print("Speech Recognizer Test")
    print("="*60)
    
    recognizer = SpeechRecognizer(model_size="large-v3")
    status = recognizer.get_status()
    
    print(f"\nAvailable: {status['available']}")
    print(f"Model: {status['model_size']}")
    print(f"VRAM Required: {status['vram_required']}GB")
    
    if status['available']:
        print("\nLoading model...")
        success = recognizer.load_model(lambda s, p: print(f"  [{p}%] {s}"))
        print(f"Load Result: {success}")
        
        if success:
            print(f"\nDevice: {recognizer.device}")
            print(f"Compute Type: {recognizer.compute_type}")
