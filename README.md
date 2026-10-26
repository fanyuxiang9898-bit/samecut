# Samecut / 同款快剪

**抖音参考链接 + 你的照片 → 一支使用参考音乐、跟随切镜节奏的写真快剪。**

本地运行，带中文网页和命令行。不需要云模型、API Key 或上传照片到第三方服务。

> 当前是可运行的 **v0.1 写真 / PPT 快剪工具**，不是任意视频的一比一复刻模型。它检测硬切点、读取比例与背景色、沿用参考原声，并使用变化的文字排版。原片字体、字幕、人物动作、复杂拼贴和特效不会被自动识别或精确复制。

## 开始使用

需要 Python 3.10+，以及 PATH 中可运行的 **FFmpeg 和 ffprobe**（FFmpeg 构建需包含 libx264）。代码可在 Windows / macOS / Linux 使用；本地实测 Windows，CI 测试 Linux。

```bash
git clone https://github.com/fanyuxiang9898-bit/samecut.git
cd samecut
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m samecut serve
```

macOS / Linux：

```bash
.venv/bin/python -m pip install .
.venv/bin/python -m samecut serve
```

打开 **http://127.0.0.1:8765**：

1. 粘贴抖音分享内容，或者上传参考视频。两者同时填写时使用上传视频。
2. 选择照片，在预览中检查水印。勾选“已检查没有平台水印”。
3. 输入轮换名字，例如 `chance, QIANCHENG`。按需要开启“近两天”，填写相应照片的实际发布日期。
4. 点击生成，下载 MP4，查看分镜和检查报告。

默认最多 120 张照片、单文件 250 MB、参考最长 3 分钟。服务只监听本机，不是可直接部署到公网的多用户服务。任务在 `runs/` 保存；关闭服务不会删除成片，但内存里的任务列表不会跨重启恢复。

## 能做什么

| 环节 | v0.1 行为 |
| --- | --- |
| 抖音链接 | 调用 yt-dlp 支持的公开提取流程；不读取浏览器 Cookie |
| 下载失败 | 明确报错，允许改为本地 MP4，不绕过登录/验证码 |
| 参考分析 | FFmpeg 场景分数识别硬切，保留时长与画面比例；静态参考使用 1 秒回退节奏 |
| 音乐 | 沿用参考音轨，编码 AAC；包括原片中已有的人声，不做音乐分离 |
| 照片 | 解码内容哈希 + 感知差异哈希去重；每张最多出场一次 |
| 素材不足 | 合并最短相邻镜头，报告节奏改变，不循环照片填满 |
| 文字 | 名字轮换；衬线、斜体、无衬线、粗体及横排/竖排位置变化 |
| 画面 | 完整容纳照片，轻微推进/拉远；背景色取自相应参考画面 |
| 水印 | 只接纳用户确认干净的素材；明确标记有水印的照片始终排除 |
| 新图 | 检查清单中的发布日期；要求开启时，近期照片优先进入实际成片 |
| 验收 | 检查连续时间线、无重复、最终时长、音轨和末帧 |

水印检查是**人工声明**，不是 OCR 检测；程序不会自动修复水印。发布日期由使用者提供，不独立联网核实，不使用文件修改时间冒充发布日期。感知去重是启发式，可能误判相似构图或漏掉大幅裁切后的重复；最终仍需观看成片。

字体从操作系统读取，不随仓库分发。中文等非拉丁文字在 CLI 中用 `--font /path/to/font.ttf` 指定有相应字形的字体；网页 v0.1 主要针对英文名字。

## 命令行

```bash
python -m samecut run --reference reference.mp4 --assets photos --output runs/my-edit --aliases chance QIANCHENG --reviewed-clean
```

`--reference` 也接受完整抖音分享文案，请用引号包围。输出目录必须不存在或为空，避免覆盖既有工作。

使用逐图清单，并强制包含近两天照片：

```bash
python -m samecut run --reference reference.mp4 --assets photos --manifest assets.json --recent-days 2 --output runs/fresh-edit
```

清单以文件名为键；示例见 [examples/assets.json](examples/assets.json)。`watermark` 为 `clean` 的图才会接纳；`present` / 未知状态会被排除。`--reviewed-clean` 表示你已检查所有未标记的照片，仍不会覆盖清单中明确标记的水印状态。

`--recent-days 2` 指今天和昨天两个日历日，不是滚动 48 小时。CLI 使用本机日期，也可用 `--as-of YYYY-MM-DD` 固定检查基准；网页使用浏览器本地日期。`published_at` 可填 ISO 日期或以 ISO 日期开头的时间字符串。未知、过期、未来日期都不满足强制近期要求。

可调参数：`--width 640/1280/1920`（其他偶数也可）、`--threshold 0.23`（切镜灵敏度）、`--font`。默认字体与位置是规则生成，不是从参考字体反查。

每次输出包含：

- `video.mp4`：H.264 + AAC 成片。
- `analysis.json`：检测到的原始切点和视频信息。
- `assets-report.json`：素材接纳/排除原因。
- `recipe.json`：实际使用照片、切点、文字和排版的可审查记录。
- `report.json`：验证结果与降级说明。
- `last-frame.jpg`、`clips/`：末帧和渲染中间文件。

这些文件可能包含个人素材路径，不应直接提交到公开仓库。`runs/` 已被忽略。当前 recipe 用于审查，不提供修改 recipe 后直接重渲染的命令。

## 一分钟验证（无需外部素材）

```bash
python -m samecut demo --output runs/demo
python -m unittest discover -s tests -v
```

Demo 生成原创几何图形和正弦测试音，再完整跑一遍 4 秒剪辑。测试覆盖真实 MP4 导出、尾帧、音轨、素材去重、近期图实际入片、时间线缺口、水印状态、链接失败与本地网页请求保护。

## 实现与复用

```text
抖音分享 → yt-dlp ─┐
本地参考 ──────────┴→ FFprobe / FFmpeg → 切点、时长、比例、原声
照片 + 清单 → 水印状态门槛 → 哈希去重 → 日期约束 → 唯一照片序列
                                  ↓
                        Pillow 排版 + FFmpeg 渲染
                                  ↓
                         MP4 + 分镜 + 检查报告
```

用现有工具完成下载、媒体处理与图像排版；项目只实现串联、素材约束、排版和界面。参考了 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的公开接口和 [FFmpeg](https://ffmpeg.org/) 滤镜能力。评估过 [PySceneDetect](https://github.com/Breakthrough/PySceneDetect)；v0.1 使用 FFmpeg 自带场景检测，避免额外 OpenCV 依赖。

## 范围与后续方向

- 已实现：链接/视频输入、照片输入、硬切节奏、原声、去重、轮换名字、本地网页、日期/水印声明检查、测试与 CI。
- 待实现：OCR 文字位置提取、视觉模型风格分析、可编辑时间线、视频素材片段、复杂转场、自动素材检索。
- 下载器是否能取得某个抖音视频取决于平台当前状态；CI 不承诺公开链接一直可下载。

欢迎以 issue 描述“参考中哪种特征未被保留”，并提供可公开授权的小样；不要上传他人的私密素材或 Cookie。

## 许可证

项目代码为 [MIT](LICENSE)。第三方工具的许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。代码开源不代表参考音乐、照片或字体可随意再分发，请自行确认使用权。仓库不包含真人照片、下载的视频、音乐、系统字体或账号凭据。
