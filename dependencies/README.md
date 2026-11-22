# 依赖缓存与本机平台

此工作区目前位于 Windows x64，所以活动依赖仅保存在 `windows-x64/`。macOS 和 Linux 的依赖由各平台在打包时准备。

在某个平台上运行 `python packaging/download_platform.py`，脚本根据系统和 CPU 架构创建唯一匹配的依赖目录，下载 Python 3.11、当前平台的 Qt / PDF / 图片 / 推理 wheel、FFmpeg、LibreOffice 和需要的系统运行组件。下载后运行 `python packaging/inventory.py` 生成 SHA-256 清单和离线安装锁。`python packaging/fetch_wheels.py` 只处理当前主机的平台锁。

`windows-x64/` 当前包含 Windows x64 Python 3.11 运行时、49 个 Python wheel、FFmpeg、LibreOffice MSI 和 VC++ 运行库。模型推理运行库随程序安装，PDF 视觉模型权重仍由用户在设置页主动下载。

后续在 Windows、Apple Silicon macOS 或 Ubuntu x64 上分别运行构建工作流。工作流先自动获取当前 runner 的依赖，然后从该平台目录制作安装包。因此 Windows 安装包不带 macOS/Linux 二进制，另外两个平台也各自只带对应的二进制。Linux 目标是 Ubuntu 22.04 x64，macOS 当前默认构建 Apple Silicon。
