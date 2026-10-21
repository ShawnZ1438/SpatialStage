# SpatialStage · 四声道舞台声音 Cue 系统

[English](README.md) · [架构](docs/ARCHITECTURE.md) · [校准步骤](docs/CALIBRATION.md) · [AutoCal](docs/AUTOCAL.md) · [修复与验收](docs/RELIABILITY.md) · [待定决策](docs/OPEN_QUESTIONS.md)

**v0.3.1：排练原型，不是正式演出或听力安全认证系统。** 浏览器控制界面 + Mac 本地 Python 四声道音频引擎。演员是聆听者，没有观众朝向；不做演员跟踪，不记录研究参与者数据，也不声称对 ADHD 有治疗或改善效果。当前 Python 回调仍有锁和内存分配，尚未完成真实 Apple Silicon Mac / 调音台 / 麦克风 / 四音箱验收。必须保留独立的物理静音手段。

## 1. 安装与启动

推荐原生 Apple Silicon Python 3.12，支持范围 3.11–3.13。音频接口/调音台必须向 Mac 暴露至少四路独立输出，工作采样率 48 kHz。不要把普通双声道 USB 接口或耳机输出误当成四声道。

```bash
# 已有 Homebrew 的 Mac，首次准备依赖：
brew install python@3.12 portaudio libsndfile ffmpeg
git clone https://github.com/ShawnZ1438/SpatialStage.git
cd SpatialStage
./run_mac.command
```

打开 `http://127.0.0.1:8765`。启动器首次运行或 `pyproject.toml` 变化时创建/更新 `.venv` 依赖，此时可能需要联网；依赖齐全后的常规运行在本机完成。新建环境可用 `SPATIALSTAGE_PYTHON=/path/to/python3.12 ./run_mac.command` 指定解释器；不会擅自删除不兼容的旧环境。

已有仓库：先备份项目数据，再 `git pull --ff-only`，然后运行启动器。不要用强制覆盖来丢弃你自己的修改。手动方式：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
spatialstage
# 或：
python -m uvicorn stagespatialcue.server:create_app --factory --host 127.0.0.1 --port 8765
```

项目默认保存在 `~/.spatialstage/projects`，可用 `STAGE_SPATIAL_DATA` 指定另一目录。网页不负责播放声音，刷新页面不会关闭音频设备；不过离开页面时未保存的编辑仍需处理。

## 2. 四音箱空间设计与物理连接

在地面标记舞台中心 `(0,0)` 以及 12 点钟方向。+X 向右、+Y 向上；0° 在上、90° 在右、180° 在下、270° 在左，顺时针增加。输入每只音箱相对中心的 **X/Y 米制坐标**；系统用 `atan2(x,y)` 和欧氏距离转换。仅四个距离不足以确定空间布局。原点由现场中心标记定义，不自动追踪演员或重算活动中心。

| 音箱 | 建议初始角度 | 默认输出 |
|---|---:|---:|
| L 左前 | 315° | CH1 |
| R 右前 | 45° | CH2 |
| RR 右后 | 135° | CH3 |
| RL 左后 | 225° | CH4 |

四只音箱尽量均匀围绕活动圆周、朝向中心，可以为避开圆边缘后移。以实际测量坐标为准，不强制精确对角线。校验四路不重复，相邻音箱夹角小于 180°。采用以中心为参考的二维恒功率 VBAP，计算相邻两只音箱的幅度。表盘的 0.01° 是输入分辨率，不是保证可听辨的空间精度。

```text
Mac → USB/Thunderbolt 四输出声卡或多通道 USB 调音台
    → 四条独立 return / line 通道
    → 四条独立 bus / direct out → L / R / RR / RL
```

四个接口最终若被调音台合并成同一个立体声 master，就失去了独立声向控制。声卡方案保留；USB 调音台、模拟线路或 aggregate device 的实际兼容性取决于设备暴露的通道、驱动、采样率和时钟，不能承诺“所有连接方式”自动工作。现场调音台和接口型号仍待确认。

先让演员离场，降低物理增益，逐路 Test CH 验证 CH1–4 与实际音箱对应。几何校准预览只给出理论时间差/增益，不会自动施加延迟；测量式 AutoCal 是另一套人工审批流程。模型不计算墙面反射，不代表现实场地没有反射。中心附近成立的虚拟声向也不保证覆盖整个演员活动范围。

## 3. 素材导入、排列和保存

建议命名 `001_Footsteps.wav`、`002_Car.wav`。选择文件夹或多个文件：**只排序本次新导入的文件，再追加到原有列表**；不会重新排序手动编排好的 Cue。↑/↓ 调序，点击行查看配置。选中行只是编辑对象，只有 **ARM SELECTED** 才把它设为 NEXT。

NEXT 按 Cue ID 保存，调序或导入不会偷偷改成另一条音频；删除 NEXT 后显示需要重新 ARM，不自动猜测下一条。列表中 BEFORE 仅表示位于 NEXT 之前，不能当成已经播放的记录。

WAV/AIFF/FLAC/OGG 由 libsndfile 解码；不支持的格式可由已安装 FFmpeg 回退。当前所有文件都会下混成单声道并重采样到 48 kHz，**不保留立体声宽度**。单文件预解码上限 30 分钟，FFmpeg 回退会按该上限截断，长素材请拆分。解码缓存上限 700 MiB，不代表整个进程最大内存。上传每文件 150 MiB、整次请求 256 MiB、每批 250 文件，大批素材请分批。

修改当前 Cue 的文件只影响下一次重新播放；正在播放或已排队的 PCM 不换。声向、增益和包络可实时更新，已有播放计划不会因修改 pre/post wait 而重新排期。实时改变自然 fade-in/out 时加入 15 ms 过渡。想测试新的时间安排，请 STOP 后重新 ARM/GO。

自动保存采用串行修订队列：前一次保存未返回时仍保留后续编辑，并继续提交最新状态。失败显示 **Save failed — changes retained**，可点 **Retry save**；设置对话框只在后端确认保存后关闭。离开页面有未保存状态提醒。当前不支持多标签页并发版本冲突解决，**同一项目只用一个编辑窗口**，导入/替换媒体或切换项目期间不要同时编辑其他参数。

## 4. 播放控制与精确语义

| 操作 | 行为 |
|---|---|
| 空格 / FADE GO | 播放 NEXT 及自动链，遵守 start mode、pre-wait、transition |
| C / CUT GO | 立即触发一条 NEXT，忽略 pre-wait/queue/layer，5 ms 去点击替换，不继续整条自动链 |
| S / STOP | 40 ms 软停止，并取消待播；重复停止不得抬高停止包络或延长原结束点 |
| Alt+↓ / SKIP | 只推进 NEXT，不停止已经播放的音频 |
| MAIN MUTE | 最终输出约 15 ms 渐变静音/解除静音；**音频和全局时钟仍在走，不是暂停** |
| Shift+Esc / PANIC | 软件立即清空 voice、延迟缓冲并静音，同时请求取消 AutoCal；输入框/对话框中也可触发 |

普通输入操作不会误触发空格播放。PANIC 不可能收回设备、调音台或音箱里已经缓冲的采样，因此仍需物理静音。STOP/PANIC 不等待网页保存；还在等待保存的 GO 会被取消，不在急停后补发。

start mode 有 replace（替换）、layer（叠加）、queue（等已有声音结束）。Replace 可用可调交叉淡化，或去点击直接切换；短音效的转入淡化最多占素材一半。每条 Cue 自己的自然淡入淡出仍作用于文件内部，不额外拉长文件。

自动链：`auto_continue` 以当前声音开始时间 + 当前 post-wait 为下一条锚点；`auto_follow` 以当前声音结束 + post-wait 为锚点；下一条再叠加自己的 pre-wait。两侧间隔都设置时会相加，fade 时间不从间隔里扣除。同一自动链中 **同帧开始的零间隔 Cue 视作同时播放组**，即使默认 replace 也不互相吞掉；不同开始时间仍按 replace 处理。这是当前明示的实现选择，后续可讨论是否改成专门的 Group Cue。

ARM/自动链推进时后台预热下一组 PCM。**冷缓存 GO 会明确拒绝，不同步解码、不排一个迟到播放任务。** 等 Ready 或运行 Preflight 后再按 GO。整条自动链需要在缓存容量内；Preflight 报告媒体/缓存问题。输出设备掉线后会锁定静音并拒绝 GO；只能人工重连、检查后解除静音，不自动重播。

## 5. 360° 声向、包络与全局引导

最终方向 = Cue 基础角度 + Cue 方向包络偏移 + 全局旋转 + 全局时间包络，最后归一化到 0–360°。Cue 包络可为自由关键帧或方向 ADSR；ADSR 控制角度偏移，不是音量。0→360° 的未折返偏移代表顺时针一整圈。

汽车从左向右：基础角度 270°，偏移 0→180° 表示经上半圈；0→−180° 表示经下半圈。当前只有圆周方向，不等于真实二维“从左侧某点经过演员面前再到右侧某点”的轨迹，距离/坐标路径设计留待后续。

方向 ADSR 的 Release 当前按文件结尾触发，不是 STOP 按键触发。全局包络从第一条排定 Cue 开始，静音和空场时间仍继续；无活动声音时重新 ARM 会重置演出包络。真正的暂停/恢复、全局时钟手动冻结和触发式 Release 尚未实现，不能把 MAIN MUTE 当成这些功能。

## 6. AutoCal（保持已确认配置）

**1 测量点 / balanced / XLR 麦克风 / EQ 关闭。** 麦克风放舞台中心、接近演员耳高；尽量使用同一兼容双工接口/时钟。停止并断开 show 输出，保持 MAIN MUTE，演员离场，物理输出降低，确认麦克风通道和四路输出再开始。

AutoCal 是独立测量流：show 的 MAIN MUTE **不会阻止用户明确启动的扫频测试**。四通道依次扫频，结果显示录音电平 dBFS、SNR、相对延迟和归一化频响。保存的是配置和诊断 JSON，不存原始麦克风录音。测量完成后仍需人工复核、键入 APPLY，且质量、设备与布局检查通过才能启用有限衰减和相对延迟；不能靠普通项目保存绕过批准。EQ 一直关闭。

新加 **Cancel measurement**，PANIC 也请求终止测量。取消期间锁仍占用，等待驱动/worker 返回后才释放；半途取消不会保存成可应用的完整报告。停止是 best-effort，现场必须仍能物理静音。单点 balanced 只针对中心，不是 Audyssey 的多位置优化；dBFS 不是 dB SPL，不能据此声称绝对听力安全。调音台增益/DSP、音箱位置或路由有变化后必须重新检查校准。更多见 [AUTOCAL.md](docs/AUTOCAL.md)。

## 7. 备份、安全和测试

项目 JSON 原子写入，媒体路径限制在项目内部。ZIP **仅支持导出**：当前项目 JSON、被引用媒体和 AutoCal JSON；不包含 events.jsonl、临时文件和未引用素材。超过 8 MiB 的导出缓冲转到临时磁盘文件，再分块传输。暂无已验证 ZIP 恢复/导入按钮，备份时也应保留原始项目文件夹。

本机服务器只绑定 127.0.0.1:8765，Host/浏览器 Origin 收紧到本机 8765 端口。不能把它当成对本机恶意程序的权限隔离，也不要开放给局域网或外网。操作诊断默认关闭；不增加参与者研究日志。

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
node --check stagespatialcue/static/app.js
node --check stagespatialcue/static/save-queue.js
node --test tests/js/*.test.cjs
python -m ruff check stagespatialcue tests
python -m playwright install chromium
python scripts/browser_smoke.py --spawn
```

CI 配置覆盖 Python 3.11/3.12/3.13、JS 语法/保存竞争回归、Python 正确性 lint 和浏览器交互；是否通过应查看具体提交结果。浏览器测试使用临时项目和静音素材，不发声，支持 `--browser-path`，没有写死 Mac/Linux 路径。受限测试环境可显式选 `--inline-transport`：离线页面通过测试桥访问本地 API，**不等同于正常 HTTP 导航测试**。

本次五项核心 bug 均有失败复现和回归覆盖，更多边界及硬件验收见 [RELIABILITY.md](docs/RELIABILITY.md)。上真机后重点验证逐路接线、连按 GO/STOP、mute、掉线、最大 polyphony、校准取消和物理限幅；所有演员参与前由现场音频负责人确认安全电平。
