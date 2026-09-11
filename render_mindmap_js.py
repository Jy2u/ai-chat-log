"""思维导图页面的前端脚本。"""

_MM_JS = r"""
(function () {
    document.documentElement.classList.add("mm-ui");
    var menu = document.createElement("div");
    menu.className = "mm-menu";
    menu.hidden = true;
    document.body.appendChild(menu);
    var marquee = document.createElement("div");
    marquee.className = "mm-marquee";
    marquee.hidden = true;
    document.body.appendChild(marquee);
    var currentId = null;
    var cam = { scale: 1, tx: 0, ty: 0 };
    var dragMoved = false;
    var boxing = false;
    var boxArmed = false;
    var boxStart = { x: 0, y: 0 };
    var multiSelect = false;
    var selectedNodeIds = {};
    var selectedEids = {};

    function hideMenu() { menu.hidden = true; }

    function applyView() {
        var pan = document.querySelector(".mm-pan");
        var canvas = document.querySelector(".mm-canvas");
        if (!pan || !canvas) return;
        pan.style.left = cam.tx + "px";
        pan.style.top = cam.ty + "px";
        canvas.style.zoom = (Math.abs(cam.scale - 1) < 0.001) ? "" : String(cam.scale);
    }

    function sendCam() {
        location.href = "app://setcam/0#" + encodeURIComponent(JSON.stringify({
            tx: cam.tx, ty: cam.ty, scale: cam.scale
        }));
    }

    function lineGeom(a, b, ov) {
        var x1 = parseFloat(a.style.left) + a.offsetWidth;
        var y1 = parseFloat(a.style.top) + a.offsetHeight / 2;
        var x2 = parseFloat(b.style.left);
        var y2 = parseFloat(b.style.top) + b.offsetHeight / 2;
        if (ov) {
            if (ov.end === "from") { x1 = ov.x; y1 = ov.y; }
            if (ov.end === "to") { x2 = ov.x; y2 = ov.y; }
        }
        var mx = (x1 + x2) / 2;
        var my = (y1 + y2) / 2;
        return {
            d: "M " + x1 + " " + y1 + " C " + mx + " " + y1 + ", " + mx + " " + y2 + ", " + x2 + " " + y2,
            mx: mx, my: my, x1: x1, y1: y1, x2: x2, y2: y2
        };
    }

    var selectedEid = null;
    var rubber = null;
    var handleFrom = null;
    var handleTo = null;
    var ignoreClick = false;
    var selectedNodeId = null;
    var portLeft = null;
    var portRight = null;
    var linking = null;
    var drawPath = null;

    function worldPos(e) {
        return {
            x: (e.clientX - cam.tx) / cam.scale,
            y: (e.clientY - cam.ty) / cam.scale
        };
    }

    function clearDrop() {
        document.querySelectorAll(".mm-node.mm-drop").forEach(function (n) {
            n.classList.remove("mm-drop");
        });
    }

    function clearEdgeSelect() {
        selectedEid = null;
        selectedEids = {};
        rubber = null;
        document.querySelectorAll(".mm-edge.selected, .mm-edge-label.selected").forEach(function (el) {
            el.classList.remove("selected");
        });
        if (handleFrom) handleFrom.classList.remove("on");
        if (handleTo) handleTo.classList.remove("on");
        clearDrop();
    }

    function selectEdge(el) {
        var eid = el.getAttribute("data-eid");
        if (!eid) return;
        cancelLink();
        clearNodeSelect();
        clearEdgeSelect();
        multiSelect = false;
        selectedEid = eid;
        selectedEids[eid] = true;
        document.querySelectorAll(".mm-edge, .mm-edge-label").forEach(function (item) {
            if (item.getAttribute("data-eid") === eid) item.classList.add("selected");
        });
        updateLines();
    }

    function clearNodeSelect() {
        selectedNodeId = null;
        selectedNodeIds = {};
        document.querySelectorAll(".mm-node.selected").forEach(function (n) {
            n.classList.remove("selected");
        });
        if (portLeft) portLeft.classList.remove("on");
        if (portRight) portRight.classList.remove("on");
    }

    function selectNode(el) {
        var id = el.getAttribute("data-id");
        if (!id) return;
        cancelLink();
        clearEdgeSelect();
        multiSelect = false;
        selectedNodeId = id;
        selectedNodeIds = {};
        selectedNodeIds[id] = true;
        document.querySelectorAll(".mm-node.selected").forEach(function (n) {
            n.classList.remove("selected");
        });
        el.classList.add("selected");
        updateLines();
    }

    function portPos(el, side) {
        var x = parseFloat(el.style.left) || 0;
        var y = parseFloat(el.style.top) || 0;
        var w = el.offsetWidth;
        var h = el.offsetHeight;
        return {
            x: side === "left" ? x : x + w,
            y: y + h / 2
        };
    }

    function updatePorts() {
        if (!portLeft || !portRight || !selectedNodeId) {
            if (portLeft) portLeft.classList.remove("on");
            if (portRight) portRight.classList.remove("on");
            return;
        }
        var el = document.querySelector('.mm-node[data-id="' + selectedNodeId + '"]');
        if (!el) { clearNodeSelect(); return; }
        var L = portPos(el, "left");
        var R = portPos(el, "right");
        portLeft.style.left = L.x + "px";
        portLeft.style.top = L.y + "px";
        portRight.style.left = R.x + "px";
        portRight.style.top = R.y + "px";
        portLeft.classList.add("on");
        portRight.classList.add("on");
    }

    function cancelLink() {
        linking = null;
        document.body.classList.remove("mm-linking");
        if (drawPath) drawPath.style.display = "none";
        clearDrop();
    }

    function updateDrawLine(toX, toY) {
        if (!drawPath || !linking) {
            if (drawPath) drawPath.style.display = "none";
            return;
        }
        var el = document.querySelector('.mm-node[data-id="' + linking.id + '"]');
        if (!el) { cancelLink(); return; }
        var p = portPos(el, linking.side);
        var mx = (p.x + toX) / 2;
        drawPath.setAttribute("d",
            "M " + p.x + " " + p.y + " C " + mx + " " + p.y + ", " + mx + " " + toY + ", " + toX + " " + toY);
        drawPath.style.display = "";
    }

    function startLink(side) {
        if (!selectedNodeId) return;
        linking = { id: selectedNodeId, side: side };
        document.body.classList.add("mm-linking");
    }

    function finishLink(node) {
        if (!linking) return;
        var target = node.getAttribute("data-id");
        var src = linking.id;
        var side = linking.side;
        cancelLink();
        if (!target || target === src) return;
        location.href = "app://connect/" + src + "#" +
            encodeURIComponent(JSON.stringify({
                side: side,
                target: parseInt(target, 10)
            }));
    }

    function updateHandles(byId) {
        if (!handleFrom || !handleTo || !selectedEid) {
            if (handleFrom) handleFrom.classList.remove("on");
            if (handleTo) handleTo.classList.remove("on");
            return;
        }
        var g = document.querySelector('.mm-edge[data-eid="' + selectedEid + '"]');
        if (!g) { clearEdgeSelect(); return; }
        var a = byId[g.getAttribute("data-from")];
        var b = byId[g.getAttribute("data-to")];
        if (!a || !b) return;
        var geo = lineGeom(a, b, rubber && rubber.eid === selectedEid ? rubber : null);
        handleFrom.style.left = geo.x1 + "px";
        handleFrom.style.top = geo.y1 + "px";
        handleTo.style.left = geo.x2 + "px";
        handleTo.style.top = geo.y2 + "px";
        handleFrom.classList.add("on");
        handleTo.classList.add("on");
    }

    function updateLines() {
        var byId = {};
        document.querySelectorAll(".mm-node").forEach(function (el) {
            byId[el.getAttribute("data-id")] = el;
        });
        document.querySelectorAll(".mm-edge").forEach(function (g) {
            var a = byId[g.getAttribute("data-from")];
            var b = byId[g.getAttribute("data-to")];
            if (!a || !b) return;
            var ov = (rubber && g.getAttribute("data-eid") === selectedEid) ? rubber : null;
            var geo = lineGeom(a, b, ov);
            g.querySelectorAll("path").forEach(function (p) {
                p.setAttribute("d", geo.d);
            });
        });
        document.querySelectorAll(".mm-edge-label").forEach(function (el) {
            var a = byId[el.getAttribute("data-from")];
            var b = byId[el.getAttribute("data-to")];
            if (!a || !b) return;
            var ov = (rubber && el.getAttribute("data-eid") === selectedEid) ? rubber : null;
            var geo = lineGeom(a, b, ov);
            el.style.left = geo.mx + "px";
            el.style.top = geo.my + "px";
        });
        updateHandles(byId);
        updatePorts();
    }

    function subtreeOf(rootEl) {
        var ids = {};
        ids[rootEl.getAttribute("data-id")] = true;
        var changed = true;
        while (changed) {
            changed = false;
            document.querySelectorAll(".mm-node").forEach(function (el) {
                var id = el.getAttribute("data-id");
                var p = el.getAttribute("data-parent");
                if (p && ids[p] && !ids[id]) { ids[id] = true; changed = true; }
            });
        }
        var out = [];
        document.querySelectorAll(".mm-node").forEach(function (el) {
            if (ids[el.getAttribute("data-id")]) out.push(el);
        });
        return out;
    }

    function pointInRect(x, y, r) {
        return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;
    }

    function rectsOverlap(a, b) {
        return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    }

    function segsIntersect(ax, ay, bx, by, cx, cy, dx, dy) {
        function cross(ox, oy, px, py) { return ox * py - oy * px; }
        var d1 = cross(bx - ax, by - ay, cx - ax, cy - ay);
        var d2 = cross(bx - ax, by - ay, dx - ax, dy - ay);
        var d3 = cross(dx - cx, dy - cy, ax - cx, ay - cy);
        var d4 = cross(dx - cx, dy - cy, bx - cx, by - cy);
        return d1 * d2 < 0 && d3 * d4 < 0;
    }

    function segmentHitsRect(x1, y1, x2, y2, r) {
        if (pointInRect(x1, y1, r) || pointInRect(x2, y2, r)) return true;
        var x3 = r.x, y3 = r.y, x4 = r.x + r.w, y4 = r.y + r.h;
        return segsIntersect(x1, y1, x2, y2, x3, y3, x4, y3)
            || segsIntersect(x1, y1, x2, y2, x4, y3, x4, y4)
            || segsIntersect(x1, y1, x2, y2, x4, y4, x3, y4)
            || segsIntersect(x1, y1, x2, y2, x3, y4, x3, y3);
    }

    function bezierHitsRect(geo, r) {
        var mx = (geo.x1 + geo.x2) / 2;
        var prevX = geo.x1, prevY = geo.y1;
        if (pointInRect(prevX, prevY, r)) return true;
        for (var i = 1; i <= 24; i++) {
            var t = i / 24, u = 1 - t;
            var x = u*u*u*geo.x1 + 3*u*u*t*mx + 3*u*t*t*mx + t*t*t*geo.x2;
            var y = u*u*u*geo.y1 + 3*u*u*t*geo.y1 + 3*u*t*t*geo.y2 + t*t*t*geo.y2;
            if (pointInRect(x, y, r) || segmentHitsRect(prevX, prevY, x, y, r)) return true;
            prevX = x;
            prevY = y;
        }
        return false;
    }

    function clientBox(x0, y0, x1, y1) {
        return {
            x: Math.min(x0, x1),
            y: Math.min(y0, y1),
            w: Math.abs(x1 - x0),
            h: Math.abs(y1 - y0)
        };
    }

    function worldRectFromClient(cr) {
        var x0 = (cr.x - cam.tx) / cam.scale;
        var y0 = (cr.y - cam.ty) / cam.scale;
        var x1 = (cr.x + cr.w - cam.tx) / cam.scale;
        var y1 = (cr.y + cr.h - cam.ty) / cam.scale;
        return clientBox(x0, y0, x1, y1);
    }

    function showMarquee(cr) {
        marquee.hidden = false;
        marquee.style.left = cr.x + "px";
        marquee.style.top = cr.y + "px";
        marquee.style.width = cr.w + "px";
        marquee.style.height = cr.h + "px";
    }

    function hideMarquee() {
        marquee.hidden = true;
        document.body.classList.remove("mm-boxing");
    }

    function applyBoxSelection(wr) {
        cancelLink();
        hideMenu();
        clearNodeSelect();
        clearEdgeSelect();
        multiSelect = true;
        var byId = {};
        document.querySelectorAll(".mm-node").forEach(function (el) {
            byId[el.getAttribute("data-id")] = el;
            var nr = {
                x: parseFloat(el.style.left) || 0,
                y: parseFloat(el.style.top) || 0,
                w: el.offsetWidth,
                h: el.offsetHeight
            };
            if (rectsOverlap(nr, wr)) {
                var id = el.getAttribute("data-id");
                selectedNodeIds[id] = true;
                el.classList.add("selected");
            }
        });
        document.querySelectorAll(".mm-edge").forEach(function (g) {
            var a = byId[g.getAttribute("data-from")];
            var b = byId[g.getAttribute("data-to")];
            if (!a || !b) return;
            if (!bezierHitsRect(lineGeom(a, b), wr)) return;
            var eid = g.getAttribute("data-eid");
            selectedEids[eid] = true;
        });
        document.querySelectorAll(".mm-edge-label").forEach(function (el) {
            if (!el.textContent) return;
            var lr = {
                x: (parseFloat(el.style.left) || 0) - el.offsetWidth / 2,
                y: (parseFloat(el.style.top) || 0) - el.offsetHeight / 2,
                w: el.offsetWidth,
                h: el.offsetHeight
            };
            if (!rectsOverlap(lr, wr)) return;
            var eid = el.getAttribute("data-eid");
            selectedEids[eid] = true;
        });
        Object.keys(selectedEids).forEach(function (eid) {
            var g = document.querySelector('.mm-edge[data-eid="' + eid + '"]');
            if (!g) return;
            [g.getAttribute("data-from"), g.getAttribute("data-to")].forEach(function (id) {
                if (!id || selectedNodeIds[id]) return;
                selectedNodeIds[id] = true;
                if (byId[id]) byId[id].classList.add("selected");
            });
        });
        document.querySelectorAll(".mm-edge, .mm-edge-label").forEach(function (item) {
            if (selectedEids[item.getAttribute("data-eid")]) item.classList.add("selected");
        });
        var nids = Object.keys(selectedNodeIds);
        var eids = Object.keys(selectedEids);
        selectedNodeId = nids.length === 1 ? nids[0] : null;
        selectedEid = eids.length === 1 ? eids[0] : null;
        if (!nids.length && !eids.length) multiSelect = false;
        updateLines();
    }

    function selectedNodeEls() {
        var out = [];
        document.querySelectorAll(".mm-node").forEach(function (el) {
            if (selectedNodeIds[el.getAttribute("data-id")]) out.push(el);
        });
        return out;
    }

    function beginDrag(els, e) {
        if (!els || !els.length) return;
        var startX = e.clientX, startY = e.clientY;
        var armed = false;
        els.forEach(function (el) {
            el._sx = parseFloat(el.style.left) || 0;
            el._sy = parseFloat(el.style.top) || 0;
        });
        var timer = setTimeout(function () {
            armed = true;
            document.body.classList.add("mm-drag");
        }, multiSelect ? 0 : 180);
        function move(ev) {
            var dx = ev.clientX - startX, dy = ev.clientY - startY;
            if (!armed && dx * dx + dy * dy > 36) {
                armed = true;
                document.body.classList.add("mm-drag");
            }
            if (!armed) return;
            dragMoved = true;
            var wx = dx / cam.scale, wy = dy / cam.scale;
            els.forEach(function (el) {
                el.style.left = (el._sx + wx) + "px";
                el.style.top = (el._sy + wy) + "px";
            });
            updateLines();
        }
        function up() {
            clearTimeout(timer);
            window.removeEventListener("mousemove", move);
            window.removeEventListener("mouseup", up);
            document.body.classList.remove("mm-drag");
            if (armed && dragMoved) {
                var payload = els.map(function (el) {
                    return {
                        id: parseInt(el.getAttribute("data-id"), 10),
                        x: parseFloat(el.style.left),
                        y: parseFloat(el.style.top)
                    };
                });
                location.href = "app://setpos/0#" + encodeURIComponent(JSON.stringify(payload));
                ignoreClick = true;
                setTimeout(function () { ignoreClick = false; }, 50);
            }
            setTimeout(function () { dragMoved = false; }, 400);
        }
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", up);
    }

    var lastWorld = { x: 80, y: 80 };
    document.addEventListener("click", function (e) {
        hideMenu();
        if (ignoreClick) return;
        if (e.target.closest(".mm-handle, .mm-port, .mm-menu")) return;
        if (linking) {
            var hit = e.target.closest(".mm-node");
            if (hit) finishLink(hit);
            else cancelLink();
            return;
        }
        var edge = e.target.closest(".mm-edge, .mm-edge-label");
        var node = e.target.closest(".mm-node");
        if (edge) {
            var eid = edge.getAttribute("data-eid");
            if (multiSelect && selectedEids[eid]) return;
            selectEdge(edge);
            return;
        }
        if (node) {
            var nid = node.getAttribute("data-id");
            if (multiSelect && selectedNodeIds[nid]) return;
            selectNode(node);
            return;
        }
        clearEdgeSelect();
        clearNodeSelect();
        multiSelect = false;
    });
    document.addEventListener("contextmenu", function (e) {
        e.preventDefault();
        var node = e.target.closest(".mm-node");
        var edge = e.target.closest(".mm-edge, .mm-edge-label");
        if (node) {
            currentId = node.getAttribute("data-id");
            var isRoot = node.classList.contains("root");
            var hlLabel = node.classList.contains("hl") ? "取消高亮" : "高亮";
            menu.innerHTML =
                '<button type="button" data-act="addbox">新建子框</button>' +
                '<button type="button" data-act="addtext">新建子句</button>' +
                '<button type="button" data-act="togglehl">' + hlLabel + '</button>' +
                (isRoot ? "" :
                    '<button type="button" data-act="delone" class="danger">只删除此单元</button>' +
                    '<button type="button" data-act="delnode" class="danger">删除此单元及后续</button>');
            menu.hidden = false;
            menu.style.left = e.clientX + "px";
            menu.style.top = e.clientY + "px";
            return;
        }
        if (edge) {
            selectEdge(edge);
            currentId = edge.getAttribute("data-eid");
            menu.innerHTML =
                '<button type="button" data-act="edgebox">在连线上新建子框</button>' +
                '<button type="button" data-act="edgetext">在连线上新建子句</button>' +
                '<button type="button" data-act="editedge">编辑标注</button>' +
                '<button type="button" data-act="deledge" class="danger">删除连线</button>';
            menu.hidden = false;
            menu.style.left = e.clientX + "px";
            menu.style.top = e.clientY + "px";
            return;
        }
        lastWorld = worldPos(e);
        currentId = "0";
        menu.innerHTML =
            '<button type="button" data-act="addfreebox">新建独立子框</button>' +
            '<button type="button" data-act="addfreetext">新建独立子句</button>';
        menu.hidden = false;
        menu.style.left = e.clientX + "px";
        menu.style.top = e.clientY + "px";
    });
    menu.addEventListener("click", function (e) {
        var btn = e.target.closest("button");
        if (!btn || !currentId) return;
        e.stopPropagation();
        hideMenu();
        var act = btn.getAttribute("data-act");
        if (act === "addfreebox" || act === "addfreetext") {
            location.href = "app://" + act + "/0#" +
                encodeURIComponent(JSON.stringify(lastWorld));
            return;
        }
        location.href = "app://" + act + "/" + currentId;
    });

    document.querySelectorAll(".mm-edge-label").forEach(function (el) {
        el.addEventListener("dblclick", function (e) {
            e.preventDefault();
            e.stopPropagation();
            hideMenu();
            location.href = "app://editedge/" + el.getAttribute("data-eid");
        });
    });

    document.querySelectorAll(".mm-node").forEach(function (node) {
        var body = node.querySelector(".mm-body");
        node.addEventListener("dblclick", function (e) {
            if (dragMoved) { e.preventDefault(); return; }
            e.preventDefault();
            hideMenu();
            var raw = node.getAttribute("data-raw");
            body.textContent = raw === null ? (body.innerText || "") : raw;
            body.contentEditable = "true";
            body.focus();
            var sel = window.getSelection();
            var range = document.createRange();
            range.selectNodeContents(body);
            sel.removeAllRanges();
            sel.addRange(range);
        });
        body.addEventListener("input", function () {
            updateLines();
        });
        body.addEventListener("blur", function () {
            if (body.contentEditable !== "true") return;
            body.contentEditable = "false";
            var text = (body.innerText || "").replace(/\u00a0/g, " ");
            if (text.slice(-1) === "\n") text = text.slice(0, -1);
            location.href = "app://savenode/" + node.getAttribute("data-id") +
                "#" + encodeURIComponent(text);
        });
        body.addEventListener("keydown", function (e) {
            if (e.key === "Escape") { body.blur(); return; }
            if (e.key === "Enter" && !e.shiftKey && !node.classList.contains("text")) {
                e.preventDefault();
                body.blur();
            }
        });
        node.addEventListener("mousedown", function (e) {
            if (e.button !== 0) return;
            if (body.isContentEditable) return;
            if (linking) {
                e.preventDefault();
                e.stopPropagation();
                hideMenu();
                finishLink(node);
                return;
            }
            e.stopPropagation();
            hideMenu();
            var nid = node.getAttribute("data-id");
            var movingGroup = multiSelect && selectedNodeIds[nid];
            var els;
            if (movingGroup) {
                els = selectedNodeEls();
            } else {
                multiSelect = false;
                clearEdgeSelect();
                els = subtreeOf(node);
            }
            beginDrag(els, e);
        });
    });

    var viewport = document.querySelector(".mm-viewport");
    var world = document.querySelector(".mm-world");
    var canvas = document.querySelector(".mm-canvas");
    if (canvas) {
        handleFrom = document.createElement("div");
        handleTo = document.createElement("div");
        handleFrom.className = "mm-handle";
        handleTo.className = "mm-handle";
        handleFrom.setAttribute("data-end", "from");
        handleTo.setAttribute("data-end", "to");
        canvas.appendChild(handleFrom);
        canvas.appendChild(handleTo);
        portLeft = document.createElement("div");
        portRight = document.createElement("div");
        portLeft.className = "mm-port";
        portRight.className = "mm-port";
        portLeft.setAttribute("data-side", "left");
        portRight.setAttribute("data-side", "right");
        canvas.appendChild(portLeft);
        canvas.appendChild(portRight);
        var svg = canvas.querySelector(".mm-lines");
        if (svg) {
            drawPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
            drawPath.setAttribute("class", "mm-draw-line");
            drawPath.style.display = "none";
            svg.appendChild(drawPath);
        }
        [portLeft, portRight].forEach(function (p) {
            p.addEventListener("mousedown", function (e) {
                e.preventDefault();
                e.stopPropagation();
            });
            p.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                hideMenu();
                startLink(p.getAttribute("data-side"));
                var w = worldPos(e);
                updateDrawLine(w.x, w.y);
            });
        });
        window.addEventListener("mousemove", function (e) {
            if (!linking) return;
            var w = worldPos(e);
            updateDrawLine(w.x, w.y);
            clearDrop();
            portLeft.style.pointerEvents = "none";
            portRight.style.pointerEvents = "none";
            var under = document.elementFromPoint(e.clientX, e.clientY);
            portLeft.style.pointerEvents = "";
            portRight.style.pointerEvents = "";
            var n = under && under.closest(".mm-node");
            if (n && n.getAttribute("data-id") !== linking.id) n.classList.add("mm-drop");
        });
        window.addEventListener("keydown", function (e) {
            if (e.key === "Escape") {
                if (boxing) {
                    hideMarquee();
                    boxing = false;
                    boxArmed = false;
                    return;
                }
                cancelLink();
            }
        });
        [handleFrom, handleTo].forEach(function (h) {
            h.addEventListener("mousedown", function (e) {
                if (e.button !== 0 || !selectedEid) return;
                e.preventDefault();
                e.stopPropagation();
                hideMenu();
                var end = h.getAttribute("data-end");
                document.body.classList.add("mm-relink");
                function hitNode(ev) {
                    h.style.pointerEvents = "none";
                    handleFrom.style.pointerEvents = "none";
                    handleTo.style.pointerEvents = "none";
                    var under = document.elementFromPoint(ev.clientX, ev.clientY);
                    handleFrom.style.pointerEvents = "";
                    handleTo.style.pointerEvents = "";
                    return under && under.closest(".mm-node");
                }
                function move(ev) {
                    var w = worldPos(ev);
                    rubber = { end: end, x: w.x, y: w.y, eid: selectedEid };
                    updateLines();
                    clearDrop();
                    var n = hitNode(ev);
                    if (n) n.classList.add("mm-drop");
                }
                function up(ev) {
                    window.removeEventListener("mousemove", move);
                    window.removeEventListener("mouseup", up);
                    document.body.classList.remove("mm-relink");
                    var n = hitNode(ev);
                    var target = n ? n.getAttribute("data-id") : null;
                    rubber = null;
                    clearDrop();
                    updateLines();
                    ignoreClick = true;
                    setTimeout(function () { ignoreClick = false; }, 50);
                    if (!target || !selectedEid) return;
                    location.href = "app://relink/" + selectedEid + "#" +
                        encodeURIComponent(JSON.stringify({ end: end, target: parseInt(target, 10) }));
                }
                window.addEventListener("mousemove", move);
                window.addEventListener("mouseup", up);
            });
        });
    }
    if (viewport && world) {
        var baseW = parseFloat(viewport.getAttribute("data-w")) || 400;
        var baseH = parseFloat(viewport.getAttribute("data-h")) || 240;
        var savedScale = parseFloat(viewport.getAttribute("data-scale"));
        if (isFinite(savedScale) && savedScale > 0) {
            cam.scale = savedScale;
            cam.tx = parseFloat(viewport.getAttribute("data-tx")) || 0;
            cam.ty = parseFloat(viewport.getAttribute("data-ty")) || 0;
        } else {
            cam.tx = Math.max(40, (viewport.clientWidth - baseW) / 2);
            cam.ty = Math.max(72, (viewport.clientHeight - baseH) / 2);
        }
        applyView();
        sendCam();
        requestAnimationFrame(function () { updateLines(); });

        var panning = false;
        var lastX = 0;
        var lastY = 0;
        viewport.addEventListener("mousedown", function (e) {
            if (e.button !== 0) return;
            if (boxing) return;
            if (e.target.closest(".mm-node, .mm-menu, .mm-edge, .mm-edge-label, .mm-handle, .mm-port")) return;
            if (document.activeElement && document.activeElement.isContentEditable) return;
            panning = true;
            lastX = e.clientX;
            lastY = e.clientY;
            document.body.classList.add("mm-drag");
            e.preventDefault();
        });
        window.addEventListener("mousemove", function (e) {
            if (!panning) return;
            cam.tx += e.clientX - lastX;
            cam.ty += e.clientY - lastY;
            lastX = e.clientX;
            lastY = e.clientY;
            applyView();
        });
        window.addEventListener("mouseup", function () {
            if (panning) sendCam();
            panning = false;
            document.body.classList.remove("mm-drag");
        });

        window.addEventListener("wheel", function (e) {
            if (!e.ctrlKey) return;
            e.preventDefault();
            e.stopPropagation();
            var factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
            var next = Math.min(2.5, Math.max(0.4, cam.scale * factor));
            if (Math.abs(next - cam.scale) < 0.001) return;
            var mx = (e.clientX - cam.tx) / cam.scale;
            var my = (e.clientY - cam.ty) / cam.scale;
            cam.scale = next;
            cam.tx = e.clientX - mx * cam.scale;
            cam.ty = e.clientY - my * cam.scale;
            applyView();
            sendCam();
        }, { passive: false });
    }

    function startBox(e) {
        e.preventDefault();
        e.stopPropagation();
        if (boxing) return;
        if (document.activeElement && document.activeElement.isContentEditable) {
            document.activeElement.blur();
        }
        hideMenu();
        cancelLink();
        boxing = true;
        boxArmed = false;
        boxStart = { x: e.clientX, y: e.clientY };
        document.body.classList.add("mm-boxing");
        showMarquee({ x: e.clientX, y: e.clientY, w: 0, h: 0 });
    }
    function moveBox(e) {
        if (!boxing) return;
        e.preventDefault();
        var cr = clientBox(boxStart.x, boxStart.y, e.clientX, e.clientY);
        showMarquee(cr);
        if (cr.w >= 4 || cr.h >= 4) {
            boxArmed = true;
            applyBoxSelection(worldRectFromClient(cr));
        }
    }
    function endBox() {
        if (!boxing) return;
        hideMarquee();
        boxing = false;
        if (boxArmed) {
            ignoreClick = true;
            setTimeout(function () { ignoreClick = false; }, 50);
        }
        boxArmed = false;
    }
    window.addEventListener("mousedown", function (e) {
        if (e.button === 1) startBox(e);
    }, true);
    window.addEventListener("pointerdown", function (e) {
        if (e.button === 1 || e.buttons === 4) startBox(e);
    }, true);
    window.addEventListener("mousemove", moveBox);
    window.addEventListener("pointermove", moveBox);
    window.addEventListener("mouseup", endBox);
    window.addEventListener("pointerup", endBox);
    window.addEventListener("pointercancel", endBox);
    window.addEventListener("auxclick", function (e) {
        if (e.button === 1) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, true);
    document.addEventListener("mousedown", function (e) {
        if (e.button !== 0 || !multiSelect) return;
        var edge = e.target.closest(".mm-edge, .mm-edge-label");
        if (!edge) return;
        var eid = edge.getAttribute("data-eid");
        if (!selectedEids[eid]) return;
        var els = selectedNodeEls();
        if (!els.length) return;
        e.preventDefault();
        e.stopPropagation();
        hideMenu();
        beginDrag(els, e);
    }, true);
})();
"""

