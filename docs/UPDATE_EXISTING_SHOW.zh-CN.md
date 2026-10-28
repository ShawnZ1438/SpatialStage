# 现场已有编排：更新程序，单独更新音箱

此变更在 `feat/show-themes-programming` 分支；待维护者确认已推送的 SHA 后再更新。不要拉 main 期待获得此修复。

## 本次操作变化

- 点击 cue 只选中，不改 NEXT，不再把列表滚动到顶部。层参数变化需要重绘时也保留列表滚动。
- 明确选中某条后，FADE GO / 空格从该条开始，遵守原 start mode、pre-wait、fade、auto-continue / auto-follow 和 post-wait。成功后消耗这次选中意图；再次 FADE GO 接着 NEXT，想重播同条就再次选中。自动链可能一次排入多条，因此 NEXT 是自动组后第一条，不一定只显示 k+1。
- 显式跳转取消旧主播放链尚未开始的 cue；已经响起的声音仍按新 cue 原有替换/叠加规则处理。单条 ▶ 叠加播放不移动 NEXT、不重定向主顺序；CUT GO 仍使用 NEXT。选择 cue 后的待启动目标显示在播放提示里。
- 静音和未连接仍禁止 GO。选中 GO 会先保存并在请求线程准备音频，成功后才调度；STOP/PANIC 可取消尚在等待保存/准备的 GO。准备未完成时重复点击不会叠加请求。

## 更新前保全（在现场 Mac 操作，不是远程代操作）

1. 网页等待「已保存到本机」，记录当前项目名称及页面「演出数据」目录。导出项目 ZIP 作独立备份；ZIP 暂无一键导入，另备份完整数据目录才便于原位恢复。
2. 结束播放、录制和测量，MAIN MUTE 打开。双击原目录 `Stop SpatialStage.command`；如果身份或活动检查拒绝，按提示处理，不强杀。关闭旧网页，避免其旧内存再次保存。
3. 复制整个演出数据目录到带日期的独立备份。正式目录默认 `~/.spatialstage/projects`；模拟目录在原 checkout 的 `SpatialStage-test-data`，自定义目录以页面显示为准。

## 更新程序（推荐新目录，保留现场的脏 checkout / Start 补丁）

在终端进入想保存程序的父目录，选择一个尚不存在的新目录名：

```sh
git clone --branch feat/show-themes-programming https://github.com/ShawnZ1438/SpatialStage.git SpatialStage-update
cd SpatialStage-update
git rev-parse HEAD
./run_mac.command --install-only
```

核对 HEAD 等于维护者给的发布 SHA。安装要求仍为 Python 3.11–3.13 及音频依赖，见 [部署手册](DEPLOY.zh-CN.md)。新 checkout 使用新 `.venv`，不要复制旧 `.venv`。启动脚本现已明确把本 checkout 放到 PYTHONPATH 前面，不需要把旧 Start 脚本整体覆盖回来。旧目录及其中所有本地补丁保留。

如果希望原位更新，先 `git status --short`、`git branch --show-current`、`git remote -v`。仅在工作区完全干净且已位于上述分支时使用 `git pull --ff-only origin feat/show-themes-programming`；出现分歧就停。存在本地修改（包括 Start 补丁）时走上面的新目录方案，不使用 reset/clean 或盲目 stash/pop。

正式环境默认继续读同一用户的 `~/.spatialstage/projects`，不会被 repo 模板覆盖。若现场实际使用模拟或自定义数据目录，必须显式复用其原绝对路径：

```sh
STAGE_SPATIAL_DATA='/现场记录的原演出数据目录' ./run_mac.command --no-open
```

不要误点新目录的 Simulation 入口把新建模拟项目当成原演出。更新后核对项目名、cue 数量/顺序/层和抽查路径，再运行媒体预检。浏览器完整刷新，初始保持静音，设备索引需在该 Mac 上重新核对；不要假定另一台 Mac 的输出设备映射相同。

## 音箱专项迁移（已有项目不会自动接收模板几何）

已确认 CH1 左前、CH2 右前、CH3 右后、CH4 左后；1–2/3–4＝8.65 m，2–3/1–4＝6.47 m。发布模板中心为 (0,0)，坐标依次为 (-4.325,+3.235)、(+4.325,+3.235)、(+4.325,-3.235)、(-4.325,-3.235)。+Y 沿当前前方约定。

服务停止、网页关闭且完整备份后，在新程序目录运行，替换为**实际当前项目**的 JSON 路径（不是 repo 模板）：

```sh
.venv/bin/python -m stagespatialcue.speaker_rectangle '/实际演出数据目录/项目ID/project.json'
# 核对预览的通道、名称和几何后执行：
.venv/bin/python -m stagespatialcue.speaker_rectangle '/实际演出数据目录/项目ID/project.json' --apply
```

工具只修改 speakers，保留原中心、朝向、通道与名称、trim；不缩放 cue、路径或关键帧，不替换整个 show。现有几何不构成按1–2–3–4排列的矩形会拒绝；端口8765仍有服务也会拒绝。应用前生成 `project.json.before-speaker-rectangle-时间戳` 原字节备份。非默认端口的服务也须人工先停止，工具仅自动检查8765。

重新启动后检查舞台与音箱通道。原 AutoCal 数据不适用于改动后的现场布局：先在 Edit 停用旧校准，重新完成现场测量再使用。真四路输出/声压/长稳验收不能由无声模拟代替。

回滚：保存并停止服务、关闭网页后，用专项备份替换对应 `project.json`；程序使用原 checkout 启动。若要恢复更新前整场编排，恢复完整数据目录备份，不用 Git 覆盖用户数据。
