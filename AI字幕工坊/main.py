#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI动漫字幕工坊 - 主程序入口
专业级AI动漫字幕工作站
"""

import sys
import os

# 设置工作目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import launch_app

if __name__ == "__main__":
    launch_app()
