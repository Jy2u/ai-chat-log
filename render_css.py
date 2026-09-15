"""聊天页与思维导图页共用的 CSS。"""

from pygments.formatters import HtmlFormatter

_pygments_css = HtmlFormatter(style="monokai").get_style_defs(".codeblock")


_CSS = (
    """
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
    margin: 0;
    min-height: 100vh;
    background: linear-gradient(160deg, #d7e2ff 0%, #e8edfb 42%, #efe6f6 100%);
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    color: #262c3d;
    -webkit-font-smoothing: antialiased;
}
::selection { background: rgba(99, 125, 255, .3); }

/* 背景光斑：液态玻璃需要有色彩可供模糊透出 */
.blob {
    position: fixed; border-radius: 50%;
    filter: blur(90px); z-index: 0; pointer-events: none;
}
.b1 {
    width: 620px; height: 620px; top: -180px; left: -160px;
    background: rgba(124, 152, 255, .58);
    animation: drift1 26s ease-in-out infinite alternate;
}
.b2 {
    width: 540px; height: 540px; bottom: -200px; right: -140px;
    background: rgba(255, 158, 208, .48);
    animation: drift2 32s ease-in-out infinite alternate;
}
.b3 {
    width: 480px; height: 480px; top: 28%; left: 50%;
    background: rgba(118, 214, 213, .4);
    animation: drift3 38s ease-in-out infinite alternate;
}
@keyframes drift1 { to { transform: translate(70px, 50px) scale(1.1); } }
@keyframes drift2 { to { transform: translate(-60px, -40px) scale(1.06); } }
@keyframes drift3 { to { transform: translate(-80px, 60px); } }

.wrap {
    position: relative; z-index: 1;
    max-width: 920px; margin: 0 auto; padding: 8px 22px 40px;
}

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(122, 138, 185, .35); border-radius: 8px;
    border: 2px solid transparent; background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background-color: rgba(122, 138, 185, .6); }

.page-head, .search-head {
    display: flex; justify-content: center;
    margin: 22px 0 8px; user-select: none;
}
.search-head { justify-content: flex-start; margin: 24px 0 12px; }
.page-head span, .search-head span {
    background: rgba(255, 255, 255, .4);
    backdrop-filter: blur(14px) saturate(150%);
    -webkit-backdrop-filter: blur(14px) saturate(150%);
    border: 1px solid rgba(255, 255, 255, .6);
    border-radius: 999px; padding: 6px 18px;
    color: #7a84a2; font-size: 12px;
    box-shadow: 0 4px 14px rgba(90, 110, 180, .08);
}
.search-head span { font-size: 13px; color: #5d6684; }

.empty {
    text-align: center; color: #8a93ad; margin-top: 110px;
    font-size: 14px; line-height: 2; user-select: none;
    position: relative; z-index: 1;
}
.empty .big {
    width: 88px; height: 88px; line-height: 88px;
    margin: 0 auto 18px; font-size: 38px; border-radius: 50%;
    background: rgba(255, 255, 255, .45);
    backdrop-filter: blur(16px) saturate(150%);
    -webkit-backdrop-filter: blur(16px) saturate(150%);
    border: 1px solid rgba(255, 255, 255, .65);
    box-shadow: 0 12px 32px rgba(90, 110, 180, .14),
                inset 0 1px 0 rgba(255, 255, 255, .8);
}

.msg { display: flex; flex-direction: column; margin: 20px 0; scroll-margin-top: 18px; }
.msg.flash .bubble {
    animation: msgflash 1.1s ease;
}
@keyframes msgflash {
    0% { box-shadow: 0 0 0 3px rgba(74, 99, 240, .45); }
    100% { box-shadow: none; }
}
.msg.user { align-items: flex-end; }
.msg.ai { align-items: flex-start; }
.meta {
    font-size: 12px; color: #7f88a6; margin: 0 10px 6px;
    user-select: none;
}
.meta .role { font-weight: 600; }
.msg.user .meta .role { color: #4a63f0; }
.msg.ai .meta .role { color: #0f9d78; }
.ops { visibility: hidden; margin-left: 10px; }
.msg:hover .ops { visibility: visible; }
.ops a {
    color: #97a0bb; text-decoration: none; font-size: 11px;
    margin-left: 8px;
}
.ops a:hover { color: #4a63f0; }
.ops a.danger:hover { color: #e5484d; }

.bubble {
    max-width: 78%; padding: 12px 18px; border-radius: 20px;
    line-height: 1.7; font-size: 14.5px; overflow-wrap: anywhere;
}
.msg.user .bubble {
    background: linear-gradient(135deg,
        rgba(101, 128, 255, .85), rgba(72, 98, 242, .75));
    backdrop-filter: blur(18px) saturate(160%);
    -webkit-backdrop-filter: blur(18px) saturate(160%);
    border: 1px solid rgba(255, 255, 255, .4);
    border-bottom-right-radius: 7px;
    box-shadow: 0 10px 28px rgba(79, 110, 247, .3),
                inset 0 1px 0 rgba(255, 255, 255, .45);
    color: #fff;
}
.msg.ai .bubble {
    background: rgba(255, 255, 255, .52);
    backdrop-filter: blur(20px) saturate(150%);
    -webkit-backdrop-filter: blur(20px) saturate(150%);
    border: 1px solid rgba(255, 255, 255, .65);
    border-bottom-left-radius: 7px;
    box-shadow: 0 10px 28px rgba(80, 100, 160, .12),
                inset 0 1px 0 rgba(255, 255, 255, .8);
}
.bubble > :first-child { margin-top: 0; }
.bubble > :last-child { margin-bottom: 0; }
.bubble p { margin: .55em 0; }
.bubble h1, .bubble h2, .bubble h3 { margin: .8em 0 .4em; }
.bubble h1 { font-size: 1.25em; } .bubble h2 { font-size: 1.15em; }
.bubble h3 { font-size: 1.05em; }
.bubble ul, .bubble ol { margin: .4em 0; padding-left: 1.5em; }
.bubble li { margin: .2em 0; }
.bubble a { color: #4a63f0; }
.msg.user .bubble a { color: #e3eaff; }
.bubble blockquote {
    margin: .5em 0; padding: 4px 14px;
    border-left: 3px solid rgba(124, 145, 255, .55);
    background: rgba(255, 255, 255, .25); border-radius: 8px;
    color: #5d6684;
}
.msg.user .bubble blockquote {
    border-left-color: rgba(255, 255, 255, .55);
    background: rgba(255, 255, 255, .12); color: #e6ecff;
}
.bubble code {
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 13px; background: rgba(255, 255, 255, .55);
    border: 1px solid rgba(140, 155, 200, .3);
    color: #c7254e; padding: 1px 6px; border-radius: 6px;
}
.msg.user .bubble code {
    background: rgba(255, 255, 255, .22);
    border-color: rgba(255, 255, 255, .3); color: #fff;
}
.bubble pre.codeblock {
    position: relative;
    background: rgba(24, 27, 39, .86);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, .14);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .1);
    color: #f8f8f2;
    border-radius: 14px; padding: 28px 15px 13px;
    overflow-x: auto; margin: .6em 0;
}
.bubble pre.codeblock::before {
    content: attr(data-lang);
    position: absolute; top: 7px; right: 14px;
    font-size: 11px; color: #98a0b8; user-select: none;
}
.bubble pre.codeblock code {
    background: none; border: none; color: inherit;
    padding: 0; border-radius: 0;
    font-size: 13px; line-height: 1.55; white-space: pre;
}
.bubble table {
    border-collapse: collapse; margin: .6em 0; font-size: 13.5px;
    display: block; overflow-x: auto; max-width: 100%;
}
.bubble th, .bubble td {
    border: 1px solid rgba(122, 140, 200, .3);
    padding: 5px 12px; text-align: left;
}
.bubble th { background: rgba(255, 255, 255, .5); }
.msg.user .bubble th, .msg.user .bubble td {
    border-color: rgba(255, 255, 255, .4);
}
.msg.user .bubble th { background: rgba(255, 255, 255, .18); }
.bubble hr {
    border: none; border-top: 1px solid rgba(122, 140, 200, .3);
    margin: .8em 0;
}
.bubble img { max-width: 100%; border-radius: 10px; }
.bubble.image-bubble { padding: 6px; }
.msg.ai .bubble.canvas-bubble {
    max-width: min(1140px, 100%);
    width: 100%;
    padding: 18px 20px;
}
.cv { color: #262c3d; }
.cv-stack { display: flex; flex-direction: column; }
.cv-row { display: flex; align-items: center; }
.cv-grid { display: grid; }
.cv-h1 { font-size: 1.45em; margin: 0 0 .15em; font-weight: 700; }
.cv-h2 { font-size: 1.18em; margin: .2em 0 .1em; font-weight: 700; }
.cv-h3 { font-size: 1.02em; margin: .15em 0 .05em; font-weight: 650; }
.cv-text { margin: 0; line-height: 1.7; }
.cv-tone-secondary, .cv-tone-tertiary { color: #6a738c; }
.cv-tone-tertiary { opacity: .85; }
.cv-size-small { font-size: 12.5px; }
.cv-pill {
    display: inline-flex; align-items: center;
    padding: 3px 10px; border-radius: 999px; font-size: 12px;
    background: rgba(255,255,255,.7);
    border: 1px solid rgba(140,155,200,.35); color: #4a5166;
}
.cv-pill.on {
    background: rgba(74,99,240,.16);
    border-color: rgba(74,99,240,.35); color: #3d54d6;
}
.cv-pill.sm { font-size: 11px; padding: 2px 8px; }
.cv-card {
    background: rgba(255,255,255,.55);
    border: 1px solid rgba(255,255,255,.75);
    border-radius: 14px; overflow: hidden;
}
.cv-card-head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; padding: 10px 14px 0; font-weight: 650;
}
.cv-card-title { flex: 1; }
.cv-card-body { padding: 10px 14px 14px; }
.cv-callout {
    border-radius: 12px; padding: 12px 14px;
    border: 1px solid rgba(74,99,240,.22);
    background: rgba(74,99,240,.08);
}
.cv-callout.success { background: rgba(15,157,120,.08); border-color: rgba(15,157,120,.25); }
.cv-callout.warning { background: rgba(214,140,20,.10); border-color: rgba(214,140,20,.28); }
.cv-callout.danger { background: rgba(229,72,77,.08); border-color: rgba(229,72,77,.25); }
.cv-callout-title { font-weight: 700; margin-bottom: 4px; }
.cv-stat { min-width: 120px; }
.cv-stat-val { font-size: 1.35em; font-weight: 750; line-height: 1.2; }
.cv-stat-lab { font-size: 12px; color: #6a738c; margin-top: 2px; }
.cv-stat.success .cv-stat-val { color: #0f9d78; }
.cv-stat.warning .cv-stat-val { color: #c48412; }
.cv-stat.danger .cv-stat-val { color: #d64545; }
.cv-hr { border: none; border-top: 1px solid rgba(140,155,200,.35); margin: 8px 0; }
.cv-spacer { flex: 1; }
.cv-table-wrap { overflow-x: auto; border: 1px solid rgba(140,155,200,.28); border-radius: 12px; }
.cv-table { width: 100%; border-collapse: collapse; font-size: 13px; display: table; }
.cv-table th, .cv-table td {
    border: none; border-bottom: 1px solid rgba(140,155,200,.2);
    padding: 8px 10px; vertical-align: top; text-align: left;
}
.cv-table th { background: rgba(255,255,255,.55); font-weight: 650; }
.cv-table tr.stripe td { background: rgba(255,255,255,.28); }
.cv-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    margin-right: 6px; vertical-align: middle;
    background: #8b94ad;
}
.cv-dot.success { background: #0f9d78; }
.cv-dot.warning { background: #d69a12; }
.cv-dot.danger { background: #e5484d; }
.cv-dot.info { background: #4a63f0; }
.cv-dot.neutral { background: #8b94ad; }
.cv-bars { display: flex; flex-direction: column; }
.cv-bars-plot {
    display: flex; align-items: stretch; justify-content: space-around;
    gap: 18px; flex: 1; min-height: 180px; padding: 8px 8px 0;
    border-bottom: 1px solid rgba(140,155,200,.28);
}
.cv-bar-group {
    display: flex; align-items: flex-end; justify-content: center;
    gap: 3px; flex: 1; position: relative; padding-bottom: 22px;
}
.cv-bar { width: 10px; min-height: 2px; border-radius: 3px 3px 0 0; }
.cv-bar-cat {
    position: absolute; left: 0; right: 0; bottom: 0;
    text-align: center; font-size: 11px; color: #6a738c;
}
.cv-bars-legend {
    display: flex; flex-wrap: wrap; gap: 8px 14px;
    margin: 10px 0 0; font-size: 12px; color: #4a5166;
}
.cv-bar-leg { display: inline-flex; align-items: center; gap: 6px; }
.cv-bar-leg i {
    width: 8px; height: 8px; border-radius: 2px; display: inline-block;
}
.msg-img {
    display: block; max-width: 100%; max-height: 420px;
    border-radius: 14px; cursor: zoom-in;
}

.session-tag {
    font-size: 12px; color: #8a93ad; margin: 0 10px 6px;
    user-select: none;
}
.trash-bar {
    text-align: right; margin: 0 10px 14px; font-size: 13px;
}
.trash-bar a {
    display: inline-block; padding: 6px 12px; border-radius: 9px;
    color: #e5484d; text-decoration: none; font-weight: 600;
    background: rgba(229, 72, 77, .08); border: 1px solid rgba(229, 72, 77, .28);
}
.trash-bar a:hover { background: rgba(229, 72, 77, .16); }
.trash-item {
    display: flex; align-items: center; gap: 16px;
    margin: 0 10px 10px; padding: 14px 16px;
    background: rgba(255, 255, 255, .62);
    border: 1px solid rgba(255, 255, 255, .85);
    border-radius: 14px;
    box-shadow: 0 6px 18px rgba(31, 38, 135, .06);
}
.trash-item .meta { flex: 1; min-width: 0; }
.trash-item .kind {
    font-size: 11px; color: #6b75d8; font-weight: 600;
}
.trash-item .name {
    margin-top: 2px; font-size: 15px; font-weight: 600; color: #2c3345;
}
.trash-item .sub { margin-top: 4px; font-size: 12px; color: #8a93ad; }
.trash-ops { flex-shrink: 0; display: flex; gap: 8px; }
.trash-ops a {
    display: inline-block; padding: 6px 12px; border-radius: 9px;
    color: #4b64e0; text-decoration: none; font-size: 13px; font-weight: 600;
    background: rgba(74, 99, 240, .1); border: 1px solid rgba(74, 99, 240, .22);
}
.trash-ops a:hover { background: rgba(74, 99, 240, .18); }
.trash-ops a.danger {
    color: #e5484d; background: rgba(229, 72, 77, .08);
    border-color: rgba(229, 72, 77, .28);
}
.trash-ops a.danger:hover { background: rgba(229, 72, 77, .16); }
.session-tag a { color: #4b64e0; text-decoration: none; }
.session-tag a:hover { text-decoration: underline; }

html.chat-ui .wrap { padding-right: 196px; max-width: 1100px; }
.chat-nav {
    position: fixed; z-index: 6;
    right: 12px; top: 64px; bottom: 22px;
    width: 172px;
    display: flex; flex-direction: column;
    padding: 12px 8px 10px;
    background: rgba(255, 255, 255, .56);
    backdrop-filter: blur(22px) saturate(170%);
    -webkit-backdrop-filter: blur(22px) saturate(170%);
    border: 1px solid rgba(255, 255, 255, .88);
    border-radius: 20px;
    box-shadow: 0 12px 32px rgba(31, 38, 135, .12),
                inset 0 1px 0 rgba(255, 255, 255, .9);
}
.chat-nav-title {
    font-size: 11px; color: #8b94ad; letter-spacing: .04em;
    padding: 0 8px 8px; user-select: none; flex-shrink: 0;
}
.chat-nav-list {
    flex: 1; min-height: 0; overflow: auto; padding: 0 2px 4px;
}
.chat-nav-item {
    position: relative; display: block; margin: 0 0 6px;
    padding: 10px 30px 10px 10px;
    border-radius: 12px; text-decoration: none; color: #3a4152;
    background: rgba(74, 99, 240, .09);
    border: 1px solid rgba(255, 255, 255, .55);
}
.chat-nav-item:hover { background: rgba(255, 255, 255, .88); }
.chat-nav-item.on {
    background: rgba(74, 99, 240, .18);
    border-color: rgba(74, 99, 240, .28);
    box-shadow: 0 0 0 1px rgba(74, 99, 240, .12);
}
.chat-nav-num {
    position: absolute; top: 6px; right: 6px;
    min-width: 20px; height: 20px; padding: 0 5px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 999px; box-sizing: border-box;
    font-size: 11px; font-weight: 700; color: #fff;
    background: #4a63f0;
    box-shadow: 0 2px 6px rgba(74, 99, 240, .35);
}
.chat-nav-item.on .chat-nav-num { background: #3550e6; }
.chat-nav-text {
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
    overflow: hidden; font-size: 12px; line-height: 1.4;
}

.tex-display {
    display: block; text-align: center;
    margin: .75em 0; overflow-x: auto; overflow-y: hidden;
    padding: 4px 0;
}
.tex-inline { display: inline; }
.bubble .tex-display, .bubble .tex-inline, .bubble .katex {
    overflow-wrap: normal; word-break: normal;
}
.bubble .katex-display { margin: .35em 0; }

.wrap-wide { max-width: none; padding: 12px 18px 0; }
html.mm-ui, html.mm-ui body {
    overflow: hidden; height: 100%; margin: 0;
    overscroll-behavior: none;
}
.mm-hint {
    text-align: center; color: #7f88a6; font-size: 12px;
    margin: 8px 0 16px; user-select: none;
    position: relative; z-index: 3; pointer-events: none;
}
.page-head { cursor: default; position: relative; z-index: 3; pointer-events: none; }
body.mm-drag, body.mm-drag .mm-viewport { cursor: grabbing; user-select: none; }
body.mm-boxing, body.mm-boxing .mm-viewport { cursor: crosshair; user-select: none; }
.mm-marquee {
    position: fixed; z-index: 40; pointer-events: none;
    box-sizing: border-box;
    border: 1.5px solid rgba(74, 99, 240, .92);
    background: rgba(74, 99, 240, .14);
}
.mm-viewport {
    position: fixed; inset: 0; z-index: 1;
    overflow: hidden; cursor: grab;
}
.mm-pan {
    position: absolute; left: 0; top: 0;
}
.mm-world {
    position: relative;
}
.mm-canvas { position: relative; overflow: visible; }
.mm-lines { position: absolute; inset: 0; overflow: visible; pointer-events: none; }
.mm-edge-hit {
    pointer-events: stroke; cursor: pointer;
}
.mm-edge.hl .mm-edge-line {
    stroke: #ff8a2a;
    stroke-width: 2.6;
    filter: drop-shadow(0 0 3px rgba(255, 150, 50, .95))
            drop-shadow(0 0 10px rgba(255, 140, 40, .55));
}
.mm-edge.selected .mm-edge-line {
    stroke: #4a63f0; stroke-width: 3;
    filter: none;
}
.mm-edge-label.hl {
    color: #c45a08;
    border-color: rgba(255, 160, 60, .75);
    box-shadow: 0 0 12px rgba(255, 145, 45, .4);
}
.mm-edge-label.selected {
    color: #405de6;
    border-color: rgba(74, 99, 240, .55);
}
.mm-handle {
    position: absolute; z-index: 6;
    width: 14px; height: 14px; margin: -7px 0 0 -7px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid #4a63f0;
    box-shadow: 0 1px 6px rgba(74, 99, 240, .35);
    cursor: grab; display: none;
}
.mm-handle.on { display: block; }
body.mm-relink .mm-handle { cursor: grabbing; }
.mm-node.mm-drop {
    outline: 2px solid #4a63f0;
    outline-offset: 2px;
}
.mm-node.selected {
    outline: 2px solid #4a63f0;
    outline-offset: 2px;
}
.mm-port {
    position: absolute; z-index: 7;
    width: 14px; height: 14px; margin: -7px 0 0 -7px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid #4a63f0;
    box-shadow: 0 0 0 3px rgba(74, 99, 240, .28);
    cursor: crosshair; display: none;
}
.mm-port.on { display: block; }
.mm-resize {
    position: absolute; z-index: 8;
    width: 10px; height: 10px; margin: -5px 0 0 -5px;
    border-radius: 2px;
    background: #fff;
    border: 2px solid #4a63f0;
    box-shadow: 0 0 0 3px rgba(74, 99, 240, .22);
    display: none;
}
.mm-resize.on { display: block; }
.mm-resize[data-corner="nw"], .mm-resize[data-corner="se"] { cursor: nwse-resize; }
.mm-resize[data-corner="ne"], .mm-resize[data-corner="sw"] { cursor: nesw-resize; }
.mm-node.mm-sized { overflow: auto; }
.mm-draw-line {
    fill: none; stroke: #4a63f0; stroke-width: 2;
    stroke-dasharray: 6 4; pointer-events: none;
}
.mm-edge-label {
    position: absolute; z-index: 2;
    transform: translate(-50%, -50%);
    max-width: 168px; padding: 3px 10px;
    font-size: 12px; line-height: 1.35; text-align: center;
    color: #4b5570;
    background: rgba(255, 255, 255, .58);
    backdrop-filter: blur(14px) saturate(160%);
    -webkit-backdrop-filter: blur(14px) saturate(160%);
    border: 1px solid rgba(255, 255, 255, .88);
    border-top: 1px solid rgba(255, 255, 255, 1);
    border-radius: 10px;
    box-shadow: 0 6px 16px rgba(31, 38, 135, .08);
    pointer-events: auto; cursor: pointer;
    overflow-wrap: anywhere; white-space: pre-wrap;
    user-select: none;
}
.mm-edge-label:empty { display: none; }
.mm-node {
    position: absolute; box-sizing: border-box;
    height: auto;
    overflow: visible;
    padding: 10px 14px;
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255, 255, 255, .7), rgba(255, 255, 255, .42));
    backdrop-filter: blur(26px) saturate(180%);
    -webkit-backdrop-filter: blur(26px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, .82);
    border-top: 1px solid rgba(255, 255, 255, 1);
    box-shadow: 0 10px 26px rgba(31, 38, 135, .1),
                inset 0 1px 1px rgba(255, 255, 255, .9);
    color: #1d2335;
    cursor: grab;
}
.mm-node.root, .mm-node.box, .mm-node.text {
    display: flex;
    align-items: center;
    justify-content: center;
}
.mm-node.mm-prose {
    align-items: stretch;
    justify-content: flex-start;
}
.mm-node.root {
    background: linear-gradient(180deg, rgba(168, 188, 255, .48), rgba(96, 122, 255, .26));
    border-color: rgba(255, 255, 255, .9);
    color: #24357a;
    box-shadow: 0 12px 28px rgba(74, 99, 240, .16),
                inset 0 1px 1px rgba(255, 255, 255, .75);
}
.mm-node.text {
    background: transparent;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    box-shadow: none;
    border: 1px dashed rgba(120, 135, 175, .65);
    border-radius: 8px;
    padding: 6px 8px;
}
.mm-body {
    font-size: 13.5px; line-height: 1.45;
    overflow-wrap: anywhere; word-break: break-word;
    white-space: pre-wrap;
    outline: none; min-height: 1.2em; min-width: 0;
}
.mm-body:empty::before {
    content: "双击编辑"; color: #b0b8cc; font-weight: normal;
}
.mm-node.root .mm-body, .mm-node.box .mm-body, .mm-node.text .mm-body {
    font-weight: 600; text-align: center; width: 100%;
    display: block;
}
.mm-node.mm-prose .mm-body {
    text-align: left;
    font-weight: 500;
}
.mm-node.root.mm-prose .mm-body { font-weight: bold; }
.mm-node.root .mm-body { font-weight: bold; font-size: 15px; }
.mm-node.text .mm-body { font-weight: normal; }
.mm-body .tex-inline, .mm-body .tex-display, .mm-body .katex,
.mm-body .katex-display {
    overflow-wrap: normal; word-break: normal; white-space: normal;
}
.mm-body .tex-display, .mm-body .katex-display { margin: .35em 0; }
.mm-node.hl {
    border-color: rgba(255, 175, 80, .95);
    box-shadow: 0 0 0 1px rgba(255, 150, 50, .55),
                0 0 14px 4px rgba(255, 145, 40, .42),
                0 0 28px 8px rgba(255, 140, 40, .22),
                0 8px 22px rgba(31, 38, 135, .08),
                inset 0 1px 1px rgba(255, 255, 255, .85);
}
.mm-node.text.hl {
    box-shadow: 0 0 0 1px rgba(255, 150, 50, .4),
                0 0 14px 4px rgba(255, 145, 40, .42),
                0 0 28px 8px rgba(255, 140, 40, .22);
}
.mm-menu {
    position: fixed; z-index: 20; min-width: 132px;
    background: rgba(248, 250, 255, .72);
    backdrop-filter: blur(18px) saturate(160%);
    -webkit-backdrop-filter: blur(18px) saturate(160%);
    border: 1px solid rgba(255, 255, 255, .88);
    border-top: 1px solid rgba(255, 255, 255, 1);
    border-radius: 14px; padding: 6px;
    box-shadow: 0 12px 30px rgba(31, 38, 135, .14);
}
.mm-menu button {
    display: block; width: 100%; text-align: left;
    background: transparent; border: none; border-radius: 8px;
    padding: 8px 14px; color: #2c3345; font-size: 13px; cursor: pointer;
    font-family: inherit;
}
.mm-menu button:hover { background: rgba(100, 140, 255, .15); color: #4a63f0; }
.mm-menu button.danger:hover { color: #e5484d; background: rgba(229, 72, 77, .1); }
.mm-menu-meta {
    padding: 3px 14px;
    color: #7a84a2;
    font-size: 11px;
    line-height: 1.45;
    pointer-events: none;
    user-select: none;
}
.mm-menu-sep {
    height: 1px;
    margin: 5px 8px 6px;
    background: rgba(130, 145, 190, 0.22);
}

html.doc-ui, html.doc-ui body {
    overflow: hidden; height: 100%; margin: 0;
}
html.doc-ui .wrap-wide {
    height: 100vh; display: flex; flex-direction: column;
    padding: 8px 16px 12px;
}
html.doc-ui .page-head { margin: 10px 0 8px; }
.doc-split {
    flex: 1; min-height: 0;
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
}
.doc-src {
    width: 100%; height: 100%; resize: none; border: none;
    border-radius: 16px; padding: 14px 16px;
    background: rgba(255, 255, 255, .78);
    box-shadow: 0 8px 28px rgba(31, 38, 135, .08);
    font-family: Consolas, "Cascadia Mono", "Microsoft YaHei", monospace;
    font-size: 14px; line-height: 1.55; color: #262c3d; outline: none;
}
.doc-src:focus {
    box-shadow: 0 8px 28px rgba(74, 99, 240, .16);
}
.doc-preview-wrap {
    overflow: auto; border-radius: 16px;
    background: rgba(255, 255, 255, .62);
    box-shadow: 0 8px 28px rgba(31, 38, 135, .08);
}
.doc-preview { padding: 10px 18px 28px; line-height: 1.7; font-size: 14.5px; }
.doc-preview .empty { margin-top: 48px; }
.doc-preview h1, .doc-preview h2, .doc-preview h3,
.doc-preview h4, .doc-preview h5, .doc-preview h6 { margin: .8em 0 .4em; }
.doc-preview h1 { font-size: 1.45em; }
.doc-preview h2 { font-size: 1.28em; }
.doc-preview h3 { font-size: 1.12em; }
.doc-preview p { margin: .55em 0; }
.doc-preview ul, .doc-preview ol { margin: .4em 0 .4em 1.3em; }
.doc-preview blockquote {
    margin: .6em 0; padding: .2em .9em;
    border-left: 3px solid rgba(74, 99, 240, .55);
    color: #4a5166; background: rgba(74, 99, 240, .08);
}
.doc-preview table { border-collapse: collapse; margin: .6em 0; }
.doc-preview th, .doc-preview td {
    border: 1px solid rgba(165, 175, 205, .65); padding: 4px 10px;
}
.doc-preview hr {
    border: none; border-top: 1px solid rgba(165, 175, 205, .55); margin: 1em 0;
}
.doc-preview a { color: #4a63f0; }
"""
    + _pygments_css
)

