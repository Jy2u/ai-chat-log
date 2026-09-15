# agents.md

给在本仓库工作的 AI 编码代理的说明。

## 项目概述

**AI 对话记录器**：Windows 单用户桌面工具（PySide6 + QtWebEngine）。监听系统剪贴板，弹出悬浮条把复制的文字/图片记为「提问 / 回答」，按课题 → 文件夹 → 会话三层组织，附思维导图、Markdown 文档、待办、底部常驻（提示词 / 密钥 / 账号密码）与回收站。数据全部存本机 `data/` 目录（SQLite 数据库 + 图片），无网络服务、无多用户。

## 运行环境

- Windows + Python 3；入口 `main.py`，日常启动用 `启动.bat`（`pythonw main.py`，无控制台）。
- 安装依赖：`pip install -r requirements.txt`（仅 `PySide6`、`markdown-it-py`、`pygments`）。
- 必须在 `main.py` 里先于创建 `QApplication` 导入 QtWebEngine 相关模块（见 `main.py` 顶部注释）；不要把这类导入移到别处。
- 崩溃日志写入 `data/last_error.txt`（`main.py:_install_crash_log`），因为 `pythonw` 没有控制台。

## 架构

```
main.py            入口：崩溃日志、剪贴板监听（ClipboardWatcher）、单实例锁、托盘
main_window.py     APP_QSS 样式表 + MainWindow 组装
float_bar.py       复制后弹出的悬浮条（提问 / 回答）
db.py              数据层核心（约 1300 行）：建库、迁移、全部 SQL
db_documents.py    文档表操作
db_mindmaps.py     思维导图操作
db_trash.py        回收站
render.py          对话气泡 HTML 渲染
render_canvas.py   Cursor Canvas JSX → 卡片/表格渲染（约 1400 行）
render_doc.py      Markdown 文档渲染
render_css.py      渲染层共用 CSS
render_mindmap_js.py  思维导图页内 JS（约 1000 行）
autostart.py       开机自启（写注册表）
cursor_import.py   Cursor 对话导出文件导入（含图片）
ui/                Qt 界面层
  widgets.py       通用控件（约 1200 行）
  tree.py          左侧树：课题 / 文件夹 / 会话
  sidebar.py       左侧悬停边栏
  view.py          中间视图切换（气泡流 / 导图 / 文档）
  ops.py           右键菜单与记录操作（约 1000 行）
  todo.py          右侧待办面板
  stash.py         底部常驻栏
  style.py         QSS 主题（liquid-glass 风格）
  icons.py         程序内图标
  cursor_import_dialog.py  Cursor 导入对话框
ui/icons.py 之外的资源在 data/katex/ 与 vendor/katex/（KaTeX 字体与脚本）
```

依赖方向：`ui/` 与 `render*.py` → `db*.py` → SQLite；`main.py` 组装顶层组件。`db.py` 是事实上的核心模块，改 schema 前先读它的迁移逻辑。

## 约定

- 面向最终用户的字符串一律中文（README、菜单、提示语、备注均已是中文）。
- UI 走 QSS 主题（`ui/style.py`、`main_window.py:APP_QSS`），改样式不要散落内联样式。
- 剪贴板隐私约定：密码管理器通过 MIME 标记声明的内容不得记录（见 `main.py:_mime_marked_private`）。
- 单实例通过共享内存锁（`SINGLE_INSTANCE_KEY`）保证，勿绕过。

## 验证方式

无测试套件、无 linter 配置。改动后运行 `python main.py`（或 `启动.bat`）做冒烟验证：

1. 启动后悬浮条随剪贴板复制弹出，提问/回答能入库。
2. 左侧树切换课题/文件夹/会话正常。
3. 气泡流、思维导图、文档三种视图能打开。
4. 退出确认 `data/last_error.txt` 无新增。

分支 `refactor/main` 用于重构，保持行为不变；大改动请拆小步提交。
