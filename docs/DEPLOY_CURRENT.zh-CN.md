# 从零部署当前演出包

本功能分支包含20条音频、当前演出配置和应用。首次导入采用 show/project-template.json，恢复cue ID、顺序、增益、方向、路径、预设和调度。已有本地项目不会被模板覆盖。设备连接、运行中NEXT、master推子/静音不是项目模板；每次启动断开设备并保持静音。声学校准不跨机器启用，需在现场重新验收。

1. 安装 Python 3.11–3.13（推荐3.12），Mac可用 `brew install python@3.12`。MP3/M4A导入另需FFmpeg；随包WAV/FLAC无需它。
2. `git clone --branch feat/cue-layers https://github.com/ShawnZ1438/SpatialStage.git`，或下载该分支的GitHub ZIP并解压。音频约409 MiB，均为普通Git文件，不需要LFS或付费存储。
3. 双击 Install SpatialStage.command，一次安装依赖。
4. 双击 Start SpatialStage.command（主数据：`~/.spatialstage/projects`）或 Start Simulation (Mac).command（隔离数据：仓库 `SpatialStage-test-data`）。打开 http://127.0.0.1:8765/ 。模拟入口只切数据目录，输出需自行连接。
5. Edit → LOCAL SIMULATION → Connect silent simulation → Preflight；应20条、约624.1MiB。明确确认SILENT ENGINE后解除MAIN MUTE，可无声检查逻辑。
6. 要试听，Edit里选Virtual 4 speakers或Mono sum；Connect headphone monitor第一次在设备列表为空时只列设备，选耳机/内置双声道后再次点击连接。重连后保持静音，先降低主推子再明确解除静音。监听比旧版提高6dB，增加0.98峰值保护与monitor overload blocks提示；四路输出和capture不变。近音箱的虚拟位置可能超限，降低音量或移回中心。真实四路设备用Audio devices / Connect audio。
7. 界面（v0.4）：左边音频库、中间舞台图、右边 Cue 列表。把音频拖到舞台图或 Cue 上即可加层，详见 SHOW_GUIDE 第 4、5 节。Cue 列表里单击选择；“从选中cue开始 · 仅准备”或“回到第一条 · 仅准备”设置NEXT/SEL，再GO。双击或“试听选中”只播这一条，立即替换、不自动接续，NEXT保留此条；未连接/静音/未预载时拒绝。STOP淡出，PANIC清空并静音。
8. 选择cue后↑/↓调整顺序，自动保存。#序号是播放顺序，标题01–20是素材编号。活动/等待声音先STOP再重排。没有拖拽；按钮支持键盘。空间/增益编辑会影响当前同cue声音；换媒体下次播放生效。
9. 等Saved locally（失败先Retry save），停止capture/测量、PANIC，然后双击Stop SpatialStage.command。它核验应用身份并正常结束后台服务。成功后才切换环境或更新代码；不需寻找隐藏终端。只开一个编辑窗口。

新机器要复现随包快照，请使用空数据目录；不要删除已有项目来强制恢复。可以在终端设置 `STAGE_SPATIAL_DATA=/path/to/new-directory ./run_mac.command`。现有项目中的用户编辑/顺序不被正常更新和bundle同步覆盖。

音频来源与再分发依据见 show/RIGHTS.md，字节校验见show/SHA256SUMS。此处无声/离线测试不是实际四路声卡、调音台、声学校准或长稳验收；现场应另做低电平逐路与物理急停验收。
