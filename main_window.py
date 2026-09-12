"""主窗口：会话列表 + 聊天气泡流 + 搜索 + 导出。"""

from PySide6.QtCore import QSettings, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QMainWindow

import autostart
from db import Database
from ui.ops import OpsMixin
from ui.sidebar import SidebarMixin
from ui.style import APP_QSS
from ui.tree import TreeMixin
from ui.view import ViewMixin


class MainWindow(SidebarMixin, TreeMixin, OpsMixin, ViewMixin, QMainWindow):
    hidden_to_tray = Signal()

    def __init__(self, db: Database):
        super().__init__()
        self._db = db
        self._settings = QSettings("little-tools", "ai-chat-logger")
        self._suppress_cb = None
        self._loading = False
        self._search_mode = False
        self._current_sid = None
        self._current_mid = None
        self._current_did = None
        self._current_kind = "session"
        self._trash_mode = False
        self._current_subject_id = None
        self._loading_subjects = False
        self._mm_view = {}
        self._fitting_sidebars = False
        self._sidebars_ready = False
        self._user_splitting = False
        self._match_popup = None
        # 只用「用户拖过分割条」这个新键。旧的 sidebar_user_sized
        # 会在窗口首次显示时被误写成 True，导致自动撑宽永远不再跑。
        self._sidebar_user_sized = self._settings.value(
            "sidebar_dragged", False, type=bool
        )

        self.setWindowTitle("AI 对话记录器")
        self.resize(1600, 740)

        self.pause_action = QAction("暂停记录", self)
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._on_pause_toggled)

        self.autostart_action = QAction("开机自启", self)
        self.autostart_action.setCheckable(True)
        # 先设初值再连接信号，避免初始化时触发一次写注册表
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.toggled.connect(self._on_autostart_toggled)

        self._build_toolbar()
        self._build_body()
        self._status = QLabel()
        self.statusBar().addWidget(self._status)

        self._init_subject_selection()
        self.reload_subjects()
        self.reload_sessions()
        self._setup_auto_backup()

