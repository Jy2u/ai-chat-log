"""把 Cursor Canvas 的 JSX 转成聊天里能看的 HTML。"""

from __future__ import annotations

import html
import re


_IMPORT_RE = re.compile(r"""from\s+["']cursor/canvas["']""")
_FENCE_RE = re.compile(
    r"^```(?:tsx|jsx|typescript|javascript|ts|js)?\s*\n([\s\S]*?)\n```\s*$"
)


class _ParseError(Exception):
    pass


class _Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name: str, props: dict, children: list):
        self.name = name
        self.props = props
        self.children = children


def is_canvas_source(text: str) -> bool:
    raw = _unwrap(text or "")
    return bool(_IMPORT_RE.search(raw))


def try_canvas_html(text: str) -> str | None:
    raw = _unwrap(text or "")
    if not _IMPORT_RE.search(raw):
        return None
    jsx = _extract_jsx(raw)
    if not jsx:
        return None
    try:
        tree = _Parser(jsx).parse_jsx()
    except _ParseError:
        return None
    return f'<div class="cv">{_render(tree)}</div>'


def _unwrap(text: str) -> str:
    s = (text or "").strip()
    m = _FENCE_RE.match(s)
    return m.group(1).strip() if m else s


def _extract_jsx(src: str) -> str:
    m = re.search(r"return\s*\(", src)
    if m:
        start = m.end() - 1
        try:
            end = _match_pair(src, start, "(", ")")
        except _ParseError:
            return ""
        return src[start + 1 : end].strip()
    m = re.search(r"<(?:Stack|Row|Grid|Card|Callout)\b", src)
    return src[m.start() :].strip() if m else ""


def _match_pair(src: str, start: int, left: str, right: str) -> int:
    depth = 0
    i = start
    in_str = ""
    while i < len(src):
        c = src[i]
        if in_str:
            if c == "\\" and i + 1 < len(src):
                i += 2
                continue
            if c == in_str:
                in_str = ""
            i += 1
            continue
        if c in "\"'":
            in_str = c
            i += 1
            continue
        if c == left:
            depth += 1
        elif c == right:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise _ParseError("unbalanced")


class _Parser:
    def __init__(self, src: str):
        self.s = src
        self.i = 0

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1
        if self.s.startswith("{/*", self.i):
            end = self.s.find("*/}", self.i)
            if end < 0:
                raise _ParseError("comment")
            self.i = end + 3
            self.skip_ws()

    def parse_jsx(self) -> _Node:
        self.skip_ws()
        if self.peek() != "<":
            raise _ParseError("expected tag")
        self.i += 1
        name = self._read_name()
        props = {}
        self.skip_ws()
        while self.peek() and self.peek() not in ">/":
            key, val = self._parse_attr()
            props[key] = val
            self.skip_ws()
        if self.s.startswith("/>", self.i):
            self.i += 2
            return _Node(name, props, [])
        if self.peek() != ">":
            raise _ParseError("expected >")
        self.i += 1
        children = []
        while True:
            if self.s.startswith("</", self.i):
                self.i += 2
                self._read_name()
                self.skip_ws()
                if self.peek() != ">":
                    raise _ParseError("expected close >")
                self.i += 1
                break
            if self.peek() == "<":
                children.append(self.parse_jsx())
                continue
            if self.peek() == "{":
                self.i += 1
                self.skip_ws()
                if self.s.startswith("/*", self.i):
                    end = self.s.find("*/}", self.i)
                    if end < 0:
                        raise _ParseError("comment")
                    self.i = end + 3
                    continue
                children.append(self._parse_value())
                self.skip_ws()
                if self.peek() != "}":
                    raise _ParseError("expected }")
                self.i += 1
                continue
            text = self._read_text()
            if text.strip():
                children.append(_Node("#text", {"value": text}, []))
        return _Node(name, props, children)

    def _parse_attr(self):
        key = self._read_name()
        self.skip_ws()
        if self.peek() != "=":
            return key, True
        self.i += 1
        self.skip_ws()
        if self.peek() in "\"'":
            return key, self._read_string()
        if self.peek() != "{":
            raise _ParseError("expected {")
        self.i += 1
        val = self._parse_value()
        self.skip_ws()
        if self.peek() != "}":
            raise _ParseError("expected }")
        self.i += 1
        return key, val

    def _parse_value(self):
        self.skip_ws()
        c = self.peek()
        if c == "{":
            return self._parse_object()
        if c == "[":
            return self._parse_array()
        if c == "<":
            return self.parse_jsx()
        if c in "\"'":
            return self._read_string()
        if c == "-" or c.isdigit():
            return self._read_number()
        ident = self._read_name()
        if ident == "true":
            return True
        if ident == "false":
            return False
        if ident == "null":
            return None
        return ident

    def _parse_array(self) -> list:
        if self.peek() != "[":
            raise _ParseError("expected [")
        self.i += 1
        items = []
        while True:
            self.skip_ws()
            if self.peek() == "]":
                self.i += 1
                return items
            items.append(self._parse_value())
            self.skip_ws()
            if self.peek() == ",":
                self.i += 1
                continue
            if self.peek() == "]":
                self.i += 1
                return items
            raise _ParseError("expected , or ]")

    def _parse_object(self) -> dict:
        if self.peek() != "{":
            raise _ParseError("expected {")
        self.i += 1
        out = {}
        while True:
            self.skip_ws()
            if self.peek() == "}":
                self.i += 1
                return out
            if self.peek() in "\"'":
                key = self._read_string()
            else:
                key = self._read_name()
            self.skip_ws()
            if self.peek() != ":":
                raise _ParseError("expected :")
            self.i += 1
            out[key] = self._parse_value()
            self.skip_ws()
            if self.peek() == ",":
                self.i += 1
                continue
            if self.peek() == "}":
                self.i += 1
                return out
            raise _ParseError("expected , or }")

    def _read_name(self) -> str:
        self.skip_ws()
        m = re.match(r"[A-Za-z_][\w.-]*", self.s[self.i :])
        if not m:
            raise _ParseError("expected name")
        self.i += m.end()
        return m.group(0)

    def _read_string(self) -> str:
        q = self.peek()
        if q not in "\"'":
            raise _ParseError("expected string")
        self.i += 1
        out = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\" and self.i + 1 < len(self.s):
                out.append(self.s[self.i + 1])
                self.i += 2
                continue
            if c == q:
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1
        raise _ParseError("unterminated string")

    def _read_number(self):
        m = re.match(r"-?\d+(?:\.\d+)?", self.s[self.i :])
        if not m:
            raise _ParseError("expected number")
        self.i += m.end()
        raw = m.group(0)
        return float(raw) if "." in raw else int(raw)

    def _read_text(self) -> str:
        start = self.i
        while self.i < len(self.s) and self.s[self.i] not in "{<":
            self.i += 1
        return self.s[start : self.i]


def _css_style(style) -> str:
    if not isinstance(style, dict):
        return ""
    unitless = {"fontWeight", "opacity", "zIndex", "lineHeight", "flex", "order"}
    parts = []
    for key, val in style.items():
        css_key = re.sub(r"[A-Z]", lambda m: "-" + m.group().lower(), str(key))
        if isinstance(val, (int, float)) and key not in unitless:
            parts.append(f"{css_key}:{val}px")
        else:
            parts.append(f"{css_key}:{val}")
    return ";".join(parts)


def _style_attr(extra: str = "", style=None) -> str:
    bits = [bit for bit in (extra, _css_style(style)) if bit]
    if not bits:
        return ""
    return f' style="{html.escape(";".join(bits), quote=True)}"'


def _rich_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    parts = re.split(r"`([^`]+)`", text)
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(f"<code>{html.escape(part)}</code>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def _render(node) -> str:
    if node is None:
        return ""
    if isinstance(node, _Node):
        return _render_tag(node)
    if isinstance(node, list):
        return "".join(_render(x) for x in node)
    if isinstance(node, bool):
        return ""
    return _rich_text(str(node))


def _kids(node: _Node) -> str:
    return "".join(_render(child) for child in node.children)


def _render_tag(node: _Node) -> str:
    name = node.name
    props = node.props
    if name == "#text":
        return _rich_text(props.get("value", ""))

    if name == "Stack":
        gap = props.get("gap", 12)
        return (
            f'<div class="cv-stack"'
            f'{_style_attr(f"gap:{gap}px", props.get("style"))}>'
            f"{_kids(node)}</div>"
        )
    if name == "Row":
        gap = props.get("gap", 8)
        extra = f"gap:{gap}px"
        if props.get("wrap"):
            extra += ";flex-wrap:wrap"
        align = {"start": "flex-start", "end": "flex-end"}.get(
            props.get("align"), props.get("align")
        )
        if align:
            extra += f";align-items:{align}"
        return (
            f'<div class="cv-row"{_style_attr(extra, props.get("style"))}>'
            f"{_kids(node)}</div>"
        )
    if name == "Grid":
        cols = props.get("columns", 2)
        gap = props.get("gap", 16)
        if isinstance(cols, (int, float)):
            tmpl = f"repeat({int(cols)}, minmax(0, 1fr))"
        else:
            tmpl = str(cols)
        extra = f"grid-template-columns:{tmpl};gap:{gap}px"
        return (
            f'<div class="cv-grid"{_style_attr(extra, props.get("style"))}>'
            f"{_kids(node)}</div>"
        )
    if name in ("H1", "H2", "H3"):
        tag = name.lower()
        return f'<{tag} class="cv-{tag}">{_kids(node)}</{tag}>'
    if name == "Text":
        cls = ["cv-text"]
        tone = props.get("tone")
        size = props.get("size")
        if tone:
            cls.append(f"cv-tone-{tone}")
        if size:
            cls.append(f"cv-size-{size}")
        return f'<p class="{" ".join(cls)}">{_kids(node)}</p>'
    if name == "Pill":
        cls = ["cv-pill"]
        if props.get("active"):
            cls.append("on")
        if props.get("size") == "sm":
            cls.append("sm")
        return f'<span class="{" ".join(cls)}">{_kids(node)}</span>'
    if name == "Card":
        return f'<div class="cv-card">{_kids(node)}</div>'
    if name == "CardHeader":
        trailing = props.get("trailing")
        trail = (
            f'<div class="cv-card-trail">{_render(trailing)}</div>' if trailing else ""
        )
        return (
            f'<div class="cv-card-head"><div class="cv-card-title">'
            f"{_kids(node)}</div>{trail}</div>"
        )
    if name == "CardBody":
        return f'<div class="cv-card-body">{_kids(node)}</div>'
    if name == "Callout":
        tone = props.get("tone") or "info"
        title = props.get("title")
        title_html = (
            f'<div class="cv-callout-title">{html.escape(str(title))}</div>'
            if title
            else ""
        )
        return (
            f'<div class="cv-callout {html.escape(str(tone))}">'
            f'{title_html}<div class="cv-callout-body">{_kids(node)}</div></div>'
        )
    if name == "Stat":
        tone = props.get("tone") or ""
        value = props.get("value", "")
        label = props.get("label", "")
        return (
            f'<div class="cv-stat {html.escape(str(tone))}">'
            f'<div class="cv-stat-val">{html.escape(str(value))}</div>'
            f'<div class="cv-stat-lab">{html.escape(str(label))}</div></div>'
        )
    if name == "Divider":
        return '<hr class="cv-hr">'
    if name == "Spacer":
        return '<div class="cv-spacer"></div>'
    if name == "Table":
        return _render_table(props)
    if name == "Code":
        return f'<code class="cv-code">{_kids(node)}</code>'
    if name == "Link":
        href = html.escape(str(props.get("href") or "#"), quote=True)
        return f'<a class="cv-link" href="{href}">{_kids(node)}</a>'
    return f'<div class="cv-box">{_kids(node)}</div>'


def _render_table(props: dict) -> str:
    headers = props.get("headers") or []
    rows = props.get("rows") or []
    tones = props.get("rowTone") or []
    striped = bool(props.get("striped"))

    def cell(value) -> str:
        if isinstance(value, _Node):
            return _render(value)
        return _rich_text(str(value))

    ths = "".join(f"<th>{cell(h)}</th>" for h in headers)
    body = []
    for i, row in enumerate(rows):
        if not isinstance(row, list):
            row = [row]
        tone = tones[i] if i < len(tones) else ""
        cls = []
        if tone:
            cls.append(f"cv-tone-{tone}")
        if striped and i % 2:
            cls.append("stripe")
        tds = []
        for j, item in enumerate(row[: len(headers) or None]):
            dot = (
                f'<span class="cv-dot {html.escape(str(tone))}"></span>'
                if j == 0 and tone
                else ""
            )
            tds.append(f"<td>{dot}{cell(item)}</td>")
        while headers and len(tds) < len(headers):
            tds.append("<td></td>")
        cls_attr = f' class="{" ".join(cls)}"' if cls else ""
        body.append(f"<tr{cls_attr}>{''.join(tds)}</tr>")
    return (
        '<div class="cv-table-wrap"><table class="cv-table">'
        f"<thead><tr>{ths}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )
