# UI 设计文档（Tauri 2 重写版）

> 本文是「AI 对话记录器」PySide6 → Tauri 2（无框架 TypeScript + CSS）整体重写的 **UI/UX 完整规格**。所有颜色、尺寸、动画时长均为从旧源码逐项提取的精确值，来源以括注标明（`ui/style.py`、`ui/sidebar.py`、`ui/widgets.py`、`ui/tree.py`、`ui/todo.py`、`ui/stash.py`、`ui/ops.py`、`float_bar.py`、`render_css.py`、`render.py`、`render_doc.py`、`render_mindmap_js.py`、`main_window.py`）。
>
> 术语映射：旧版 Qt Widget → 新版 DOM 元素。Qt 特有 hack（Fusion 样式强制、`::branch` 置空、`WM_NCHITTEST` 点击穿透、`QGraphicsDropShadowEffect`）一律不移植，Web 端分别用 CSS 默认行为、HTML 原生结构、`pointer-events` 与 `box-shadow` 替代，正文相应处已注明。

---

## 目录

1. [窗口总布局](#1-窗口总布局)
2. [液态玻璃设计体系](#2-液态玻璃设计体系)
3. [各区域详设](#3-各区域详设)
4. [四视图排版（气泡流 / 思维导图 / 文档 / 回收站·搜索）](#4-四视图排版)
5. [交互细节表](#5-交互细节表)

---

## 1. 窗口总布局

### 1.1 窗口

| 属性 | 值 | 来源 |
|---|---|---|
| 标题 | `AI 对话记录器` | main_window.py:44 |
| 默认尺寸 | **1600 × 740** | main_window.py:45 `resize(1600, 740)` |
| 关闭行为 | 隐藏到托盘（不退出），首次隐藏时托盘气泡提示 | ui/view.py:585-588, main.py:391-400 |
| 窗口背景 | `linear-gradient(135deg, #d3ddff 0%, #e6ecfb 35%, #e0f1f5 70%, #f1e5f6 100%)`（左上→右下对角） | style.py:38-41 |

### 1.2 整体结构（对应旧 QMainWindow 的 widget 树）

```
QMainWindow（主窗口）
├─ QToolBar #mainToolBar                      → 顶部工具栏（§3.1）
├─ SideOverlay（独立透明浮层窗）               → 左侧悬停展开边栏（§3.2，Web 改为绝对定位 div）
├─ centralWidget: QSplitter #stashSplit（垂直，handleWidth=8，不可折叠）
│  ├─ main（水平布局，间距 0）
│  │  ├─ #bodyHost（WebEngineView 容器）       → 中间视图区（气泡流/导图/文档/回收站，§4）
│  │  ├─ #todoDivider（固定宽 8px 白色渐隐竖条）→ 待办栏与视图区分隔装饰条
│  │  └─ TodoPanel（固定宽 260px）             → 右侧待办栏（§3.4）
│  └─ StashPanel（最小高 148px）               → 底部常驻栏（§3.5，QSplitter 下部，默认高 168）
└─ QStatusBar + QLabel #status                 → 底部状态栏
```

依据：`ui/sidebar.py:_build_body`（279-381 行）：root splitter 垂直、`setHandleWidth(8)`、`setChildrenCollapsible(False)`、`setSizes([640, 168])`（即上部 640 / 下部 168 的默认比例，拉伸因子 1:0）；main 水平布局 `body_host(伸展) + todo_divider(固定 8) + todo_panel(固定 260)`。

### 1.3 各区默认/极值尺寸

| 区块 | 宽/高 | 来源 |
|---|---|---|
| 左侧边栏（展开时总宽） | 默认 430px；最小内容宽 `max(320, side_width)`；收起时只留 **26px** 细条（SIDE_RAIL_W） | sidebar.py:62,328,544-546 |
| 边栏内两列（课题列 / 文件夹列） | 内部水平 splitter，handleWidth 6，初始 `setSizes([168, 252])`；自动撑宽下限：课题列 ≥140、文件夹列 ≥200，按「最长一行标题完整显示」自动加大 | sidebar.py:279-285,448-463 |
| 右侧待办栏 | 固定 **260px**（TODO_PANEL_W） | todo.py:24 |
| 待办与视图间隔条 | 固定 8px | sidebar.py:342-346 |
| 底部常驻栏 | 最小高 148px，初始 168px，可拖垂直 splitter 调整 | stash.py:202, sidebar.py:370 |
| 工具栏 | `padding: 8px 12px`，按钮间距 6px | style.py:126-132 |

### 1.4 状态栏

- 背景 `linear-gradient(180deg, rgba(238,242,253,.7), rgba(255,255,255,.86))`，顶部 1px `#ffffff` 分隔线（style.py:329-333）。
- 文字 `#7a84a2`、12px（style.py:334）。
- 状态文本由各操作写入（如「会话「X」 · N 条记录 · 复制文字后点悬浮条即可记录，关闭窗口将最小化到托盘」view.py:62-65；「已复制到剪贴板」sidebar.py:469 等），Web 版保持一个单行状态区，同文案。

### 1.5 侧栏宽度持久化（settings.json 键）

| 键 | 含义 | 来源 |
|---|---|---|
| `sidebar_dragged` | 用户是否拖过边栏分隔条（只有拖动才算，程序化 setSizes 不写） | sidebar.py:40-42,418-441 |
| `subject_width` / `folder_width` | 两列宽度（≥110 / ≥120 才写） | sidebar.py:525-540 |
| `sidebar_width` | 边栏总宽 | 同上 |

---

## 2. 液态玻璃设计体系

全部以 **CSS 自定义属性** 落在 `:root`，组件只引用变量（对应旧版「主题只允许改 style.py」的约定）。

### 2.1 色板

#### 基础色

| 令牌 | 值 | 用途 |
|---|---|---|
| `--ink-900` | `#262c3d` | 正文（Web 页 body） |
| `--ink-800` | `#2c3345` | 树行标题/待办正文 |
| `--ink-700` | `#3a4152` | 普通按钮文字/表单文字 |
| `--ink-600` | `#3d4459` | 工具栏按钮文字 |
| `--ink-500` | `#454e68` / `#565f7c` | 导图连线标签文字/搜索头 |
| `--ink-400` | `#5d6684` / `#5a647c` | 次级按钮文字/常驻栏分类按钮 |
| `--ink-300` | `#656e88` | 备注/提示文字 |
| `--ink-250` | `#6b779a` / `#737d9c` / `#7a84a2` / `#7f88a6` | 折叠按钮/元信息/状态栏/气泡 meta |
| `--ink-200` | `#8b94ad` | 空态、提示、元信息（多处） |
| `--ink-150` | `#8a93ad` | Web 页空态/会话标签 |
| `--ink-100` | `#97a0bb` / `#9aa2b5` / `#a8b0c6` | 气泡操作链接/悬浮条×按钮 |
| `--primary` | `#4a63f0` | 主品牌蓝（选中、悬停、focus 边） |
| `--primary-ink` | `#2b3776` | 菜单选中项文字 |
| `--accent-green` | `#0f9d78` / `#0e9a76` | 回答角色色/回答按钮渐变底 |
| `--danger` | `#e5484d` | 危险操作（删除、彻底删除） |
| `--focus-ring` | `rgba(79,110,247,.42)` | 输入框 focus 外边框（style.py:324,429） |

#### 主按钮渐变（三段，垂直 180°）

```
默认:   #7d99ff 0% → #5f7cf9 50% → #4a63f0 100%
悬停:   #8ea6ff 0% → #6e89fb 50% → #5670f3 100%
按下:   #5670f3 0% → #4459de 100%（两段）
禁用:   rgba(170,182,216,.55) 平色
```
来源：style.py:79-100（glassNoteOk）、194-210（QPushButton:default）、433-451（todoAdd）；float_bar.py:119-133（btnQ 同款）。

回答按钮（悬浮条专用，绿色三段）：`#2ed3ab → #16b58a → #0e9a76`，悬停 `#3fddb6 → #1cc79b → #12a882`，按下 `#12a882 → #0c8a68`（float_bar.py:134-148）。

#### 悬浮条卡片（深色，独立体系）

```
背景:  linear-gradient(180deg, rgba(48,54,76,.96), rgba(28,32,48,.94))
边框:  1px rgba(255,255,255,.22)；顶边 rgba(255,255,255,.38)；底边 rgba(8,10,22,.55)
圆角:  16px
预览文字: #e2e7f5 12px "Microsoft YaHei","Segoe UI"
```
（float_bar.py:95-109）

#### 三档磨砂玻璃（核心做 glass 的公式）

| 档位 | 渐变（180°） | 典型用途 | 来源 |
|---|---|---|---|
| 一级面板 | `rgba(255,255,255,.92) 0% → rgba(247,249,255,.86) 45% → rgba(232,238,252,.84) 100%` | 玻璃对话框面板 | style.py:44-53 |
| 一级面板（侧栏/待办变体） | 白 .88/.9 → .76/.78 | sidePanel/todoGlass/todoGroup | style.py:228-235,393-400,452-459 |
| 二级内容块 | `rgba(255,255,255,.88) → rgba(244,247,255,.76)` | 输入槽、行卡片 | style.py:64-72,420-427,460-467 |
| 三级小元件 | 白 .8~.86 → .64~.72 | chip、标记、日期框 | style.py:161-170,503-511,526-533 |

Web 页内组件的磨砂统一为 `backdrop-filter: blur(22px) saturate(180%)`（render_css.py 中所有玻璃卡片），导图节点用 `blur(26px) saturate(180%)`，代码块用 `blur(20px) saturate(150%)`。

#### 凸起/凹陷三边框规则（贯穿全 QSS，Web 用 border-top/bottom-color 复刻）

- **凸起件**（面板/按钮/卡片）：`border` 白 .5~.95，`border-top: #ffffff`（纯白高光），`border-bottom: rgba(146,162,205,.30~.45)`（暗边）。
- **凹陷件**（输入框/列表槽）：反过来——`border-top: rgba(150,166,208,.34~.42)`（暗），`border-bottom: #ffffff`（亮）。
- 主色按钮底边单独加深：`rgba(48,66,168,.6)`。

### 2.2 五色匹配色 MATCH_COLORS（ui/widgets.py:109-140）

| key | 名称 | 色板 swatch | 行填充 fill（alpha） | 描边 border |
|---|---|---|---|---|
| `orange` | 亮橙色 | `#ff9a3d` | `rgba(255,154,61,.706)`（alpha 180） | `#ff8a2a` |
| `pink` | 淡粉色 | `#ffc2d4` | `rgba(255,194,212,.745)`（190） | `#f39ab3` |
| `blue` | 淡蓝色 | `#b4d4ff` | `rgba(180,212,255,.765)`（195） | `#7eb0f0` |
| `gray` | 灰色 | `#c5cad3` | `rgba(197,202,211,.784)`（200） | `#9aa1ad` |
| `purple` | 淡紫色 | `#d4c2f5` | `rgba(212,194,245,.765)`（195） | `#b89ae0` |

会话行被匹配色填充时：选中态在 fill alpha 上 **+36**（上限 255），描边宽 1.4px（widgets.py:534-540）。待办日期组的日期 chip 按 `date.toordinal() % 5` 轮转同五色的 tone（todo.py:25,48），五 tone 的完整渐变见 §3.4。

### 2.3 圆角体系

| 半径 | 用途 |
|---|---|
| **20px** | 玻璃对话框面板、chat-nav、glassNotePanel |
| **18px** | sidePanel、todoGlass、todoGroup、stashNav、待办列表面板 |
| **16px** | 导图节点（mm-node）、悬浮条卡片、importTableWrap、todoGroup、对话气泡（bubble） |
| **15px** | QLineEdit / todoInput（胶囊感输入框） |
| **14px** | glassNoteEdit、glassHelpBrowser、todoRow、matchColorPopup、importHint、代码块（pre.codeblock）、cv-card、trash-item、msg-img、doc-src/doc-preview-wrap |
| **12px** | 主/次按钮（glassNoteOk/Cancel、工具栏按钮、sideRailBtn）、气泡内 blockquote、QMenu 面板、树行气泡（delegate 12,12）、todoDate、cv-callout、树 chip（10,10 见下） |
| **11px** | QPushButton 通用、importTable 表头圆角 |
| **10px** | todoNote、todoNoteEdit、sessionNoteTip、树标签 chip（10,10）、导图连线标签 mm-edge-label、stashCopy |
| **9px** | trash-bar / trash-ops 链接按钮、matchColorBtn |
| **8px** | 树行内匹配/导入按钮（8,8）、气泡内 code 行内码、mm-node.text（文字节点） |
| **7px** | 气泡小角：user 气泡 `border-bottom-right-radius: 7px`，AI 气泡 `border-bottom-left-radius: 7px` |
| **999px** | 胶囊：glassNoteTitle、todoTitle、todoDoneHead、todoMark、autoBackupHint、page-head/search-head 徽章、chat-nav-num、cv-pill |

### 2.4 三档投影（旧 QGraphicsDropShadowEffect → CSS box-shadow）

来源 style.py:18-34 `apply_glass_shadow`。Qt 的 blurRadius≈2×CSS blur 半径的视觉等价，规格按下表直接落 `box-shadow`（blur 取 blurRadius，offset 同）：

| 档 | 参数（CSS 等价写法） | 用途 |
|---|---|---|
| **panel** | `0 8px 26px rgba(58,78,130,.306)`（Qt blur 26 / offset (0,8) / 色 rgba(58,78,130,78)） | 侧栏面板、待办玻璃、常驻栏导航 |
| **dialog** | `0 16px 46px rgba(58,78,130,.373)`（blur 46 / (0,16) / alpha 95） | 四个玻璃对话框面板 |
| **button** | `0 5px 18px rgba(63,88,200,.431)`（blur 18 / (0,5) / alpha 110） | 主按钮（保存/导入/关闭/+） |

Web 页内已有现成复合投影（render_css.py），四视图按 §4 原值保留，例如卡片标准投影：
```
box-shadow: 0 12px 30px rgba(58,78,130,.16),
            0 3px 8px rgba(58,78,130,.08),
            inset 0 1px 0 rgba(255,255,255,.92);
```

悬浮条投影专用（float_bar.py:55-58）：blur 40 / offset (0,12) / `rgba(15,20,45,.588)`（150）→ CSS `0 12px 40px rgba(15,20,45,.59)`，卡片外留白 20/14/20/28 给投影。

### 2.5 动画体系

| 动画 | 时长 | 缓动 | 来源 |
|---|---|---|---|
| 侧栏浮层展开/收起 | **240ms** | OutCubic | sidebar.py:63 SIDE_ANIM_MS, 659-676 |
| 侧栏收起延时（鼠标离开后） | 160ms 定时器后才动画 | — | sidebar.py:337-340 |
| 侧栏展开延时 | 0ms（进入立即展开） | — | sidebar.py:64 SIDE_HOVER_MS=0 |
| 树行悬停浮起 | 进入 **220ms** OutCubic 0→1；离开 **160ms** InCubic 1→0 | 行整体上移 `lift = round(3 × t)` px，阴影 alpha `72 × t` | widgets.py:909-928,521-531 |
| 悬浮条淡入 | **160ms** OutCubic（windowOpacity 0→1） | float_bar.py:204-206,238 |
| 悬浮条淡出 | **200ms**（当前透明度→0，播完 hide） | float_bar.py:227-242 |
| 悬浮条自动隐藏 | 3000ms（AUTO_HIDE_MS）；鼠标离开后 3000ms（LEAVE_HIDE_MS）；hover 进入即停表 | float_bar.py:23-24,249-256 |
| 备注气泡出现延时 | 200ms（NOTE_TIP_SHOW_MS 停留触发） | widgets.py:71,1008 |
| 新消息高亮闪烁 | 1100ms ease，box-shadow `0 0 0 3px rgba(74,99,240,.45)` → 无 | render_css.py:98-104 |
| 页面滚动 | `scroll-behavior: smooth`；目录点击 smooth + flash 1200ms | render_css.py:11, render.py:353-361 |
| 背景光斑漂移 | 26s / 32s / 38s ease-in-out infinite alternate | render_css.py:27-44 |
| 导图节点长按启动拖动 | 180ms（多选框选时 0ms）；移动阈值 6px（`dx²+dy²>36`） | render_mindmap_js.py:549-555 |
| 文档自动保存防抖 | 420ms input 防抖 + blur 立即保存 | render_doc.py:19-23 |
| 按钮按下位移 | 无过渡参数（QSS 直接换 padding 7px/16px/5px 模拟下沉），Web 建议 `transition: none` 保持一致按压瞬变 | style.py:91-95,146-152 |

> 240ms 侧栏动画在 Web 版直接用 CSS `transition: width 240ms cubic-bezier(0.215,0.61,0.355,1)`（OutCubic 贝塞尔近似值）或 `width 240ms cubic-bezier(0,0,0.58,1)`；推荐前者。同理 160ms 淡入用 `opacity 160ms cubic-bezier(0.215,0.61,0.355,1)`，200ms 淡出用 `opacity 200ms ease-out`。

### 2.6 滚动条

**桌面壳（QSS 侧，style.py:672-685）：**

```
宽/高 9px，轨道透明，margin 2px；
滑块 rgba(122,138,185,.5)，圆角 4px，最小长 30px；
悬停 rgba(110,126,175,.75)；
无上下箭头（add-line/sub-line 0×0），翻页区透明。
```

**Web 视图（render_css.py:51-57）：**

```
::-webkit-scrollbar { width/height: 10px; track 透明; }
thumb: rgba(110,126,175,.5), 圆角 8px, border 2px transparent + background-clip: padding-box;
thumb:hover: rgba(96,112,165,.72)
```

两套并存是因为旧版一个在 Qt 壳、一个在网页内；新版统一到 WebView 后可任选一套，建议统一 Web 版数值（10px），桌面壳内嵌滚动区（待办/常驻栏）也用同款 `::-webkit-scrollbar` 规则。

### 2.7 字体

- 壳：Qt 默认（未指定，Windows 上为 Segoe UI 9pt 系）；Web 页 body：`"Segoe UI","Microsoft YaHei",sans-serif`（render_css.py:16），文字色 `#262c3d`，`-webkit-font-smoothing: antialiased`。
- 代码：`Consolas, "Cascadia Mono", monospace`，行内 13px，代码块 13px/行高 1.55（render_css.py:178-179,216）。
- 悬浮条预览：12px `"Microsoft YaHei","Segoe UI"`。
- 字号梯度（QSS）：11（todoHint / todoMark / todoDate 元信息）、11.5（autoBackupHint）、12（菜单/状态/元信息/chip 大多数）、12.5（工具栏按钮/输入框/导入表格）、13（树行/正文/todoText/菜单条目）、15（todoDelete ×）。
- 导图节点正文 13.5px/行高 1.45，根节点 15px 加粗；文字节点正常字重（render_css.py:723-741）。

---

## 3. 各区域详设

### 3.1 工具栏（#mainToolBar）

水平排布（sidebar.py:132-173）：

```
[备份整个软件] [回收站] [markdown语法] [尚未自动备份···倒计时] ←弹性空隙→ [搜索框 240px] [⚙(仅图标)]
```

| 项 | 类型 | 行为 |
|---|---|---|
| 备份整个软件 | 文本按钮 | 弹输入框「备份原因：」→ 全量备份（程序+DB+图片）到 `~/Documents/AIChatRecord备份/{时间戳}-{原因}`（ops.py:815-934） |
| 回收站 | 文本按钮 | 主视图切换为回收站页（§4.4） |
| markdown语法 | 文本按钮 | 打开 MarkdownHelpDialog（§3.6） |
| 自动备份提示 | 只读胶囊 label | 文案 `上次自动备份 YYYY-MM-DD HH:MM · 下次还有 X小时Y分` 或 `尚未自动备份（起始 …） · …`，每秒刷新（ops.py:853-873）；样式 #autoBackupHint（11.5px #656e88 胶囊） |
| 搜索框 | QLineEdit 240px | 占位符「搜索全部记录，回车确认」，带清除按钮；回车执行全库搜索；清空时退出搜索回会话（view.py:134-150） |
| ⚙ 设置 | 仅图标按钮（18×18 图标） | 打开 SettingsDialog（§3.6） |

工具栏容器：`linear-gradient(180deg, rgba(255,255,255,.9), rgba(240,244,255,.74))`，底部 1px `rgba(146,162,205,.34)`，padding 8px 12px、间距 6px（style.py:126-132）。

按钮（QToolButton）：12px 上下 14px 左右 padding、圆角 12px、字 12.5px `#3d4459`；悬停白底 `#4a63f0` 字；按下底边翻转为亮（style.py:133-152）。**唯一 checked 态特殊样式**是工具栏无 checked 按钮，checked 橙色样式（`rgba(255,150,116,.42)→rgba(255,122,84,.3)`、字 `#bf4526`）保留给未来需要（style.py:153-160）。

齿轮图标为 8 齿+中孔的绘制图形（icons.py:101-119）；课题/文件夹/会话/导图/文档图标均为绘制图形（笔记本/文件夹/气泡/分叉/文档页，icons.py:7-98），Web 版可改为同形 SVG。

### 3.2 左侧边栏（SideOverlay 浮层）

#### 结构与行为（sidebar.py:80-126, 175-381, 602-690）

- **旧版是独立透明子窗口**盖在主窗口上，透明区域通过 `WM_NCHITTEST` 返回 `HTTRANSPARENT` 把点击穿透给下面的网页。**新版改为普通 `position:absolute; left:0; top:<工具栏底>; bottom:<状态栏顶>` 的 div**，收起时 `width:26px`，展开时 `width:侧栏内容宽`——不需要点击穿透 hack，因为收起态只占 26px 细条，不会遮挡中间视图的按钮（这正是旧版 `_sidebar_window_width` 注释的动机）。
- 细条（26px）即 #sideRail 的可视化：竖向白玻璃条（`rgba(255,255,255,.8)→rgba(242,246,255,.66)` 水平渐变，圆角 16px，白顶/`rgba(146,162,205,.32)` 底边）。用户悬停细条（或整个边栏区域）→ 立即展开（0ms 延时）；鼠标离开 → 160ms 后开始 240ms OutCubic 收起动画。若鼠标按下（拖拽中）或有弹出菜单打开，不收起（sidebar.py:616-643）。
- 展开动画只改**裁切宽度**，内容层保持完整宽度不重排（SideClip 模式）：Web 用外层 `overflow:hidden` + 内层固定宽度的两明治结构实现，`transition` 挂外层 width。
- 边栏右侧 1px `rgba(146,162,205,.34)` 分隔线（#sideClip）。

#### 内容（两层 sidePanel 玻璃卡，`margin 8/10/8/10`，间距 8）

**上：课题列（subjectPanel）**
- 头部说明：`课题 · 点击切换 · 双击重命名 · 拖动排序`（#sideHead：12px `#7a84a2`，padding 10px 12px 4px，自动换行）。
- 课题树：每行 `名称（N）` + 笔记本图标；缩进 8px；行 hover/选中样式见树行规格；悬停 tooltip `课题 · 创建于 {created_at} · 拖动可调整顺序`。
- 树缩进 8px、图标 16×16（sidebar.py:207-208）。

**下：文件夹/会话列（panel）**
- 头部说明：`本课题的周期文件夹 · 点击切换 · 双击重命名 · 拖动排序 · 右键可建会话 / 文件夹 / 思维导图 / 文档`。
- 会话树缩进 22px、图标 16×16；文件夹行加粗、文本前缀 `▸`（收起）/`▾`（展开）+ 两空格（tree.py:396-397,688-690）。

#### 两列间分隔条

水平 splitter，handleWidth 6px，拖动后写 `subject_width`/`folder_width`（仅用户手拖才记 `sidebar_dragged`）。初始 168/252；启动时自动撑宽到「最长标题一行放下」（算法 `_oneline_tree_width`：粗体字宽 + PAD_X×2 + GAP + 图标宽 + 36 + 缩进×深度 + 行内按钮预留，sidebar.py:383-463）。

### 3.3 会话树（SessionTree）行内自绘元素

树行不用 QSS 选中背景，全部由 delegate 自绘（widgets.py:472-851），Web 版直接译成每行一个 div 卡片：

#### 行卡片几何

- 内边距 `_PAD_X=10 / _PAD_Y=10`，图标-文字间距 `_GAP=8`，元信息行高 `_META_H=16`。
- 气泡矩形 = 行矩形左缩 2、右缩 6(+标签列 58+6)、上下 3，再上移 `lift`；圆角 12px。
- 悬停/选中浮起：`lift = round(3×t)` px；阴影 `rgba(70,90,150, 72×t)` 圆角 12，位于气泡下方 (+2,+5,-2,+4)。
- 默认卡面：白 `alpha 200+36t`，边 `alpha 232+20t` 宽 1.25；顶边内侧高光线白 alpha 255（left+12→right-12, y=top+1），底边暗线 `rgba(146,162,205, 70+40t)`（y=bottom-1）。选中态：fill alpha 240、border alpha 255。
- 选中文字 `#4a63f0` 加粗；普通 `#2c3345`。
- 标题换行 `WrapAnywhere`，行高按内容算，最小 38px；带时间行最小 56px、加 `_META_H+4`（widgets.py:782-816）。

#### 双行时间（session/mindmap/document 行）

第二行 `创建 YYYY-MM-DD HH:MM  ·  编辑 YYYY-MM-DD HH:MM`（时间截到分钟；编辑缺失回退创建），字号比正文小 2pt（≈11px）、色 `#737d9c`，右端省略号（widgets.py:480-484,622-646）。

#### chip 标签（会话行右侧独立列）

- 列宽 `SESSION_TAG_RESERVE=58px`，与气泡间距 `_TAG_COL_GAP=6`；chip 高 `_TAG_CHIP_H=20`，垂直间距 `_TAG_CHIP_GAP=5`，整列垂直居中（widgets.py:72-75,668-702）。
- 字号 9pt 加粗；chip 圆角 10px；描边 `rgba(255,255,255,230)` 宽 1.1 + 顶部内高光 `rgba(255,255,255,245)`（left+6→right-6, top+1）。
- 三种规格（widgets.py:76-95）：

| key | 文字 | 前景色 | 渐变（顶→底） |
|---|---|---|---|
| cursor | Cursor | `#2a4ec4` | `rgba(190,208,255,.86)` → `rgba(74,99,240,.46)` |
| codex | Codex | `#0b6b5c` | `rgba(170,232,214,.86)` → `rgba(32,168,140,.46)` |
| done | 已完成 | `#187a48` | `rgba(176,232,198,.86)` → `rgba(46,168,108,.44)` |

排序：cursor/codex 在前、已完成在后（`session_tag_keys`）。

#### 匹配按钮 / 导入按钮（仅文件夹行）

- 匹配按钮：`46×22px`，距行右缘 8px，垂直居中；圆角 8px。常态白 `alpha 220`、边 `rgba(146,162,205,.706)`、字 9pt `#5d6684`「匹配」；悬停白 `alpha 248`、边 `rgba(74,99,240,.706)`、字 `#4a63f0`；激活（匹配中）填充 `rgba(74,99,240,.902)`、边 `#4a63f0`、白字（widgets.py:99-102,158-174,704-729）。
- 导入按钮：同尺寸 46×22，在匹配按钮左侧，间距 5px；样式同匹配按钮（悬停变 `#4a63f0` 字），文字「导入」（widgets.py:103-105,167-174,731-746）。
- 文件夹行为此右侧预留 `FOLDER_BTNS_EXTRA = 46+8+4+46+5 = 109px`。

#### 匹配模式的行内元素

- 进入匹配（点某文件夹【匹配】）后：该文件夹展开，其中每个会话行右缘出现**圆形勾选框** 16×16（右距 10）：描边 `#4a63f0` 1.4px，未选白 `alpha 236` 填充，选中填充 `rgba(74,99,240,1)` + 白色对勾（1.8px 两笔线段）；已被选中的会话行外围叠加 `#4a63f0` 1.8px **虚线**描边（圆角 12）（widgets.py:565-570,748-765）。
- 第二次点【匹配】（已有选中）→ 在按钮左下 (-8,+6) 弹 MatchColorPopup（玻璃小面板：标题「选择高亮颜色」+ 五个色名按钮 + 「清除匹配」，按钮带 16×16 圆形色板图标，内距 10、间距 6）（widgets.py:189-227）。

#### 备注气泡（会话备注悬浮提示）

- 停留 200ms 后出现；深色气泡：`linear-gradient(180deg, rgba(48,53,72,.96), rgba(33,37,52,.96))`、字 `#eef1fb` 12px、边 `rgba(255,255,255,.16)`（顶 .32、底 `rgba(0,0,0,.35)`）、圆角 10px、padding 6px 10px、最大宽 260px 自动换行（widgets.py:71,960-986）。
- 位置：鼠标全局位置 +(+14,+18)，超出右缘 clamp（≥8、≤宽-气泡宽-8），超出底部翻到指针上方 -10；鼠标穿透不拦截事件（widgets.py:1024-1038）。

#### 树交互语义（详见 §5 汇总表）

单击文件夹 = 展开/收起（选中态还给当前内容项）；单击会话/导图/文档 = 切换视图；双击 = 重命名；右键 = 上下文菜单；拖拽 = 排序/移动（§5.2）。空文件夹单击提示状态栏「这个文件夹还是空的：右键在此新建会话、思维导图或文档，或把条目拖进来」（tree.py:634-637）。

### 3.4 待办栏（TodoPanel，260px）

结构（todo.py:390-516）：

```
todoDock（透明容器，margin 8/12/10/12）
└─ todoGlass（玻璃卡 18px 圆角，内距 10/12/10/12，间距 10，panel 投影）
   ├─ todoTitle「待办」（胶囊 999px，12px 加粗 #737d9c，白渐变）
   ├─ todoHint「年-月-日-事情 · 单击待办可加备注」（11px #8b94ad 居中）
   ├─ [todoInput（弹性，胶囊 15px，占位「2026-09-11-事情」）] [todoAdd +（30×30 圆钮，主色渐变）]
   └─ 滚动列表（间距 8）
       ├─ 无待办：todoEmpty「还没有待办」（12px #8b94ad，padding 28px 8px 居中）
       └─ TodoDateGroup（日期组）/ TodoRow（无日期单行）
```

#### 日期组 TodoDateGroup（todoGroup 玻璃卡，16px 圆角，内距 8，间距 4）

- 日期 chip（todoDate）：居中、12px 加粗、圆角 12、padding 6px 10px、白顶/`rgba(146,162,205,.34)` 底边。五 tone 按 `日期序号 % 5` 轮转（orange→pink→blue→gray→purple）：

| tone | 字色 | 渐变（180°） | 底边色 |
|---|---|---|---|
| orange | `#a85200` | `rgba(255,186,116,.72)→rgba(255,154,61,.56)` | `rgba(188,110,40,.38)` |
| pink | `#b5406c` | `rgba(255,205,220,.78)→rgba(255,178,202,.62)` | `rgba(190,110,140,.34)` |
| blue | `#245296` | `rgba(196,221,255,.82)→rgba(164,200,255,.64)` | `rgba(96,134,196,.36)` |
| gray | `#515868` | `rgba(212,217,226,.82)→rgba(186,192,204,.64)` | `rgba(130,138,152,.36)` |
| purple | `#62419b` | `rgba(223,209,250,.82)→rgba(200,180,240,.64)` | `rgba(140,112,190,.36)` |

（style.py:552-589）已完成组的日期 chip 变灰：字 `#8b94ad`、底 `rgba(255,255,255,.55)`。

- 组内分两段：未完成行列表（间距 2）；有已完成项时显示「已完成」胶囊头（todoDoneHead：11px 加粗 `#7a84a2`，margin 4px 20px 0，胶囊 999px）+ 已完成行列表。

#### 待办行 TodoRow（todoRow 卡，14px 圆角，padding 8/8/6/8，间距 8）

```
[✓ 勾选圆钮 22×22] [标题（todoText 13px #2c3345 换行）+ 标记胶囊] [备注块（todoNote）] [× 删除]
```

- 勾选钮（todoCheck）：22×22 圆形，白 `alpha .92` 底、1.5px 边 `rgba(130,145,190,.5)`；hover 边 `rgba(74,99,240,.6)`；选中态主色渐变+白 ✓ 12px 加粗。完成后标题删除线 + 灰 `#8b94ad`、整行卡变半透明白 `.62/.5`。
- 标记胶囊（todoMark）：10px 加粗、padding 2px 8px、999px。
  - 延后（later）：字 `#a85200`，`rgba(255,191,122,.85)→rgba(255,160,72,.7)`，底边 `rgba(188,110,40,.4)`。
  - 不做了（skip）：字 `#615866`，`rgba(226,221,233,.9)→rgba(196,189,205,.78)`，底边 `rgba(140,132,150,.38)`；行文字变 `#8b94ad`。
- 备注（todoNote）：11px `#656e88`、白 `.86` 底圆角 10、padding 6px 9px；完成后变 `#9aa2b6`/白 .58。
- 备注 编辑态（todoNoteEdit）：白底、`rgba(79,110,247,.32)` 边（顶 .5）、圆角 10、11px。
- 删除（todoDelete）：× 15px `#a8b0c6`，hover `#e5484d` + `rgba(229,72,77,.12)` 底，圆角 10。
- 排序：未完成按 `mark(skip=2, later=1, 无=0) → sort_order → -id`；已完成 `sort_order → -id`（todo.py:56-65）。
- 交互：单击行（非按钮区）→ 进入备注编辑（隐藏备注、显示输入框、全选）；Esc 取消；回车/失焦保存并 emit；右键菜单【延后】【不做了】（checkable，重复点取消）+ 已有标记时「取消标记」（todo.py:199-217）。
- 日期解析：`^【?\s*(\d{4})-(\d{1,2})-(\d{1,2})-(.+?)\s*】?$`（可选全角括号包裹），显示正文去掉日期前缀；组间按日期倒序；无日期单条平铺在所有日期组之后（todo.py:30-94）。

### 3.5 底部常驻栏（StashPanel）

结构（stash.py:190-342）：

```
stashBar（透明，最小高 148，外距 10/0/10/10）
└─ 水平 inner（间距 10）
   ├─ stashNav 分类导航（固定 132×132 玻璃方卡，18px 圆角，panel 投影，内距 8/10/8/10，间距 6）
   │   └─ 三个互斥按钮（垂直均分）：提示词 / 密钥 / 账号密码（stashNavBtn）
   └─ todoGlass 玻璃卡（弹性）
       ├─ 输入行：todoInput（固定宽 180，占位随分类变）+ todoAdd +（30×30）
       └─ 横向滚动列表（行距 8，右 padding 4）
           ├─ 空态（todoEmpty：左对齐垂直居中，文案随分类：「还没有提示词/密钥/账号密码」）
           └─ StashRow × N（横向卡片，宽 200~280）
```

- 分类按钮（stashNavBtn）：12.5px 加粗 `#5a647c`，透明底 10px 圆角，padding 4px 6px；hover 白 `.85`；选中（checked）白渐变底 + `#4a63f0` 字 + 完整三边框（白顶/`rgba(146,162,205,.4)` 底）。默认选「提示词」。
- 输入占位随分类：「提示词」/「粘贴密钥」/「账号和密码」（stash.py:25-29）。
- StashRow：复用 todoRow/todoText/todoNote/todoDelete 样式；宽 200–280；`padding 8/8/6/8`。单击复制（正文优先，无正文复制标题），双击进入行内编辑（复用 todoNoteEdit；Esc 取消、回车/失焦保存；空文本回退原值），× 删除。单击与双击的区分用 500ms（系统双击间隔）延时定时器实现（stash.py:93-114）。
- 复制后写剪贴板 + 状态栏「已复制到剪贴板」+ 通知剪贴板监听抑制下一次事件（sidebar.py:465-469）。

### 3.6 四个无边框玻璃对话框

公共骨架（GlassNoteDialog 为例，widgets.py:282-379）：

```
modal 遮罩（透明背景 dialog）
└─ 外距 28/22/28/34（给投影留白）
   └─ glassNotePanel：一级面板渐变、20px 圆角、白 .92 边（顶纯白/底 rgba(146,162,205,.38)）、dialog 投影
       ├─ glassNoteTitle：胶囊 999px、13px 加粗 #556081、居中、padding 6px 20px
       ├─ 内容区
       └─ 按钮行（右对齐，间距 10）：glassNoteCancel（次按钮）+ glassNoteOk（主按钮，button 投影）
```

- 主按钮（glassNoteOk）：主色三段渐变、12px 圆角、padding 7px 22px、白字加粗、min-width 76px。
- 次按钮（glassNoteCancel）：白渐变、字 `#5d6684`，hover 纯白 + `#4a63f0` 字。
- **拖动**：按住面板非输入区可拖动整窗（mousePress/Move/Release，widgets.py:353-369）——Web 版在 title 胶囊和面板空白处实现同等拖拽（对 fixed 定位 modal 改 left/top）。
- 键位：Ctrl+Enter 确定、Esc 取消（widgets.py:344-351）。

| 对话框 | 尺寸 | 内容 |
|---|---|---|
| **GlassNoteDialog 会话备注** | 440×300 | title「会话备注」+ 多行编辑（glassNoteEdit：白 .88 底、14px 圆角、凹陷三边框、focus 变 `rgba(79,110,247,.42)` 边+纯白底；占位「写一点备注，指针停在对话上会看到」）+ 取消/保存（widgets.py:282-379） |
| **SettingsDialog 设置** | 宽固定 440（高自适应） | title「设置」+ 分组标题「常规」（settingsCaption 12px 加粗 #8b94ad）+ 两个复选框（17×17 指示器）：「开机自启动（开机后静默缩在托盘）」「暂停记录（复制内容不再弹出悬浮条）」+ 分组「数据」+ 行：说明「所有记录保存在 data\chatlog.db」+「打开数据文件夹」次按钮 + 右下「关闭」主按钮（widgets.py:381-469） |
| **MarkdownHelpDialog** | 760×640 | title「Markdown 语法」+ 富文本浏览区（glassHelpBrowser：白 .72 底、14px 圆角、内 padding 4）+「关闭」主按钮。内容为 render_doc.markdown_help_html() 的样例文档（widgets.py:1293-1362）。Web 版改为滚动 div |
| **CursorImportDialog** | **960×620** | title「从 Cursor 导入对话」+ importHint 胶囊说明（「选择一个 Cursor 对话导入到当前文件夹。列表只读取本机缓存，不会修改原始数据。」，14px 圆角、9px/15px padding）+ importTableWrap 玻璃框（16px 圆角、panel 投影、内距 6）内表格 + 取消/导入。表格（importTable）：四列「标题(280)/工作区(330)/更新时间(145)/对话轮数(90, 拉伸)」，行高 34，整行单选、不可编辑、无网格线；行底部 1px `rgba(150,168,210,.22)` 分隔；hover 白 .82；选中蓝渐变 `rgba(148,174,255,.55)→rgba(103,133,245,.42)`、字 `#2b3776`；表头白渐变、12px 加粗 `#737d9c`、左上/右上 11px 圆角。默认选中第 0 行并聚焦；双击行=导入；未选中时「导入」禁用（cursor_import_dialog.py:22-131） |

所有 QInputDialog/QMessageBox（新建/重命名/删除确认/备份原因/删除记录确认等）沿用系统原生风格，Web 版统一改为同款玻璃 modal（输入型复用 GlassNoteDialog 骨架，确认型用 title+正文+取消/确认）。确认文案逐条见 §5 各表。

### 3.7 悬浮条（FloatBar，Tauri 第二窗口）

窗口属性（float_bar.py:31-39）：无边框、置顶、不抢焦点（WindowDoesNotAcceptFocus / WA_ShowWithoutActivating）、透明背景、不进任务栏。Web 版为 Tauri 独立透明子窗口。

#### 布局

```
外层（留白 20/14/20/28 给投影）
└─ #card（深色玻璃卡 16px 圆角，投影 0 12px 40px rgba(15,20,45,.59)）
    └─ 水平（内距 16/10/10/10，间距 8）
        ├─ [缩略图（仅图片时，高 34px 缩放，宽>120 则缩到 120）]
        ├─ 预览文字（固定宽 300px）
        ├─ [提问 btnQ（主蓝渐变）]
        ├─ [回答 btnA（绿色渐变）]
        └─ [× btnX（透明，#9aa2b5 16px）]
```

- 按钮：10px 圆角、padding 7px 16px、12px 加粗白字；三键 cursor:pointer、不抢焦点。
- 文本预览：`已复制 N 字　{压缩空白后 220px 宽度截断的文本}`。
- 图片预览：`已复制图片 W×H` + 缩略图。

#### 出现位置（_move_near_cursor，float_bar.py:212-225）

```
x = 鼠标x + 12,  y = 鼠标y + 18
若 y + 高 > 屏幕可用区底 - 8：翻上 y = 鼠标y - 高 - 14
x = clamp(屏左+8, x, 屏右-宽-8)；y = clamp(屏顶+8, y, 屏底-高-8)
```
（屏幕取鼠标所在屏，兜底主屏。）

#### 生命周期

- 命中剪贴板新内容 → 显示于鼠标旁，160ms 淡入；3s 计时自动 200ms 淡出隐藏。
- 鼠标进入悬浮条 → 停表；离开 → 重启 3s 计时。
- 点提问/回答 → 立即隐藏（不播动画）→ invoke 入库 → 主窗口 `notify_message_added`（切会话、滚到新消息、1.1s flash 高亮、窗口置前）。
- 点 × → 200ms 淡出。
- 已显示时再来新内容：直接换内容重定位（不重播淡入，透明度保持 1）、重置 3s 计时（`_popup` 逻辑）。
- 「暂停记录」开启时不弹（main.py:304-310）。

### 3.8 托盘（Tauri tray-icon）

- tooltip「AI 对话记录器」；菜单（main.py:370-377）：`显示主窗口 / 暂停记录(勾选) / 开机自启(勾选) / ── / 重启 / 退出`。
- 单击/双击图标 = 显示主窗口（置前、解除最小化）。
- 首次隐藏到托盘时气泡通知：「AI 对话记录器仍在运行 / 复制文字仍会弹出悬浮条，可从托盘图标退出。」
- `--minimized` 启动参数 = 只驻托盘不显示窗口（main.py:403-404）。

---

## 4. 四视图排版

四视图共用同一 HTML/CSS 基底（render.py `_page` + render_css.py `_CSS`），新版作为主窗口中间视图区的四个互斥状态。

### 4.0 公共页面基底

- body 背景：`linear-gradient(160deg, #d2dfff 0%, #e6ecfc 42%, #efe3f7 100%)`；三个固定定位**背景光斑**（.blob）：
  - b1：620×620，top:-180 left:-160，`rgba(124,152,255,.46)`，`drift1 26s ease-in-out infinite alternate`（translate(70px,50px) scale(1.1)）
  - b2：540×540，bottom:-200 right:-140，`rgba(255,158,208,.38)`，`drift2 32s`（translate(-60px,-40px) scale(1.06)）
  - b3：480×480，top:28% left:50%，`rgba(118,214,213,.3)`，`drift3 38s`（translate(-80px,60px)）
  - 光斑均 `blur(90px)`、`pointer-events:none`、z-index 0（render_css.py:22-44）
- 内容容器 `.wrap`：`max-width 920px; margin 0 auto; padding 8px 22px 40px; z-index 1`；宽视图（导图/文档）`.wrap-wide`：`max-width none; padding 12px 18px 0`。
- 文字选中色 `::selection rgba(99,125,255,.3)`。
- 页头徽章（page-head/search-head）：胶囊 999px、白渐变、`blur(22px) saturate(180%)`、12px `#656e88`、居中、margin 22px 0 8px（搜索页左对齐 13px `#565f7c`）。
- 空态 `.empty`：居中、14px、行高 2、`margin-top 110px`、`#8a93ad`；大图标 `.big` 88×88 圆形白玻璃（投影 12/30+3/8）、38px 字符（💬 会话空态 / 🗑 回收站空态）。
- KaTeX：`.tex-display`（块级居中、`overflow-x:auto`、margin .75em 0）、`.tex-inline` 行内；渲染 `katex.render(text, el, {displayMode, throwOnError:false})`（render.py:120-133,213-230）。
- **新版桥接变化**：旧 `app://` iframe 桥 + `window.appCall` 改为 `invoke()`；http(s) 链接改由 `on_navigation` 拦截转系统浏览器；CSP 拦远程资源（对应 LocalOnlyInterceptor）。

### 4.1 气泡流视图（会话）

**页头**：`会话「名称」 · 创建于 YYYY-MM-DD HH:MM:SS · N 条记录`。

**空会话**：空态文案「复制任意文字后，在弹出的悬浮条上点『提问』或『回答』，记录就会出现在这里」。

**消息结构**（render.py:281-314）：

```
.msg.user（右对齐）/ .msg.ai（左对齐）      margin 20px 0, scroll-margin-top 18px
├─ .meta：12px #7f88a6，user 侧 margin 0 10px 6px 靠右
│   「我 / AI（加粗，user=#4a63f0，ai=#0f9d78） · 时间」+ 悬停显示的操作链接 .ops
│   操作：复制原文|复制图片 · 改为回答|改为提问 · 删除（danger：hover #e5484d）
└─ .bubble（max-width 78%、padding 12px 18px、圆角 20px、字号 14.5px、行高 1.7、overflow-wrap anywhere）
```

- **user 气泡**：`linear-gradient(160deg, rgba(125,153,255,.96), rgba(74,99,240,.92))`、白 .45 边（顶 .75 / 底 `rgba(48,66,168,.55)`）、右下角 7px、白字；投影 `0 14px 32px rgba(74,99,240,.34), 0 3px 8px rgba(74,99,240,.2), inset 0 1px 0 rgba(255,255,255,.5)`。
- **AI 气泡**：白渐变 `.88/.78`、白 .92 边（顶纯白/底 `rgba(146,162,205,.38)`）、左下角 7px、字 `#262c3d`（继承）；投影 `0 12px 30px rgba(58,78,130,.16), 0 3px 8px rgba(58,78,130,.08), inset 0 1px 0 rgba(255,255,255,.92)`。
- 时间显示：当天只显 `HH:MM`，否则 `YYYY-MM-DD HH:MM`（render.py:170-177）。
- **图片消息**：`.bubble.image-bubble`（padding 6px）内 `<img class="msg-img">`：max-width 100%、max-height 420px、圆角 14px、cursor zoom-in；点击用系统看图工具打开（`app://` 之外的 file 链接，仅放行 data/images/ 内文件）。
- **Canvas 消息**：`.msg.ai .bubble.canvas-bubble`：`max-width min(1140px,100%)`、width 100%、padding 18px 20px；内部为 `cv-*` 静态 HTML（cv-stack/cv-row/cv-grid 布局、cv-h1~h3、cv-pill、cv-card、cv-callout(success/warning/danger)、cv-stat、cv-table、cv-dot(五色)、cv-bars 柱状图、cv-hr 等完整类目，样式见 render_css.py:249-392，此处全部保留原值）。
- **内联元素**：行内 code（白渐变底、`#c7254e` 字、6px 圆角；user 侧白 .26 底白字）；代码块 `pre.codeblock`（深色 `rgba(30,34,48,.95)→rgba(20,23,34,.93)`、`blur(20px) saturate(150%)`、圆角 14、padding 28px 15px 13px、右上角 `data-lang` 语言标签 11px `#98a0b8`、monokai 高亮——新版换 highlight.js monokai 主题 CSS 等价替换）；表格（`border rgba(122,140,200,.42)`、th 白渐变、`display:block; overflow-x:auto`）；blockquote（左 3px `rgba(110,133,255,.8)` 竖条、白渐变底、8px 圆角、字 `#565f7c`；user 侧白 .2 底 `#edf1ff` 字）；链接 `#4a63f0`（user 侧 `#e3eaff`）；hr（双线：暗 1px + 白高光）。
- **Markdown 渲染管线**：markdown-it `commonmark` preset + `html:false, breaks:true` + enable(table, strikethrough)；公式先抽取（$$…$$、\[…\]、\(…\)、行内 $…$、独立 [ 多行块 ] 且形态似 LaTeX）再还原，避免 Markdown 破坏公式（render.py:44-143）。
- **打开会话默认滚到底**（scroll_bottom=True）。

**右侧提问目录（chat-nav，仅在有提问时）**（render_css.py:467-530, render.py:329-429）：

- 固定定位：`right:12px; top:64px; bottom:22px; width:172px`；白玻璃卡 20px 圆角、panel 级投影+inset 高光、内距 12px 8px 10px。
- 标题「提问」（11px `#8b94ad` letter-spacing .04em）。
- 条目：预览每个 user 消息（去 Markdown 符号、42 字截断、3 行 line-clamp）、圆角 12、右上网名序号胶囊（min-width 20×20、主蓝渐变 `#6379f5→#4257ea`，当前项 `#4a63f0→#3550e6`）。
- 滚动同步：以 `scrollY + max(80, innerHeight×0.18)` 为界标当前项，目录自动滚到可见。
- 点击条目：smooth 滚到消息 + flash 1200ms。
- chat-ui 下 `.wrap` 特化：`padding-right:196px; max-width:1100px`（给固定目录让位）。

**新消息跳转**（_JUMP_MSG_JS）：滚动到 `msg-{id}` 居中 + flash 类；找不到则滚到底；load 后 80ms/280ms 各重试一次。

**性能红线（新版行为变化）**：旧版每次记录后整页重写 view.html 重载；新版改为增量 append 单条气泡 DOM + 局部 KaTeX 渲染；打开会话首屏只取最近 200 条，上滚分页「加载更早」。

### 4.2 思维导图视图

页面结构（render.py:638-767）：

```
.wrap-wide
├─ page-head：思维导图「名称」 · N 个节点
├─ mm-hint（提示行，12px #7f88a6 居中，z-index 3，pointer-events none）
└─ .mm-viewport（fixed inset:0, overflow hidden, cursor grab）
    └─ .mm-pan（绝对定位，left/top = cam.tx/ty）
        └─ .mm-world > .mm-canvas（width/height = 布局尺寸, overflow visible）
            ├─ svg.mm-lines（连线层，pointer-events none；内含每边的命中粗线 16px 透明 + 可视线）
            ├─ .mm-edge-label × N（连线标签，绝对定位在中点）
            └─ .mm-node × N（绝对定位卡片）
```

- **页面级**：`html.mm-ui` overflow hidden、禁 overscroll；拖背景时 body 加 `.mm-drag`（cursor grabbing）；中键框选时 `.mm-boxing`（crosshair）。
- **节点**（mm-node）：绝对定位、padding 10px 14px、圆角 18px、白玻璃 `blur(26px) saturate(180%)`、标准三投影、字 `#1d2335`、cursor grab；正文 .mm-body 13.5px/1.45 `white-space:pre-wrap`，空节点占位「双击编辑」（`#b0b8cc`）。
  - 根节点（.root）：蓝玻璃 `rgba(206,219,255,.94)→rgba(160,182,255,.86)`、字 `#223478`、加粗 15px、投影 `0 14px 32px rgba(74,99,240,.26)…`。
  - 文字节点（.text）：**无玻璃**——透明底、无投影、1px 虚线边 `rgba(104,119,162,.82)`、8px 圆角、padding 6px 8px、正常字重。
  - 散文节点（.mm-prose，多行或 >32 字）：左对齐非居中。
  - 高亮（.hl）：橙边 `rgba(255,168,66,.98)`（顶 `rgba(255,218,170,1)` / 底 `rgba(203,112,18,.7)`）+ 三层橙色辉光（`0 0 14px 4px rgba(255,145,40,.48)`、`0 0 28px 8px rgba(255,140,40,.26)`）叠加标准投影；text 节点只保留辉光。
  - 手工定尺寸（.mm-sized，有 box_w/box_h）：固定 width/height、overflow auto；四角出现 .mm-resize 手柄（10×10、白底 2px 蓝边方点、nwse/nesw-resize 光标）。
- **连线**：贝塞尔 `M x1 y1 C mx y1, mx y2, x2 y2`（父右边中点 → 子左边中点）；常态 `rgba(90,110,180,.45)` 2px；两端节点都高亮时（.hl）橙色 `#ff8a2a` 2.6px + 双层 drop-shadow 辉光；选中（.selected）`#4a63f0` 3px；命中区透明 16px 宽（pointer-events:stroke）。
- **连线标签**（.mm-edge-label）：绝对定位在中点（translate(-50%,-50%)）、max-width 168px、padding 3px 10px、12px/1.35 居中、白玻璃 10px 圆角、`overflow-wrap anywhere; white-space:pre-wrap`；空标签不显示；高亮橙字 `#b04f05`、选中蓝字 `#3550e6`。双击标签 = 编辑标注。
- **交互手柄**：.mm-handle / .mm-port 均为 14×14 白底 2px 蓝边圆点（margin -7px）、默认 display:none、`.on` 显示；port 带 `0 0 0 3px rgba(74,99,240,.28)` 外圈。拖动节点时四角出现 resize 手柄，左右两端出现 port；拖出连线显示 .mm-draw-line（蓝 2px 虚线 `6 4`）；可放置目标节点 .mm-drop 蓝色 2px outline（offset 2px）；选中节点同款 outline。
- **框选**（中键）：.mm-marquee 固定定位蓝色选框（1.5px `rgba(74,99,240,.95)` 边、`rgba(74,99,240,.18)` 填充）；框到的节点+连线一起选中、一起拖动。
- **缩放**：Ctrl+滚轮，因子 1.12，范围 **0.4 ~ 2.5**，以鼠标为锚（render_mindmap_js.py:930-936）；实现用 CSS `zoom`（scale≈1 时清空）。
- **相机**：tx/ty/scale 持久化（settings.json，每导图一份），变更时 `app://setcam`（→ invoke）。
- **节点拖动**：长按 180ms 启动（多选框选中时 0ms），位移阈值 6px；松手批量 `setpos`。
- **自动布局**（prepare_mindmap_layout）：缺失坐标的节点才排版——根 (32+extra_x, 32)，子节点 x = 父.x+父.w+56（h_gap），y = 上一个兄弟.y+h+18（v_gap）或父.y；节点尺寸估算按字符单位（中文 1.0 / ASCII 0.58 / 空白 0.4，char_px 14）：box 最小 168×(32+行×22) 最大宽 280，text 最小 140 最大宽 300；多根横向间隔 40；画布四周 pad 32（render.py:536-635）。
- **右键菜单**（mm-menu）：固定定位、min-width 132px、白玻璃 14px 圆角、padding 6、panel 级投影；条目按钮 8px 14px padding、13px `#2c3345`、8px 圆角、hover 蓝渐变底 `#4a63f0` 字；danger hover `#e5484d` 红渐变底；菜单顶部可带两行元信息（mm-menu-meta：11px `#656e88`，创建/编辑时间）+ 分隔线（mm-menu-sep）。菜单位置 = 鼠标 clientX/Y。菜单项清单见 §5.3。
- 画布上 `contextmenu` 全局 preventDefault。

### 4.3 文档视图（左编辑右预览）

结构（render_doc.py:41-63 + render_css.py:805-877）：

```
html.doc-ui（overflow hidden, 100%）
└─ .wrap-wide（height 100vh, flex column, padding 8px 16px 12px）
    ├─ page-head：文档「名称」 · Markdown · 左侧编辑，右侧预览
    └─ .doc-split（flex:1, grid 1fr 1fr, gap 12px）
        ├─ textarea#doc-src（.doc-src）
        └─ .doc-preview-wrap > #doc-preview（.doc-preview）
```

- **编辑区**（.doc-src）：100% 宽高、圆角 16、padding 14px 16px、白渐变底、标准三投影、Consolas 14px/1.55、字 `#262c3d`、`resize:none; outline:none; spellcheck=false`；占位「在这里用 Markdown 写作，例如：# 一级标题」；focus 边变蓝 `rgba(74,99,240,.45)` + 蓝投影。启动自动聚焦。
- **预览区**（.doc-preview-wrap）：overflow auto、圆角 16、白渐变底、同投影；内容 .doc-preview：padding 10px 18px 28px、14.5px/1.7；标题 h1 1.45em / h2 1.28em / h3 1.12em；blockquote 左 3px `rgba(74,99,240,.75)`、浅蓝渐变底；表格、hr、链接样式同 §4.1。空文档预览空态「还没有内容，左边写 Markdown，右侧即时预览」。
- **保存流**：input 420ms 防抖 + blur 立即 → `savedoc` invoke → 成功后仅更新预览区 innerHTML + 局部 KaTeX 渲染（`window.__docPreview` 模式，不整页刷新）。
- 语法帮助：工具栏「markdown语法」打开 modal（替代旧 QTextBrowser 独立弹窗）。

### 4.4 回收站视图 / 搜索视图

**回收站**（render.py:462-516 + render_css.py:402-465）：

- 页头（search-head 左对齐）：`回收站 · N 项（恢复后回到原来的位置；彻底删除不可恢复）`。
- 右上操作条（.trash-bar）：红色「清空回收站」按钮（9px 圆角、6px 12px padding、红白渐变、`#e5484d` 字加粗）。
- 空态：🗑 大图标 +「回收站是空的 / 删除的课题、会话、文件夹、思维导图和文档会出现在这里」。
- 条目卡（.trash-item）：横向 flex、gap 16、margin 0 10px 10px、padding 14px 16px、白玻璃 14px 圆角、标准三投影：
  ```
  [元信息（弹性）]                          [恢复] [彻底删除]
   ├ kind：11px #6b75d8 加粗（课题/文件夹/会话/思维导图/文档）
   ├ name：15px 加粗 #2c3345
   └ sub：12px #8a93ad —— 位置链「课题「X」 · 文件夹「Y」 · 会话「Z」」+ 明细 + 「删除于 {deleted_at}」
  ```
  明细：文件夹/课题=`N 个会话`、会话=`N 条记录`、其他=类型名。
- 操作按钮（.trash-ops）：蓝白渐变 `#4b64e0` 字（恢复）与红色版（彻底删除），9px 圆角。
- **搜索视图**（render.py:432-450）：页头 `搜索「关键字」，共 N 条结果（点击消息上方会话名可跳转）`；无结果空态「没有找到相关记录」。每条结果 = `.session-tag`「来自 会话「名称」（蓝色链接，hover 下划线，点击 app://goto 切课题+会话）」+ 消息气泡（**无操作链接**，ops=False）；不滚到底。

---

## 5. 交互细节表

### 5.1 右键菜单 —— 会话树（ui/ops.py:936-1112 `_tree_menu`）

**空白处（无条目）：**

| 菜单项 | 动作 |
|---|---|
| 新建会话（根目录） | 在根目录建会话 |
| 新建文件夹 | 建文件夹 |
| 新建思维导图（根目录） | 根目录建导图 |
| 新建文档（根目录） | 根目录建文档 |
| ── | |
| 打开回收站 | 切回收站视图 |

**文件夹行：**

| 菜单项 | 动作 |
|---|---|
| 在此文件夹新建会话 | 建会话（展开该文件夹） |
| 在此文件夹新建思维导图 | 建导图 |
| 在此文件夹新建文档 | 建文档 |
| 下载整个文件夹 | 导出 zip（对话/思维导图/文档/图片 子目录） |
| 重命名文件夹 | 输入框重命名 |
| 移动到课题 ▸ | 子菜单：全部其他课题名（无则禁用） |
| ── | |
| 删除文件夹 | 确认「确定把文件夹「X」及其中 N 个会话、M 条记录移入回收站吗？\n可稍后在回收站恢复。」 |

**会话行**（右键同时切换到该会话）：

| 菜单项 | 动作 |
|---|---|
| 新建会话 / 新建思维导图 / 新建文档 / 新建文件夹 | 同层新建（_add_sibling_create_actions，见下） |
| ── | |
| 重命名 | 输入框重命名 |
| 编辑备注 / 添加备注（按有无备注切换文案） | GlassNoteDialog |
| ── | |
| 【cursor】（checkable） | 切换 source=cursor（已勾选则清除） |
| 【codex】（checkable） | 切换 source=codex |
| 【已完成】（checkable） | 切换 done |
| ── | |
| 在此会话下新建思维导图 | 挂在会话下 |
| 在此会话下新建文档 | 挂在会话下 |
| 复制到 ▸ | 子菜单：（根目录）+ 全部文件夹（含当前；复制副本） |
| 移动到 ▸ | 子菜单：（根目录）+ 除当前所在文件夹外的文件夹（当前在根则不列根目录） |
| 移动到课题 ▸ | 子菜单：其他课题 |
| 导出 Markdown | 单会话导出 .md |
| 导出匹配的全部对话（颜色名 · N 个） | *仅有 match_color 时出现*：同课题同文件夹同色全部导出 |
| 取消颜色匹配 | *仅有 match_color 时出现*：清除该会话颜色 |
| ── | |
| 删除会话 | 确认「确定把会话「X」及其 N 条记录移入回收站吗？\n可稍后在回收站恢复。」 |

**思维导图行**（右键同时选中）：同层新建四项 ── 重命名 ── 复制到 ▸ ── 移动到 ▸（挂在会话下时不跳过逻辑同上）── 移动到课题 ▸ ── 删除思维导图（确认移入回收站）。

**文档行**（右键同时选中）：同层新建四项 ── 重命名 ── 复制到 ▸ ── 移动到 ▸ ── 移动到课题 ▸ ── 导出 Markdown ── 删除文档（确认移入回收站）。

> 「同层新建」（_add_sibling_create_actions, ops.py:124-168）：新建会话（落在该条目所在文件夹/根）、新建思维导图、新建文档（条目挂在会话下则同挂该会话，否则同文件夹）、新建文件夹；随后分隔线。所有新建/重命名对话框默认值：会话=`YYYY-MM-DD`（保持默认名则仍参与首条自动命名）、文件夹=「新文件夹」、导图=「思维导图」、文档=「文档」。

### 5.2 右键菜单 —— 课题树（ui/tree.py:127-137 `_subject_menu`）

| 菜单项 | 动作 |
|---|---|
| 新建课题 | 输入框（默认「新课题」） |
| 重命名课题 | *有目标时*；右键同时选中该课题 |
| ── | |
| 删除课题 | 确认「确定把课题「X」及其中 N 个文件夹、M 个会话、K 条记录移入回收站吗？」；至少保留一个课题（否则提示） |

### 5.3 右键菜单 —— 思维导图画布（render_mindmap_js.py:620-663）

**节点上**（顶部两行元信息「创建 YYYY-MM-DD HH:MM」「编辑 …」+ 分隔线）：

| 菜单项 | 动作 | 备注 |
|---|---|---|
| 新建子框 | addbox（先批量保存现位置） | |
| 新建子句 | addtext | |
| 高亮 / 取消高亮 | togglehl（按当前状态切换文案） | |
| 只删除此单元 | delone（danger） | *仅非根节点*；确认「只删除这个单元，它下面的节点会接到上一级。确定吗？」 |
| 删除此单元及后续 | delnode（danger） | *仅非根节点*；确认「确定删除这个节点以及它下面的全部分支吗？」；根节点删除被拒（状态栏「中心框请在左侧删除整张导图」） |

**连线上：**

| 菜单项 | 动作 |
|---|---|
| 在连线上新建子框 | edgebox（连线中点插入 box，先存位置） |
| 在连线上新建子句 | edgetext |
| 编辑标注 | editedge（输入框「两端单元的关系：」） |
| 删除连线 | deledge（danger；确认「确定删除这两个单元之间的连线吗？单元本身会保留。」） |

**空白处：**

| 菜单项 | 动作 |
|---|---|
| 新建独立子框 | addfreebox（在右键世界坐标处，默认 (80,80)） |
| 新建独立子句 | addfreetext |

### 5.4 右键菜单 —— 待办行（ui/todo.py:199-217）

| 菜单项 | 动作 |
|---|---|
| 【延后】（checkable） | mark=later；重复点取消 |
| 【不做了】（checkable） | mark=skip；重复点取消 |
| ──（仅有标记时） | |
| 取消标记 | 清除 mark |

### 5.5 拖放规则（`_on_entry_dropped`，ui/tree.py:747-843；`_ordered_insert` widgets.py:229-244）

落点语义来自 Qt dropIndicatorPosition：**above**（目标上方）/ **below**（目标下方）/ **on**（落在目标上）。Web 版用 HTML5 DnD 自算：鼠标 y 在目标行上 1/4 内=above、下 1/4 内=below、中间=on（与 Qt View 行为一致）。

| 拖动源 | 落点 | 语义 |
|---|---|---|
| 任何 | 拖到自身（同 kind 同 id） | 忽略 |
| 文件夹 | 任意位置 | **只在顶层换序**：目标若嵌在文件夹内，向上找顶层祖先作为目标，place 强制 below；空目标=移到末尾（above 则插最前） |
| 会话/导图/文档 | **on 文件夹** | 移入该文件夹，**插到该文件夹子列表第 1 位**，展开文件夹并选中 |
| 导图/文档 | **on 会话** | 挂到该会话下，插到会话子列表第 1 位 |
| 会话 | **on 会话** | place 视作 below（目标后排序） |
| 会话/导图/文档 | above/below 同层条目 | 目标所在层为目的地（文件夹内 or 根 or 会话下）；插到目标前/后 |
| 会话/导图/文档 | above/below **会话的子项**（导图/文档挂在会话下时） | session 源：改以该会话为目标、below，落到会话所在文件夹；导图/文档源：落到该会话下 |
| 任何 | 空白处（无目标） | 移到根目录末尾（above=最前） |

`_ordered_insert` 算法：从列表剔除拖动项 → 目标不存在/None 时按 above 插头 / below 尾 → 否则 index(target)，below 则 index+1，插入。排序持久化 `reorder_tree_items`。

**课题树拖放**（tree.py:845-852）：仅课题间换序，同 `_ordered_insert`；拖到自身忽略。

**匹配模式中禁用拖放**（widgets.py:1167-1170 dropEvent 直接 ignore）。

### 5.6 单击 / 双击 / 右键语义总表

| 区域 | 单击 | 双击 | 右键 |
|---|---|---|---|
| 课题行 | 切换课题（记住旧课题视图状态，恢复新课题上次视图） | 重命名课题 | 课题菜单（§5.2） |
| 文件夹行 | 展开/收起（选中态还给当前内容项；空文件夹→状态栏提示） | 重命名文件夹 | 文件夹菜单（§5.1） |
| 会话行 | 切换到气泡流（有子导图/文档则同时展开） | 重命名会话 | 会话菜单（§5.1） |
| 导图行 | 切换到导图视图 | 重命名导图 | 导图菜单 |
| 文档行 | 切换到文档视图 | 重命名文档 | 文档菜单 |
| 文件夹行【匹配】钮 | 第一次：进入匹配模式（展开文件夹，状态栏引导）；第二次：无选中→退出；有选中→弹颜色选择 | — | — |
| 文件夹行【导入】钮 | 打开 CursorImportDialog 导入到该文件夹 | — | — |
| 匹配模式中会话行 | 勾选/取消勾选该会话（不切换视图） | — | — |
| 待办行主体 | 进入备注编辑（非按钮区） | — | 待办标记菜单（§5.4） |
| 待办 ✓ 钮 | 切换完成（勾中后 suppress 一次单击，避免误触编辑） | — | — |
| 待办 × 钮 | 删除待办 | — | — |
| 待办输入框 | 聚焦 | — | — |
| 常驻栏行主体 | 复制（500ms 延时判定，双击则取消） | 行内编辑 | — |
| 常驻栏 × 钮 | 删除 | — | — |
| 气泡 .ops 链接 | 复制原文/图片（并抑制下一次剪贴板事件）、改为提问/回答（flip 整页刷新→新版局部替换）、删除（确认「确定删除这条记录吗？」，图片消息同时删文件） | — | — |
| 导图节点 | 选中（显示 resize 手柄+port）；已选中再次单击=进入连线条（点其他节点完成）；多选框选中集中点击不取消 | 编辑正文（contenteditable） | 节点菜单（§5.3） |
| 导图连线/标签 | 选中（显示端点 handle，可拖端点改接） | （标签）编辑标注 | 连线菜单（§5.3） |
| 导图空白 | 清除全部选择 | — | 空白菜单（新建独立子框/子句） |
| 导图背景 | 按住拖 = 平移画布（pan） | — | — |
| 导图（中键） | 按住拖 = 橡皮框选（节点+连线）；**需禁用 WebView2 中键自动滚屏** | — | — |
| 导图（Ctrl+滚轮） | 以鼠标为锚缩放 0.4~2.5 | — | — |
| 搜索结果会话名链接 | 跳转（必要时切课题）到该会话 | — | — |
| 回收站 恢复/彻底删除/清空 | 恢复到原位置（自动切课题、展开文件夹、选中）；彻底删除（确认「此操作不可恢复」）；清空（确认 N 项不可恢复） | — | — |

### 5.7 键位表

| 键 | 位置 | 行为 | 来源 |
|---|---|---|---|
| **Esc** | 玻璃对话框 | 取消/关闭 | widgets.py:348 |
| **Esc** | 匹配模式中的会话树 | 退出匹配模式 | widgets.py:1160-1165 |
| **Esc** | 待办备注编辑框 | 取消编辑还原 | todo.py:228-233 |
| **Esc** | 常驻栏行内编辑框 | 取消编辑还原 | stash.py:125-130 |
| **Ctrl+Enter** | GlassNoteDialog（备注） | 保存 | widgets.py:345 |
| **Enter** | 工具栏搜索框 | 执行搜索（空关键字忽略） | sidebar.py:164 |
| **Enter** | 待办/常驻栏输入框 | 添加 | todo.py:417, stash.py:237 |
| **Enter** | 行内编辑框（备注/常驻） | 保存（editingFinished） | todo.py:156, stash.py:69 |
| **Enter / 双击** | CursorImportDialog 表格行 | 确认导入 | cursor_import_dialog.py:85 |
| **Ctrl+滚轮** | 导图画布 | 缩放 | render_mindmap_js.py:930 |
| **中键拖** | 导图画布 | 框选 | render_mindmap_js.py |
| **Tab** | 备注编辑框 | 切焦点不插入制表符（TabChangesFocus） | widgets.py:308 |

### 5.8 其他全局交互约定

- **复制原文/图片、常驻栏复制**：写剪贴板前设置一次性抑制标志，避免自己的复制触发悬浮条（main.py:302, view.py:234-243, sidebar.py:465-469）。
- **删除即软删**：课题/文件夹/会话/导图/文档删除全部进回收站（deleted_at），消息单条删除是硬删（连图片文件）。
- **状态栏文案**：每个写操作都有对应状态反馈（已复制/已移动/已导出/已恢复/已拦截…），Web 版维持同文案清单（散见 ops.py/view.py 各处）。
- **新记录通知流**：悬浮条入库 → 主窗口切会话+跳转高亮+解除最小化+置前（view.py:118-130）。
- **搜索模式退出**：清空搜索框（文字变化触发）或点击树中任何内容项。
- **导图视图相机**：平移/缩放即写 `setcam`（新版存 settings.json），重开导图恢复视角。
- **外链/本地文件防护**：http(s) 链接点击转系统浏览器；记录内容中的 file:// 链接仅放行 data/images/ 内文件，其余拦截并提示「已拦截记录内容里指向外部文件的链接」；远程图片资源由 CSP 阻断（防 IP 泄露）（widgets.py:1247-1290）。

---

## 附录：Qt hack 不移植清单

| 旧实现 | 处置 |
|---|---|
| `QStyleFactory.create("Fusion")` 强制树样式（避免 Win11 原生选中条） | 不需要——HTML/CSS 自绘行卡片，无原生样式干扰（sidebar.py:191,254） |
| `::branch` 全状态置空（去 Qt 展开箭头） | 不需要——展开箭头由行内 `▸/▾` 文本字符实现（tree.py:396） |
| `WM_NCHITTEST`→`HTTRANSPARENT` 点击穿透（SideOverlay） | 不需要——收起态只占 26px，展开态本就要接收点击（sidebar.py:91-104） |
| `QGraphicsDropShadowEffect` 三档投影 | CSS `box-shadow` 原生实现（style.py:18-34 → §2.4） |
| `QTWEBENGINE_CHROMIUM_FLAGS=--disable-features=MiddleClickAutoscroll` | 改为 Tauri 创建窗口前设 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`；失败则页内 `auxclick/pointerdown` 中键 `preventDefault()`（main.py:41-47） |
| QSettings 注册表持久化 | settings.json（见总计划 Phase 1 步骤 6） |
| `data/view.html` 写盘+load 整页刷新 | 内存中直接更新 DOM；气泡流增量 append（性能红线） |
