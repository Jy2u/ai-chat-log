"""渲染层：Markdown 转 HTML、聊天页面模板（液态玻璃风格）、会话导出。"""

import html
import re
import shutil
from datetime import datetime
from pathlib import Path

from markdown_it import MarkdownIt
from pygments import highlight as pyg_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name

from db import DATA_DIR, IMAGES_DIR
from render_css import _CSS
from render_mindmap_js import _MM_JS

_VENDOR_KATEX = Path(__file__).resolve().parent / "vendor" / "katex"
_DATA_KATEX = Path(DATA_DIR) / "katex"

_formatter = HtmlFormatter(style="monokai", nowrap=True)

def _highlight(code: str, lang: str, attrs: str) -> str:
    lang = (lang or "").strip()
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        lexer = TextLexer()
    body = pyg_highlight(code, lexer, _formatter)
    label = html.escape(lang) if lang else "text"
    return (
        f'<pre class="codeblock" data-lang="{label}">'
        f"<code>{body}</code></pre>"
    )


# html=False：粘贴内容里的原始 HTML 一律按文本转义显示，避免页面被打乱
_md = MarkdownIt(
    "commonmark",
    {"html": False, "breaks": True, "highlight": _highlight},
).enable("table").enable("strikethrough")


_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_DISPLAY_DOLLAR_RE = re.compile(r"\$\$([\s\S]+?)\$\$")
_DISPLAY_BRACKET_TEX_RE = re.compile(r"\\\[([\s\S]+?)\\\]")
_INLINE_PAREN_RE = re.compile(r"\\\(([\s\S]+?)\\\)")
_INLINE_DOLLAR_RE = re.compile(
    r"(?<![A-Za-z0-9\\])\$(?!\$)((?:[^$\n\\]|\\.)+?)\$(?![A-Za-z0-9])"
)
_BRACKET_BLOCK_RE = re.compile(
    r"^[ \t]*\[[ \t]*\r?\n"
    r"([^\n]*(?:\r?\n[^\n]+){0,12})\r?\n"
    r"[ \t]*\][ \t]*$",
    re.MULTILINE,
)


def _looks_like_latex(src: str) -> bool:
    """单独成行的 [ ... ] 既可能是公式，也可能是普通列表，用形态粗筛。"""
    s = src.strip()
    if not s or len(s) > 4000:
        return False
    if re.search(r"\\[a-zA-Z]+", s):
        return True
    if re.search(r"[_^]", s) and re.search(r"[=<>+\-*/|]", s):
        return True
    if "|" in s and "=" in s:
        return True
    return False


def _stash_by_regex(pattern: re.Pattern, text: str, bucket: list, display: bool, pred=None):
    def repl(match):
        body = match.group(1)
        if pred is not None and not pred(body):
            return match.group(0)
        token = f"⟦MATH{len(bucket)}⟧"
        bucket.append((display, body))
        return token

    return pattern.sub(repl, text)


def _stash_code(text: str):
    codes = []

    def repl(match):
        token = f"⟦CODE{len(codes)}⟧"
        codes.append(match.group(0))
        return token

    text = _CODE_FENCE_RE.sub(repl, text)
    text = _INLINE_CODE_RE.sub(repl, text)
    return text, codes


def _unstash(text: str, items: list, kind: str):
    for i in range(len(items) - 1, -1, -1):
        text = text.replace(f"⟦{kind}{i}⟧", items[i])
    return text


def _extract_math(text: str):
    """先抽出公式，避免 Markdown 把 _, |, [] 拆掉。"""
    maths = []
    text, codes = _stash_code(text)
    text = _stash_by_regex(_DISPLAY_DOLLAR_RE, text, maths, True)
    text = _stash_by_regex(_DISPLAY_BRACKET_TEX_RE, text, maths, True)
    text = _stash_by_regex(
        _BRACKET_BLOCK_RE, text, maths, True, pred=_looks_like_latex
    )
    text = _stash_by_regex(_INLINE_PAREN_RE, text, maths, False)
    text = _stash_by_regex(_INLINE_DOLLAR_RE, text, maths, False)
    text = _unstash(text, codes, "CODE")
    return text, maths


def _math_html(latex: str, display: bool) -> str:
    cls = "tex-display" if display else "tex-inline"
    return f'<span class="{cls}">{html.escape(latex.strip())}</span>'


def _restore_math(html_out: str, maths: list) -> str:
    for i in range(len(maths) - 1, -1, -1):
        display, latex = maths[i]
        token = f"⟦MATH{i}⟧"
        snippet = _math_html(latex, display)
        if display:
            html_out = html_out.replace(f"<p>{token}</p>", snippet)
        html_out = html_out.replace(token, snippet)
    return html_out


def md_to_html(text: str) -> str:
    from render_canvas import try_canvas_html

    canvas = try_canvas_html(text)
    if canvas:
        return canvas
    text, maths = _extract_math(text)
    return _restore_math(_md.render(text), maths)


def _node_is_prose(text: str) -> bool:
    """多行或较长的节点用左对齐，短标题才居中。"""
    raw = (text or "").rstrip()
    if not raw:
        return False
    if "\n" in raw:
        return True
    return len(raw) > 32


def node_content_html(text: str) -> str:
    """导图节点：转义正文，并把 \\( \\) / $ 公式变成 KaTeX 占位。"""
    raw = text or ""
    if not raw:
        return ""
    extracted, maths = _extract_math(raw)
    return _restore_math(html.escape(extracted), maths)


def _attr_nl(text: str) -> str:
    """写入 HTML 属性时保留换行（浏览器会把属性里的真换行吃掉）。"""
    return html.escape(text or "", quote=True).replace("\n", "&#10;")


def fmt_time(created_at: str) -> str:
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return created_at
    if dt.date() == datetime.now().date():
        return dt.strftime("%H:%M")
    return dt.strftime("%Y-%m-%d %H:%M")


def _ensure_katex_assets() -> bool:
    """把 KaTeX 拷到 data/katex/，与 view.html 同目录，避免 file:// 跨目录限制。"""
    src_js = _VENDOR_KATEX / "katex.min.js"
    src_css = _VENDOR_KATEX / "katex.min.css"
    src_fonts = _VENDOR_KATEX / "fonts"
    if not (src_js.is_file() and src_css.is_file() and src_fonts.is_dir()):
        return False
    dest = _DATA_KATEX
    dest_fonts = dest / "fonts"
    dest_js = dest / "katex.min.js"
    if dest_js.is_file() and dest_js.stat().st_mtime >= src_js.stat().st_mtime:
        return True
    dest.mkdir(parents=True, exist_ok=True)
    dest_fonts.mkdir(parents=True, exist_ok=True)
    for name in ("katex.min.js", "katex.min.css"):
        shutil.copy2(_VENDOR_KATEX / name, dest / name)
    for font in src_fonts.glob("*.woff2"):
        shutil.copy2(font, dest_fonts / font.name)
    return True


def _page(body: str, scroll_bottom: bool, wide: bool = False, extra_js: str = "") -> str:
    katex_ok = _ensure_katex_assets()
    katex_head = (
        '<link rel="stylesheet" href="katex/katex.min.css">\n'
        if katex_ok
        else ""
    )
    scroll = (
        "window.scrollTo(0, document.body.scrollHeight);"
        if scroll_bottom
        else ""
    )
    katex_js = (
        """
<script src="katex/katex.min.js"></script>
<script>
(function () {
    if (!window.katex) return;
    document.querySelectorAll(".tex-display, .tex-inline").forEach(function (el) {
        katex.render(el.textContent, el, {
            displayMode: el.classList.contains("tex-display"),
            throwOnError: false
        });
    });
})();
</script>
"""
        if katex_ok
        else ""
    )
    wrap_cls = "wrap wrap-wide" if wide else "wrap"
    bridge = r"""
<script>
window.appCall = function (url) {
    var f = document.getElementById("__appBridge");
    if (!f) {
        f = document.createElement("iframe");
        f.id = "__appBridge";
        f.setAttribute("aria-hidden", "true");
        f.style.cssText = "position:fixed;left:0;top:0;width:0;height:0;border:0;opacity:0;pointer-events:none";
        document.documentElement.appendChild(f);
    }
    var hash = url.indexOf("#");
    var stamp = "_=" + Date.now();
    if (hash < 0) {
        url += (url.indexOf("?") >= 0 ? "&" : "?") + stamp;
    } else {
        var base = url.slice(0, hash);
        url = base + (base.indexOf("?") >= 0 ? "&" : "?") + stamp + url.slice(hash);
    }
    f.src = url;
};
document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a");
    if (!a) return;
    var href = a.getAttribute("href") || "";
    if (href.indexOf("app://") === 0) {
        e.preventDefault();
        window.appCall(href);
    }
}, true);
</script>
"""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{_CSS}</style>
{katex_head}</head>
<body>
<div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>
<div class="{wrap_cls}">{body}</div>
{katex_js}<script>{scroll}</script>
{bridge}
{f"<script>{extra_js}</script>" if extra_js else ""}
</body></html>"""


def _image_uri(msg: dict) -> str:
    return Path(IMAGES_DIR, msg["content"]).as_uri()


def _message_html(msg: dict, ops: bool = True, extra_meta: str = "") -> str:
    role = msg["role"]
    is_image = msg.get("kind") == "image"
    role_name = "我" if role == "user" else "AI"
    flip_text = "改为回答" if role == "user" else "改为提问"
    copy_text = "复制图片" if is_image else "复制原文"
    ops_html = ""
    if ops:
        ops_html = (
            f'<span class="ops">'
            f'<a href="app://copy/{msg["id"]}">{copy_text}</a>'
            f'<a href="app://flip/{msg["id"]}">{flip_text}</a>'
            f'<a class="danger" href="app://del/{msg["id"]}">删除</a>'
            f"</span>"
        )
    if is_image:
        uri = _image_uri(msg)
        bubble_cls = "bubble image-bubble"
        body = (
            f'<a href="{uri}" title="点击用系统看图工具打开">'
            f'<img class="msg-img" src="{uri}" alt="图片"></a>'
        )
    else:
        from render_canvas import is_canvas_source

        bubble_cls = "bubble canvas-bubble" if is_canvas_source(msg["content"]) else "bubble"
        body = md_to_html(msg["content"])
    return (
        f'<div class="msg {role}" id="msg-{msg["id"]}">'
        f'<div class="meta"><span class="role">{role_name}</span>'
        f" · {fmt_time(msg['created_at'])}{extra_meta}{ops_html}</div>"
        f'<div class="{bubble_cls}">{body}</div>'
        f"</div>"
    )


def _msg_nav_preview(msg: dict, limit: int = 42) -> str:
    if msg.get("kind") == "image":
        return "图片"
    text = re.sub(r"\s+", " ", msg.get("content") or "").strip()
    text = re.sub(r"^[#>*`\-\s]+", "", text)
    if not text:
        return "（空）"
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


_CHAT_NAV_JS = r"""
(function () {
    document.documentElement.classList.add("chat-ui");
    var items = [].slice.call(document.querySelectorAll(".chat-nav-item"));
    if (!items.length) return;
    var msgs = items.map(function (a) {
        return document.getElementById((a.getAttribute("href") || "").slice(1));
    });
    function sync() {
        var y = window.scrollY + Math.max(80, window.innerHeight * 0.18);
        var cur = 0;
        for (var i = 0; i < msgs.length; i++) {
            if (msgs[i] && msgs[i].offsetTop <= y) cur = i;
        }
        items.forEach(function (a, i) { a.classList.toggle("on", i === cur); });
        var on = items[cur];
        if (on && on.scrollIntoView) {
            var box = on.parentElement;
            if (box && box.classList.contains("chat-nav-list")) {
                var top = on.offsetTop - box.clientHeight / 2 + on.offsetHeight / 2;
                if (Math.abs(box.scrollTop - top) > 24) box.scrollTop = top;
            }
        }
    }
    items.forEach(function (a) {
        a.addEventListener("click", function (e) {
            e.preventDefault();
            var el = document.getElementById((a.getAttribute("href") || "").slice(1));
            if (!el) return;
            el.scrollIntoView({ behavior: "smooth", block: "start" });
            el.classList.add("flash");
            setTimeout(function () { el.classList.remove("flash"); }, 1200);
        });
    });
    window.addEventListener("scroll", sync, { passive: true });
    sync();
})();
"""

_JUMP_MSG_JS = r"""
(function (id) {
    function go() {
        var el = id ? document.getElementById("msg-" + id) : null;
        if (el) {
            el.scrollIntoView({ block: "center" });
            el.classList.add("flash");
            return;
        }
        var y = Math.max(
            document.body.scrollHeight,
            document.documentElement.scrollHeight
        );
        window.scrollTo(0, y);
    }
    go();
    window.addEventListener("load", go);
    setTimeout(go, 80);
    setTimeout(go, 280);
})(%d);
"""


def _chat_nav_html(messages: list) -> str:
    questions = [m for m in messages if m.get("role") == "user"]
    if not questions:
        return ""
    items = []
    for i, m in enumerate(questions, 1):
        preview = html.escape(_msg_nav_preview(m))
        items.append(
            f'<a class="chat-nav-item" href="#msg-{m["id"]}">'
            f'<span class="chat-nav-num">{i}</span>'
            f'<span class="chat-nav-text">{preview}</span></a>'
        )
    return (
        '<nav class="chat-nav" aria-label="提问目录">'
        '<div class="chat-nav-title">提问</div>'
        f'<div class="chat-nav-list">{"".join(items)}</div></nav>'
    )


def build_chat_page(session: dict, messages: list, highlight_id=None) -> str:
    if not messages:
        body = (
            '<div class="empty"><div class="big">&#128172;</div>'
            "复制任意文字后，在弹出的悬浮条上<br>"
            "点「提问」或「回答」，记录就会出现在这里</div>"
        )
        return _page(body, scroll_bottom=False)

    head = (
        '<div class="page-head"><span>'
        f'会话「{html.escape(session["name"])}」'
        f" · 创建于 {session['created_at']}"
        f" · {len(messages)} 条记录</span></div>"
    )
    body = head + "".join(_message_html(m) for m in messages) + _chat_nav_html(messages)
    extra = _CHAT_NAV_JS
    if highlight_id:
        extra += _JUMP_MSG_JS % int(highlight_id)
    return _page(body, scroll_bottom=True, extra_js=extra)


def build_search_page(keyword: str, results: list) -> str:
    head = (
        '<div class="search-head"><span>'
        f"搜索「{html.escape(keyword)}」，共 {len(results)} 条结果"
        "（点击消息上方会话名可跳转）</span></div>"
    )
    if not results:
        body = head + '<div class="empty">没有找到相关记录</div>'
        return _page(body, scroll_bottom=False)

    parts = [head]
    for m in results:
        tag = (
            f'<div class="session-tag">来自 '
            f'<a href="app://goto/{m["session_id"]}">'
            f"会话「{html.escape(m['session_name'])}」</a></div>"
        )
        parts.append(tag + _message_html(m, ops=False))
    return _page("".join(parts), scroll_bottom=False)


_TRASH_KIND = {
    "subject": "课题",
    "folder": "文件夹",
    "session": "会话",
    "mindmap": "思维导图",
    "document": "文档",
}


def build_trash_page(items: list) -> str:
    n = len(items)
    head = (
        '<div class="search-head"><span>'
        f"回收站 · {n} 项"
        "（恢复后回到原来的位置；彻底删除不可恢复）</span></div>"
    )
    bar = (
        '<div class="trash-bar">'
        '<a class="danger" href="app://emptytrash/0">清空回收站</a>'
        "</div>"
    )
    if not items:
        body = (
            head
            + '<div class="empty"><div class="big">&#128465;</div>'
            "回收站是空的<br>删除的课题、会话、文件夹、思维导图和文档会出现在这里</div>"
        )
        return _page(body, scroll_bottom=False)

    parts = [head, bar]
    for it in items:
        kind = it["kind"]
        kind_name = _TRASH_KIND.get(kind, kind)
        loc = []
        if kind != "subject":
            loc.append(f"课题「{it.get('subject_name') or '未分组'}」")
        if it.get("folder_name"):
            loc.append(f"文件夹「{it['folder_name']}」")
        if it.get("session_name"):
            loc.append(f"会话「{it['session_name']}」")
        extra = it.get("extra") or 0
        if kind in ("folder", "subject"):
            detail = f"{extra} 个会话"
        elif kind == "session":
            detail = f"{extra} 条记录"
        else:
            detail = kind_name
        when = html.escape(it.get("deleted_at") or "")
        iid = it["id"]
        loc_html = (
            html.escape(" · ".join(loc)) + " · " if loc else ""
        )
        parts.append(
            '<div class="trash-item">'
            f'<div class="meta"><span class="kind">{html.escape(kind_name)}</span>'
            f'<div class="name">{html.escape(it.get("name") or "未命名")}</div>'
            f'<div class="sub">{loc_html}'
            f"{html.escape(detail)} · 删除于 {when}</div></div>"
            f'<span class="trash-ops">'
            f'<a href="app://restore/{iid}#{kind}">恢复</a>'
            f'<a class="danger" href="app://purge/{iid}#{kind}">彻底删除</a>'
            f"</span></div>"
        )
    return _page("".join(parts), scroll_bottom=False)


def _mindmap_forest(nodes: list):
    by_parent = {}
    for n in nodes:
        key = n["parent_id"]
        by_parent.setdefault(key, []).append(dict(n, children=[]))
    for kids in by_parent.values():
        kids.sort(key=lambda c: (c.get("sort_order") or 0, c["id"]))

    def attach(node):
        node["children"] = [
            attach(c) for c in by_parent.get(node["id"], [])
        ]
        return node

    return [attach(r) for r in by_parent.get(None) or []]


def _mm_char_units(text: str) -> float:
    """中文约 1 宽，西文约半宽，用来估换行。"""
    u = 0.0
    for ch in text:
        o = ord(ch)
        if o <= 32:
            u += 0.4
        elif o < 127:
            u += 0.58
        else:
            u += 1.0
    return u


def _mm_node_size(node):
    text = node.get("content") or ""
    is_text = node["kind"] == "text"
    pad_h = 18 if is_text else 32
    line_h = 20 if is_text else 22
    min_w = 140 if is_text else 168
    max_w = 300 if is_text else 280
    char_px = 14.0
    if not text.strip():
        w, h = min_w, pad_h + line_h
    else:
        paras = text.split("\n")
        longest = max(_mm_char_units(p) for p in paras)
        w = int(min(max_w, max(min_w, longest * char_px + 36)))
        cols = max(6.0, (w - 28) / char_px)
        lines = 0
        for para in paras:
            u = _mm_char_units(para)
            lines += max(1, int((u + cols - 1e-6) // cols))
        lines = min(max(lines, 1), 40)
        h = pad_h + lines * line_h
    bw, bh = node.get("box_w"), node.get("box_h")
    try:
        if bw is not None and float(bw) > 0:
            w = max(80, int(round(float(bw))))
    except (TypeError, ValueError):
        pass
    try:
        if bh is not None and float(bh) > 0:
            h = max(36, int(round(float(bh))))
    except (TypeError, ValueError):
        pass
    return w, h


def _has_pos(node) -> bool:
    return node.get("pos_x") is not None and node.get("pos_y") is not None


def prepare_mindmap_layout(nodes: list):
    """补齐缺失坐标，已有位置一律不动。返回 (flat, width, height, 新坐标)。"""
    roots = _mindmap_forest(nodes)
    if not roots:
        return [], 400, 240, []

    def collect(node, acc):
        acc.append(node)
        for child in node["children"]:
            collect(child, acc)
        return acc

    h_gap, v_gap = 56, 18
    laid = []
    newly = []
    extra_x = 0

    def visit(node, parent=None, index=0):
        w, h = _mm_node_size(node)
        node["w"], node["h"] = w, h
        if _has_pos(node):
            node["x"] = float(node["pos_x"])
            node["y"] = float(node["pos_y"])
        else:
            if parent is None:
                node["x"], node["y"] = 32 + extra_x, 32
            else:
                node["x"] = parent["x"] + parent["w"] + h_gap
                prevs = parent["children"][:index]
                if prevs:
                    last = prevs[-1]
                    node["y"] = last["y"] + last["h"] + v_gap
                else:
                    node["y"] = parent["y"]
            newly.append(node)
        for i, child in enumerate(node["children"]):
            visit(child, node, i)

    for root in roots:
        visit(root)
        chunk = collect(root, [])
        laid.extend(chunk)
        extra_x = max(extra_x, max(n["x"] + n["w"] for n in chunk) + 40)
    pad = 32
    width = max(n["x"] + n["w"] for n in laid) + pad
    height = max(n["y"] + n["h"] for n in laid) + pad
    return laid, width, height, newly


def build_mindmap_page(mindmap: dict, nodes: list, view=None, edges=None):
    hint = (
        '<div class="mm-hint">右键空白：新建独立子框 / 子句 ·'
        " 单击单元：四角拖动改大小，两端连接点可连线 ·"
        " 右键节点：新建 / 高亮 / 删除 · 右键连线：插入节点、标注或删除连线 ·"
        " 左键点连线可选中拖端点 · 双击编辑 · 长按拖动节点 ·"
        " 中键拖动框选（框到的单元和连线都会选中，可一起拖动） ·"
        " 拖动空白处移动画布 · Ctrl+滚轮缩放</div>"
    )
    laid, width, height, newly = prepare_mindmap_layout(nodes)
    if not laid:
        return _page(
            hint + '<div class="empty">这张导图还没有节点</div>', False, True
        ), None

    paths = []
    labels = []
    by_id = {n["id"]: n for n in laid}
    edge_list = edges if edges is not None else [
        {
            "id": n["id"],
            "from_id": n["parent_id"],
            "to_id": n["id"],
            "label": n.get("edge_label") or "",
        }
        for n in laid
        if n.get("parent_id") is not None and n["parent_id"] in by_id
    ]
    for e in edge_list:
        p = by_id.get(e["from_id"])
        n = by_id.get(e["to_id"])
        if not p or not n:
            continue
        x1 = p["x"] + p["w"]
        y1 = p["y"] + p["h"] / 2
        x2 = n["x"]
        y2 = n["y"] + n["h"] / 2
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        d = (
            f"M {x1:.1f} {y1:.1f} C {mx:.1f} {y1:.1f},"
            f" {mx:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"
        )
        eid = e["id"]
        both_hl = bool(p.get("highlighted")) and bool(n.get("highlighted"))
        hl_cls = " hl" if both_hl else ""
        paths.append(
            f'<g class="mm-edge{hl_cls}" data-eid="{eid}" data-from="{p["id"]}"'
            f' data-to="{n["id"]}">'
            f'<path class="mm-edge-hit" fill="none" stroke="transparent"'
            f' stroke-width="16" d="{d}"/>'
            f'<path class="mm-edge-line" fill="none"'
            f' stroke="rgba(90,110,180,.45)" stroke-width="2" d="{d}"/>'
            f"</g>"
        )
        label = (e.get("label") or "").strip()
        labels.append(
            f'<div class="mm-edge-label{hl_cls}" data-eid="{eid}"'
            f' data-from="{p["id"]}" data-to="{n["id"]}"'
            f' style="left:{mx:.0f}px;top:{my:.0f}px">'
            f"{html.escape(label)}</div>"
        )
    svg = (
        f'<svg class="mm-lines" width="{width:.0f}" height="{height:.0f}"'
        f' viewBox="0 0 {width:.0f} {height:.0f}" overflow="visible">'
        f'{"".join(paths)}</svg>'
    )
    cards = []
    primary = min(
        (n["id"] for n in laid if n["parent_id"] is None),
        default=None,
    )
    for n in laid:
        is_root = n["id"] == primary
        cls = "mm-node"
        if is_root:
            cls += " root"
        cls += " text" if n["kind"] == "text" else " box"
        if n.get("highlighted"):
            cls += " hl"
        raw = n.get("content") or ""
        if _node_is_prose(raw):
            cls += " mm-prose"
        sized = n.get("box_w") is not None and n.get("box_h") is not None
        if sized:
            cls += " mm-sized"
        nid = n["id"]
        parent_attr = "" if n["parent_id"] is None else str(n["parent_id"])
        size_css = (
            f'width:{n["w"]:.0f}px;height:{n["h"]:.0f}px'
            if sized
            else f'width:{n["w"]:.0f}px;min-height:{n["h"]:.0f}px'
        )
        cards.append(
            f'<div class="{cls}" data-id="{nid}" data-parent="{parent_attr}"'
            f' data-raw="{_attr_nl(raw)}"'
            f' data-created="{html.escape(n.get("created_at") or "", quote=True)}"'
            f' data-updated="{html.escape(n.get("updated_at") or "", quote=True)}"'
            f' style="left:{n["x"]:.0f}px;top:{n["y"]:.0f}px;{size_css}">'
            f'<div class="mm-body">{node_content_html(raw)}</div></div>'
        )
    head = (
        '<div class="page-head"><span>'
        f'思维导图「{html.escape(mindmap["name"])}」'
        f" · {len(laid)} 个节点</span></div>"
    )
    cam_attr = ""
    if isinstance(view, dict) and view.get("scale"):
        cam_attr = (
            f' data-tx="{float(view.get("tx", 0)):.2f}"'
            f' data-ty="{float(view.get("ty", 0)):.2f}"'
            f' data-scale="{float(view.get("scale", 1)):.4f}"'
        )
    canvas = (
        f'<div class="mm-viewport" data-w="{width:.0f}" data-h="{height:.0f}"'
        f"{cam_attr}>"
        f'<div class="mm-pan"><div class="mm-world"><div class="mm-canvas"'
        f' style="width:{width:.0f}px;height:{height:.0f}px;overflow:visible">'
        f'{svg}{"".join(labels)}{"".join(cards)}</div></div></div></div>'
    )
    page = _page(
        head + hint + canvas,
        scroll_bottom=False,
        wide=True,
        extra_js=_MM_JS,
    )
    to_save = None
    if newly:
        to_save = [{"id": n["id"], "x": n["x"], "y": n["y"]} for n in newly]
    return page, to_save


def export_markdown(session: dict, messages: list, image_rel: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# {session['name']}",
        "",
        f"> 创建于 {session['created_at']} · 导出于 {now}"
        f" · 共 {len(messages)} 条记录",
        "",
    ]
    for m in messages:
        role_name = "我" if m["role"] == "user" else "AI"
        lines.append("---")
        lines.append("")
        lines.append(f"**{role_name}** · {m['created_at']}")
        lines.append("")
        if m.get("kind") == "image":
            name = m.get("content") or ""
            if image_rel and name:
                href = f"{image_rel.rstrip('/')}/{name}"
            else:
                href = _image_uri(m)
            lines.append(f"![图片]({href})")
        else:
            lines.append(m["content"])
        lines.append("")
    return "\n".join(lines)


def _mermaid_label(text: str, limit: int = 80) -> str:
    t = (text or "").replace("\r\n", "\n").strip() or "（空）"
    t = t.replace("\n", " ")
    for a, b in (
        ('"', "'"),
        ("[", "("),
        ("]", ")"),
        ("{", "("),
        ("}", ")"),
        ("`", "'"),
        ("|", "/"),
    ):
        t = t.replace(a, b)
    if len(t) > limit:
        t = t[: limit - 1] + "…"
    return t


def export_mindmap_markdown(mindmap: dict, nodes: list, edges: list) -> str:
    """思维导图导出为 Markdown：大纲 + Mermaid 流程图。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_id = {n["id"]: n for n in nodes}
    children = {}
    for n in nodes:
        children.setdefault(n["parent_id"], []).append(n)
    for kids in children.values():
        kids.sort(key=lambda x: (x.get("sort_order") or 0, x["id"]))

    def outline_title(n):
        raw = (n.get("content") or "").strip() or "（空）"
        first = raw.split("\n", 1)[0]
        kind = "子句" if n.get("kind") == "text" else "子框"
        star = " ★" if n.get("highlighted") else ""
        return f"{first}{star}（{kind}）"

    lines = [
        f"# {mindmap['name']}",
        "",
        f"> 思维导图 · 创建于 {mindmap['created_at']} · 导出于 {now}"
        f" · {len(nodes)} 个节点",
        "",
        "用 Markdown 保存。下面的 Mermaid 图可在 VS Code、Typora、GitHub 里预览。",
        "",
        "## 结构",
        "",
    ]

    def walk(n, depth):
        lines.append("  " * depth + "- " + outline_title(n))
        for child in children.get(n["id"], []):
            walk(child, depth + 1)

    roots = children.get(None) or []
    if not roots and not nodes:
        lines.append("（空导图）")
    else:
        for r in roots:
            walk(r, 0)
        hanging = [
            n for n in nodes
            if n["parent_id"] is not None and n["parent_id"] not in by_id
        ]
        for n in hanging:
            walk(n, 0)

    lines.extend(["", "## 关系图", "", "```mermaid", "flowchart LR"])
    for n in nodes:
        label = _mermaid_label(n.get("content") or "")
        nid = f"n{n['id']}"
        if n.get("kind") == "text":
            lines.append(f'  {nid}("{label}")')
        else:
            lines.append(f'  {nid}["{label}"]')
    for e in edges or []:
        a, b = e.get("from_id"), e.get("to_id")
        if a not in by_id or b not in by_id:
            continue
        both = bool(by_id[a].get("highlighted")) and bool(
            by_id[b].get("highlighted")
        )
        arrow = "==>" if both else "-->"
        lab = (e.get("label") or "").strip()
        if lab:
            lines.append(
                f'  n{a} {arrow}|"{_mermaid_label(lab, 40)}"| n{b}'
            )
        else:
            lines.append(f"  n{a} {arrow} n{b}")
    for n in nodes:
        if n.get("highlighted"):
            lines.append(
                f"  style n{n['id']} fill:#ffe8cc,stroke:#ff8a2a,stroke-width:2px"
            )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)
