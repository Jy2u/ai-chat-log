"""应用级样式表（液态玻璃风）。"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

# 应用级样式表（液态玻璃风）：在 main.py 里通过 app.setStyleSheet 应用，
# 这样托盘菜单、对话框等独立窗口也能吃到同一套风格。
#
# 统一的三档磨砂玻璃 + 立体感做法，改样式时照着来：
#   一级面板：白 0.92 → 淡蓝 0.84 渐变
#   二级内容块：白 0.88 → 0.78
#   三级小元件：白 0.82 → 0.70
#   凸起件（面板/按钮/卡片）顶边纯白、底边 rgba(146,162,205,0.3~0.45)
#   凹陷件（输入框/列表槽）反过来：顶边偏暗、底边纯白
#   主色按钮：#7d99ff → #5f7cf9 → #4a63f0，底边 rgba(48,66,168,0.6)


def apply_glass_shadow(widget, kind="panel"):
    """给玻璃面板加一层投影。Qt 的 QSS 画不出 box-shadow，只能用效果。"""
    shadow = QGraphicsDropShadowEffect(widget)
    if kind == "dialog":
        shadow.setBlurRadius(46)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(58, 78, 130, 95))
    elif kind == "button":
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(63, 88, 200, 110))
    else:
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(58, 78, 130, 78))
    widget.setGraphicsEffect(shadow)
    return shadow


APP_QSS = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #d3ddff, stop:0.35 #e6ecfb, stop:0.7 #e0f1f5, stop:1 #f1e5f6);
}
QDialog { background: #e9edf9; }
#glassNoteDialog { background: transparent; }
#glassNotePanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.92),
        stop:0.45 rgba(247, 249, 255, 0.86),
        stop:1 rgba(232, 238, 252, 0.84));
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.38);
    border-radius: 20px;
}
#glassNoteTitle {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(240, 244, 255, 0.78));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.32);
    border-radius: 999px;
    color: #556081; font-size: 13px; font-weight: 600;
    padding: 6px 20px;
}
#glassNoteEdit {
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid rgba(150, 166, 208, 0.42);
    border-bottom: 1px solid #ffffff;
    border-radius: 14px;
    padding: 8px 10px;
    color: #2c3345; font-size: 13px;
}
#glassNoteEdit:focus {
    border: 1px solid rgba(79, 110, 247, 0.42);
    border-top: 1px solid rgba(79, 110, 247, 0.6);
    background: #ffffff;
}
#glassNoteOk {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7d99ff, stop:0.5 #5f7cf9, stop:1 #4a63f0);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-top: 1px solid rgba(255, 255, 255, 0.75);
    border-bottom: 1px solid rgba(48, 66, 168, 0.6);
    border-radius: 12px; padding: 7px 22px; color: #ffffff;
    font-weight: 600; min-width: 76px;
}
#glassNoteOk:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8ea6ff, stop:0.5 #6e89fb, stop:1 #5670f3);
}
#glassNoteOk:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #5670f3, stop:1 #4459de);
    padding: 8px 22px 6px;
}
#glassNoteOk:disabled {
    background: rgba(170, 182, 216, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.5);
    color: rgba(255, 255, 255, 0.85);
}
#glassNoteCancel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(238, 242, 253, 0.8));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.45);
    border-radius: 12px; padding: 7px 22px; color: #5d6684;
    font-weight: 600; min-width: 76px;
}
#glassNoteCancel:hover { background: #ffffff; color: #4a63f0; }
#glassNoteCancel:pressed {
    background: rgba(236, 240, 252, 0.95);
    padding: 8px 22px 6px;
}
#glassHelpBrowser {
    background: rgba(255, 255, 255, 0.72);
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid rgba(150, 166, 208, 0.36);
    border-bottom: 1px solid #ffffff;
    border-radius: 14px;
    color: #2c3345;
    padding: 4px;
}
QLabel { background: transparent; color: #3a4152; }

QToolBar, #mainToolBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.9), stop:1 rgba(240, 244, 255, 0.74));
    border: none;
    border-bottom: 1px solid rgba(146, 162, 205, 0.34);
    padding: 8px 12px; spacing: 6px;
}
QToolBar QToolButton, #mainToolBar QToolButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.86), stop:1 rgba(241, 245, 255, 0.72));
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.42);
    padding: 6px 14px;
    border-radius: 12px; color: #3d4459; font-size: 12.5px;
}
QToolBar QToolButton:hover, #mainToolBar QToolButton:hover {
    background: #ffffff;
    color: #4a63f0;
}
QToolBar QToolButton:pressed, #mainToolBar QToolButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(228, 234, 250, 0.95), stop:1 rgba(240, 244, 255, 0.9));
    border-top: 1px solid rgba(146, 162, 205, 0.42);
    border-bottom: 1px solid #ffffff;
    padding: 7px 14px 5px;
}
QToolBar QToolButton:checked, #mainToolBar QToolButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 150, 116, 0.42), stop:1 rgba(255, 122, 84, 0.3));
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-top: 1px solid rgba(255, 255, 255, 0.85);
    border-bottom: 1px solid rgba(190, 96, 62, 0.45);
    color: #bf4526;
}
#autoBackupHint {
    color: #656e88; font-size: 11.5px;
    padding: 4px 14px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.82), stop:1 rgba(242, 246, 255, 0.7));
    border: 1px solid rgba(255, 255, 255, 0.9);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.3);
    border-radius: 999px;
}
#mainSearch {
    min-height: 28px;
    background: rgba(255, 255, 255, 0.86);
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid rgba(150, 166, 208, 0.4);
    border-bottom: 1px solid #ffffff;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(238, 242, 253, 0.82));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.45);
    border-radius: 11px; padding: 6px 16px; color: #3a4152;
}
QPushButton:hover { background: #ffffff; color: #4a63f0; }
QPushButton:pressed {
    background: rgba(236, 240, 252, 0.95);
    border-top: 1px solid rgba(146, 162, 205, 0.45);
    border-bottom: 1px solid #ffffff;
    padding: 7px 16px 5px;
}
QPushButton:default {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7d99ff, stop:0.5 #5f7cf9, stop:1 #4a63f0);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-top: 1px solid rgba(255, 255, 255, 0.75);
    border-bottom: 1px solid rgba(48, 66, 168, 0.6);
    color: #ffffff; font-weight: 600;
}
QPushButton:default:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8ea6ff, stop:0.5 #6e89fb, stop:1 #5670f3);
    color: #ffffff;
}
QPushButton:default:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #5670f3, stop:1 #4459de);
}

#bodyHost {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #d5dfff, stop:0.45 #e6ecfb, stop:1 #ede3f5);
}
#sideOverlay {
    background: transparent;
    border: none;
}
#sideClip, #sideClipView {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(240, 244, 255, 0.94), stop:1 rgba(230, 236, 252, 0.86));
    border: none;
}
#sideClip {
    border-right: 1px solid rgba(146, 162, 205, 0.34);
}
#sidePanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.88), stop:1 rgba(244, 247, 255, 0.76));
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.34);
    border-radius: 18px;
}
#sideHead {
    color: #7a84a2; font-size: 12px; padding: 10px 12px 4px;
}
#sessionTree, #subjectTree {
    background: transparent; border: none;
    font-size: 13px; outline: 0;
    show-decoration-selected: 0;
}
#sessionTree::item, #subjectTree::item {
    padding: 2px 4px;
    color: #2c3345;
    background: transparent;
    border: none;
}
#sessionTree::item:hover,
#sessionTree::item:selected,
#sessionTree::item:selected:active,
#sessionTree::item:selected:!active,
#subjectTree::item:hover,
#subjectTree::item:selected,
#subjectTree::item:selected:active,
#subjectTree::item:selected:!active {
    background: transparent;
    border: none;
}
#sessionTree::item:selected, #subjectTree::item:selected {
    color: #4a63f0;
    font-weight: bold;
}
#sessionTree::branch,
#sessionTree::branch:hover,
#sessionTree::branch:selected,
#sessionTree::branch:has-siblings,
#sessionTree::branch:has-siblings:adjoins-item,
#sessionTree::branch:!has-children:!has-siblings:adjoins-item,
#sessionTree::branch:has-children:!has-siblings:closed,
#sessionTree::branch:closed:has-children:has-siblings,
#sessionTree::branch:open:has-children:!has-siblings,
#sessionTree::branch:open:has-children:has-siblings,
#subjectTree::branch,
#subjectTree::branch:hover,
#subjectTree::branch:selected,
#subjectTree::branch:has-siblings,
#subjectTree::branch:has-siblings:adjoins-item,
#subjectTree::branch:!has-children:!has-siblings:adjoins-item,
#subjectTree::branch:has-children:!has-siblings:closed,
#subjectTree::branch:closed:has-children:has-siblings,
#subjectTree::branch:open:has-children:!has-siblings,
#subjectTree::branch:open:has-children:has-siblings {
    background: transparent;
    border: none;
    image: none;
    border-image: none;
}
#sideToggle {
    background: transparent; border: none;
    padding: 4px 10px; color: #6b779a; font-size: 12px;
    border-radius: 10px;
}
#sideToggle:hover { background: rgba(255, 255, 255, 0.9); color: #4a63f0; }
#sideRail {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 255, 255, 0.8), stop:1 rgba(242, 246, 255, 0.66));
    border: 1px solid rgba(255, 255, 255, 0.9);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.32);
    border-radius: 16px;
}
#sideRailBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.9), stop:1 rgba(240, 244, 255, 0.76));
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.4);
    border-radius: 12px;
    padding: 12px 4px;
    color: #4a63f0; font-size: 12px;
}

QLineEdit {
    background: rgba(255, 255, 255, 0.86);
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid rgba(150, 166, 208, 0.4);
    border-bottom: 1px solid #ffffff;
    border-radius: 15px; padding: 6px 14px;
    font-size: 12.5px; color: #3a4152;
}
QLineEdit:focus {
    border: 1px solid rgba(79, 110, 247, 0.42);
    border-top: 1px solid rgba(79, 110, 247, 0.6);
    background: #ffffff;
}

QStatusBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(238, 242, 253, 0.7), stop:1 rgba(255, 255, 255, 0.86));
    border-top: 1px solid #ffffff;
}
QStatusBar QLabel { color: #7a84a2; font-size: 12px; }
QSplitter::handle { background: transparent; }

QMenu {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.97), stop:1 rgba(240, 244, 255, 0.93));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.45);
    border-radius: 12px; padding: 6px;
}
QMenu::item {
    padding: 6px 24px; border-radius: 7px; color: #3a4152;
}
QMenu::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(120, 148, 255, 0.28), stop:1 rgba(79, 110, 247, 0.2));
    color: #2b3776;
}
QMenu::item:checked { font-weight: 600; color: #4a63f0; }
QMenu::separator {
    height: 1px; background: rgba(146, 162, 205, 0.45); margin: 4px 8px;
}

#matchColorPopup {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.96), stop:1 rgba(240, 244, 255, 0.9));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.45);
    border-radius: 14px;
}
#matchColorCaption {
    color: #8b94ad; font-size: 12px; font-weight: 600;
    padding: 2px 4px 4px;
}
#matchColorBtn {
    text-align: left;
    padding: 7px 14px;
    border-radius: 9px;
}
#matchColorClear {
    text-align: left;
    padding: 7px 14px;
    color: #6b75d8;
}

#todoDivider {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255, 255, 255, 0),
        stop:0.5 rgba(255, 255, 255, 0.55),
        stop:1 rgba(255, 255, 255, 0));
    border: none;
    min-width: 8px; max-width: 8px;
}
#todoDock {
    background: transparent;
    border: none;
}
#todoGlass {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.9), stop:1 rgba(242, 246, 255, 0.78));
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.36);
    border-radius: 18px;
}
#todoTitle {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(240, 244, 255, 0.78));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.32);
    border-radius: 999px;
    color: #737d9c; font-size: 12px; font-weight: 600;
    padding: 5px 16px;
}
#todoHint {
    color: #8b94ad; font-size: 11px; padding: 0 2px;
    background: transparent;
}
#todoEmpty {
    color: #8b94ad; font-size: 12px; padding: 28px 8px;
    background: transparent;
}
#todoScroll, #todoList { background: transparent; border: none; }
#todoInput {
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid rgba(150, 166, 208, 0.4);
    border-bottom: 1px solid #ffffff;
    border-radius: 15px; padding: 6px 12px;
    font-size: 12.5px; color: #3a4152;
}
#todoInput:focus {
    border: 1px solid rgba(79, 110, 247, 0.45);
    border-top: 1px solid rgba(79, 110, 247, 0.6);
    background: #ffffff;
}
#todoAdd {
    width: 30px; height: 30px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7d99ff, stop:0.5 #5f7cf9, stop:1 #4a63f0);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-top: 1px solid rgba(255, 255, 255, 0.75);
    border-bottom: 1px solid rgba(48, 66, 168, 0.6);
    border-radius: 15px;
    color: #ffffff; font-size: 18px; font-weight: 600;
    padding: 0;
}
#todoAdd:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8ea6ff, stop:0.5 #6e89fb, stop:1 #5670f3);
}
#todoAdd:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #5670f3, stop:1 #4459de);
}
#todoGroup {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.8), stop:1 rgba(244, 247, 255, 0.66));
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.3);
    border-radius: 16px;
}
#todoRow {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.92), stop:1 rgba(243, 246, 255, 0.8));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.36);
    border-radius: 14px;
}
#todoRow:hover {
    background: #ffffff;
}
#todoRow[done="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.62), stop:1 rgba(242, 245, 253, 0.5));
    border: 1px solid rgba(255, 255, 255, 0.72);
    border-bottom: 1px solid rgba(146, 162, 205, 0.22);
}
#todoRowInner {
    background: transparent;
    border: none;
    border-radius: 10px;
}
#todoRowInner:hover {
    background: rgba(255, 255, 255, 0.75);
}
#todoRowInner[done="true"] {
    background: transparent;
    border: none;
}
#todoSection { background: transparent; }
#todoDoneHead {
    color: #7a84a2; font-size: 11px; font-weight: 600;
    padding: 3px 12px; margin: 4px 20px 0;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.82), stop:1 rgba(242, 246, 255, 0.7));
    border: 1px solid rgba(255, 255, 255, 0.9);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.3);
    border-radius: 999px;
}
#todoText { color: #2c3345; font-size: 13px; background: transparent; }
#todoRow[done="true"] #todoText,
#todoRowInner[done="true"] #todoText { color: #8b94ad; }
#todoNote {
    color: #656e88; font-size: 11px;
    background: rgba(255, 255, 255, 0.86);
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid rgba(150, 166, 208, 0.34);
    border-bottom: 1px solid #ffffff;
    border-radius: 10px;
    padding: 6px 9px;
}
#todoRow[done="true"] #todoNote,
#todoRowInner[done="true"] #todoNote {
    color: #9aa2b6;
    background: rgba(255, 255, 255, 0.58);
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-top: 1px solid rgba(150, 166, 208, 0.24);
}
#todoNoteEdit {
    background: #ffffff;
    border: 1px solid rgba(79, 110, 247, 0.32);
    border-top: 1px solid rgba(79, 110, 247, 0.5);
    border-radius: 10px; padding: 6px 9px;
    font-size: 11px; color: #3a4152;
}
#todoMark {
    font-size: 10px; font-weight: 600;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.32);
}
#todoMark[kind="later"] {
    color: #a85200;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 191, 122, 0.85), stop:1 rgba(255, 160, 72, 0.7));
    border-color: rgba(255, 255, 255, 0.8);
    border-bottom-color: rgba(188, 110, 40, 0.4);
}
#todoMark[kind="skip"] {
    color: #615866;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(226, 221, 233, 0.9), stop:1 rgba(196, 189, 205, 0.78));
    border-color: rgba(255, 255, 255, 0.8);
    border-bottom-color: rgba(140, 132, 150, 0.38);
}
#todoRow[mark="skip"] #todoText,
#todoRowInner[mark="skip"] #todoText { color: #8b94ad; }
#todoRow[mark="skip"] #todoNote,
#todoRowInner[mark="skip"] #todoNote { color: #a0a6b8; }
#todoDate {
    font-size: 12px; font-weight: 600;
    padding: 6px 10px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.34);
}
#todoDate[tone="orange"] {
    color: #a85200;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 186, 116, 0.72), stop:1 rgba(255, 154, 61, 0.56));
    border-bottom-color: rgba(188, 110, 40, 0.38);
}
#todoDate[tone="pink"] {
    color: #b5406c;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 205, 220, 0.78), stop:1 rgba(255, 178, 202, 0.62));
    border-bottom-color: rgba(190, 110, 140, 0.34);
}
#todoDate[tone="blue"] {
    color: #245296;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(196, 221, 255, 0.82), stop:1 rgba(164, 200, 255, 0.64));
    border-bottom-color: rgba(96, 134, 196, 0.36);
}
#todoDate[tone="gray"] {
    color: #515868;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(212, 217, 226, 0.82), stop:1 rgba(186, 192, 204, 0.64));
    border-bottom-color: rgba(130, 138, 152, 0.36);
}
#todoDate[tone="purple"] {
    color: #62419b;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(223, 209, 250, 0.82), stop:1 rgba(200, 180, 240, 0.64));
    border-bottom-color: rgba(140, 112, 190, 0.36);
}
#todoRow[done="true"] #todoDate {
    color: #8b94ad;
    background: rgba(255, 255, 255, 0.55);
    border-bottom-color: rgba(146, 162, 205, 0.22);
}
QToolButton::menu-indicator { image: none; width: 0; height: 0; }
#todoCheck {
    min-width: 22px; max-width: 22px;
    width: 22px; height: 22px;
    background: rgba(255, 255, 255, 0.92);
    border: 1.5px solid rgba(130, 145, 190, 0.5);
    border-radius: 11px;
    color: #ffffff; font-size: 12px; font-weight: 700;
    padding: 0;
}
#todoCheck:hover {
    border-color: rgba(74, 99, 240, 0.6);
    background: #ffffff;
}
#todoCheck:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7d99ff, stop:0.5 #5f7cf9, stop:1 #4a63f0);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-top: 1px solid rgba(255, 255, 255, 0.75);
    border-bottom: 1px solid rgba(48, 66, 168, 0.6);
    color: #ffffff;
}
#todoDelete {
    background: transparent; border: none;
    color: #a8b0c6; font-size: 15px; padding: 2px 6px;
    border-radius: 10px;
}
#todoDelete:hover {
    color: #e5484d;
    background: rgba(229, 72, 77, 0.12);
}
#stashCopy {
    background: transparent; border: none;
    color: #5b6aa8; font-size: 11px; padding: 2px 6px;
    border-radius: 8px;
}
#stashCopy:hover {
    color: #4a63f0;
    background: rgba(79, 110, 247, 0.12);
}
#stashSplit::handle {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0),
        stop:0.5 rgba(255, 255, 255, 0.55),
        stop:1 rgba(255, 255, 255, 0));
}
#stashBar { background: transparent; border: none; }
#stashNav {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.9), stop:1 rgba(242, 246, 255, 0.78));
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.36);
    border-radius: 18px;
}
#stashNavBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    color: #5a647c;
    font-size: 12.5px;
    font-weight: 600;
    padding: 4px 6px;
}
#stashNavBtn:hover {
    background: rgba(255, 255, 255, 0.85);
    color: #3a4152;
}
#stashNavBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffffff, stop:1 rgba(240, 244, 255, 0.88));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.4);
    color: #4a63f0;
}

QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical {
    background: rgba(122, 138, 185, 0.5);
    border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(110, 126, 175, 0.75); }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: rgba(122, 138, 185, 0.5);
    border-radius: 4px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: rgba(110, 126, 175, 0.75); }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QToolTip {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(48, 53, 72, 0.97), stop:1 rgba(33, 37, 52, 0.97));
    color: #eef1fb;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-top: 1px solid rgba(255, 255, 255, 0.3);
    padding: 5px 9px;
}
#sessionNoteTip {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(48, 53, 72, 0.96), stop:1 rgba(33, 37, 52, 0.96));
    color: #eef1fb;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-top: 1px solid rgba(255, 255, 255, 0.32);
    border-bottom: 1px solid rgba(0, 0, 0, 0.35);
    padding: 6px 10px;
    border-radius: 10px; font-size: 12px;
}

QCheckBox {
    color: #3a4152; font-size: 13px; spacing: 8px;
    background: transparent;
}
QCheckBox::indicator { width: 17px; height: 17px; }
#settingsCaption {
    color: #8b94ad; font-size: 12px; font-weight: 600;
}

#importHint {
    color: #656e88; font-size: 12px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.8), stop:1 rgba(243, 246, 255, 0.64));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.28);
    border-radius: 14px;
    padding: 9px 15px;
}
#importTableWrap {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.84), stop:1 rgba(246, 249, 255, 0.72));
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid rgba(146, 162, 205, 0.34);
    border-radius: 16px;
}
#importTable {
    background: transparent;
    border: none;
    outline: 0;
    font-size: 12.5px;
    color: #2c3345;
    selection-color: #33408f;
    selection-background-color: rgba(150, 175, 255, 0.34);
}
#importTable::item {
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid rgba(150, 168, 210, 0.22);
    background: transparent;
}
#importTable::item:hover { background: rgba(255, 255, 255, 0.82); }
#importTable::item:selected,
#importTable::item:selected:active,
#importTable::item:selected:!active {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(148, 174, 255, 0.55), stop:1 rgba(103, 133, 245, 0.42));
    color: #2b3776;
}
#importTable QHeaderView { background: transparent; }
#importTable QHeaderView::section {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.96), stop:1 rgba(238, 243, 255, 0.82));
    border: none;
    border-bottom: 1px solid rgba(146, 162, 205, 0.36);
    color: #737d9c; font-size: 12px; font-weight: 600;
    padding: 8px 10px;
}
#importTable QHeaderView::section:first { border-top-left-radius: 11px; }
#importTable QHeaderView::section:last { border-top-right-radius: 11px; }
#importTable QTableCornerButton::section {
    background: transparent; border: none;
}
"""

