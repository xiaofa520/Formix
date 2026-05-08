# Formix 命令行使用文档

## 一、功能说明

Formix 内置了一个命令行页面，用于直接调用：

- `ffmpeg`
- `ffplay`
- `ffprobe`

这个页面不是系统终端，也不会执行其他系统命令。它只允许运行 FFmpeg 工具链相关命令。

## 二、支持范围

当前支持：

- 执行 `ffmpeg` 全部常规参数
- 执行 `ffplay` 播放命令
- 执行 `ffprobe` 媒体信息查询命令
- 带空格路径
- 带引号路径
- 命令历史记录
- `Ctrl + C` 中断当前运行
- `ffmpeg` 执行时显示底部进度条

当前不支持：

- `cmd`、`powershell`、`bash` 等系统命令
- 管道和重定向
- 多条命令串联执行
- 命令替换表达式

被拦截的内容包括：

- `|`
- `&`
- `;`
- `>`
- `<`
- `` ` ``
- `$()`

## 三、基础操作

进入“命令行”页面后：

1. 页面会自动聚焦到输入区域
2. 直接输入命令
3. 按 `Enter` 执行
4. 按 `Ctrl + Enter` 换行
5. 按 `Ctrl + C` 中断当前命令
6. 按键盘 `↑` / `↓` 切换历史命令

说明：

- 如果命令正在运行，按 `Enter` 不会再次提交，而是按取消逻辑处理。
- 可以用鼠标拖动选择日志、命令输出和错误内容进行复制。

## 四、路径输入规则

### 1. 推荐写法

如果路径中包含空格，建议始终使用英文双引号：

```bash
ffmpeg -i "D:/Videos/input file.mp4" "D:/Output/output.mp4"
```

### 2. 支持无引号路径

如果路径本身没有空格，也可以直接写：

```bash
ffprobe D:/Videos/input.mp4
```

### 3. 输入文件

通常通过 `-i` 指定输入文件：

```bash
ffmpeg -i "input.mp4" -c:v libx264 "output.mp4"
```

### 4. 输出文件

通常命令最后一个非选项参数会被识别为输出文件：

```bash
ffmpeg -i "input.mp4" -c:v libx264 "D:/Output/output.mp4"
```

### 5. 兼容示例

以下两种写法都支持：

```bash
ffmpeg -y -i C:/xxx/xxx.mp4 -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k -movflags +faststart -crf 18 /xxx/xxx.avi
```

```bash
ffmpeg -y -i "C:/xxx/xxx.mp4" -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k -movflags +faststart -crf 18 "D:/xxx/xxx.mp4"
```

但从稳定性考虑，仍建议优先使用带引号路径。

## 五、常见命令示例

### 1. 视频转 MP4

```bash
ffmpeg -i "input.mkv" -c:v libx264 -c:a aac "output.mp4"
```

### 2. 视频转 WebM

```bash
ffmpeg -i "input.mp4" -c:v libvpx-vp9 -c:a libopus "output.webm"
```

### 3. 提取音频

```bash
ffmpeg -i "input.mp4" -vn -c:a libmp3lame "output.mp3"
```

### 4. 只复制流不重新编码

```bash
ffmpeg -i "input.mp4" -c copy "output.mkv"
```

### 5. 查询媒体信息

```bash
ffprobe "input.mp4"
```

### 6. 查看完整流信息

```bash
ffprobe -hide_banner -show_format -show_streams "input.mp4"
```

### 7. 播放媒体文件

```bash
ffplay "input.mp4"
```

### 8. 查看帮助

```bash
ffmpeg -h
ffprobe -h
ffplay -h
```

## 六、进度与中断

### 1. 进度条

当运行 `ffmpeg` 转换命令时，页面底部会显示进度条。

说明：

- 只有 `ffmpeg` 转换任务显示进度条
- `ffplay` 和 `ffprobe` 不显示转换进度条

### 2. 中断运行

如果当前命令仍在执行，可以使用：

- `Ctrl + C`

程序会向当前运行任务发送取消信号。

## 七、历史记录

命令页会记录你本次使用过程中执行过的命令。

操作方式：

- `↑`：上一条历史命令
- `↓`：下一条历史命令

说明：

- 正在执行命令时，历史切换不会生效
- 连续重复的同一条命令不会重复追加到末尾

## 八、缺失组件时的行为

如果软件没有找到对应工具，会直接提示：

- 缺少 `ffmpeg`
- 缺少 `ffprobe`
- 缺少 `ffplay`

这时请到“设置”页面下载或更新 FFmpeg 套件。

## 九、常见问题

### 1. 为什么我的命令被拒绝执行

通常是以下原因之一：

1. 命令不是以 `ffmpeg`、`ffplay`、`ffprobe` 开头
2. 命令中包含被拦截的 shell 控制符
3. 引号不成对，导致命令解析失败

### 2. 为什么路径明明存在却打不开

优先检查：

1. 路径里是否有空格
2. 是否缺少双引号
3. 输入和输出路径是否写反
4. 文件扩展名和编码参数是否匹配

### 3. 为什么 `ffprobe` 或 `ffplay` 不能运行

通常是本地缺少对应可执行文件。  
可以在设置页重新下载 FFmpeg 套件。

### 4. 为什么命令页不能像系统终端那样执行所有命令

这是有意限制。  
当前页面设计目标是安全地执行 FFmpeg 工具链命令，而不是提供一个完整系统 Shell。

## 十、建议

推荐这样使用命令页：

- 路径尽量加双引号
- 先用 `ffprobe` 看清源文件信息
- 再执行 `ffmpeg` 转换
- 不确定参数时先执行 `ffmpeg -h`
- 复杂命令先从一条最小可运行命令开始逐步增加参数
