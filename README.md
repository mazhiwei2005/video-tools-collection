# 🎬 视频工具集合

> 一站式视频处理工具集，包含 B 站工具、动漫下载、视频处理等多种实用工具

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)

## 📦 工具列表

### 🎥 B 站工具

| 工具 | 功能 | 路径 |
|------|------|------|
| **B 站上传工具** | 批量上传视频到 B 站 | `B站上传工具/` |
| **B 站弹幕发射器** | 发送弹幕到 B 站视频 | `B站弹幕发射器/` |
| **B 站弹幕下载器** | 下载 B 站视频弹幕 | `B站弹幕下载器/` |
| **B 站查询工具** | 查询 B 站番剧信息 | `B站查询工具/` |

### 📺 动漫工具

| 工具 | 功能 | 路径 |
|------|------|------|
| **动漫下载器** | 从稀饭动漫下载视频 | `动漫下载器/` |
| **动漫下载工具** | 通用动漫下载工具 | `动漫下载工具/` |
| **稀饭动漫下载器** | 稀饭动漫专用下载器 | `稀饭动漫下载器/` |
| **AniCh 下载器** | 从 AniCh 下载动漫 | `AniCh下载器/` |
| **m3u8 下载器** | 下载 m3u8 视频流 | `m3u8_downloader/` |
| **动漫标题查询** | 查询动漫标题信息 | `动漫标题查询/` |
| **动漫集数查询器** | 查询动漫集数信息 | `动漫集数查询器/` |

### 🎞️ 视频处理

| 工具 | 功能 | 路径 |
|------|------|------|
| **视频处理工具** | 视频格式转换、剪辑 | `视频处理工具/` |
| **视频提取字幕** | 从视频中提取字幕 | `视频提取字幕/` |
| **视频去重** | 视频去重处理 | `视频去重/` |
| **黑屏音频工具** | 处理黑屏音频问题 | `黑屏音频工具/` |
| **AI 字幕工坊** | AI 生成字幕 | `AI字幕工坊/` |
| **智微视频综合软件** | 综合视频处理软件 | `智微视频综合软件/` |

## 🚀 快速开始

### 环境要求
- Python 3.10+
- FFmpeg
- Chrome/Edge 浏览器（用于 B 站工具）

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/mazhiwei2005/video-tools-collection.git
cd video-tools-collection
```

2. **安装依赖**
```bash
pip install requests selenium pillow ffmpeg-python
```

3. **配置 FFmpeg**
```bash
# 下载 FFmpeg 并添加到 PATH
# 或者将 ffmpeg.exe 放在各工具目录下
```

## 🎯 使用指南

### B 站上传工具
```bash
cd B站上传工具
python bili_uploader.py
```
- 支持批量上传
- 支持自动填写标题、简介
- 支持设置封面

### 动漫下载器
```bash
cd 动漫下载器
python universal_downloader.py
```
- 支持多线路下载
- 支持断点续传
- 支持批量下载

### B 站弹幕发射器
```bash
cd B站弹幕发射器
python danmaku_sender.py
```
- 支持发送弹幕
- 支持批量发送
- 支持定时发送

### B 站查询工具
```bash
cd B站查询工具
python query_tool.py
```
- 查询番剧信息
- 查询 UP 主信息
- 查询视频信息

## ⚙️ 配置说明

### B 站工具配置
```json
{
  "cookie_file": "bili_cookie.json",
  "upload_config": "upload_config.json",
  "default_cover": "_default_cover.jpg"
}
```

### 下载器配置
```json
{
  "save_dir": "G:\\测试下载",
  "domain": "dm.xifanacg.com",
  "线路": 1,
  "并发数": 3
}
```

## 📁 项目结构

```
video-tools-collection/
├── B站上传工具/           # B 站视频上传
├── B站弹幕发射器/         # B 站弹幕发送
├── B站弹幕下载器/         # B 站弹幕下载
├── B站查询工具/           # B 站信息查询
├── 动漫下载器/            # 稀饭动漫下载
├── 动漫下载工具/          # 通用动漫下载
├── 稀饭动漫下载器/        # 稀饭专用下载
├── AniCh下载器/           # AniCh 下载
├── m3u8_downloader/       # m3u8 流下载
├── 动漫标题查询/          # 动漫标题查询
├── 动漫集数查询器/        # 动漫集数查询
├── 视频处理工具/          # 视频处理
├── 视频提取字幕/          # 字幕提取
├── 视频去重/              # 视频去重
├── 黑屏音频工具/          # 音频处理
├── AI字幕工坊/            # AI 字幕生成
├── 智微视频综合软件/      # 综合处理
└── README.md
```

## 🔧 高级功能

### 批量处理
- 支持文件夹批量导入
- 支持批量下载
- 支持批量上传

### 定时任务
- 支持定时下载
- 支持定时上传
- 支持任务队列

### 自动化
- 自动登录 B 站
- 自动填写信息
- 自动上传视频

## 📊 性能优化

### 下载优化
- 多线程下载
- 断点续传
- 自动重试

### 上传优化
- 分片上传
- 并发上传
- 自动重试

## 🐛 常见问题

### Q: B 站工具登录失败？
A: 检查 cookie 是否过期，重新获取 cookie。

### Q: 下载速度慢？
A: 尝试切换下载线路，或检查网络连接。

### Q: 上传失败？
A: 检查视频格式是否符合 B 站要求，检查网络连接。

### Q: 弹幕发送失败？
A: 检查登录状态，检查弹幕内容是否合规。

## 📝 更新日志

### v1.0 (2025-06-01)
- 初始版本发布
- 整合所有视频工具
- 添加统一文档

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 🙏 致谢

- [FFmpeg](https://ffmpeg.org/) - 视频处理框架
- [Selenium](https://www.selenium.dev/) - 浏览器自动化
- [requests](https://docs.python-requests.org/) - HTTP 库

## 📞 联系方式

- GitHub: [@mazhiwei2005](https://github.com/mazhiwei2005)
- Email: 359923331@qq.com

---

⭐ 如果这个项目对你有帮助，请给个 Star 支持一下！
