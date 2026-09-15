"""把 Cursor Canvas 转成聊天里能看的 HTML。

不只认写死的标签：会跑一遍常见的 const / 函数 / map / 计算，
再把算出来的树画出来。图表、钩子点选仍是静态预览。
"""

from __future__ import annotations

import html
import re


_IMPORT_RE = re.compile(r"""from\s+["']cursor/canvas["']""")
_FENCE_RE = re.compile(
    r"^```(?:tsx|jsx|typescript|javascript|ts|js)?\s*\n([\s\S]*?)\n```\s*$"
)
_IDENT_RE = re.compile(r"[A-Za-z_][\w$]*")


class _ParseError(Exception):
    pass


class _Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name: str, props: dict, children: list):
        self.name = name
        self.props = props
        self.children = children


class _Fn:
    def __init__(self, params: list, body: str, kind: str, engine: _Engine):
        self.params = params
        self.body = body
        self.kind = kind
        self.engine = engine

    def __call__(self, args, env: dict):
        local = dict(env)
        for i, name in enumerate(self.params):
            local[name] = args[i] if i < len(args) else None
        if self.kind == "expr":
            return _Engine(self.body, local).parse_expr()
        return _Engine(self.body, local).run_block()


def is_canvas_source(text: str) -> bool:
    raw = _unwrap(text or "")
    return bool(_IMPORT_RE.search(raw))


def try_canvas_html(text: str) -> str | None:
    raw = _unwrap(text or "")
    if not _IMPORT_RE.search(raw):
        return None
    try:
        tree = _Engine(_strip_ts(raw), _builtins()).run_module()
    except Exception:
        return None
    if tree is None:
        return None
    return f'<div class="cv">{_render(tree)}</div>'


def _unwrap(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("【") and s.endswith("】"):
        s = s[1:-1].strip()
    m = _FENCE_RE.match(s)
    return m.group(1).strip() if m else s


def _builtins() -> dict:
    def use_canvas_state(*args):
        default = args[1] if len(args) > 1 else (args[0] if args else None)
        return [default, lambda *_a, **_k: None]

    return {
        "undefined": None,
        "null": None,
        "true": True,
        "false": False,
        "useCanvasState": use_canvas_state,
        "useHostTheme": lambda: {},
        "useMemo": lambda fn, *_a: fn() if callable(fn) else fn,
        "useState": use_canvas_state,
    }


def _strip_ts(src: str) -> str:
    s = _strip_imports(src)
    s = _strip_type_aliases(s)
    s = re.sub(r"\s+as\s+const\b", "", s)
    s = _strip_trailing_generics(s)
    s = _strip_annotations(s)
    s = re.sub(r"\)\s*:\s*[A-Za-z_<{][^;{]*\{", ") {", s)
    return s


def _strip_imports(src: str) -> str:
    return re.sub(
        r"import\s+(?:type\s+)?[\s\S]*?from\s+[\"'][^\"']+[\"']\s*;?",
        "",
        src,
    )


def _strip_type_aliases(src: str) -> str:
    out = []
    i = 0
    while i < len(src):
        m = re.match(r"type\s+[A-Za-z_][\w$]*\s*=", src[i:])
        if not m:
            out.append(src[i])
            i += 1
            continue
        i += m.end()
        i = _skip_balanced_until(src, i, {";"})
        if i < len(src) and src[i] == ";":
            i += 1
    return "".join(out)


def _looks_like_generic(src: str, i: int) -> bool:
    """ident<...> is a TS generic, not JSX text + closing tag, and not n<10."""
    if i >= len(src) or src[i] != "<":
        return False
    if i + 1 < len(src) and src[i + 1] == "/":
        return False
    j = _skip_ws_idx(src, i + 1)
    if j >= len(src):
        return False
    return src[j] in "\"'{_" or src[j].isalpha()


def _strip_trailing_generics(src: str) -> str:
    out = []
    i = 0
    while i < len(src):
        m = _IDENT_RE.match(src, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            if _looks_like_generic(src, i):
                i = _skip_pair(src, i, "<", ">") + 1
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def _strip_annotations(src: str) -> str:
    out = []
    i = 0
    while i < len(src):
        m = re.match(r"(const|let|var)\s+", src[i:])
        if m:
            out.append(src[i : i + m.end()])
            i += m.end()
            if i < len(src) and src[i] in "[({":
                continue
            ident = _IDENT_RE.match(src, i)
            if ident:
                out.append(ident.group(0))
                i = ident.end()
                j = _skip_ws_idx(src, i)
                if j < len(src) and src[j] == ":":
                    i = _skip_type(src, j + 1)
            continue
        out.append(src[i])
        i += 1
    src = "".join(out)
    out = []
    i = 0
    while i < len(src):
        if src.startswith("function", i) and (
            i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")
        ):
            j = i + 8
            j = _skip_ws_idx(src, j)
            ident = _IDENT_RE.match(src, j)
            if ident:
                out.append(src[i:ident.end()])
                i = ident.end()
                i = _skip_ws_idx(src, i)
                if i < len(src) and src[i] == "(":
                    out.append("(")
                    i += 1
                    src, i, chunk = _strip_param_types(src, i)
                    out.append(chunk)
                continue
        out.append(src[i])
        i += 1
    return "".join(out)


def _strip_param_types(src: str, i: int):
    chunk = []
    depth = 1
    while i < len(src) and depth:
        c = src[i]
        if c in "\"'`":
            end = _skip_string(src, i)
            chunk.append(src[i : end + 1])
            i = end + 1
            continue
        if c == "(":
            depth += 1
            chunk.append(c)
            i += 1
            continue
        if c == ")":
            depth -= 1
            if depth == 0:
                break
            chunk.append(c)
            i += 1
            continue
        if c == ":":
            i = _skip_type(src, i + 1)
            continue
        chunk.append(c)
        i += 1
    return src, i, "".join(chunk)


def _skip_type(src: str, i: int) -> int:
    i = _skip_ws_idx(src, i)
    while i < len(src):
        if src[i] in "\"'":
            i = _skip_string(src, i) + 1
            continue
        if src[i] == "<":
            i = _skip_pair(src, i, "<", ">") + 1
            continue
        if src[i] == "(":
            i = _skip_pair(src, i, "(", ")") + 1
            continue
        if src[i] == "[":
            i = _skip_pair(src, i, "[", "]") + 1
            continue
        if src[i] == "{":
            i = _skip_pair(src, i, "{", "}") + 1
            continue
        if src[i] in "=,);{":
            return i
        if src.startswith("=>", i):
            return i
        i += 1
    return i


def _skip_ws_idx(src: str, i: int) -> int:
    while i < len(src) and src[i] in " \t\r\n":
        i += 1
    return i


def _skip_string(src: str, i: int) -> int:
    q = src[i]
    i += 1
    while i < len(src):
        if src[i] == "\\" and i + 1 < len(src):
            i += 2
            continue
        if src[i] == q:
            return i
        i += 1
    return i


def _skip_pair(src: str, i: int, left: str, right: str) -> int:
    depth = 0
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
        if c in "\"'`":
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


def _skip_balanced_until(src: str, i: int, stops: set) -> int:
    depth = 0
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
        if c in "\"'`":
            in_str = c
            i += 1
            continue
        if c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif depth <= 0 and c in stops:
            return i
        i += 1
    return i


class _Engine:
    def __init__(self, src: str, env: dict):
        self.s = src
        self.i = 0
        self.env = env
        self.skip_eval = False

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def _is(self, chars: str) -> bool:
        ch = self.peek()
        return bool(ch) and ch in chars

    def skip_ws(self):
        while self.i < len(self.s):
            if self.s[self.i] in " \t\r\n":
                self.i += 1
                continue
            if self.s.startswith("//", self.i):
                nl = self.s.find("\n", self.i)
                self.i = len(self.s) if nl < 0 else nl + 1
                continue
            if self.s.startswith("/*", self.i):
                end = self.s.find("*/", self.i + 2)
                self.i = len(self.s) if end < 0 else end + 2
                continue
            break

    def run_module(self):
        default = None
        while True:
            self.skip_ws()
            if not self.peek():
                break
            exported = False
            if self._eat("export"):
                self.skip_ws()
                exported = self._eat("default")
                self.skip_ws()
            if self._starts_kw("function"):
                fn = self._parse_function()
                self.env[fn[0]] = fn[1]
                if exported:
                    default = fn[1]
                continue
            if self._starts_kw("const") or self._starts_kw("let") or self._starts_kw("var"):
                self._parse_decl()
                continue
            if self.peek() == ";":
                self.i += 1
                continue
            break
        if default is None:
            return None
        return default([], self.env)

    def run_block(self):
        ret = None
        self.skip_ws()
        if self.peek() == "{":
            self.i += 1
        while True:
            self.skip_ws()
            if not self.peek() or self.peek() == "}":
                if self.peek() == "}":
                    self.i += 1
                return ret
            if self._starts_kw("return"):
                self.i += 6
                self.skip_ws()
                if self._is(";}"):
                    return None
                ret = self.parse_expr()
                self.skip_ws()
                self._eat(";")
                return ret
            if self._starts_kw("const") or self._starts_kw("let") or self._starts_kw("var"):
                self._parse_decl()
                continue
            if self._starts_kw("function"):
                fn = self._parse_function()
                self.env[fn[0]] = fn[1]
                continue
            if self._starts_kw("for"):
                self._parse_for()
                continue
            if self._starts_kw("if"):
                val = self._parse_if()
                if val is not _NO_RETURN:
                    return val
                continue
            self.parse_expr()
            self.skip_ws()
            self._eat(";")

    def _parse_decl(self):
        self.skip_ws()
        if self._eat("const") or self._eat("let") or self._eat("var"):
            pass
        self.skip_ws()
        if self.peek() == "[":
            names = self._parse_ident_list("[", "]")
            self.skip_ws()
            self._need("=")
            value = self.parse_expr()
            seq = list(value) if isinstance(value, (list, tuple)) else [value]
            for i, name in enumerate(names):
                self.env[name] = seq[i] if i < len(seq) else None
        else:
            name = self._read_ident()
            self.skip_ws()
            self._need("=")
            self.env[name] = self.parse_expr()
        self.skip_ws()
        self._eat(";")

    def _parse_function(self):
        self._need_kw("function")
        self.skip_ws()
        name = self._read_ident()
        self.skip_ws()
        params = self._parse_ident_list("(", ")")
        self.skip_ws()
        start = self.i
        if self.peek() != "{":
            raise _ParseError("function body")
        self.i = _skip_pair(self.s, self.i, "{", "}") + 1
        body = self.s[start:self.i]
        return name, _Fn(params, body, "block", self)

    def _parse_for(self):
        self._need_kw("for")
        self.skip_ws()
        self._need("(")
        self.skip_ws()
        self._eat("const") or self._eat("let") or self._eat("var")
        self.skip_ws()
        name = self._read_ident()
        self.skip_ws()
        self._need_kw("of")
        items = self.parse_expr()
        self.skip_ws()
        self._need(")")
        self.skip_ws()
        body_src = self._read_stmt_source()
        if not isinstance(items, list):
            return
        saved = dict(self.env)
        for item in items:
            self.env[name] = item
            _Engine(body_src, self.env).run_block() if body_src.lstrip().startswith("{") else _Engine(
                body_src, self.env
            ).parse_expr()
        # keep assignments made to objects in env; restore only overwritten scalars? 
        # for-of only introduced `name`. Restore name if it existed.
        if name in saved:
            self.env[name] = saved[name]
        else:
            self.env.pop(name, None)

    def _parse_if(self):
        self._need_kw("if")
        self.skip_ws()
        self._need("(")
        cond = self.parse_expr()
        self.skip_ws()
        self._need(")")
        self.skip_ws()
        body = self._read_stmt_source()
        else_body = ""
        self.skip_ws()
        if self._starts_kw("else"):
            self.i += 4
            self.skip_ws()
            else_body = self._read_stmt_source()
        chosen = body if cond else else_body
        if not chosen:
            return _NO_RETURN
        if "return" in chosen:
            return _Engine(chosen, self.env).run_block()
        if chosen.lstrip().startswith("{"):
            _Engine(chosen, self.env).run_block()
        else:
            _Engine(chosen, self.env).parse_expr()
        return _NO_RETURN

    def _read_stmt_source(self) -> str:
        self.skip_ws()
        start = self.i
        if self.peek() == "{":
            end = _skip_pair(self.s, self.i, "{", "}")
            self.i = end + 1
            return self.s[start:self.i]
        self.i = _skip_balanced_until(self.s, self.i, {";"})
        if self.peek() == ";":
            self.i += 1
        return self.s[start:self.i]

    def parse_expr(self):
        return self._parse_assign()

    def _parse_assign(self):
        start = self.i
        left_place = self._try_lvalue()
        self.skip_ws()
        if left_place is not None and self.peek() == "=" and not self.s.startswith("=>", self.i) and not self.s.startswith("===", self.i) and not self.s.startswith("==", self.i):
            self.i += 1
            value = self.parse_expr()
            if self.skip_eval:
                return value
            target, key = left_place
            if key is None:
                self.env[target] = value
            else:
                target[key] = value
            return value
        self.i = start
        return self._parse_ternary()

    def _try_lvalue(self):
        self.skip_ws()
        ident = _IDENT_RE.match(self.s, self.i)
        if not ident:
            return None
        name = ident.group(0)
        if name in ("true", "false", "null", "undefined", "function", "const"):
            return None
        pos = ident.end()
        obj = self.env.get(name, _MISSING)
        j = pos
        while True:
            k = _skip_ws_idx(self.s, j)
            if k < len(self.s) and self.s[k] == ".":
                k += 1
                k = _skip_ws_idx(self.s, k)
                nxt = _IDENT_RE.match(self.s, k)
                if not nxt:
                    return None
                if obj is _MISSING or obj is None:
                    return None
                name = nxt.group(0)
                rest = _skip_ws_idx(self.s, nxt.end())
                if rest < len(self.s) and self.s[rest] in ".[":
                    obj = _get_prop(obj, name)
                    j = nxt.end()
                    continue
                self.i = nxt.end()
                return obj, name
            if k < len(self.s) and self.s[k] == "[":
                saved = self.i
                self.i = k + 1
                key = self.parse_expr()
                self.skip_ws()
                if self.peek() != "]":
                    self.i = saved
                    return None
                self.i += 1
                rest = self.i
                rest = _skip_ws_idx(self.s, rest)
                if rest < len(self.s) and self.s[rest] in ".[":
                    obj = _get_prop(obj, key)
                    j = self.i
                    continue
                return obj, key
            self.i = pos
            return name, None

    def _parse_ternary(self):
        cond = self._parse_or()
        self.skip_ws()
        if self.peek() != "?":
            return cond
        if self.s.startswith("?.", self.i):
            return cond
        self.i += 1
        yes = self.parse_expr()
        self.skip_ws()
        self._need(":")
        no = self.parse_expr()
        return yes if cond else no

    def _parse_or(self):
        left = self._parse_and()
        while True:
            self.skip_ws()
            if self.s.startswith("||", self.i):
                self.i += 2
                right = self._parse_and()
                left = left or right
            else:
                return left

    def _parse_and(self):
        left = self._parse_eq()
        while True:
            self.skip_ws()
            if self.s.startswith("&&", self.i):
                self.i += 2
                right = self._parse_eq()
                left = left and right
            else:
                return left

    def _parse_eq(self):
        left = self._parse_add()
        while True:
            self.skip_ws()
            if self.s.startswith("===", self.i) or self.s.startswith("!==", self.i):
                op = self.s[self.i : self.i + 3]
                self.i += 3
                right = self._parse_add()
                left = (left != right) if op == "!==" else (left == right)
            elif self.s.startswith("==", self.i) or self.s.startswith("!=", self.i):
                op = self.s[self.i : self.i + 2]
                self.i += 2
                right = self._parse_add()
                left = (left != right) if op == "!=" else (left == right)
            elif self.s.startswith("<=", self.i) or self.s.startswith(">=", self.i):
                op = self.s[self.i : self.i + 2]
                self.i += 2
                right = self._parse_add()
                left = left <= right if op == "<=" else left >= right
            elif self._is("<>") and not self.s.startswith("=>", self.i):
                op = self.peek()
                self.i += 1
                right = self._parse_add()
                left = left < right if op == "<" else left > right
            else:
                return left

    def _parse_add(self):
        left = self._parse_mul()
        while True:
            self.skip_ws()
            if self.peek() == "+" and not self.s.startswith("++", self.i):
                self.i += 1
                right = self._parse_mul()
                if isinstance(left, str) or isinstance(right, str):
                    left = f"{_js_str(left)}{_js_str(right)}"
                else:
                    left = (left or 0) + (right or 0)
            elif self.peek() == "-" and not self.s.startswith("--", self.i):
                self.i += 1
                right = self._parse_mul()
                left = (left or 0) - (right or 0)
            else:
                return left

    def _parse_mul(self):
        left = self._parse_prefix()
        while True:
            self.skip_ws()
            if self._is("*/%"):
                op = self.peek()
                self.i += 1
                right = self._parse_prefix()
                if op == "*":
                    left = left * right
                elif op == "/":
                    left = left / right
                else:
                    left = left % right
            else:
                return left

    def _parse_prefix(self):
        self.skip_ws()
        if self.peek() == "!":
            self.i += 1
            return not self._parse_prefix()
        if self.peek() == "-":
            self.i += 1
            return -self._parse_prefix()
        if self.peek() == "+":
            self.i += 1
            return +self._parse_prefix()
        if self.s.startswith("...", self.i):
            self.i += 3
            return ("...", self._parse_prefix())
        return self._parse_postfix()

    def _parse_postfix(self):
        val = self._parse_atom()
        while True:
            self.skip_ws()
            if self.peek() == ".":
                self.i += 1
                name = self._read_ident()
                val = _get_prop(val, name)
                continue
            if self.peek() == "[":
                self.i += 1
                key = self.parse_expr()
                self.skip_ws()
                self._need("]")
                val = _get_prop(val, key)
                continue
            if self.peek() == "(":
                args = self._parse_args()
                if self.skip_eval:
                    val = None
                    continue
                try:
                    val = _call(val, args, self.env)
                except _ParseError as e:
                    raise _ParseError(self._err(str(e))) from e
                continue
            if self.peek() == "!":
                self.i += 1
                continue
            return val

    def _parse_atom(self):
        self.skip_ws()
        c = self.peek()
        if c == "<":
            return self._parse_jsx()
        if c and c in "\"'":
            return self._read_string()
        if c == "`":
            return self._read_template()
        if c.isdigit() or (c == "." and self.i + 1 < len(self.s) and self.s[self.i + 1].isdigit()):
            return self._read_number()
        if c == "[":
            return self._parse_array()
        if c == "{":
            return self._parse_object()
        if c == "(":
            return self._parse_paren_or_arrow()
        ident = _IDENT_RE.match(self.s, self.i)
        if ident:
            name = ident.group(0)
            self.i = ident.end()
            self.skip_ws()
            if self.s.startswith("=>", self.i):
                self.i += 2
                return self._make_arrow([name])
            if name == "undefined":
                return None
            return self.env.get(name)
        raise _ParseError("atom")

    def _parse_paren_or_arrow(self):
        start = self.i
        self.i += 1
        self.skip_ws()
        if self.peek() == ")":
            self.i += 1
            self.skip_ws()
            if self.s.startswith("=>", self.i):
                self.i += 2
                return self._make_arrow([])
            return None
        peek_ident = _IDENT_RE.match(self.s, self.i)
        saved = self.i
        if peek_ident:
            names = [peek_ident.group(0)]
            self.i = peek_ident.end()
            ok = True
            while True:
                self.skip_ws()
                if self.peek() == ",":
                    self.i += 1
                    self.skip_ws()
                    nxt = _IDENT_RE.match(self.s, self.i)
                    if not nxt:
                        ok = False
                        break
                    names.append(nxt.group(0))
                    self.i = nxt.end()
                    continue
                if self.peek() == ")":
                    self.i += 1
                    self.skip_ws()
                    if self.s.startswith("=>", self.i):
                        self.i += 2
                        return self._make_arrow(names)
                    break
                ok = False
                break
            if not ok:
                self.i = saved
        self.i = start + 1
        val = self.parse_expr()
        self.skip_ws()
        self._need(")")
        return val

    def _make_arrow(self, params: list) -> _Fn:
        self.skip_ws()
        if self.peek() == "{":
            start = self.i
            self.i = _skip_pair(self.s, self.i, "{", "}") + 1
            return _Fn(params, self.s[start:self.i], "block", self)
        before = self.i
        prev = self.skip_eval
        self.skip_eval = True
        try:
            self.parse_expr()
        finally:
            self.skip_eval = prev
        return _Fn(params, self.s[before:self.i], "expr", self)

    def _parse_array(self) -> list:
        self._need("[")
        items = []
        while True:
            self.skip_ws()
            if self.peek() == "]":
                self.i += 1
                return items
            val = self.parse_expr()
            if isinstance(val, tuple) and val and val[0] == "...":
                extra = val[1]
                if isinstance(extra, list):
                    items.extend(extra)
                elif extra is not None:
                    items.append(extra)
            else:
                items.append(val)
            self.skip_ws()
            if self.peek() == ",":
                self.i += 1
                continue
            if self.peek() == "]":
                self.i += 1
                return items
            raise _ParseError("array")

    def _parse_object(self) -> dict:
        self._need("{")
        out = {}
        while True:
            self.skip_ws()
            if self.peek() == "}":
                self.i += 1
                return out
            if self.s.startswith("...", self.i):
                self.i += 3
                extra = self.parse_expr()
                if isinstance(extra, dict):
                    out.update(extra)
            elif self.peek() == "[":
                self.i += 1
                key = self.parse_expr()
                self.skip_ws()
                self._need("]")
                self.skip_ws()
                self._need(":")
                out[key] = self.parse_expr()
            elif self._is("\"'"):
                key = self._read_string()
                self.skip_ws()
                self._need(":")
                out[key] = self.parse_expr()
            else:
                key = self._read_ident()
                self.skip_ws()
                if self.peek() == ":":
                    self.i += 1
                    out[key] = self.parse_expr()
                else:
                    out[key] = self.env.get(key)
            self.skip_ws()
            if self.peek() == ",":
                self.i += 1
                continue
            if self.peek() == "}":
                self.i += 1
                return out
            raise _ParseError("object")

    def _parse_jsx(self) -> _Node:
        self._need("<")
        name = self._read_ident()
        props = {}
        self.skip_ws()
        while self.peek() and self.peek() not in ">/":
            key = self._read_ident()
            self.skip_ws()
            if self.peek() != "=":
                props[key] = True
            else:
                self.i += 1
                self.skip_ws()
                if self._is("\"'"):
                    props[key] = self._read_string()
                else:
                    self._need("{")
                    props[key] = self.parse_expr()
                    self.skip_ws()
                    self._need("}")
            self.skip_ws()
        if self.s.startswith("/>", self.i):
            self.i += 2
            return _Node(name, props, [])
        self._need(">")
        children = []
        while True:
            self.skip_ws()
            if not self.peek():
                raise _ParseError("unclosed jsx")
            if self.s.startswith("</", self.i):
                self.i += 2
                self._read_ident()
                self.skip_ws()
                self._need(">")
                break
            if self.peek() == "<":
                children.append(self._parse_jsx())
                continue
            if self.peek() == "{":
                self.i += 1
                self.skip_ws()
                if self.s.startswith("/*", self.i):
                    end = self.s.find("*/", self.i)
                    self.i = end + 2 if end >= 0 else len(self.s)
                    self.skip_ws()
                    self._need("}")
                    continue
                val = self.parse_expr()
                if isinstance(val, tuple) and val and val[0] == "...":
                    extra = val[1]
                    if isinstance(extra, list):
                        children.extend(extra)
                    elif extra is not None:
                        children.append(extra)
                elif val is not None and val is not False:
                    children.append(val)
                self.skip_ws()
                self._need("}")
                continue
            start = self.i
            while self.i < len(self.s) and self.s[self.i] not in "{<":
                self.i += 1
            text = self.s[start:self.i]
            if text.strip():
                children.append(_Node("#text", {"value": text}, []))
        return _Node(name, props, children)

    def _parse_args(self) -> list:
        self._need("(")
        args = []
        while True:
            self.skip_ws()
            if self.peek() == ")":
                self.i += 1
                return args
            args.append(self.parse_expr())
            self.skip_ws()
            if self.peek() == ",":
                self.i += 1
                continue
            if self.peek() == ")":
                self.i += 1
                return args
            raise _ParseError("args")

    def _parse_ident_list(self, left: str, right: str) -> list:
        self._need(left)
        names = []
        while True:
            self.skip_ws()
            if self.peek() == right:
                self.i += 1
                return names
            names.append(self._read_ident())
            self.skip_ws()
            if self.peek() == ",":
                self.i += 1
                continue
            if self.peek() == right:
                self.i += 1
                return names
            raise _ParseError("ident list")

    def _read_ident(self) -> str:
        self.skip_ws()
        m = _IDENT_RE.match(self.s, self.i)
        if not m:
            raise _ParseError("ident")
        self.i = m.end()
        return m.group(0)

    def _read_string(self) -> str:
        q = self.peek()
        end = _skip_string(self.s, self.i)
        raw = self.s[self.i + 1 : end]
        self.i = end + 1
        return raw.encode("utf-8").decode("unicode_escape") if "\\" in raw else raw

    def _read_template(self) -> str:
        self._need("`")
        out = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                out.append(self.s[self.i + 1])
                self.i += 2
                continue
            if c == "`":
                self.i += 1
                return "".join(out)
            if self.s.startswith("${", self.i):
                self.i += 2
                out.append(_js_str(self.parse_expr()))
                self.skip_ws()
                self._need("}")
                continue
            out.append(c)
            self.i += 1
        raise _ParseError("template")

    def _read_number(self):
        m = re.match(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", self.s[self.i :])
        if not m:
            raise _ParseError("number")
        self.i += m.end()
        raw = m.group(0)
        return float(raw) if "." in raw or "e" in raw.lower() else int(raw)

    def _starts_kw(self, word: str) -> bool:
        self.skip_ws()
        if not self.s.startswith(word, self.i):
            return False
        end = self.i + len(word)
        if end < len(self.s) and (self.s[end].isalnum() or self.s[end] in "_$"):
            return False
        return True

    def _eat(self, token: str) -> bool:
        self.skip_ws()
        if self.s.startswith(token, self.i):
            end = self.i + len(token)
            if token.isalpha() and end < len(self.s) and (self.s[end].isalnum() or self.s[end] in "_$"):
                return False
            self.i = end
            return True
        return False

    def _need(self, token: str):
        if not self._eat(token):
            raise _ParseError(self._err(f"expected {token}"))

    def _need_kw(self, word: str):
        if not self._starts_kw(word):
            raise _ParseError(self._err(f"expected {word}"))
        self.i += len(word)

    def _err(self, msg: str) -> str:
        lo = max(0, self.i - 50)
        hi = min(len(self.s), self.i + 50)
        return f"{msg} at {self.i}: {self.s[lo:hi]!r}"


_NO_RETURN = object()
_MISSING = object()


def _js_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _get_prop(obj, key):
    if obj is None:
        return None
    if isinstance(obj, _Fn) or callable(obj):
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    if isinstance(obj, list):
        if key == "length":
            return len(obj)
        if key == "map":
            return ("__map", obj)
        if key == "find":
            return ("__find", obj)
        if key == "filter":
            return ("__filter", obj)
        if isinstance(key, int) and 0 <= key < len(obj):
            return obj[key]
        return None
    if isinstance(obj, (int, float)):
        if key == "toFixed":
            return ("__toFixed", obj)
        if key == "toLocaleString":
            return ("__toLocaleString", obj)
    if isinstance(obj, str):
        if key == "length":
            return len(obj)
    return None


def _call(fn, args, env):
    if isinstance(fn, _Fn):
        return fn(args, env)
    if callable(fn):
        return fn(*args)
    if isinstance(fn, tuple):
        kind, target = fn
        if kind == "__map":
            cb = args[0]
            out = []
            for i, item in enumerate(target):
                out.append(_call(cb, [item, i], env) if isinstance(cb, _Fn) else cb)
            return out
        if kind == "__find":
            cb = args[0]
            for item in target:
                if _call(cb, [item], env):
                    return item
            return None
        if kind == "__filter":
            cb = args[0]
            return [item for item in target if _call(cb, [item], env)]
        if kind == "__toFixed":
            digits = int(args[0]) if args else 0
            return f"{float(target):.{digits}f}"
        if kind == "__toLocaleString":
            if isinstance(target, float) and target != int(target):
                return f"{target:,}"
            return f"{int(target):,}"
    raise _ParseError(f"not callable: {fn!r}")


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
    if node is None or node is False:
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
        justify = {
            "start": "flex-start",
            "end": "flex-end",
            "space-between": "space-between",
            "center": "center",
        }.get(props.get("justify"), props.get("justify"))
        if justify:
            extra += f";justify-content:{justify}"
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
    if name == "BarChart":
        return _render_bars(props)
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
    aligns = props.get("columnAlign") or []
    striped = bool(props.get("striped"))

    def cell(value) -> str:
        if value is None:
            return ""
        if isinstance(value, _Node):
            return _render(value)
        return _rich_text(str(value))

    def align_attr(index: int) -> str:
        if index >= len(aligns) or not aligns[index]:
            return ""
        return f' style="text-align:{html.escape(str(aligns[index]))}"'

    ths = "".join(
        f"<th{align_attr(i)}>{cell(h)}</th>" for i, h in enumerate(headers)
    )
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
            tds.append(f"<td{align_attr(j)}>{dot}{cell(item)}</td>")
        while headers and len(tds) < len(headers):
            tds.append(f"<td{align_attr(len(tds))}></td>")
        cls_attr = f' class="{" ".join(cls)}"' if cls else ""
        body.append(f"<tr{cls_attr}>{''.join(tds)}</tr>")
    return (
        '<div class="cv-table-wrap"><table class="cv-table">'
        f"<thead><tr>{ths}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


_BAR_COLORS = [
    "#4a63f0",
    "#7b849c",
    "#0f9d78",
    "#c48412",
    "#9a6bdb",
    "#d64545",
    "#3d8ea8",
    "#b5651d",
]


def _render_bars(props: dict) -> str:
    categories = props.get("categories") or []
    series = props.get("series") or []
    y_max = float(props.get("yMax") or 100) or 100
    height = int(props.get("height") or 260)
    suffix = props.get("valueSuffix") or ""
    groups = []
    for ci, cat in enumerate(categories):
        bars = []
        for si, item in enumerate(series):
            if not isinstance(item, dict):
                continue
            data = item.get("data") or []
            raw = data[ci] if ci < len(data) else 0
            try:
                val = float(raw)
            except (TypeError, ValueError):
                val = 0
            pct = max(0, min(100, val / y_max * 100))
            color = (
                "#4a63f0"
                if item.get("tone") == "info"
                else _BAR_COLORS[(si + 1) % len(_BAR_COLORS)]
            )
            title = html.escape(f"{item.get('name', '')} · {cat}: {val}{suffix}")
            bars.append(
                f'<div class="cv-bar" style="height:{pct:.1f}%;background:{color}"'
                f' title="{title}"></div>'
            )
        groups.append(
            f'<div class="cv-bar-group">{"".join(bars)}'
            f'<div class="cv-bar-cat">{html.escape(str(cat))}</div></div>'
        )
    legend = []
    for si, item in enumerate(series):
        if not isinstance(item, dict):
            continue
        color = (
            "#4a63f0"
            if item.get("tone") == "info"
            else _BAR_COLORS[(si + 1) % len(_BAR_COLORS)]
        )
        legend.append(
            f'<span class="cv-bar-leg">'
            f'<i style="background:{color}"></i>'
            f'{html.escape(str(item.get("name", "")))}</span>'
        )
    return (
        f'<div class="cv-bars" style="height:{height}px">'
        f'<div class="cv-bars-plot">{"".join(groups)}</div></div>'
        f'<div class="cv-bars-legend">{"".join(legend)}</div>'
    )
