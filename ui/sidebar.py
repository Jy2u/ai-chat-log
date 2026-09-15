"""主窗口：工具栏与侧栏布局。"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QFontMetrics
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QStyleFactory,
    QToolBar,
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
from ui.stash import StashPanel
from ui.todo import TODO_PANEL_W, TodoPanel
from ui.widgets import (
    ChatPage,
    LocalOnlyInterceptor,
    MATCH_BTN_EXTRA,
    ROLE_DONE,
    ROLE_KIND,
    ROLE_SOURCE,
    SESSION_TAG_RESERVE,
    SessionTree,
    SessionTreeDelegate,
    SubjectTree,
    _enable_tree_wrap,
    session_tag_keys,
)

SIDE_RAIL_W = 26
SIDE_ANIM_MS = 240
SIDE_HOVER_MS = 0
_WM_NCHITTEST = 0x0084
_HTTRANSPARENT = -1


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class SideOverlay(QWidget):
    """顶层浮层：窗口尺寸固定，透明区域把点击还给下面的页面。"""

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self.setObjectName("sideOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            except (TypeError, ValueError, OverflowError):
                return super().nativeEvent(eventType, message)
            if msg.message == _WM_NCHITTEST:
                clip = getattr(self._owner, "_side_clip", None)
                if clip is not None:
                    # WM_NCHITTEST 给的是屏幕物理坐标，高分屏上不能直接 map。
                    local = self.mapFromGlobal(QCursor.pos())
                    if not clip.geometry().contains(local):
                        return True, _HTTRANSPARENT
        return super().nativeEvent(eventType, message)


class SideClip(QScrollArea):
    """只改裁切宽度，不滚动内容，避免动画时重排文字。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sideClip")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.viewport().setObjectName("sideClipView")
        self.viewport().setAutoFillBackground(False)

    def scrollContentsBy(self, dx, dy):
        return

    def ensureVisible(self, x, y, xmargin=50, ymargin=50):
        return


class SidebarMixin:
    # ---------- 界面搭建 ----------

    def _build_toolbar(self):
        bar = QToolBar()
        bar.setObjectName("mainToolBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        bar.setIconSize(QSize(18, 18))
        self.addToolBar(bar)

        act_backup = QAction("备份整个软件", self)
        act_backup.triggered.connect(self.backup_data)
        act_trash = QAction("回收站", self)
        act_trash.triggered.connect(self.open_trash)
        bar.addAction(act_backup)
        bar.addAction(act_trash)
        act_md = QAction("markdown语法", self)
        act_md.triggered.connect(self.show_markdown_help)
        bar.addAction(act_md)

        self._auto_backup_hint = QLabel("尚未自动备份")
        self._auto_backup_hint.setObjectName("autoBackupHint")
        bar.addWidget(self._auto_backup_hint)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        self._search = QLineEdit()
        self._search.setObjectName("mainSearch")
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
        side = SideOverlay(self)
        side.setMinimumWidth(0)

        # 内容层保持展开宽度，裁切层负责露出多少，避免收起时文字被挤成多行。
        content = QWidget()
        content.setObjectName("sideContent")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(8, 10, 8, 10)
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
        self._subject_tree.setMinimumWidth(0)
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
        self._tree = SessionTree()
        self._tree.setObjectName("sessionTree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(22)
        self._tree.setIconSize(QSize(16, 16))
        self._tree.setMinimumWidth(0)
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
        self._tree.import_clicked.connect(self.import_external_conversation)
        self._tree.match_cancelled.connect(self._exit_match_mode)
        self._tree.match_session_toggled.connect(self._on_match_session_toggled)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._tree_menu)
        side_lay.addWidget(head)
        side_lay.addWidget(self._tree, 1)

        inner = QSplitter()
        inner.setHandleWidth(6)
        inner.addWidget(subject_panel)
        inner.addWidget(panel)
        inner.setStretchFactor(0, 0)
        inner.setStretchFactor(1, 1)
        inner.setSizes([168, 252])
        inner.setMinimumWidth(0)
        inner.splitterMoved.connect(self._on_splitter_moved)
        self._watch_splitter_drag(inner)
        self._inner_split = inner
        self._subject_panel = subject_panel
        subject_panel.setMinimumWidth(0)
        panel.setMinimumWidth(0)
        outer.addWidget(inner)

        clip = SideClip(side)
        clip.setWidget(content)

        self._web = QWebEngineView()
        self._page = ChatPage(self._web)
        self._page.app_action.connect(self._handle_app_action)
        self._page.setBackgroundColor(QColor("#e6ebf8"))
        self._interceptor = LocalOnlyInterceptor()
        self._page.profile().setUrlRequestInterceptor(self._interceptor)
        self._web.setPage(self._page)
        self._web.setStyleSheet("background: transparent;")

        body_host = QWidget()
        body_host.setObjectName("bodyHost")
        body_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        body_lay = QVBoxLayout(body_host)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        body_lay.addWidget(self._web, 1)
        body_host.installEventFilter(self)

        side.setParent(self)
        side.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        side.setAttribute(Qt.WA_TranslucentBackground, True)
        side.setAttribute(Qt.WA_ShowWithoutActivating, True)
        side.installEventFilter(self)

        self._body_host = body_host
        self._side_inner = inner
        self._side_clip = clip
        self._side_content = content
        self._side_panel = panel
        self._side = side
        self._side_width = 430
        self._side_overlay_w = SIDE_RAIL_W
        self._side_anim = None
        self._sidebar_collapsed = True
        self._side_hovering = False
        self._side_expand_timer = QTimer(self)
        self._side_expand_timer.setSingleShot(True)
        self._side_expand_timer.setInterval(SIDE_HOVER_MS)
        self._side_expand_timer.timeout.connect(self._try_expand_sidebar)
        self._side_collapse_timer = QTimer(self)
        self._side_collapse_timer.setSingleShot(True)
        self._side_collapse_timer.setInterval(160)
        self._side_collapse_timer.timeout.connect(self._try_collapse_sidebar)

        todo_divider = QFrame()
        todo_divider.setObjectName("todoDivider")
        todo_divider.setAttribute(Qt.WA_StyledBackground, True)
        todo_divider.setFixedWidth(8)
        todo_divider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._todo_panel = TodoPanel(self._db)
        self._todo_panel.setFixedWidth(TODO_PANEL_W)

        main = QWidget()
        main_lay = QHBoxLayout(main)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        main_lay.addWidget(body_host, 1)
        main_lay.addWidget(todo_divider, 0)
        main_lay.addWidget(self._todo_panel, 0)

        self._stash_panel = StashPanel(self._db)
        self._stash_panel.copied.connect(self._on_stash_copied)

        root = QSplitter(Qt.Vertical)
        root.setObjectName("stashSplit")
        root.setChildrenCollapsible(False)
        root.setHandleWidth(8)
        root.addWidget(main)
        root.addWidget(self._stash_panel)
        root.setStretchFactor(0, 1)
        root.setStretchFactor(1, 0)
        root.setSizes([640, 168])
        self.setCentralWidget(root)
        if self._sidebar_user_sized:
            saved_sw = self._settings.value("subject_width", 0, type=int)
            saved_fw = self._settings.value("folder_width", 0, type=int)
            saved_w = self._settings.value("sidebar_width", 0, type=int)
            if saved_sw >= 110 and saved_fw >= 160:
                inner.setSizes([saved_sw, saved_fw])
                self._side_width = saved_sw + saved_fw + 22
            elif saved_w >= 320:
                self._side_width = saved_w
        self._sync_side_overlay()

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
            elif item.data(0, ROLE_KIND) == "session" and session_tag_keys(
                item.data(0, ROLE_SOURCE), item.data(0, ROLE_DONE)
            ):
                widest = max(widest, w + SESSION_TAG_RESERVE)
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
        if obj is getattr(self, "_body_host", None) and event.type() == QEvent.Resize:
            self._sync_side_overlay()
        elif obj is getattr(self, "_side", None):
            et = event.type()
            if et == QEvent.Enter:
                self._on_sidebar_enter()
            elif et == QEvent.Leave:
                self._on_sidebar_leave()
        elif isinstance(obj, QSplitterHandle):
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

    def _on_stash_copied(self, text: str):
        if self._suppress_cb:
            self._suppress_cb()
        QApplication.clipboard().setText(text)
        self._status.setText("已复制到剪贴板")

    def _todo_reserved_width(self) -> int:
        panel = getattr(self, "_todo_panel", None)
        if panel is None or not panel.isVisible():
            return 0
        return TODO_PANEL_W + 8

    def _fit_sidebars_to_oneline(self, force=False):
        """只调整浮层里两列的宽度，不改聊天 / 导图画布尺寸。"""
        if self._sidebars_ready and not force:
            return
        sw, fw, side_w = self._needed_sidebar_sizes()
        self._fitting_sidebars = True
        self._inner_split.setSizes([sw, fw])
        self._side_width = side_w
        if getattr(self, "_todo_panel", None) is not None:
            self._todo_panel.setFixedWidth(TODO_PANEL_W)
        self._subject_tree.doItemsLayout()
        self._tree.doItemsLayout()
        self._sync_side_overlay()
        QTimer.singleShot(0, self._end_fitting_sidebars)

    def _end_fitting_sidebars(self):
        self._fitting_sidebars = False

    def showEvent(self, event):
        super().showEvent(event)
        side = getattr(self, "_side", None)
        if side is not None:
            side.show()
            self._sync_side_overlay()
        if not self._sidebars_ready:
            QTimer.singleShot(0, self._finish_sidebar_setup)

    def hideEvent(self, event):
        side = getattr(self, "_side", None)
        if side is not None:
            side.hide()
        super().hideEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._sync_side_overlay()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_side_overlay()

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
        if inner_sizes:
            self._side_width = sum(inner_sizes) + 22
            self._settings.setValue("sidebar_width", self._side_width)
            self._side_overlay_w = self._sidebar_content_width()
            self._sync_side_overlay()

    def _sidebar_content_width(self) -> int:
        return max(320, int(self._side_width or 430))

    def _side_anim_running(self) -> bool:
        anim = getattr(self, "_side_anim", None)
        return (
            anim is not None
            and anim.state() == QAbstractAnimation.State.Running
        )

    def _sidebar_window_width(self) -> int:
        # 收起静止时窗口必须只占细条，否则会盖住对话里的按钮。
        if self._side_anim_running() or not self._sidebar_collapsed:
            return self._sidebar_content_width()
        return SIDE_RAIL_W

    def _sync_side_clip_width(self):
        clip = getattr(self, "_side_clip", None)
        if clip is None:
            return
        w = max(SIDE_RAIL_W, int(round(self._side_overlay_w)))
        host = getattr(self, "_body_host", None)
        parent = clip.parentWidget()
        if host is not None:
            h = host.height()
        elif parent is not None:
            h = parent.height()
        else:
            h = clip.height()
        if clip.width() != w or clip.height() != h:
            clip.setGeometry(0, 0, w, max(1, h))
        content = getattr(self, "_side_content", None)
        if content is None:
            return
        cw = self._sidebar_content_width()
        if content.width() != cw or content.height() != h:
            content.setFixedSize(cw, max(1, h))

    def _sync_side_overlay(self):
        host = getattr(self, "_body_host", None)
        side = getattr(self, "_side", None)
        if host is None or side is None:
            return
        win_w = self._sidebar_window_width()
        h = host.height()
        top_left = host.mapToGlobal(QPoint(0, 0))
        geo = QRect(top_left.x(), top_left.y(), win_w, h)
        if side.minimumWidth() != 0:
            side.setMinimumWidth(0)
            side.setMaximumWidth(16777215)
        if side.geometry() != geo:
            side.setGeometry(geo)
        self._sync_side_clip_width()
        if not self._side_anim_running():
            side.raise_()
        if self.isVisible() and not side.isVisible():
            side.show()

    def _cursor_over_sidebar(self) -> bool:
        side = getattr(self, "_side", None)
        if side is None:
            return False
        return side.rect().contains(side.mapFromGlobal(QCursor.pos()))

    def _on_sidebar_enter(self):
        self._side_hovering = True
        self._side_collapse_timer.stop()
        if not self._sidebar_collapsed:
            return
        self._side_expand_timer.stop()
        self._expand_sidebar_hover()

    def _on_sidebar_leave(self):
        if self._cursor_over_sidebar():
            self._side_hovering = True
            return
        self._side_hovering = False
        self._side_expand_timer.stop()
        if QApplication.activePopupWidget() is not None:
            return
        if QApplication.mouseButtons() != Qt.NoButton:
            return
        self._side_collapse_timer.start()

    def _try_expand_sidebar(self):
        if not self._side_hovering or not self._side.underMouse():
            return
        self._expand_sidebar_hover()

    def _try_collapse_sidebar(self):
        if self._cursor_over_sidebar() or (
            getattr(self, "_side", None) is not None and self._side.underMouse()
        ):
            self._side_hovering = True
            return
        if QApplication.activePopupWidget() is not None:
            return
        if QApplication.mouseButtons() != Qt.NoButton:
            return
        self._collapse_sidebar_hover()

    def _expand_sidebar_hover(self):
        target = self._sidebar_content_width()
        self._sidebar_collapsed = False
        self._sync_side_overlay()
        self._animate_sidebar(target)

    def _collapse_sidebar_hover(self):
        if QApplication.activePopupWidget() is not None:
            return
        self._side_expand_timer.stop()
        self._side_collapse_timer.stop()
        self._sidebar_collapsed = True
        self._animate_sidebar(SIDE_RAIL_W)

    def _animate_sidebar(self, target: float):
        current = float(self._side_overlay_w)
        if abs(current - target) < 1:
            self._side_overlay_w = target
            self._sync_side_overlay()
            return
        anim = getattr(self, "_side_anim", None)
        if anim is not None:
            anim.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(SIDE_ANIM_MS)
        anim.setStartValue(current)
        anim.setEndValue(float(target))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._on_side_anim)
        anim.finished.connect(self._on_side_anim_finished)
        self._side_anim = anim
        anim.start()

    def _on_side_anim(self, value):
        self._side_overlay_w = float(value)
        self._sync_side_clip_width()

    def _on_side_anim_finished(self):
        self._sync_side_overlay()

    def _set_sidebar_collapsed(self, collapsed: bool):
        self._sidebar_collapsed = collapsed
        if collapsed:
            self._animate_sidebar(SIDE_RAIL_W)
        else:
            self._expand_sidebar_hover()
