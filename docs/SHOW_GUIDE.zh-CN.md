# SpatialStage 使用、测试与演出部署手册（Mac）

适用版本：`feat/performance-mode` 分支（合并进 `main` 之后同样适用）。
现场配置：Apple Silicon Mac + Midas M32R（USB）+ 4 只 IBO PS15，约 6 m × 6 m 场地，音箱放四角。

这份手册按顺序走一遍，分三个阶段：

| 阶段 | 在哪里做 | 需要的设备 | 对应章节 |
|---|---|---|---|
| A. 安装 | 演出用的 Mac | 网络 | 第 1–2 节 |
| B. 不接调音台的排练 / 调 Cue | Mac（或 Windows 电脑） | 耳机 | 第 3–5 节 |
| C. 现场部署与演出 | 场地 | M32R、4 只音箱、（可选）测量话筒 | 第 6–7 节 |

开发者的自动化测试在第 8 节，故障排查在第 9 节。

> **安全原则**：软件里的 MAIN MUTE 和 PANIC 只能停掉软件输出，收不回调音台、功放里已经缓冲的声音。现场必须保留一个**物理静音手段**（调音台 Mute Group 或功放电源），并且有专人负责。所有测试都从低音量开始。

---

## 1. 准备清单

**硬件**
- Apple Silicon Mac（M1 或更新），插电源使用
- USB-C 转 USB-B 线，用来连 Mac 和 M32R（USB 2.0，长度不超过 5 m）
- M32R（背面 XLR 输出 1–4 接 4 只音箱）
- 4 只 IBO PS15。**先确认是有源还是无源**：网上查到的 iBO PS15 是 15 寸无源箱（500 W），无源箱需要 4 路功放：M32R XLR 1–4 → 功放 → 音箱
- 耳机（排练时用虚拟四音箱监听）
- 可选：XLR 测量话筒（用于 AutoCal），话筒支架
- 卷尺、地胶（标记舞台中心和正前方）

**软件**（第 2 节逐步安装）
- Homebrew、Python 3.12、git、FFmpeg

**演出素材**
- 仓库里的 `show/audio/` 已经带了 15 个音频（立体声 FLAC），启动时自动导入，不需要另外拷贝。

---

## 2. 在 Mac 上安装（只做一次）

### 2.1 安装 Homebrew 和依赖

打开「终端」（启动台 → 其他 → 终端），逐行执行。

如果还没装 Homebrew（已经装过的跳过这一步）：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装完成后，按屏幕最后的提示执行那两行 `eval ...`，让 `brew` 命令生效。然后安装依赖：

```bash
brew install python@3.12 git ffmpeg portaudio libsndfile
```

- `python@3.12` 是必须的（支持 3.11–3.13）。
- `ffmpeg` 只在播放 MP3/M4A/AAC 时需要；WAV/FLAC/AIFF/OGG 不需要。
- `portaudio`、`libsndfile` 一般已经随 Python 包自带，装上也无妨。

### 2.2 获取代码和演出音频

建议放在用户目录下，路径里不要有中文或空格：

```bash
cd ~
git clone https://github.com/ShawnZ1438/SpatialStage.git
cd SpatialStage
```

**如果这个分支还没合并进 main**，请改用下面这条命令，直接拉 `feat/performance-mode` 分支：

```bash
git clone -b feat/performance-mode https://github.com/ShawnZ1438/SpatialStage.git
```

克隆完成后，`show/audio/` 里应该有 15 个 `.flac` 文件，约 169 MB。可以这样检查：

```bash
ls show/audio | wc -l
```

### 2.3 首次启动

**方法一（推荐）：** 在访达里打开 `SpatialStage` 文件夹，双击 **`Start SpatialStage.command`**。

**方法二：** 在终端里运行：

```bash
./run_mac.command
```

首次启动会发生这些事：
1. 自动创建 `.venv` 并安装依赖，需要联网，大约 1–3 分钟。之后再启动不需要联网。
2. 把 `show/audio/` 导入成项目 **Show audio (repository)**（15 个 Cue），音箱布局取自 `show/stage.json`（6 m × 6 m 四角）。终端会显示 `Repository show: Show audio (repository) (15 cues)`。
3. 浏览器自动打开 `http://127.0.0.1:8765/?mode=perform`（演出模式）。

**看到这些就说明启动成功：**
- 终端显示 `SpatialStage running at http://127.0.0.1:8765`，窗口保持打开。
- 浏览器左上角项目名是 *Show audio (repository)*，右侧列表有 15 个 Cue。
- 顶部状态显示 *Engine offline*。这是正常的，因为还没连接音频设备。

**常见的首次启动问题：**
- 双击后提示「无法打开，因为来自身份不明的开发者」：在文件上**右键 → 打开 → 打开**，只需做一次。用 `git clone` 拿到的代码一般不会出现这个提示。
- 终端提示 `permission denied`：执行 `chmod +x run_mac.command "Start SpatialStage.command"`。
- 提示 `Install supported Python first`：回到 2.1 安装 `python@3.12`。

> 启动器运行期间会用 `caffeinate` 阻止 Mac 睡眠。**演出期间不要关闭这个终端窗口**，关掉就会停止音频引擎。浏览器窗口可以刷新、关闭再打开，声音不受影响。

### 2.4 macOS 系统设置（演出机必须做）

| 设置 | 位置 | 原因 |
|---|---|---|
| 系统输出设备**不要**选 M32R | 系统设置 → 声音 → 输出，选「Mac 扬声器」 | 否则通知声、提示音会从 USB 1–2，也就是前左、前右两只音箱放出来 |
| 提示音也走 Mac 扬声器 | 系统设置 → 声音 → 声音效果 → 播放声音效果的设备 | 同上 |
| M32R 采样率 48 kHz | 应用程序 → 实用工具 → 音频 MIDI 设置 → 选 M32R 的 USB 设备 → 格式 48000 Hz | 软件固定 48 kHz，不一致会连接失败 |
| 允许「终端」使用麦克风 | 系统设置 → 隐私与安全性 → 麦克风 → 打开「终端」 | AutoCal 需要录音；不授权时 macOS 会给静音，AutoCal 会报 *Very weak microphone signal* |
| 勿扰模式 | 控制中心 → 专注模式 → 勿扰 | 避免弹窗和通知 |
| 关闭自动更新 | 系统设置 → 通用 → 软件更新 → 自动更新 → 全部关 | 避免演出时重启 |
| 不自动睡眠 | 系统设置 → 电池 → 选项 → 接电源时防止自动睡眠 | 启动器已用 caffeinate，这是双保险 |

### 2.5 以后更新代码

先在浏览器里点 **⇩ Export show ZIP** 备份当前项目，然后：

```bash
cd ~/SpatialStage
git pull --ff-only
```

再双击启动文件即可。如果依赖有变化，会自动重新安装。`show/audio/` 里新增的音频会追加到项目里；你在软件里改过的 Cue 不会被覆盖。

---

## 3. 不接调音台的本地测试（耳机）

这一步可以在任何 Mac 上做，也可以在 Windows 电脑上做（双击 `Start Simulation (Windows).cmd`）。用的是**同一个音频引擎**：一样的调度、淡入淡出和声像计算，区别只在于输出到哪里。

### 3.1 连接静音模拟引擎（检查逻辑，不出声）

1. 展开页面上方的 **LOCAL SIMULATION** 面板（演出模式下默认收起）。
2. 点 **Connect silent simulation**。顶部状态变为 *Connected / muted*。
3. 点右上角 **✓ Preflight check**，应显示 `Preflight OK: 15 cues, … MiB decoded`。
4. 点左侧 **MAIN MUTE · ON**，切到 **OFF**（主静音解除）。
5. 按 **空格**（或 FADE GO）。左侧 CH1–4 电平表会动，地图上会出现黄色的实时声源点。

### 3.2 虚拟四音箱耳机监听（能听到方位）

1. 插上耳机。
2. 在 LOCAL SIMULATION 里，第一个下拉框选 **Virtual 4 speakers (headphones)**。
3. 点一次 **Connect headphone monitor**，这一次只是列出设备；在设备下拉框里选你的耳机，**不要选 M32R**；再点一次 **Connect headphone monitor**。
4. 状态显示 *VIRTUAL 4-SPEAKER HEADPHONES*，主静音仍然开着。
5. 把左侧 MASTER 推子先放在 −30 dB 左右，关掉 MAIN MUTE，按空格播放。
6. **Listener X / Y / Head bearing** 是"听者"站的位置和面朝方向。默认 (0, 0) 面朝前方，相当于演员站在中心。
   - 把 X、Y 改成 2、2，就能听到站在右前角附近的演员听到的效果：右前音箱会明显更响、更早。
   - 地图上蓝色的点就是听者。
7. CH1–CH4 下面的增益、Mute、Solo 只影响耳机监听，不影响真实输出和录音。用 Solo 可以逐个检查某一路。

> 这是近似模拟：有电平差、到达时间差和头部遮挡，但没有 HRTF，也没有房间反射，耳机上分辨前后比较弱。最终效果以现场音箱为准。

### 3.3 录 4 声道文件 / 离线渲染

- 在静音模拟或耳机监听模式下，点 **Start new capture**，操作一段，再点 **Stop capture** → **Download 4-channel WAV**。得到的是真实 CH1–4 输出（48 kHz 浮点，最长 60 秒），可以在 DAW 里逐轨检查。
- 不开浏览器也能离线渲染某个 Cue。项目 ID 是 `~/.spatialstage/projects/` 下的文件夹名：

```bash
ls ~/.spatialstage/projects
```

```bash
.venv/bin/python scripts/render_simulation.py --data ~/.spatialstage/projects --project 项目ID --index 0 --seconds 10 --output test-output/cue001.wav --headphones 0,0,0
```

`--index` 从 0 开始数。`--headphones X,Y,朝向` 会额外生成 `cue001-headphones.wav`，是在该位置用耳机听到的版本。

### 3.4 逐个 Cue 的测试清单

每个 Cue 都过一遍：
- [ ] 能播放，开头没有咔哒声，淡入淡出时长合适
- [ ] 方向对：0° 在前，90° 在右，180° 在后，270° 在左（看 CH1–4 电平表，或用耳机听）
- [ ] 路径 Cue 的移动速度、经过的位置正确（可以用演出模式的 *Preview path time* 滑块预览）
- [ ] 立体声 Cue 的宽度合适（见 4.3）
- [ ] 开始方式（REPLACE / LAYER / WAIT）和自动接续符合预期
- [ ] 电平合理：PEAK OVER 计数不增加，XRUNS 保持 0

---

## 4. 编排 Cue（编辑模式）

点右上角 **✎ Edit mode** 进入编辑模式；点 **▶ Performance mode** 回到演出模式。

### 4.1 项目与素材

- **项目**：左上角下拉框切换，**＋** 新建，**✎ Rename show** 改名。启动时打开最近修改过的项目。
- **导入**：**＋ Import folder** 导入整个文件夹，**Files** 导入单个文件。文件名以数字开头（如 `001_Rain.wav`）的会按编号排序；新导入的 Cue 追加在列表末尾，不会打乱已经排好的顺序。
- **调序**：用每行右边的 ↑ / ↓。
- **自动保存**：右上角显示 *Saved locally* 就是已保存。如果出现 *Save failed — changes retained*，点 **Retry save**。
- **只开一个编辑窗口**：同一个项目不要在两个浏览器标签里同时编辑。

### 4.2 Inspector（右侧面板）各项含义

| 项目 | 含义 |
|---|---|
| Bearing (°) | 角度模式下的方向：0 前，90 右，180 后，270 左 |
| Cue gain (dB) | 这个 Cue 的电平 |
| Stereo / Stereo width | 立体声处理方式，见 4.3 |
| Start action | **Replace** 替换正在播放的声音（按 Transition 交叉淡化）；**Layer** 叠加播放；**Wait** 等正在播放的声音结束再开始 |
| Auto-next | **Manual GO** 每次手动按；**From this cue start** 从本 Cue 开始算起，等 Post-wait 后自动播下一个；**After this cue ends** 本 Cue 结束后等 Post-wait 再播下一个 |
| Fade in / Fade out | 文件本身的淡入淡出 |
| Replace transition / Transition | Replace 时用交叉淡化（秒数）还是 5 ms 去咔哒直切 |
| Pre-wait / Post-wait | 播放前等待 / 自动接续前等待 |
| Modulation curve | 运动方式：自由关键帧（角度随时间变）、ADSR 角度包络、**Stage-map position / XY path**（在平面图上定位，见第 5 节） |
| ⇆ Replace this Cue's audio file | 换音频文件，下次播放时生效 |

修改会在约 0.3 秒后自动保存；正在播放的 Cue 的方向、电平也会随之实时更新。

### 4.3 立体声素材（双声道不合成单声道）

立体声文件导入后，默认是 **Keep stereo · L/R width = 90°**：文件的左、右声道作为两个声源，放在 Cue 位置两侧各一半宽度的地方。

| 宽度 | 效果 | 适合 |
|---|---|---|
| 0° | 左右重合（类似单声道，但没有相位抵消） | 很窄的声源 |
| 90°（默认） | 左右落在 Cue 前方那一对音箱上（Cue 在 0° 时 = 前左 / 前右） | 一般效果、车、人群 |
| 180° | 左声道铺满左半边，右声道铺满右半边 | 环境声、房间底噪铺底 |
| Mono downmix | 合成单声道，从一个点发声 | 门铃、脚步等点状效果 |

在平面图（路径）模式下，L/R 会随路径一起绕中心转，靠近中心时自然合并到四只音箱。演出模式的地图上紫色 L / R 点表示两个声道的位置。

### 4.4 全局控制（左侧 SPATIAL MASTER）

- **Global rotation**：把所有声音整体旋转一个角度，实时生效。
- **Show-wide direction envelope**：整场演出的方向随时间变化，从第一次 GO 开始计时。
- **Approximate distance compensation**：四只音箱离中心距离不同时的近似补偿。四角对称摆放时**不要开**。

---

## 5. 演出模式：拖动位置、画路径、Store / Recall / Reset

点 **▶ Performance mode**。左边是以演员为中心、单位为米的舞台平面图，右边是目标 Cue 面板和 Cue 列表。

**目标 Cue**
- 默认编辑 **NEXT**（下一个要播放的 Cue），每次 GO 后自动跟到新的 NEXT。
- 点右侧列表里的其他 Cue，可以提前准备；点 **↺ Follow NEXT** 恢复跟随。

**定位 / 画路径**
1. 在地图上点击或拖动，就是设置 Cue 的位置。角度模式的 Cue 第一次被拖动时会自动转成平面位置，起点就是原来的方向，所以没动之前声音不变。
2. 点 **＋ Add path point**（或按住 Shift 点击）追加路径点。新点的时间自动往后排，可以在表格里改 *Time s / X m / Y m*。
3. 拖动点可以改位置；**×** 删除点；点表格某一行可以选中那个点。
4. **Preview path time** 滑块：预览任意时刻声源的位置，以及四个通道的增益。

**声音规则**
- 在**虚线（音箱连线）上**或更外侧：只用相邻两只音箱。
- 越靠近**中心**，越均匀地分到四只音箱。
- 所以穿过中心的路径不会在对角音箱之间突然跳。总响度保持不变，不做"越远越小声"。

**Store / Recall / Reset**
- **Store**：把当前位置和路径存为这个 Cue 的预设，随项目一起保存。
- **Recall**：恢复到存储的预设。
- **Reset**：回到正前方 0° 的一个静止点（可以再 Recall 回来）。
- 列表标记：**✓** 与存储一致，**●** 存储后被改过，**—** 未存储。
- **Store all / Recall all**：对全部 Cue 操作，会弹出确认。

**锁定**
- 全部调好后，勾选 **Lock map and presets for the show**：地图和编辑都会锁住，GO / STOP / PANIC / Recall 仍然可用。锁定状态记在这个浏览器里，刷新也保留。

**建议流程**：每个 Cue 调好就点 Store → 全部 ✓ 后勾选 Lock。正式演出前，先取消 Lock，点一次 **Recall all**，确认全部回到存储的状态，再勾选 Lock（锁定时 Store all / Recall all 不可用）。

---

## 6. 现场部署（M32R + 4 只 PS15）

### 6.1 布置与几何

1. 用地胶在地面标出**舞台中心 (0, 0)** 和**正前方（12 点钟）**方向。
2. 4 只音箱放在四角并朝向中心：前左 (−3, 3)、前右 (3, 3)、后右 (3, −3)、后左 (−3, −3)，单位米，离中心约 4.24 m。
   - 高音单元大约在演员耳朵高度，可以略微向下倾。
   - 30 kg 的箱子要用承重足够的支架，并加沙袋。
3. **演员活动范围建议半径 1.5–2 m 以内。** 6 × 6 m 的场地放不下半径 3–4 m 的圆：半径 3 m 已经贴墙，离角落音箱只有约 1.2 m。演员越靠近某只音箱，声音越会被"拉"向那只音箱：在半径 2 m 处，最近和最远的音箱已经相差约 9 dB、12 ms。可以用 3.2 节的耳机监听，把听者放到演员会站的位置去试听。
4. 实际量出音箱位置后，在软件里点 **⚙ Stage setup**，填入实测的 X/Y（单位米，+X 向右，+Y 向前）和输出通道，点 **Save geometry**。对话框下方的图会实时显示布局。修改时必须先打开 MAIN MUTE。

### 6.2 信号链

```text
Mac ──USB──▶ M32R USB 声卡（Card 1–4）
          ──▶ M32R 通道 25–28 ──▶ Mix Bus 1–4（限幅 / EQ）
          ──▶ XLR Out 1–4 ──▶（功放，如果是无源箱）──▶ 4 只 PS15

通道/音箱对应：CH1 前左 L · CH2 前右 R · CH3 后右 RR · CH4 后左 RL
```

四路必须**各自独立**到达对应音箱，**不能**在调音台上混进同一个立体声 Main LR。

### 6.3 M32R 设置步骤

以下菜单名称以调音台实际界面为准，可以用 M32-Edit 软件操作。

1. **采样率**：Setup → Config → Sample Rate 选 **48 kHz**。
2. **USB 声卡**：Setup → Card，选 USB，通道数 32×32（或至少 8 进 8 出）。连上 Mac 后，「音频 MIDI 设置」里应该能看到这个设备，输出 ≥ 4 路。
3. **Mac 的 4 路进调音台**：Routing → Inputs，把 *Inp 25–32* 的来源设为 **Card 1–8**。这样不占用本地 16 路话放。
4. **通道 25–28**（对应软件 CH1–4）：
   - 关掉发往 Main LR 的 LR 发送；推子推到 0 dB。
   - Sends：通道 25 → Bus 1、26 → Bus 2、27 → Bus 3、28 → Bus 4，发送 0 dB、post，其余 Bus 不发。
   - Bus 1–4 **不要** link 成立体声对。
5. **母线到输出**：Routing → Outputs，XLR Out 1–4 的来源设为 **MixBus 1–4**（post）。
6. **保护和音色**：
   - Bus 1–4 打开压缩/限幅，作为声压保护。软件里的削波保护不能代替声学限幅。
   - 角落摆放低频会偏重，用 Bus EQ 适当衰减低频，四条做一样的设置。
   - 如需对齐时间，可以用输出延时（Routing → Output → Delay）。
7. **物理急停**：建一个 **Mute Group**，包含 Bus 1–4，指定专人负责。
8. **AutoCal 用的测量话筒（可选）**：话筒接本地 Input 1，需要时打开 48 V 幻象电源；Routing → Card Out 1 设为 Local 1，把话筒信号送回 Mac。

### 6.4 在软件里连接调音台

1. 用 USB 线连接 Mac 和 M32R，双击启动文件。
2. 左侧 **AUDIO DEVICES**：点 **↻** 刷新，在下拉框里选 M32R 的 USB 设备（应显示 32 out；少于 4 路的设备是灰的），点 **Connect audio**。
3. 顶部状态显示 *Connected / muted*，MAIN MUTE 仍然是开的，这是安全设计。
4. **逐路检查接线**：
   - 先把调音台 Bus 推子和功放都调低，把软件 MASTER 推子放在 −40 dB 左右，关掉 MAIN MUTE。
   - 点 **Test CH**，输入 `1`，会从 CH1 发出 1 秒 440 Hz 的提示音。
   - 确认是**前左**音箱在响；依次测 2（前右）、3（后右）、4（后左）。
   - 对不上的话，改调音台路由，或者在 Stage setup 里改输出通道。
5. 测完把 MAIN MUTE 打开。

### 6.5 电平校准

1. **调音台电平匹配（推荐）**：演员离场，用声级计在舞台中心逐路测 Test CH 或粉红噪声，用 Bus 推子把四只调到一样响。
2. **AutoCal（可选，需要 XLR 测量话筒）**：
   1. 话筒放在舞台中心、演员耳朵高度。
   2. 软件里先 **Disconnect**（点 Connect audio 按钮断开），保持 MAIN MUTE 打开；Stage setup 里四个 Trim 必须是 0，距离补偿必须关。
   3. 点 **◉ AutoCal · XLR measurement**：
      - 选择话筒所在的输入设备（M32R USB），*Microphone input channel* 填话筒对应的 Card Out 通道（例如 1）。
      - 选择 4 路输出设备（M32R），测试电平先用默认 −30 dBFS。
      - 点 **Save AutoCal setup**。
   4. 勾选确认框（舞台无人、话筒已接、输出已断开、功放音量低），点 **◉ Measure CH1–CH4**，四路依次扫频。
   5. 查看结果（电平、到达时间、频响）。全部通过后，勾选确认框并输入 **APPLY**，点 **Apply approved profile**。之后只会做衰减和小延时，不做 EQ。
   6. 调音台的增益、路由或音箱位置改过之后，必须重新测量。
3. 最后设定演出音量：MASTER 推子加调音台 Bus 推子，由现场音响负责人确认安全电平。

### 6.6 现场硬件验收清单（演员上台前）

- [ ] CH1–4 分别只从对应音箱发声，没有串到 Main LR 或其他音箱
- [ ] 连按几次 GO / STOP 都正常；STOP 是 40 ms 淡出
- [ ] 播放中按 MAIN MUTE 能静音，再解除能恢复
- [ ] **PANIC**（Shift+Esc）能立即静音
- [ ] 拔掉 USB 线：软件锁定静音并报错 → 插回 → 重新 **Connect audio**，确认不会自动重播 → 手动解除 MAIN MUTE
- [ ] 同时播放演出中最多的几层声音，XRUNS 保持 0，PEAK OVER 不增加
- [ ] 演员站到活动范围的边缘听一遍关键 Cue
- [ ] 调音台 Mute Group（物理急停）有效，负责人明确
- [ ] 完整连排一遍

---

## 7. 演出当天

### 7.1 开场前（建议提前 30 分钟）

1. 开机顺序：调音台 → Mac → 功放/有源音箱最后开（音量先拧到最小）。
2. 双击 **Start SpatialStage.command**，确认终端窗口开着。
3. 点 **Connect audio** 选 M32R（MAIN MUTE 保持开）。
4. 点 **✓ Preflight check**，必须显示 OK。
5. 演出模式：点 **Recall all**，确认列表全部 ✓，勾选 **Lock**。
6. 在列表里选第一个 Cue → 编辑模式点 **ARM SELECTED**（或者直接看 NEXT 是否就是第一个）。
7. 低音量试播一个 Cue，然后 STOP。
8. 调好 MASTER，关掉 MAIN MUTE，等候开场。
9. 关掉其他应用，打开勿扰模式。

### 7.2 运行中的操作

| 操作 | 按键 | 作用 |
|---|---|---|
| FADE GO | **空格** | 播放 NEXT（以及自动接续的 Cue），遵守开始方式、Pre-wait 和交叉淡化 |
| CUT GO | **C** | 立刻播放 NEXT，忽略等待和交叉淡化（5 ms 去咔哒），只播这一个 |
| STOP | **S** | 40 ms 淡出停止所有声音，并取消等待中的 Cue |
| SKIP | **Alt + ↓** | 只把 NEXT 往后挪一个，不影响正在播放的声音 |
| PANIC | **Shift + Esc** | 立刻清空所有声音并打开 MAIN MUTE（在输入框里也有效） |
| MAIN MUTE | 点按钮 | 15 ms 渐变静音；**时钟继续走，不是暂停** |

注意：
- 光标在输入框里时，空格、C、S 不会触发，先点一下页面空白处。
- 如果 NEXT 显示 *Preparing NEXT audio…*，等它变成可播放再按 GO。音频还没准备好时，GO 会被拒绝，不会延迟乱播。
- 想重播某个 Cue：切到编辑模式，在列表里选中它，点 **ARM SELECTED**。
- 列表里的 *BEFORE* 只表示排在 NEXT 前面，不代表已经播放过。

### 7.3 紧急情况

| 情况 | 处理 |
|---|---|
| 声音不对，需要立刻停 | 先按 **Shift+Esc（PANIC）**，同时调音台按 **Mute Group** |
| USB 掉线 / 显示 *Output stream stopped or device lost* | 软件已自动静音。重新插线 → **Connect audio** → 确认 NEXT → 解除 MAIN MUTE → 从需要的 Cue 继续 |
| 浏览器卡住或误关 | 重新打开 `http://127.0.0.1:8765`，声音不受影响 |
| 终端窗口被关掉 | 引擎已停止。双击启动文件 → Connect audio → 编辑模式 ARM 需要的 Cue → 解除静音 |
| 播错 Cue | 按 STOP；切到编辑模式，选正确的 Cue，点 ARM SELECTED |

### 7.4 散场

1. STOP → 打开 MAIN MUTE → **Connect audio** 按钮断开。
2. 关机顺序：先关功放/音箱 → 再关调音台 → 最后关 Mac。
3. 备份：点 **⇩ Export show ZIP**，同时复制整个 `~/.spatialstage/projects/` 文件夹。ZIP 目前只能导出，不能导回。
4. 终端里按 `Ctrl + C`（或直接关掉窗口）停止引擎。

---

## 8. 开发者测试（改了代码之后）

在仓库目录里执行：

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check stagespatialcue tests scripts
```

JS 测试需要 Node（`brew install node`）：

```bash
node --test tests/js/*.test.cjs
```

浏览器回归测试（会启动一个临时服务器，**需要先关掉正在运行的 SpatialStage**，因为 8765 端口必须空闲）：

```bash
python -m playwright install chromium
python scripts/browser_smoke.py --spawn
python scripts/browser_audit_regressions.py
```

这些测试使用合成信号和模拟设备，不能代替第 6.6 节的现场硬件验收。

---

## 9. 故障排查

| 现象 | 原因与解决 |
|---|---|
| 设备列表里没有 M32R，或者是灰色 | USB 没连好、调音台 Card 没设成 USB，或者通道数少于 4 → 检查 6.3 第 2 步，点 ↻ 刷新 |
| 连接时报采样率错误 | 调音台或「音频 MIDI 设置」不是 48 kHz |
| 按 GO 没反应，提示 *MAIN MUTE is on* | 先关掉 MAIN MUTE |
| 提示 *End of cue list* | 已经播完：编辑模式选 Cue 后点 ARM SELECTED |
| 提示 *NEXT cue was removed* | NEXT 被删除了：编辑模式选一个 Cue 后点 ARM SELECTED |
| 电平表在动，但音箱没声音 | 调音台路由、Bus 推子、Mute Group、功放电源，按信号链逐级检查 |
| 只有前面两只响 | 调音台把四路混进了 Main LR，或者 Bus 被 link 成立体声 → 按 6.3 重新设置 |
| 声音来自错误的方向 | 接线或通道顺序不对 → 用 Test CH 逐路检查，改路由或 Stage setup 的输出通道 |
| XRUNS 数字一直增加，有爆音 | 关掉其他应用；接上电源；减少同时播放的层数 |
| *Save failed — changes retained* | 点 Retry save。如果是 Stage setup 保存失败，检查四路通道是否重复、音箱是否把中心包围住 |
| AutoCal 提示 *Very weak microphone signal* | 「终端」的麦克风权限没开（2.4）、话筒通道选错、幻象电源没开、话放增益太低 |
| 双击启动文件提示「身份不明的开发者」 | 右键 → 打开（只需一次） |
| 启动后浏览器打开的不是新版本 | 旧引擎还占着 8765 端口：关掉旧的终端窗口；Windows 上新启动器会提示是否停掉旧引擎 |
| 15 个 Cue 没有出现 | `show/audio/` 是空的（clone 不完整），或者没用启动文件/`spatialstage` 命令启动 → 检查 2.2 |

---

## 10. 已知限制

- 排练原型：Python 音频回调没有硬实时保证，正式演出前一定要做长时间连排。
- 没有真正的暂停/继续，MAIN MUTE 不是暂停。
- 声像以舞台中心为参考，不跟踪演员；离中心越远，方向感越偏向最近的音箱。
- 耳机虚拟监听是近似模拟，最终以现场音箱为准。
- 同一时间只用一个浏览器窗口编辑。
- ZIP 只能导出备份，不能导入恢复。
