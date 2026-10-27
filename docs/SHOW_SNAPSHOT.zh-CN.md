# 已编排演出的跨电脑恢复与配色

本分支保存的是操作者在 2026-10-27 本机已保存的演出，项目保存时间为 `2026-10-27T08:16:07.289657+00:00`：**30 条 cue、36 个音频层、20 个音频文件**。它不是旧版 20 条一文件一 cue 的模板。`show/project-template.json` 保留 cue/层/媒体 IDs、手动顺序、XY 路径、角度关键帧与 ADSR、已存空间预设、音量、延迟、淡入淡出、调度和舞台音箱配置。`show/programming-snapshot.json` 保存音频 SHA-256 和字节数；音频未转码。

## 新电脑第一次安装

下载本分支完整源码，保留 `show/` 文件夹；本变更尚未合并 main，命令为：

```bash
git clone --branch feat/show-themes-programming https://github.com/ShawnZ1438/SpatialStage.git
```

Mac 安装 Python 3.11–3.13（建议 3.12），按 [完整部署说明](DEPLOY.zh-CN.md) 安装音频依赖。双击 `Install SpatialStage.command`，再选：

- `Start SpatialStage.command`：正式项目数据，位于用户目录 `.spatialstage/projects`。
- `Start Simulation (Mac).command`：隔离模拟项目，位于 checkout 的 `SpatialStage-test-data`。

打开 `http://127.0.0.1:8765`。第一次启动会复制 20 个媒体并恢复完整 30 cue 编排；确认项目为 “Show audio (repository)”。运行预检，核对 30 cue / 36 层。首次恢复生成新项目 ID，清空输入设备偏好并停用本机 AutoCal；声音安全状态不随模板恢复。模拟与正式环境各自保存修改；不要同时启动两个入口争用端口。

**已有项目不会被此模板覆盖。** 如果当前电脑已有 repository show，更新源码不会把它替换成这份快照。需要单独查看发布快照时，用一个全新数据目录启动，例如在仓库终端运行 `STAGE_SPATIAL_DATA="$PWD/Restored-show" ./run_mac.command --no-open`，先安全停止已有实例。不要删除原项目来强迫导入。

## 使用和安全切换

顶部「配色」提供深海、石墨、暖灰、浅色；选择仅保存在当前浏览器，编排/演出共用。PANIC、静音、警告、NEXT/LIVE 的语义不变。音频层表格窄屏时可横向滚动或聚焦后使用方向键，删除按钮与延迟/静音控件保留独立列；底部 XRUNS / PEAK OVER 在独立行，不再覆盖层表格。

切换模式或关闭网站前等待「已保存到本机」。停止 cue、录制与测量，打开 MAIN MUTE，然后双击 `Stop SpatialStage.command`。它核查应用身份和活动状态，仅正常终止匹配进程；拒绝时按提示处理，不按端口批量杀进程。再启动另一入口。网页关闭不等于引擎停止。

再次备份：编排界面「导出项目 ZIP」可保存当前项目和媒体；目前没有 ZIP 导入按钮。完整恢复应在服务停止后恢复项目数据目录备份，或由维护者将已保存项目转换为发布模板。不要把含本机隐私的备份提交 GitHub。

本次恢复验证逐字段比较全部编排，而非只比较数量；真实四路路由、现场声压和长时间稳定性仍须现场验收。音频分发依据与原始名称见 [RIGHTS](../show/RIGHTS.md) 和 manifest，不将音频套用代码 MIT 许可。
