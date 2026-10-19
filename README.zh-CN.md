# StageSpatialCue — Mac 本地四声道空间音频 Cue 系统

> **当前版本 v0.1：可供界面设计、声向算法验证及排练研究的原型。尚未在真实 Mac + 四路声卡 + 调音台 + 音箱链路上验证，不能直接视为稳定的正式演出系统。** 项目的完整版功能矩阵、技术限制和测试流程请阅读 [English README](README.md)。

## 主要用途

面向戏剧舞台、空间音频创作和 ADHD 听觉研究，提供像 QLab 一样按顺序触发 Cue 的系统，但是特别突出：

- 四声道独立输出与音箱声向几何配置。
- 360° 交互式圆盘（0° 在 12 点钟，顺时针为正，270° 在 9 点钟，编辑精度 0.01°）。
- 每个 Cue 单独设置音量、fade in、fade out、替换上一轨的 transition、播放模式和方向 modulation。
- Envelope 图上的 keyframe 可拖动，用时间（秒）和相对角度（°）控制声音绕舞台移动。
- 多项目独立存储、按照文件名编号导入文件夹并排序。
- 空格 GO、S 停止、Alt+↓ Skip、Shift+Esc PANIC、主静音、总音量、四个输出电平条。
- 简单的整体空间旋转（Global rotation），会作用于正在播放的音源。
- 保存实验操作事件和音频软件帧时序记录（不等于实测声学延迟）。

## Mac 安装

确保安装 Python 3.11–3.13（推荐 Python 3.12）与 Homebrew，然后执行：

```bash
brew install python@3.12 portaudio libsndfile ffmpeg
cd StageSpatialCue
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# 可选：生成用于界面探索的模拟声音和示范 Cue
python scripts/seed_demo.py

# 启动系统
stagespatialcue
```

浏览器访问：**http://127.0.0.1:8765**，推荐使用 Chrome 来上传整个文件夹。`run_mac.command` 也可以直接在 Mac 上运行，它会尝试创建虚拟环境并安装依赖。

音频设备没有准备好时，仍可正常编辑、保存 Cue 和项目；实际四声道播放会被禁止。

## 舞台硬件连接

```text
Mac → 支持 4 路独立输出的 USB/Thunderbolt 声卡
      ↓ OUT 1、OUT 2、OUT 3、OUT 4（四根音频线）
   调音台四个独立输入
      ↓ 四条独立的 AUX / MATRIX / 专用输出路径
   音箱 1、音箱 2、音箱 3、音箱 4
```

**不能**把四条输入都混入调音台的普通立体声 L/R 主输出，否则四声道空间感会丢失。若调音台自己能够作为 Mac 的 USB 多声道音频输出设备，也可能不需要外置独立声卡，但必须确认 Mac 能看到至少 4 个独立输出通道。

1. 调低所有调音台/功放输出，先接好音频设备。
2. 打开 macOS 的「音频 MIDI 设置」（Audio MIDI Setup），确认声卡有 4 个独立输出，优先将设备采样率设为 **48 kHz**。
3. 启动本地页面，选择输出设备，点击 **Connect audio**。首次连接强制 **MAIN MUTE ON**，防止突然播放。
4. 小音量解除静音，依次测试输出 1–4。此功能播放低电平的 440 Hz 短音，但**不是**声压级标准校准信号。
5. 在 **Stage setup** 中填写每只音箱的：角度、距离（m）、声卡输出通道、独立 trim（dB）。
6. 导入声音，点击 **Preflight**，现场检查 XRUN、音量峰值、四路不串音、GO 和 STOP 的表现。

## 文件夹导入规范

```text
你的某部舞台剧/
  001_Scene1_Opening.wav
  002_Scene1_Whisper.wav
  003_Scene1_Background.wav
  004_Scene2_SpatialOrbit.wav
```

上传后会按照开头编号自动排队，允许手动上下移动。推荐统一使用 48 kHz PCM WAV。程序会把输入音频混为 mono，然后按照空间算法分配给四只音箱。MP3、M4A 等格式需要 FFmpeg 或兼容的音频解码器。

项目会保存在 `~/.stagespatialcue/projects/<项目ID>/`，含 `project.json`、`media/`、`events.jsonl`。导出按钮可把整个项目及事件日志打包 ZIP。默认只监听本机的 `127.0.0.1`，没有云端上传。

## 一个 Cue 的播放逻辑

| 配置项 | 用途 |
|---|---|
| `start_mode = replace` | 与正在播放的音频交叉淡化，之前的音轨在 `transition_s` 内退场 |
| `start_mode = layer` | 与已有声音同时播放，不打断其它音轨 |
| `start_mode = queue` | 等待所有当前或已经排队的声音结束，再等待 `pre_wait_s` 开始 |
| `fade_in_s` / `fade_out_s` | 自己的入场与自然结尾淡入淡出，互相独立 |
| `transition_s` | **replace 时**上一批音轨的短交叉淡出时间，用于避免 click |
| `pre_wait_s` | Cue 被 GO 触发之后的启动延迟；不自动等于“与上一条结束之间的间距” |
| `continue_mode = manual` | 需要人工再按一次 GO |
| `continue_mode = auto_continue` | 本 Cue 开始后 `post_wait_s` 自动触发下一个 |
| `continue_mode = auto_follow` | 本 Cue 结束后 `post_wait_s` 自动触发下一个 |
| `position_deg` | 本 Cue 的静态基本方向 |
| `modulation` | 相对于基本方向的时间变化偏移曲线 |
| `gain_db` | 本 Cue 音量 |

Modulation 使用绝对时间（秒）+ **相对角度偏移**。例如基本声向是 350°，在 4 秒内把偏移从 0° 改为 +20°，声音会通过 0° 移动到 10°。偏移达到 +360° 则是一整圈。全局旋转则独立叠加在所有 Cue 上。

**空间算法是 2D VBAP（双相邻音箱增益分配），不是空间声学仿真或 HRTF。** 只输入四只音箱到某一个点的距离，无法反推出音箱分布；因此系统也需要四个方位角。每个演员如果在舞台上移动，听到的真实方向可能不同，需要单独标注和测量。

## 研究与技术注意事项

这套原型的声向属于可重复的**软件指令参数**，不是对 ADHD 参与者的生理/心理效应测量。真正实验需要定义听众/演员的听音位置、对照条件、音量范围、音频内容、随机/平衡顺序和人类参与者伦理审查。不能把未测量的感知方向当成绝对准确。

当前尚未实现：麦克风实时输入混音、精确音箱距离延迟补偿、HRTF、立体声源保留、波形裁剪、循环播放、长文件流式解码、OSC/MIDI、外部时间码、真正实时安全的 CoreAudio 原生线程，以及临床级/演出级容错和声压保护。

技术模块与未来 JUCE/CoreAudio 迁移架构参见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)；研究设计和需求清单见 [RESEARCH_PROTOCOL.md](docs/RESEARCH_PROTOCOL.md)。

## 测试和推送 GitHub

```bash
python -m pytest -q
# 已建立本地 git commit；如需新建 GitHub 仓库并推送：
brew install gh
gh auth login
gh repo create StageSpatialCue --private --source . --remote origin --push
```

仓库当前只在提供的 ZIP 里，**尚未声称已上传到远端 GitHub**。建议确认项目名称、公开/私有权限及所属 GitHub 账号后再发布。研究参与者数据、受版权保护的原音频不要直接提交到公开仓库。
