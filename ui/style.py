"""应用级样式表（液态玻璃风）。"""

# 应用级样式表（液态玻璃风）：在 main.py 里通过 app.setStyleSheet 应用，
# 这样托盘菜单、对话框等独立窗口也能吃到同一套风格。
APP_QSS = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #e7ebfa, stop:0.45 #edeffb, stop:1 #e2eef5);
}
QDialog { background: #edf0fa; }
QLabel { background: transparent; color: #3a4152; }

QToolBar {
    background: rgba(255, 255, 255, 0.5);
    border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.75);
    padding: 8px 10px; spacing: 4px;
}
QToolBar QToolButton {
    background: transparent; padding: 6px 14px;
    border-radius: 10px; color: #3d4459; font-size: 12.5px;
}
QToolBar QToolButton:hover { background: rgba(255, 255, 255, 0.85); }
QToolBar QToolButton:pressed { background: rgba(255, 255, 255, 0.95); }
QToolBar QToolButton:checked {
    background: rgba(255, 122, 84, 0.22); color: #cf4f2e;
}
#autoBackupHint {
    color: #6a738c; font-size: 11.5px;
    padding: 0 12px 0 8px;
}

QPushButton {
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid rgba(165, 175, 205, 0.55);
    border-radius: 9px; padding: 5px 16px; color: #3a4152;
}
QPushButton:hover { background: #ffffff; }
QPushButton:default {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6d8cff, stop:1 #4f6ef7);
    border: none; color: #ffffff;
}
QPushButton:default:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7d99ff, stop:1 #5f7cf9);
}

#bodyHost { background: #edeffb; }
#sideOverlay {
    background: transparent;
    border: none;
}
#sideClip, #sideClipView {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(237, 239, 251, 0.96), stop:1 rgba(232, 236, 250, 0.90));
    border: none;
}
#sideClip {
    border-right: 1px solid rgba(255, 255, 255, 0.92);
}
#sidePanel {
    background: rgba(255, 255, 255, 0.42);
    border: 1px solid rgba(255, 255, 255, 0.65);
    border-radius: 16px;
}
#sideHead {
    color: #8b94ad; font-size: 12px; padding: 10px 12px 4px;
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
#sideToggle:hover { background: rgba(255, 255, 255, 0.7); color: #4a63f0; }
#sideRail {
    background: rgba(255, 255, 255, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 16px;
}
#sideRailBtn {
    background: rgba(255, 255, 255, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-radius: 12px;
    padding: 12px 4px;
    color: #4a63f0; font-size: 12px;
}

QLineEdit {
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.75);
    border-radius: 15px; padding: 6px 14px;
    font-size: 12.5px; color: #3a4152;
}
QLineEdit:focus {
    border-color: rgba(79, 110, 247, 0.55);
    background: rgba(255, 255, 255, 0.9);
}

QStatusBar {
    background: rgba(255, 255, 255, 0.45);
    border-top: 1px solid rgba(255, 255, 255, 0.65);
}
QStatusBar QLabel { color: #8b94ad; font-size: 12px; }
QSplitter::handle { background: transparent; }

QMenu {
    background: rgba(250, 251, 255, 0.97);
    border: 1px solid rgba(200, 210, 235, 0.8);
    border-radius: 10px; padding: 5px;
}
QMenu::item {
    padding: 6px 24px; border-radius: 7px; color: #3a4152;
}
QMenu::item:selected { background: rgba(79, 110, 247, 0.14); }
QMenu::separator {
    height: 1px; background: rgba(160, 175, 210, 0.4); margin: 4px 8px;
}

#matchColorPopup {
    background: rgba(250, 251, 255, 0.97);
    border: 1px solid rgba(200, 210, 235, 0.85);
    border-radius: 12px;
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
    background: rgba(255, 255, 255, 0.42);
    border: 1px solid rgba(255, 255, 255, 0.68);
    border-top: 1px solid rgba(255, 255, 255, 0.92);
    border-radius: 16px;
}
#todoTitle {
    background: rgba(255, 255, 255, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 999px;
    color: #7a84a2; font-size: 12px; font-weight: 600;
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
    background: rgba(255, 255, 255, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.75);
    border-radius: 15px; padding: 6px 12px;
    font-size: 12.5px; color: #3a4152;
}
#todoInput:focus {
    border-color: rgba(79, 110, 247, 0.5);
    background: rgba(255, 255, 255, 0.88);
}
#todoAdd {
    width: 30px; height: 30px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(109, 140, 255, 0.88), stop:1 rgba(79, 110, 247, 0.82));
    border: 1px solid rgba(255, 255, 255, 0.45);
    border-radius: 15px;
    color: #ffffff; font-size: 18px; font-weight: 600;
    padding: 0;
}
#todoAdd:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(125, 153, 255, 0.95), stop:1 rgba(95, 124, 249, 0.9));
}
#todoAdd:pressed {
    background: rgba(74, 99, 240, 0.9);
}
#todoGroup {
    background: rgba(255, 255, 255, 0.42);
    border: 1px solid rgba(255, 255, 255, 0.78);
    border-top: 1px solid rgba(255, 255, 255, 0.95);
    border-radius: 16px;
}
#todoRow {
    background: rgba(255, 255, 255, 0.48);
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-top: 1px solid rgba(255, 255, 255, 0.95);
    border-radius: 14px;
}
#todoRow:hover {
    background: rgba(255, 255, 255, 0.7);
}
#todoRow[done="true"] {
    background: rgba(255, 255, 255, 0.28);
    border: 1px solid rgba(255, 255, 255, 0.5);
}
#todoRowInner {
    background: transparent;
    border: none;
    border-radius: 10px;
}
#todoRowInner:hover {
    background: rgba(255, 255, 255, 0.4);
}
#todoRowInner[done="true"] {
    background: transparent;
    border: none;
}
#todoSection { background: transparent; }
#todoDoneHead {
    color: #8b94ad; font-size: 11px; font-weight: 600;
    padding: 3px 12px; margin: 4px 20px 0;
    background: rgba(255, 255, 255, 0.38);
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 999px;
}
#todoText { color: #2c3345; font-size: 13px; background: transparent; }
#todoRow[done="true"] #todoText,
#todoRowInner[done="true"] #todoText { color: #8b94ad; }
#todoNote {
    color: #6a738c; font-size: 11px;
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.82);
    border-radius: 10px;
    padding: 6px 9px;
}
#todoRow[done="true"] #todoNote,
#todoRowInner[done="true"] #todoNote {
    color: #9aa2b6;
    background: rgba(255, 255, 255, 0.32);
    border: 1px solid rgba(255, 255, 255, 0.55);
}
#todoNoteEdit {
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid rgba(79, 110, 247, 0.32);
    border-radius: 10px; padding: 6px 9px;
    font-size: 11px; color: #3a4152;
}
#todoMark {
    font-size: 10px; font-weight: 600;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.72);
    border-top: 1px solid rgba(255, 255, 255, 0.95);
}
#todoMark[kind="later"] {
    color: #b85a00;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 186, 110, 0.5), stop:1 rgba(255, 154, 61, 0.32));
    border-color: rgba(255, 255, 255, 0.7);
}
#todoMark[kind="skip"] {
    color: #6a6170;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(220, 214, 228, 0.55), stop:1 rgba(186, 178, 196, 0.36));
    border-color: rgba(255, 255, 255, 0.7);
}
#todoRow[mark="skip"] #todoText,
#todoRowInner[mark="skip"] #todoText { color: #8b94ad; }
#todoRow[mark="skip"] #todoNote,
#todoRowInner[mark="skip"] #todoNote { color: #a0a6b8; }
#todoDate {
    font-size: 12px; font-weight: 600;
    padding: 6px 10px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-top: 1px solid rgba(255, 255, 255, 0.95);
}
#todoDate[tone="orange"] {
    color: #b85a00;
    background: rgba(255, 154, 61, 0.28);
    border-color: rgba(255, 255, 255, 0.55);
}
#todoDate[tone="pink"] {
    color: #c44d78;
    background: rgba(255, 194, 212, 0.32);
    border-color: rgba(255, 255, 255, 0.55);
}
#todoDate[tone="blue"] {
    color: #2a5cb8;
    background: rgba(180, 212, 255, 0.32);
    border-color: rgba(255, 255, 255, 0.55);
}
#todoDate[tone="gray"] {
    color: #5a6170;
    background: rgba(197, 202, 211, 0.32);
    border-color: rgba(255, 255, 255, 0.55);
}
#todoDate[tone="purple"] {
    color: #6d4aa8;
    background: rgba(212, 194, 245, 0.32);
    border-color: rgba(255, 255, 255, 0.55);
}
#todoRow[done="true"] #todoDate {
    color: #8b94ad;
    background: rgba(255, 255, 255, 0.22);
}
QToolButton::menu-indicator { image: none; width: 0; height: 0; }
#todoCheck {
    min-width: 22px; max-width: 22px;
    width: 22px; height: 22px;
    background: rgba(255, 255, 255, 0.55);
    border: 1.5px solid rgba(130, 145, 190, 0.45);
    border-radius: 11px;
    color: #ffffff; font-size: 12px; font-weight: 700;
    padding: 0;
}
#todoCheck:hover {
    border-color: rgba(74, 99, 240, 0.55);
    background: rgba(255, 255, 255, 0.85);
}
#todoCheck:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6d8cff, stop:1 #4f6ef7);
    border: 1px solid rgba(255, 255, 255, 0.4);
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
    background: rgba(255, 255, 255, 0.42);
    border: 1px solid rgba(255, 255, 255, 0.68);
    border-top: 1px solid rgba(255, 255, 255, 0.92);
    border-radius: 16px;
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
    background: rgba(255, 255, 255, 0.55);
    color: #3a4152;
}
#stashNavBtn:checked {
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.9);
    color: #4a63f0;
}

QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical {
    background: rgba(130, 145, 190, 0.4);
    border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(130, 145, 190, 0.65); }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: rgba(130, 145, 190, 0.4);
    border-radius: 4px; min-width: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QToolTip {
    background: rgba(40, 44, 60, 0.94); color: #eef1fb;
    border: none; padding: 5px 9px;
}

QCheckBox {
    color: #3a4152; font-size: 13px; spacing: 8px;
    background: transparent;
}
QCheckBox::indicator { width: 17px; height: 17px; }
#settingsCaption {
    color: #8b94ad; font-size: 12px; font-weight: 600;
}
"""

