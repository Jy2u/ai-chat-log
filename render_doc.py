"""文档页（Markdown 编辑 + 预览）与语法说明。"""

import html
import json

from render import _page, md_to_html


_DOC_JS = r"""
(function () {
    document.documentElement.classList.add("doc-ui");
    var ta = document.getElementById("doc-src");
    if (!ta) return;
    var did = ta.getAttribute("data-id");
    var timer = null;
    function save() {
        location.href = "app://savedoc/" + did + "#" + encodeURIComponent(ta.value);
    }
    ta.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(save, 420);
    });
    ta.addEventListener("blur", save);
    window.__docPreview = function (html) {
        var el = document.getElementById("doc-preview");
        if (!el) return;
        el.innerHTML = html || '<div class="empty">还没有内容，左边写 Markdown</div>';
        if (!window.katex) return;
        el.querySelectorAll(".tex-display, .tex-inline").forEach(function (node) {
            katex.render(node.textContent, node, {
                displayMode: node.classList.contains("tex-display"),
                throwOnError: false
            });
        });
    };
    ta.focus();
})();
"""


def build_document_page(doc: dict) -> str:
    name = html.escape(doc.get("name") or "文档")
    raw = doc.get("content") or ""
    preview = md_to_html(raw) if raw.strip() else (
        '<div class="empty">还没有内容，左边写 Markdown，右边即时预览</div>'
    )
    head = (
        '<div class="page-head"><span>'
        f'文档「{name}」 · Markdown · 左侧编辑，右侧预览</span></div>'
    )
    body = (
        head
        + '<div class="doc-split">'
        + '<textarea id="doc-src" class="doc-src" data-id="'
        + str(doc["id"])
        + '" spellcheck="false" placeholder="在这里用 Markdown 写作，例如：# 一级标题">'
        + html.escape(raw)
        + "</textarea>"
        + '<div class="doc-preview-wrap"><div id="doc-preview" class="doc-preview">'
        + preview
        + "</div></div></div>"
    )
    return _page(body, scroll_bottom=False, wide=True, extra_js=_DOC_JS)


def document_preview_js(html_fragment: str) -> str:
    return "window.__docPreview && window.__docPreview(" + json.dumps(html_fragment) + ")"


def markdown_help_html() -> str:
    """给语法说明弹窗用的 HTML（含样例）。"""
    rows = [
        ("一级标题", "# 加空格", "# 这是一级标题", "<h1>这是一级标题</h1>"),
        ("二级标题", "## 加空格", "## 这是二级标题", "<h2>这是二级标题</h2>"),
        ("三级标题", "### 加空格", "### 这是三级标题", "<h3>这是三级标题</h3>"),
        ("四级标题", "#### 加空格", "#### 这是四级标题", "<h4>这是四级标题</h4>"),
        ("五级标题", "##### 加空格", "##### 这是五级标题", "<h5>这是五级标题</h5>"),
        ("六级标题", "###### 加空格", "###### 这是六级标题", "<h6>这是六级标题</h6>"),
        ("加粗", "两侧各两个星号", "**加粗文字**", "<p><strong>加粗文字</strong></p>"),
        ("斜体", "两侧各一个星号", "*斜体文字*", "<p><em>斜体文字</em></p>"),
        ("删除线", "两侧各两个波浪号", "~~已删除~~", "<p><del>已删除</del></p>"),
        ("行内代码", "反引号包起来", "`print(1)`", "<p><code>print(1)</code></p>"),
        (
            "代码块",
            "三个反引号，可写语言名",
            "```python\nprint('hi')\n```",
            "<pre class='help-pre'>print('hi')</pre>",
        ),
        (
            "无序列表",
            "- 或 * 加空格",
            "- 苹果\n- 香蕉",
            "<ul><li>苹果</li><li>香蕉</li></ul>",
        ),
        (
            "有序列表",
            "数字. 加空格",
            "1. 第一步\n2. 第二步",
            "<ol><li>第一步</li><li>第二步</li></ol>",
        ),
        ("引用", "> 加空格", "> 这是引用", "<blockquote>这是引用</blockquote>"),
        (
            "链接",
            "[文字](网址)",
            "[示例](https://example.com)",
            "<p><a>示例</a></p>",
        ),
        (
            "图片",
            "![说明](图片地址)",
            "![示意图](https://example.com/a.png)",
            "<p>渲染为图片</p>",
        ),
        (
            "表格",
            "竖线分隔，第二行是对齐线",
            "| 列一 | 列二 |\n| --- | --- |\n| 甲 | 乙 |",
            "<table><tr><th>列一</th><th>列二</th></tr>"
            "<tr><td>甲</td><td>乙</td></tr></table>",
        ),
        (
            "分割线",
            "三个或更多减号",
            "---",
            "<hr>",
        ),
        (
            "行内公式",
            "单个美元符号包起来",
            r"$E = mc^2$",
            "<p><em>E = mc<sup>2</sup></em></p>",
        ),
        (
            "独立公式",
            "两个美元符号包起来",
            "$$\n\\sum_{i=1}^{n} i\n$$",
            "<p>居中公式</p>",
        ),
    ]
    items = []
    for title, rule, sample, shown in rows:
        items.append(
            "<div class='md-item'>"
            f"<div class='md-name'>{html.escape(title)}</div>"
            f"<div class='md-rule'>写法：{html.escape(rule)}</div>"
            "<div class='md-cols'>"
            "<div><div class='md-cap'>输入样例</div>"
            f"<pre>{html.escape(sample)}</pre></div>"
            f"<div><div class='md-cap'>效果</div><div class='md-out'>{shown}</div></div>"
            "</div></div>"
        )
    return f"""
<style>
body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
       color: #2c3345; background: #edf0fa; margin: 0; }}
.md-wrap {{ padding: 8px 4px 18px; }}
.md-lead {{ color: #5a6278; font-size: 13px; margin: 0 8px 14px; line-height: 1.6; }}
.md-item {{
    background: rgba(255,255,255,.82);
    border: 1px solid rgba(165,175,205,.45);
    border-radius: 12px; padding: 12px 14px; margin: 0 4px 10px;
}}
.md-name {{ font-weight: 700; font-size: 14px; color: #2a3144; }}
.md-rule {{ color: #5b647c; font-size: 12.5px; margin: 4px 0 8px; }}
.md-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.md-cap {{ font-size: 11px; color: #7a8298; margin-bottom: 4px; }}
pre, .help-pre {{
    margin: 0; white-space: pre-wrap; word-break: break-all;
    background: #1e2230; color: #e8ecf8; border-radius: 8px;
    padding: 8px 10px; font-size: 12.5px; font-family: Consolas, monospace;
}}
.md-out {{
    background: #f7f8fd; border-radius: 8px; padding: 6px 10px;
    border: 1px solid rgba(165,175,205,.35); font-size: 13px;
}}
.md-out h1, .md-out h2, .md-out h3, .md-out h4, .md-out h5, .md-out h6 {{
    margin: .2em 0;
}}
.md-out ul, .md-out ol {{ margin: .2em 0 .2em 1.2em; padding: 0; }}
.md-out blockquote {{
    margin: .2em 0; padding: .2em .8em; border-left: 3px solid #7a8cff;
    color: #4a5166; background: #eef1fb;
}}
.md-out table {{ border-collapse: collapse; }}
.md-out th, .md-out td {{
    border: 1px solid #c5cce0; padding: 3px 8px; font-size: 12.5px;
}}
.md-out code {{
    background: #eceff8; padding: 1px 5px; border-radius: 4px; font-size: 12.5px;
}}
</style>
<div class="md-wrap">
<p class="md-lead">文档使用 Markdown 语法。左边是写法，右边是大致效果。
标题必须是「#」后面跟一个空格，例如 <code># 标题</code>，不能写成 <code>#标题</code>。</p>
{''.join(items)}
</div>
"""
