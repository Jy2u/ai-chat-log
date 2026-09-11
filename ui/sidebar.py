"""主窗口：工具栏与侧栏布局。"""

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QFontMetrics
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QStyleFactory,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ui.icons import (
    _make_chat_icon,
    _make_doc_icon,
    _make_folder_icon,
    _make_gear_icon,
    _make_map_icon,
    _make_subject_icon,
)
from ui.todo import TODO_PANEL_W, TodoPanel
from ui.widgets import (
    ChatPage,
    LocalOnlyInterceptor,
    MATCH_BTN_EXTRA,
    ROLE_KIND,
    SessionTree,
    SessionTreeDelegate,
    SubjectTree,
    _enable_tree_wrap,
)


class SidebarMixin:
    # ---------- 界面搭建 ----------

    def _build_toolbar(self):
        bar = QToolBar()
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        bar.setIconSize(QSize(18, 18))
        self.addToolBar(bar)

        act_new_subject = QAction("新建课题", self)
        act_new_subject.triggered.connect(self.new_subject)
        act_new = QAction("新建会话", self)
        act_new.triggered.connect(lambda: self.new_session())
        act_new_folder = QAction("新建文件夹", self)
        act_new_folder.triggered.connect(self.new_folder)
        act_export = QAction("导出 Markdown", self)
        act_export.triggered.connect(self.export_session)
        act_backup = QAction("备份整个软件", self)
        act_backup.triggered.connect(self.backup_data)
        act_trash = QAction("回收站", self)
        act_trash.triggered.connect(self.open_trash)
        act_map = QAction("新建思维导图", self)
        act_map.triggered.connect(lambda: self.new_mindmap())
        act_doc = QAction("新建文档", self)
        act_doc.triggered.connect(lambda: self.new_document())
        bar.addAction(act_new_subject)
        bar.addAction(act_new)
        bar.addAction(act_new_folder)
        bar.addAction(act_map)
        bar.addAction(act_doc)
        bar.addAction(act_export)
        bar.addAction(act_backup)
        bar.addAction(act_trash)
        act_md = QAction("markdown语法", self)
        act_md.triggered.connect(self.show_markdown_help)
        bar.addAction(act_md)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索全部记录，回车确认")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(240)
        self._search.returnPressed.connect(self._do_search)
        self._search.textChanged.connect(self._on_search_text_changed)
        bar.addWidget(self._search)

        act_settings = QAction(_make_gear_icon(), "设置", self)
        act_settings.triggered.connect(self._open_settings)
        bar.addAction(act_settings)
        gear_btn = bar.widgetForAction(act_settings)
        if gear_btn is not None:
            gear_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)

    def _build_body(self):
        side = QWidget()
        outer = QVBoxLayout(side)
        outer.setContentsMargins(12, 12, 4, 12)
        outer.setSpacing(8)

        self._subject_icon = _make_subject_icon()
        self._folder_icon = _make_folder_icon()
        self._chat_icon = _make_chat_icon()
        self._map_icon = _make_map_icon()
        self._doc_icon = _make_doc_icon()
        fusion = QStyleFactory.create("Fusion")

        subject_panel = QFrame()
        subject_panel.setObjectName("sidePanel")
        sub_lay = QVBoxLayout(subject_panel)
        sub_lay.setContentsMargins(6, 6, 6, 8)
        sub_lay.setSpacing(2)
        sub_head = QLabel("课题 · 点击切换 · 双击重命名 · 拖动排序")
        sub_head.setObjectName("sideHead")
        sub_head.setWordWrap(True)
        self._subject_tree = SubjectTree()
        self._subject_tree.setObjectName("subjectTree")
        self._subject_tree.setHeaderHidden(True)
        self._subject_tree.setRootIsDecorated(False)
        self._subject_tree.setIndentation(8)
        self._subject_tree.setIconSize(QSize(16, 16))
        self._subject_tree.setExpandsOnDoubleClick(False)
        self._subject_tree.setAllColumnsShowFocus(False)
        if fusion is not None:
            self._subject_tree.setStyle(fusion)
        self._subject_tree.setDragEnabled(True)
        self._subject_tree.setAcceptDrops(True)
        self._subject_tree.setDropIndicatorShown(True)
        self._subject_tree.setDragDropMode(QTreeWidget.InternalMove)
        self._subject_tree.setDefaultDropAction(Qt.MoveAction)
        _enable_tree_wrap(self._subject_tree)
        self._subject_tree.setItemDelegate(SessionTreeDelegate(self._subject_tree))
        self._subject_tree.currentItemChanged.connect(
            self._on_subject_current_changed
        )
        self._subject_tree.itemDoubleClicked.connect(
            self._on_subject_double_clicked
        )
        self._subject_tree.subject_dropped.connect(self._on_subject_dropped)
        self._subject_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._subject_tree.customContextMenuRequested.connect(self._subject_menu)
        sub_lay.addWidget(sub_head)
        sub_lay.addWidget(self._subject_tree, 1)

        panel = QFrame()
        panel.setObjectName("sidePanel")
        side_lay = QVBoxLayout(panel)
        side_lay.setContentsMargins(6, 6, 6, 8)
        side_lay.setSpacing(2)
        head = QLabel(
            "本课题的周期文件夹 · 点击切换 · 双击重命名 · 拖动排序 · 右键可建会话 / 文件夹 / 思维导图 / 文档"
        )
        head.setObjectName("sideHead")
        head.setWordWrap(True)
        self._side_toggle = QToolButton()
        self._side_toggle.setObjectName("sideToggle")
        self._side_toggle.setText("收起")
        self._side_toggle.setToolTip("收起侧边栏")
        self._side_toggle.setAutoRaise(True)
        self._side_toggle.clicked.connect(lambda: self._set_sidebar_collapsed(True))
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 4, 0)
        head_row.setSpacing(0)
        head_row.addWidget(head, 1)
        head_row.addWidget(self._side_toggle, 0, Qt.AlignTop)
        self._tree = SessionTree()
        self._tree.setObjectName("sessionTree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(22)
        self._tree.setIconSize(QSize(16, 16))
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setAllColumnsShowFocus(False)
        if fusion is not None:
            # Win11 原生样式会在选中行左侧画指示条，嵌套越深条数越多
            self._tree.setStyle(fusion)
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QTreeWidget.InternalMove)
        self._tree.setDefaultDropAction(Qt.MoveAction)
        _enable_tree_wrap(self._tree)
        self._tree.setItemDelegate(SessionTreeDelegate(self._tree))
        self._tree.entry_dropped.connect(self._on_entry_dropped)
        self._tree.currentItemChanged.connect(self._on_tree_current_changed)
        self._tree.itemClicked.connect(self._on_tree_clicked)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self._tree.itemExpanded.connect(self._on_folder_toggled)
        self._tree.itemCollapsed.connect(self._on_folder_toggled)
        self._tree.match_clicked.connect(self._on_match_clicked)
        self._tree.match_cancelled.connect(self._exit_match_mode)
        self._tree.match_session_toggled.connect(self._on_match_session_toggled)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._tree_menu)
        side_lay.addLayout(head_row)
        side_lay.addWidget(self._tree, 1)

        inner = QSplitter()
        inner.setHandleWidth(6)
        inner.addWidget(subject_panel)
        inner.addWidget(panel)
        inner.setStretchFactor(0, 0)
        inner.setStretchFactor(1, 1)
        inner.setSizes([168, 252])
        inner.splitterMoved.connect(self._on_splitter_moved)
        self._watch_splitter_drag(inner)
        self._inner_split = inner
        self._subject_panel = subject_panel
        outer.addWidget(inner)

        self._side_rail = QFrame()
        self._side_rail.setObjectName("sideRail")
        rail_lay = QVBoxLayout(self._side_rail)
        rail_lay.setContentsMargins(4, 10, 4, 10)
        expand_btn = QPushButton("展\n开")
        expand_btn.setObjectName("sideRailBtn")
        expand_btn.setToolTip("展开侧边栏")
        expand_btn.clicked.connect(lambda: self._set_sidebar_collapsed(False))
        rail_lay.addWidget(expand_btn, 0, Qt.AlignTop)
        rail_lay.addStretch(1)
        self._side_rail.hide()
        outer.addWidget(self._side_rail)

        self._web = QWebEngineView()
        self._page = ChatPage(self._web)
        self._page.app_action.connect(self._handle_app_action)
        self._interceptor = LocalOnlyInterceptor()
        self._page.profile().setUrlRequestInterceptor(self._interceptor)
        self._web.setPage(self._page)

        split = QSplitter()
        split.setHandleWidth(6)
        split.addWidget(side)
        split.addWidget(self._web)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        split.setMinimumWidth(320)
        split.setSizes([430, 810])
        split.splitterMoved.connect(self._on_splitter_moved)
        self._watch_splitter_drag(split)
        self._split = split
        self._side_inner = inner
        self._side_panel = panel
        self._side = side
        self._side_width = 430

        todo_divider = QFrame()
        todo_divider.setObjectName("todoDivider")
        todo_divider.setAttribute(Qt.WA_StyledBackground, True)
        todo_divider.setFixedWidth(8)
        todo_divider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._todo_panel = TodoPanel(self._db)
        self._todo_panel.setFixedWidth(TODO_PANEL_W)

        root = QWidget()
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        root_lay.addWidget(split, 1)
        root_lay.addWidget(todo_divider, 0)
        root_lay.addWidget(self._todo_panel, 0)
        self.setCentralWidget(root)
        self._sidebar_collapsed = False
        if self._sidebar_user_sized:
            saved_sw = self._settings.value("subject_width", 0, type=int)
            saved_fw = self._settings.value("folder_width", 0, type=int)
            saved_w = self._settings.value("sidebar_width", 0, type=int)
            if saved_sw >= 110 and saved_fw >= 160:
                inner.setSizes([saved_sw, saved_fw])
                self._side_width = saved_sw + saved_fw + 22
            elif saved_w >= 320:
                self._side_width = saved_w
        if self._settings.value("sidebar_collapsed", False, type=bool):
            self._set_sidebar_collapsed(True)

    def _oneline_tree_width(self, tree: QTreeWidget) -> int:
        """一行完整显示所需宽度（含图标、缩进、内边距）。"""
        extra = (
            SessionTreeDelegate._PAD_X * 2
            + SessionTreeDelegate._GAP
            + tree.iconSize().width()
            + 36
        )
        widest = 140

        def walk(item, depth):
            nonlocal widest
            font = QFont(item.font(0))
            font.setBold(True)
            fm = QFontMetrics(font)
            w = (
                fm.horizontalAdvance(item.text(0) or "")
                + extra
                + tree.indentation() * depth
            )
            if w > widest:
                widest = w
            if item.data(0, ROLE_KIND) == "folder":
                widest = max(widest, w + MATCH_BTN_EXTRA)
            for i in range(item.childCount()):
                walk(item.child(i), depth + 1)

        for i in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(i), 0)
        return widest

    def _watch_splitter_drag(self, splitter: QSplitter):
        """只有按住分割条拖动才算用户改宽度，程序 setSizes 不算。"""
        for i in range(splitter.count()):
            handle = splitter.handle(i)
            if handle is not None:
                handle.installEventFilter(self)

    def eventFilter(self, obj, event):
        if isinstance(obj, QSplitterHandle):
            et = event.type()
            if et == QEvent.MouseButtonPress:
                self._user_splitting = True
            elif et == QEvent.MouseButtonRelease:
                if self._user_splitting:
                    self._save_side_widths(remember_user=True)
                self._user_splitting = False
        return super().eventFilter(obj, event)

    def _on_splitter_moved(self, *_):
        if self._user_splitting:
            self._save_side_widths(remember_user=True)

    def _needed_sidebar_sizes(self):
        sw = max(140, self._oneline_tree_width(self._subject_tree) + 24)
        fw = max(200, self._oneline_tree_width(self._tree) + 24)
        handle = 6
        side_w = sw + fw + handle + 16
        saved_sw = self._settings.value("subject_width", 0, type=int)
        saved_fw = self._settings.value("folder_width", 0, type=int)
        saved_w = self._settings.value("sidebar_width", 0, type=int)
        if saved_sw >= sw:
            sw = saved_sw
        if saved_fw >= fw:
            fw = saved_fw
        side_w = max(side_w, sw + fw + handle + 16)
        if saved_w > side_w:
            side_w = saved_w
        return sw, fw, side_w

    def _todo_reserved_width(self) -> int:
        panel = getattr(self, "_todo_panel", None)
        if panel is None or not panel.isVisible():
            return 0
        return TODO_PANEL_W + 8

    def _fit_sidebars_to_oneline(self, force=False):
        """首次打开时按标题撑开左栏。之后不再改窗口，以免全屏时挤掉待办。"""
        if self._sidebar_collapsed:
            return
        if self._sidebars_ready and not force:
            return
        sw, fw, side_w = self._needed_sidebar_sizes()
        chat_min = 800
        todo_w = self._todo_reserved_width()
        locked = self.isMaximized() or self.isFullScreen()
        self._fitting_sidebars = True
        self._inner_split.setSizes([sw, fw])
        if locked:
            total = sum(self._split.sizes()) or (side_w + chat_min)
            left = min(side_w, max(200, total - chat_min))
            self._split.setSizes([left, max(chat_min, total - left)])
            self._side_width = left
        else:
            need = side_w + chat_min + 24 + todo_w
            if self.width() < need:
                self.resize(need, max(self.height(), 740))
            self._split.setSizes([side_w, chat_min])
            self._side_width = side_w
            QTimer.singleShot(
                0, lambda: self._apply_fitted_sizes(sw, fw, side_w, chat_min)
            )
            return
        if getattr(self, "_todo_panel", None) is not None:
            self._todo_panel.setFixedWidth(TODO_PANEL_W)
        QTimer.singleShot(0, self._end_fitting_sidebars)
        self._subject_tree.doItemsLayout()
        self._tree.doItemsLayout()

    def _apply_fitted_sizes(self, sw, fw, side_w, chat_min):
        """窗口 resize 生效后再分配，避免对话栏被旧宽度锁死。"""
        self._inner_split.setSizes([sw, fw])
        total = sum(self._split.sizes()) or (side_w + chat_min)
        self._split.setSizes([side_w, max(chat_min, total - side_w)])
        if getattr(self, "_todo_panel", None) is not None:
            self._todo_panel.setFixedWidth(TODO_PANEL_W)
        self._subject_tree.doItemsLayout()
        self._tree.doItemsLayout()
        self._end_fitting_sidebars()

    def _end_fitting_sidebars(self):
        self._fitting_sidebars = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._sidebars_ready:
            QTimer.singleShot(0, self._finish_sidebar_setup)

    def _finish_sidebar_setup(self):
        self._fit_sidebars_to_oneline()
        QTimer.singleShot(0, self._mark_sidebars_ready)

    def _mark_sidebars_ready(self):
        self._sidebars_ready = True

    def _save_side_widths(self, remember_user=True):
        if self._sidebar_collapsed or self._fitting_sidebars:
            return
        if not self._sidebars_ready:
            return
        if remember_user:
            self._sidebar_user_sized = True
            self._settings.setValue("sidebar_dragged", True)
        inner_sizes = self._inner_split.sizes()
        if inner_sizes and inner_sizes[0] >= 110:
            self._settings.setValue("subject_width", inner_sizes[0])
        if len(inner_sizes) > 1 and inner_sizes[1] >= 120:
            self._settings.setValue("folder_width", inner_sizes[1])
        outer = self._split.sizes()
        if outer and outer[0] > 80:
            self._side_width = outer[0]
            self._settings.setValue("sidebar_width", self._side_width)

    def _set_sidebar_collapsed(self, collapsed: bool):
        if collapsed and not self._sidebar_collapsed:
            self._save_side_widths(remember_user=False)
        self._sidebar_collapsed = collapsed
        sizes = self._split.sizes()
        if collapsed:
            if sizes and sizes[0] > 80:
                self._side_width = sizes[0]
            self._side_inner.hide()
            self._side_rail.show()
            rest = sizes[1] if len(sizes) > 1 else 800
            self._split.setSizes([48, max(400, rest)])
        else:
            self._side_rail.hide()
            self._side_inner.show()
            total = sum(sizes) if sizes else 1240
            w = self._side_width or 430
            self._split.setSizes([w, max(200, total - w)])
            self._fit_sidebars_to_oneline(force=True)
        self._settings.setValue("sidebar_collapsed", collapsed)
        self._settings.setValue("sidebar_width", self._side_width)


