# SpatialStage — 面向 ADHD 演员的四声道空间声音戏剧 Cue 系统

[English README](README.md) · [详细音箱标定流程](docs/CALIBRATION.md) · [技术架构](docs/ARCHITECTURE.md) · [待定决策](docs/OPEN_QUESTIONS.md)

> **v0.2 是 Mac 本地可运行的排练原型，而不是经过现场验收的正式演出系统。** 音频算法和 API 已实现自动化测试；实际的 Apple Silicon Mac、调音台、四路音频接口和音箱尚未完成硬件测试。请勿把软件中指定的方向直接等同于演员实际听到的方向，也不能用这个软件推断 ADHD 的治疗或研究结果。默认不保存任何参与者实验记录。

## 一、这个项目做什么

SpatialStage 专门服务于没有固定观众、以 **舞台中央 ADHD 演员为听音者** 的声音剧场探索。四只独立音箱环绕圆形演员活动区，声音根据剧本分为多个 Cue；导演/声音设计师预先设计「什么时候发声、从哪个方位、音量、停留多久、声音如何移动」，现场操作人员用 `Space / FADE GO` 或 `C / CUT GO` 触发。对于正在播放的声音，也允许实时更改声向、音量与方向调制曲线。

架构不是浏览器发出立体声，而是：

```text
Mac 本地网页（Cue 列表、360° 表盘、ADSR/Keyframe、总控）
            ↕ FastAPI localhost:8765
Python 音频引擎（时间轴、逐帧声向计算、混音、淡入/淡出）
            ↓ PortAudio / CoreAudio / 48 kHz / 4 路 PCM
Mac 看到的 4+ 通道 USB/Thunderbolt 音频设备
            ↓ OUT 1 / OUT 2 / OUT 3 / OUT 4
调音台四个相互隔离的输入/输出总线（可用 AUX/MATRIX）
            ↓
四个物理音箱：L、R、RR、RL
```

界面浏览器刷新不等于播放音频的设备被关闭；真正的四声道混音运行在本地服务中。不过 Python callback 仍有实时稳定性限制，正式演出前必须做硬件与压力测试。

## 二、舞台坐标约定（已固定）

- 舞台上**不存在“朝向观众”**的正面。零点在四音箱共同的几何中点，演员在四只音箱围成的区域内移动；所有空间算法以这个**固定中心点**为参考，并非追踪每个演员实时位置。
- `0°` 在 12 点钟，`90°` 在 3 点钟，`180°` 在 6 点钟，`270°` 在 9 点钟；角度**顺时针增加**，允许精确到小数点后两位。
- 二维平面 +X 向右（3 点钟）、+Y 向上（12 点钟），单位 **米 (m)**；不考虑墙壁反射的模拟，但物理现场反射依旧存在。
- 默认四只音箱大约放在钟面上 10–11、1–2、4–5、7–8 点方向，即：

| 物理名称 | 软件输出 | 默认方位 | 默认距中心 | 朝向中心的音箱轴线 |
|---|---:|---:|---:|---:|
| L — 左上 / Front Left | CH 1 | 315° | 3 m | 135° |
| R — 右上 / Front Right | CH 2 | 45° | 3 m | 225° |
| RR — 右下 / Rear Right | CH 3 | 135° | 3 m | 315° |
| RL — 左下 / Rear Left | CH 4 | 225° | 3 m | 45° |

不同调音台可能使用不同的编号，**软件输出通道与物理音箱可以在 Stage setup 里重新映射**。角度排序是根据实际位置决定，不强制要求四个角完全均匀。如果音箱为了躲开圆形舞台边缘而稍微往后移动，只要在表格中输入真实 X/Y，程序就能自动算出真实方位与中心距离。

### 软件如何计算声向

采用二维 **VBAP（Vector-Based Amplitude Panning）**。对于任意目标角度，软件寻找相邻的两只音箱，计算各自的正向增益，再做恒定功率归一化。例如目标正好落在右上 45°，主要走 CH2；目标在上方 0°，通过左上 CH1 与右上 CH2 同时播放形成中央虚拟声源。移动中的车声可以从 270° 向 90° 逐渐经过其它音箱。软件支持不规则的四角布局，但**不能保证每一个不断走动的演员都感到完全相同的声源方位**。

四音箱的数值建模使用：

```
X = distance × sin(angle)
Y = distance × cos(angle)
angle = atan2(X, Y) 后转换为 0–360°
distance = √(X²+Y²)
```

## 三、现场音箱如何 calibrate？需要输入什么？

在右上角 **Stage setup** 中输入每只音箱相对中心点的 **X/Y（米）、物理 Output CH、名称、独立 Trim（dB）**。坐标会自动转换为角度和距离；点击 **Preview calibration**，还可以计算中心点的以下理论参数：

1. `θ`：扬声器的实际中心方位与它应该面向舞台中心的方向；
2. `d`：扬声器距离演员参考中心的长度；
3. 近似到达时间 `d/343×1000` 毫秒（假设约 20°C 空气）；
4. 如果有远近不等的音箱，近音箱需要的理论**额外延迟** `(最远距离-d)/343×1000` 毫秒；
5. 理论距离增益建议 `20log10(d/四只音箱距离中位数)` dB。

**请注意：系统当前只显示额外延迟建议，不会把它自动加到物理音频输出里。** 调音台/功放内部延迟、现场反射和音箱自身频率响应未知，仅凭坐标无法自动完成真实 acoustic calibration。`distance compensation` 是需要你主动勾选的简化距离增益选项；默认不开。界面中的 per-speaker `Trim` 是真正会被软件应用的手动电平值。

下一步现场需要你提供：

- 四音箱相对舞台中心 `(X, Y)` 的实测坐标（米），以及舞台上 12 点钟的地面参考标记；
- Mac 接的调音台品牌/型号，能否作为 USB 多通道音频设备；如果不能，音频接口型号和独立 OUT 1–4 的接线；
- 每只音箱的扬声器/功放输出是否能被单独调节、调音台相应路由设置；
- 最好在舞台中心放一只校准过的声压计或测量麦克风，逐只音箱播放相同测试信号，记录其音量，再使用 Trim 对齐。演员还需要在舞台多个活动位置做主观声向和舒适音量检查；
- 如需精确时间补偿，另需用测量麦克风/接口测脉冲到达时间，不是只凭肉眼位置。

现场操作顺序、接线表模板、记录表见 [docs/CALIBRATION.md](docs/CALIBRATION.md)。在未知硬件前，不能保证每个 4 声道输出设备都与所有调音台无缝连接。

## 四、在 Apple Silicon Mac 上安装

建议 Mac 安装 Python 3.12、Homebrew（安装在 Apple Silicon 默认 `/opt/homebrew`）、PortAudio、libsndfile 和 FFmpeg：

```bash
brew install python@3.12 portaudio libsndfile ffmpeg

git clone https://github.com/ShawnZ1438/SpatialStage.git
cd SpatialStage
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

# 可选：生成模拟声音和示例 Cue
python scripts/seed_demo.py

# 启动本地界面
spatialstage
```

浏览器打开 **http://127.0.0.1:8765**。也可以双击 `run_mac.command` 安装并运行，但要求本机已有受支持的 Python。退出时在终端按 `Ctrl+C`。

没有 4 路音频设备，也能导入文件、编辑 Cue 并保存项目；只是不能启动真实音频播放。Mac 的系统耳机孔通常是 2 路输出，不能代替四个独立物理通道。可参考 Apple 官方 [Audio MIDI Setup](https://support.apple.com/guide/audio-midi-setup/set-up-audio-devices-ams59f301fda/mac) 及 [多通道音箱配置](https://support.apple.com/guide/audio-midi-setup/set-up-external-speakers-for-stereo-or-surround-sound-ams1005/mac)。

### Mac → 调音台的接法

**方式 A：有 4+ OUT 声卡（最通用）**：Mac USB/Thunderbolt → 音频接口 → 4 根线到调音台独立输入 → 四条隔离 AUX/MATRIX/输出总线 → 四只音箱。

**方式 B：调音台自身支持 USB 多通道音频**：Mac USB → 调音台，确保 Mac 实际能看到 ≥4 个独立输出声道，而且控制台内部能把它们分别送到四条物理输出。仅有一个立体声 USB L/R 的调音台不满足需求。

在所有设备低音量/静音下接线，设为 **48 kHz**（如果支持），选择 Output Device，点击 **Connect audio**，默认保持 **MAIN MUTE ON**。在调音台/功放音量调低的情况下手动 unmute，然后依次 **Test CH 1–4**。每个输出测试为一段低电平 440Hz 正弦音，用于检查通道连接，**不属于声压计校准信号**。

## 五、Cue 设计与两个现场切换按键

从本地选择文件夹，可以导入编号音效：

```text
MyShow-SFX/
  001_Door_Open.wav
  002_Whisper.wav
  003_Car_From_Left_to_Right.wav
  004_Ambient_Transition.wav
```

上传后按开头数字排序，之后仍可以手动 ↑↓ 排列。可改每条 Cue 的标题、文件、时长/音量、淡入、淡出、方向以及复杂 Modulation。单次上传每个文件上限 150 MiB、单轨预解码时长不超过 30 分钟，尽可能提前转成 **48 kHz PCM WAV**。原始立体声音频目前会混为 mono 再进行空间定位。

| 操作 | 实际结果 |
|---|---|
| **FADE GO**（`Space`） | 按下一条 Cue 的 start mode 与 transition 执行（默认过渡 2.5 秒，可修改） |
| **CUT GO**（`C`） | 忽略下一条 Cue 的 queue/pre-wait，立即替换正在播放的声音，用 5ms de-click 防爆音；只触发当前这一条，后续自动链接不继续 |
| **STOP**（`S`） | 所有正在播放的声音以短淡出结束；排队但未开始的声音取消 |
| **SKIP**（`Alt+↓`） | 跳过下一条 Cue 不播放 |
| **PANIC**（`Shift+Esc`） | 立即清除所有声音并强制 MAIN MUTE |
| **MAIN MUTE** | 一键静音四声道输出，解锁需要主动点击 |
| **ARM SELECTED** | 选中任何一条 Cue 作为下一条要播放的声音；单纯点击列表只编辑不播放 |

**每条 Cue 的触发方式：** `replace` 替换当前音频，旧轨根据该 Cue 的 `transition_s` 淡出（或设置为 5ms cut），新轨淡入受到原始 fade-in 及过渡长度限制；`layer` 不停止以前的轨道，同时播放；`queue` 等目前所有播放/排队的声音完毕才开始。操作者可以随时用 CUT GO 覆盖这些行为以便直接切换。

**Fade 与间隔的关系：** `fade_in_s` 和 `fade_out_s` 是这条音效**内部**的音量变化；`pre_wait_s` 是音效开始前的等待；`post_wait_s` 是自动下一条的附加间隔，不从 fade in/out 时间里扣除。

- `manual`：每次都由操作者按 GO，`post_wait_s` 不执行。
- `auto_continue`：上一条 Cue **音频开始帧**加 `post_wait_s`，然后再叠加下一条 `pre_wait_s`，自动触发下一条（可以同时播放）。
- `auto_follow`：上一条 Cue **音频实际结束帧**加 `post_wait_s`，再叠加下一条 `pre_wait_s`，自动触发下一条。自然 fade-out 已经位于音频末尾内部，不需要再算一次。

**例子：** A 从 0 秒播放，长 4 秒，最后 1 秒自然 fade-out；A 设置 `auto_follow` + `post_wait_s=2`，B 的 `pre_wait_s=1`，则 B 在 `4+2+1=7` 秒开始自己的 fade-in。不是 `4−1+2+1` 秒。

## 六、每条 Cue 的 360° 声向与 Modulation

### 交互表盘与自由 Keyframes

点击右侧圆形表盘可将基础声向设为 `0.00–359.99°`，蓝绿色指针代表 Cue 的基础位置，金黄色表示叠加当前 global 设置后的预期方向。打开 **Free keyframes**，以「X = 自己音频播放时间（秒），Y = 相对于基础角度的旋转偏移（度）」绘制轨迹。

例如汽车从左侧移到右侧：基础 `270.00°`，`(0s,0°) → (4s,+180°)`，声音在 4 秒内顺时针从 9 点钟滑向 3 点钟。想反向则设置 `−180°`。`+360°` 表示顺时针整整绕一圈，而不是采用最短转向路径。编辑精度到小数点后两位。

### 新增：方向 ADSR（不是音量 ADSR）

Cue 中的 **Direction modulation curve** 可以选择 `ADSR direction offset`：

- **Attack**：从相对基础声向的 `0°` 逐渐走到 `Peak offset`；
- **Decay**：从 `Peak offset` 走到 `Sustain offset`；
- **Sustain**：保持在 `Sustain offset`，直到音效末尾进入 Release；
- **Release**：从 `Sustain offset` 移动到 `Release final offset`。

Attack/Decay/Release 都有以秒为单位的可编辑时间，角度偏移允许为负数，也允许跨多圈。当音效太短、各阶段之和超过音频长度时，系统自动按比例压缩各阶段，避免出现负 sustain 时间。这四阶段是**声向曲线**，与音频自己的 fade in/out 无关。

### 整体声向 Global Envelope

左侧 **Spatial Master** 除了 `Global rotation` 数值外，还有可以启用的全局 show-wide keyframe 曲线。每个 keyframe 是「演出时间 / 角度偏移」。演出计时从该次 ARM 之后 **第一个实际音频开始**计算；**所有 Cue** 都会在自身方向上再加上这条全局偏移。

```
最终声向 = (Cue 基础角度
         + 本 Cue 随音效时间变化的 offset
         + Global rotation
         + Global show envelope 在演出时间上的 offset) mod 360°
```

选中当前 Cue 修改 `position_deg`、`gain_db`、Keyframes/ADSR 后，会通过自动保存（约 300ms）向正在播的 Voice 应用新值，音频引擎会平滑部分控制跳变。**调音台硬件延迟不在 300ms 内**，需现场测量。编辑**音频文件本身**只会影响今后的 GO：已经载入内存正在播放或已排程的声音不会突然换文件。舞台几何/输出通道在连接且未静音期间不允许修改。

## 七、多项目存储与文件结构

数据全部保存在本机，不上传到 GitHub 或任何第三方：

```text
~/.spatialstage/projects/<项目ID>/
  project.json       # 曲目顺序、音箱几何、声向、ADSR、全局曲线等
  media/             # 上传后的本地复制音频文件
  events.jsonl       # 只有手动开启诊断 SPATIALSTAGE_DIAGNOSTICS=1 才会出现
```

左上角 `New Project` 可以新建项目；每个项目保留自己的媒体、几何信息与 Cue 顺序，`Export show ZIP` 可以导出整个项目。默认**不记录 ADHD 演员的实验数据或行为**；可选日志仅是操作指令与软件处理情况。先前 v0.1 如保存在 `~/.stagespatialcue/projects`，需要**关闭软件后手动复制原来的项目目录**到 `~/.spatialstage/projects` 才能沿用；读取旧 JSON 会使用新增属性的默认值。

## 八、完成情况与下一步验收

**已经完成的原型能力：** 4-channel VBAP、坐标转换、理论 calibration preview、两种 GO、replace/layer/queue、cue 淡入淡出、relative keyframe、ADSR、全局声向 Envelope、播放中修改、Cue 音频替换、编号导入、批量音频预解码、项目保存/导出、主静音/声道测试/状态灯。

**还没有完成并且不能擅自声称完成：** 真实 Mac 与调音台的四声道实测，真实声压级/相对延迟标定，自动输出时间补偿，演员实时位置追踪，HRTF/真实声场重建，保留原始立体声空间床、无限 looping、大型现场压力测试、硬实时 C++ CoreAudio 引擎、以及正式演出容错验收。

本版本优先支持声音设计师按剧本进行创作和排练。对于 ADHD 演员，优先确保**音量舒适和可控、可以随时暂停/MAIN MUTE，以及现场工作人员有独立音量控制权**。声音位置仅作为刺激设计参数，不推断医疗或心理影响。

本地验证：

```bash
python -m pytest -q
node --check stagespatialcue/static/app.js  # Node 可选
```

详细边界决策见 [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md)。MIT 许可，本项目与 QLab 没有商业或技术从属关系。
