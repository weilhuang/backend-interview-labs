"""Read-only, bounded whole plugin-window proof on the already owned X display.

The caller must first verify the held process/display identity and run this probe
in its own subprocess with one hard two-second timeout. The checks below share
one deadline, including both observations. Xlib round trips themselves cannot be
interrupted safely in Python; the caller's hard timeout is therefore required.

This proves a stable sampled geometry/shape/focus route, not client ownership,
the absence of pointer grabs, or atomicity with a later normal Robot click.
No display, process, window, shape, focus, or input state is modified.
"""
import ctypes as C
import hashlib
import json
import os
import re
import time

import trust_window

MAX_PROOF_BYTES = 32768
MAX_ROOT_CHILDREN = 32
MAX_NODES = 64  # Includes the decision window itself.
MAX_DEPTH = 8  # The decision window is depth zero.
MAX_TITLE_BYTES = 1024
PROBE_SECONDS = 2.0
ACTIONS = ("CHECK_ACADEMY_PLUGIN_ONLY", "AGREE_ACADEMY_PLUGIN_ONLY")
_ATTRS = {"window_id", "pid", "title_sha256", "x", "y", "width", "height",
          "border", "window_class", "map_state", "override_redirect",
          "event_mask", "do_not_propagate_mask"}
_FIELDS = {"schema", "action", "root_id", "screen", "shape_version", "root_shape",
           "window_identity", "root_children", "dialog_tree", "focus_path",
           "focus_revert", "target_route"}


class ProofError(ValueError):
    """Fixed safe reason; never includes X titles, paths, or exception text."""
    def __init__(self, reason="WINDOW_PROOF_UNAVAILABLE"):
        self.reason = reason
        super().__init__(reason)


def _require(ok, reason="WINDOW_PROOF_UNAVAILABLE"):
    if not ok:
        raise ProofError(reason)


def _integer(value, low, high):
    _require(type(value) is int and low <= value <= high)


def _ids(value, cap, minimum=0):
    _require(type(value) is list and minimum <= len(value) <= cap)
    for item in value:
        _integer(item, 1, 0xffffffff)
    _require(len(set(value)) == len(value))


def _target(action):
    _require(type(action) is str and action in ACTIONS)
    return trust_window.target(action)


def _check_time(deadline):
    _require(time.monotonic() < deadline)


def _attrs(value, root_child=False):
    _require(type(value) is dict and set(value) == _ATTRS)
    _integer(value["window_id"], 1, 0xffffffff)
    _integer(value["x"], 0 if root_child else -32768, 1279 if root_child else 32767)
    _integer(value["y"], 0 if root_child else -32768, 899 if root_child else 32767)
    _integer(value["width"], 1, 1280)
    _integer(value["height"], 1, 900)
    _integer(value["border"], 0, 8)
    _integer(value["window_class"], 1, 2)
    _integer(value["map_state"], 0, 2)
    _integer(value["event_mask"], 0, (1 << 25) - 1)
    _integer(value["do_not_propagate_mask"], 0, (1 << 25) - 1)
    _require(type(value["override_redirect"]) is bool)
    if value["pid"] is not None:
        _integer(value["pid"], 1, 2**31 - 1)
    if value["title_sha256"] is not None:
        _require(type(value["title_sha256"]) is str and
                 re.fullmatch("[0-9a-f]{64}", value["title_sha256"]) is not None)
    if value["window_class"] == 2:
        _require(value["border"] == 0)
    if root_child:
        _require(value["x"] + value["width"] + 2 * value["border"] <= 1280 and
                 value["y"] + value["height"] + 2 * value["border"] <= 900)
        _require(value["map_state"] in (0, 2))


def _shape(value, width, height, border, window_class):
    _require(type(value) is dict and set(value) == {"bounding", "input", "clip", "orders"})
    default = [-border, -border, width + 2 * border, height + 2 * border]
    for kind in ("bounding", "input"):
        rect = value[kind]
        _require(type(rect) is list and len(rect) == 4)
        for coord in rect:
            _integer(coord, -32768, 65535)
        _require(rect == default, "INPUT_ROUTE_CHANGED")
    if window_class == 1:
        rect = value["clip"]
        _require(type(rect) is list and len(rect) == 4)
        for coord in rect:
            _integer(coord, -32768, 65535)
        _require(rect == [0, 0, width, height], "INPUT_ROUTE_CHANGED")
    else:
        _require(value["clip"] is None)
    orders = value["orders"]
    _require(type(orders) is list and len(orders) == (3 if window_class == 1 else 2))
    for order in orders:
        _integer(order, 0, 3)


def _intersection(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return (x, y, max(0, right - x), max(0, bottom - y))


def _contains(rect, point):
    return rect[0] <= point[0] < rect[0] + rect[2] and rect[1] <= point[1] < rect[1] + rect[3]


def _overlaps(a, b):
    rect = _intersection(a, b)
    return rect[2] > 0 and rect[3] > 0


def _identity(record):
    return {key: record[key] for key in
            ("window_id", "pid", "x", "y", "width", "height", "border", "title_sha256")}


def _analyze(proof, action):
    """Validate all closed records and derive the focus and geometric hit paths."""
    point = _target(action)
    _require(type(proof) is dict and set(proof) == _FIELDS)
    _integer(proof["schema"], 1, 1)
    _require(type(proof["action"]) is str and proof["action"] == action)
    _integer(proof["root_id"], 2, 0xffffffff)
    screen = proof["screen"]
    _require(type(screen) is list and len(screen) == 2)
    _integer(screen[0], 1280, 1280)
    _integer(screen[1], 900, 900)
    version = proof["shape_version"]
    _require(type(version) is list and len(version) == 2)
    _integer(version[0], 1, 65535)
    _integer(version[1], 0, 65535)
    _require(tuple(version) >= (1, 1))
    _shape(proof["root_shape"], 1280, 900, 0, 1)
    identity = trust_window.validate(proof["window_identity"], action)
    _require(identity["border"] == 0)
    modal_id, pid = identity["window_id"], identity["pid"]
    modal_rect = tuple(identity[k] for k in ("x", "y", "width", "height"))
    roots = proof["root_children"]
    _require(type(roots) is list and 1 <= len(roots) <= MAX_ROOT_CHILDREN)
    for record in roots:
        _attrs(record, root_child=True)
    root_ids = [record["window_id"] for record in roots]
    _ids(root_ids, MAX_ROOT_CHILDREN, 1)
    _require(proof["root_id"] not in root_ids and modal_id in root_ids)
    modal_index = root_ids.index(modal_id)
    decision = roots[modal_index]
    _require(_identity(decision) == identity and decision["window_class"] == 1 and
             decision["map_state"] == 2 and decision["title_sha256"] is not None)
    for record in roots[modal_index + 1:]:
        exterior = (record["x"], record["y"], record["width"] + 2 * record["border"],
                    record["height"] + 2 * record["border"])
        _require(record["map_state"] == 0 or not _overlaps(exterior, modal_rect), "WINDOW_OCCLUDED")

    tree = proof["dialog_tree"]
    _require(type(tree) is list and 1 <= len(tree) <= MAX_NODES)
    nodes = {}
    for node in tree:
        _require(type(node) is dict and set(node) == _ATTRS | {"parent", "children", "shape"})
        _attrs({k: node[k] for k in _ATTRS})
        _integer(node["parent"], 1, 0xffffffff)
        _ids(node["children"], MAX_NODES - 1)
        _shape(node["shape"], node["width"], node["height"], node["border"], node["window_class"])
        _require(node["pid"] is None or node["pid"] == pid, "INPUT_ROUTE_CHANGED")
        _require(node["window_id"] not in nodes)
        nodes[node["window_id"]] = node
    _require(tree[0]["window_id"] == modal_id and
             {k: tree[0][k] for k in _ATTRS} == decision and
             tree[0]["parent"] == proof["root_id"])
    _require(not (set(nodes) & (set(root_ids) - {modal_id})) and proof["root_id"] not in nodes)
    seen, visible, interiors = [], {}, {}

    def walk(window_id, parent, parent_origin, parent_clip, depth):
        _require(depth <= MAX_DEPTH and window_id in nodes and window_id not in seen)
        node = nodes[window_id]
        _require(node["parent"] == parent)
        seen.append(window_id)
        if parent in nodes:
            parent_state = nodes[parent]["map_state"]
            _require((parent_state == 2 and node["map_state"] != 1) or
                     (parent_state != 2 and node["map_state"] != 2))
        border = node["border"]
        outer_x, outer_y = parent_origin[0] + node["x"], parent_origin[1] + node["y"]
        origin = (outer_x + border, outer_y + border)
        exterior = (outer_x, outer_y, node["width"] + 2 * border, node["height"] + 2 * border)
        visible[window_id] = _intersection(parent_clip, exterior)
        interiors[window_id] = _intersection(parent_clip, (*origin, node["width"], node["height"]))
        if node["window_class"] == 2 and node["map_state"] != 0:
            _require(not _overlaps(visible[window_id], modal_rect), "INPUT_ROUTE_CHANGED")
        for child in node["children"]:
            walk(child, window_id, origin, interiors[window_id], depth + 1)

    walk(modal_id, proof["root_id"], (0, 0), (0, 0, 1280, 900), 0)
    _require(seen == [node["window_id"] for node in tree])
    _ids(proof["focus_path"], MAX_DEPTH + 1, 1)
    _integer(proof["focus_revert"], 0, 2)
    focus = proof["focus_path"][-1]
    _require(focus in nodes and focus not in (0, 1), "INPUT_ROUTE_CHANGED")
    focus_path = []
    while focus in nodes:
        _require(nodes[focus]["map_state"] == 2, "INPUT_ROUTE_CHANGED")
        focus_path.append(focus)
        focus = nodes[focus]["parent"]
    focus_path.reverse()
    _require(focus == proof["root_id"] and focus_path == proof["focus_path"], "INPUT_ROUTE_CHANGED")
    route, current = [modal_id], modal_id
    _require(_contains(visible[current], point))
    while True:
        hit = next((child for child in reversed(nodes[current]["children"])
                    if nodes[child]["map_state"] == 2 and _contains(visible[child], point)), None)
        if hit is None:
            break
        _require(nodes[hit]["window_class"] == 1, "INPUT_ROUTE_CHANGED")
        route.append(hit)
        current = hit
    return route


def validate(proof, action):
    """Reject any extra keys, loose types, unsupported shapes, or ambiguous route."""
    route = _analyze(proof, action)
    _ids(proof["target_route"], MAX_DEPTH + 1, 1)
    _require(proof["target_route"] == route, "INPUT_ROUTE_CHANGED")
    raw = json.dumps(proof, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    _require(len(raw) + 1 <= MAX_PROOF_BYTES)  # Includes the sidecar's final newline.
    return proof


class _WindowAttributes(C.Structure):
    _fields_ = [(name, C.c_int) for name in ("x", "y", "width", "height", "border_width", "depth")] + [
        ("visual", C.c_void_p), ("root", C.c_ulong), ("window_class", C.c_int),
        ("bit_gravity", C.c_int), ("win_gravity", C.c_int), ("backing_store", C.c_int),
        ("backing_planes", C.c_ulong), ("backing_pixel", C.c_ulong), ("save_under", C.c_int),
        ("colormap", C.c_ulong), ("map_installed", C.c_int), ("map_state", C.c_int),
        ("all_event_masks", C.c_long), ("your_event_mask", C.c_long),
        ("do_not_propagate_mask", C.c_long), ("override_redirect", C.c_int), ("screen", C.c_void_p)]


class _Rectangle(C.Structure):
    _fields_ = [("x", C.c_short), ("y", C.c_short), ("width", C.c_ushort), ("height", C.c_ushort)]


class _X11:
    """Small read-only Xlib adapter. All server-returned lists are bounded before copying."""
    def __init__(self, display, deadline):
        self.display, self.deadline = display, deadline
        self.connection, self.previous_handler = None, None
        self.error = False
        self.x, self.ext = C.CDLL("libX11.so.6"), C.CDLL("libXext.so.6")
        ptr, u, i, ui = C.c_void_p, C.c_ulong, C.c_int, C.c_uint
        p = C.POINTER
        declarations = {
            "XOpenDisplay": ([C.c_char_p], ptr), "XCloseDisplay": ([ptr], i),
            "XDefaultRootWindow": ([ptr], u), "XGetWindowAttributes": ([ptr, u, p(_WindowAttributes)], i),
            "XQueryTree": ([ptr, u, p(u), p(u), p(p(u)), p(ui)], i),
            "XGetInputFocus": ([ptr, p(u), p(i)], i),
            "XTranslateCoordinates": ([ptr, u, u, i, i, p(i), p(i), p(u)], i),
            "XInternAtom": ([ptr, C.c_char_p, i], u),
            "XGetWindowProperty": ([ptr, u, u, C.c_long, C.c_long, i, u, p(u), p(i), p(u), p(u), p(ptr)], i),
            "XFree": ([ptr], i), "XSync": ([ptr, i], i), "XSetErrorHandler": ([ptr], ptr)}
        for name, (args, result) in declarations.items():
            function = getattr(self.x, name)
            function.argtypes, function.restype = args, result
        shapes = {
            "XShapeQueryExtension": ([ptr, p(i), p(i)], i),
            "XShapeQueryVersion": ([ptr, p(i), p(i)], i),
            "XShapeGetRectangles": ([ptr, u, i, p(i), p(i)], p(_Rectangle))}
        for name, (args, result) in shapes.items():
            function = getattr(self.ext, name)
            function.argtypes, function.restype = args, result
        callback = C.CFUNCTYPE(i, ptr, ptr)
        def error_handler(*_):
            self.error = True
            return 0
        self.handler = callback(error_handler)

    def __enter__(self):
        _check_time(self.deadline)
        self.previous_handler = self.x.XSetErrorHandler(C.cast(self.handler, C.c_void_p))
        try:
            self.connection = self.x.XOpenDisplay(self.display.encode("ascii"))
            _require(bool(self.connection))
            self.sync()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        try:
            if self.connection:
                self.x.XCloseDisplay(self.connection)
                self.connection = None
        finally:
            self.x.XSetErrorHandler(self.previous_handler)

    def sync(self):
        _check_time(self.deadline)
        self.x.XSync(self.connection, False)
        _check_time(self.deadline)
        _require(not self.error)

    def call(self, fn, *args):
        _check_time(self.deadline)
        result = fn(self.connection, *args)
        self.sync()
        _require(bool(result))
        return result

    def root(self):
        return int(self.call(self.x.XDefaultRootWindow))

    def version(self):
        event, error, major, minor = C.c_int(), C.c_int(), C.c_int(), C.c_int()
        self.call(self.ext.XShapeQueryExtension, C.byref(event), C.byref(error))
        self.call(self.ext.XShapeQueryVersion, C.byref(major), C.byref(minor))
        _require((major.value, minor.value) >= (1, 1))
        return [major.value, minor.value]

    def tree(self, window, cap):
        root, parent, count = C.c_ulong(), C.c_ulong(), C.c_uint()
        children = C.POINTER(C.c_ulong)()
        try:
            self.call(self.x.XQueryTree, window, C.byref(root), C.byref(parent), C.byref(children), C.byref(count))
            _require(count.value <= cap and (count.value == 0 or bool(children)))
            result = [int(children[i]) for i in range(count.value)]
            _ids(result, cap)
            return root.value, parent.value, result
        finally:
            if children:
                self.x.XFree(children)

    def attributes(self, window, root):
        value = _WindowAttributes()
        self.call(self.x.XGetWindowAttributes, window, C.byref(value))
        _require(value.root == root and value.override_redirect in (0, 1))
        _require((value.window_class == 1 and value.depth in (24, 32)) or
                 (value.window_class == 2 and value.depth == 0))
        return {"window_id": window, "x": value.x, "y": value.y, "width": value.width,
                "height": value.height, "border": value.border_width, "window_class": value.window_class,
                "map_state": value.map_state, "override_redirect": bool(value.override_redirect),
                "event_mask": value.all_event_masks, "do_not_propagate_mask": value.do_not_propagate_mask,
                "pid": self.property(window, b"_NET_WM_PID", 32, b"CARDINAL"),
                "title_sha256": self.property(window, b"WM_NAME", 8, b"STRING")}

    def property(self, window, name, expected_format, expected_type):
        _check_time(self.deadline)
        atom = self.x.XInternAtom(self.connection, name, True)
        self.sync()
        if atom == 0:
            return None
        actual, fmt, count, remaining, data = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong(), C.c_void_p()
        try:
            _check_time(self.deadline)
            code = self.x.XGetWindowProperty(self.connection, window, atom, 0, MAX_TITLE_BYTES // 4,
                                            False, 0, C.byref(actual), C.byref(fmt), C.byref(count),
                                            C.byref(remaining), C.byref(data))
            self.sync()
            _require(code == 0 and remaining.value == 0)
            if actual.value == 0:
                _require(fmt.value == 0 and count.value == 0)
                return None
            expected = self.x.XInternAtom(self.connection, expected_type, True)
            self.sync()
            _require(expected != 0 and actual.value == expected and fmt.value == expected_format)
            if expected_format == 32:
                _require(count.value == 1 and bool(data))
                return int(C.cast(data, C.POINTER(C.c_ulong))[0])
            _require(count.value <= MAX_TITLE_BYTES and (count.value == 0 or bool(data)))
            return hashlib.sha256(C.string_at(data, count.value) if count.value else b"").hexdigest()
        finally:
            if data:
                self.x.XFree(data)

    def shape(self, window, window_class):
        result, orders = {}, []
        for name, kind in (("bounding", 0), ("input", 2), ("clip", 1)):
            if name == "clip" and window_class == 2:
                result[name] = None
                continue
            count, order = C.c_int(), C.c_int()
            rectangles = None
            try:
                _check_time(self.deadline)
                rectangles = self.ext.XShapeGetRectangles(self.connection, window, kind, C.byref(count), C.byref(order))
                self.sync()
                _require(count.value == 1 and bool(rectangles), "INPUT_ROUTE_CHANGED")
                item = rectangles[0]
                result[name] = [item.x, item.y, item.width, item.height]
                orders.append(order.value)
            finally:
                if rectangles:
                    self.x.XFree(rectangles)
        result["orders"] = orders
        return result

    def focus(self):
        focus, revert = C.c_ulong(), C.c_int()
        self.call(self.x.XGetInputFocus, C.byref(focus), C.byref(revert))
        return focus.value, revert.value

    def child_at(self, window, point):
        x, y, child = C.c_int(), C.c_int(), C.c_ulong()
        self.call(self.x.XTranslateCoordinates, window, window, *point, C.byref(x), C.byref(y), C.byref(child))
        _require((x.value, y.value) == point)
        return child.value


def _observation(x, ide_pid, action, deadline):
    _check_time(deadline)
    root = x.root()
    root_attrs = x.attributes(root, root)
    _attrs(root_attrs)
    _require(root_attrs["window_class"] == 1 and root_attrs["map_state"] == 2 and
             [root_attrs[k] for k in ("x", "y", "width", "height", "border")] == [0, 0, 1280, 900, 0])
    version = x.version()
    root_shape = x.shape(root, 1)
    tree_root, parent, children = x.tree(root, MAX_ROOT_CHILDREN)
    _require(tree_root == root and parent == 0)
    roots = [x.attributes(child, root) for child in children]
    for record in roots:
        _attrs(record, root_child=True)
    point = _target(action)
    modal_id = x.child_at(root, point)
    _require(modal_id in children)
    decision = roots[children.index(modal_id)]
    _require(decision["pid"] == ide_pid)
    identity = _identity(decision)
    trust_window.validate(identity, action)
    _require(identity["border"] == 0)
    nodes, seen = [], set()

    def walk(record, parent_id, depth):
        _check_time(deadline)
        window = record["window_id"]
        _require(depth <= MAX_DEPTH and len(seen) < MAX_NODES and window not in seen)
        seen.add(window)
        origin, actual_parent, child_ids = x.tree(window, MAX_NODES - len(seen))
        _require(origin == root and actual_parent == parent_id)
        node = {**record, "parent": parent_id, "children": child_ids,
                "shape": x.shape(window, record["window_class"])}
        nodes.append(node)
        for child in child_ids:
            walk(x.attributes(child, root), window, depth + 1)

    walk(decision, root, 0)
    focus, revert = x.focus()
    by_id = {node["window_id"]: node for node in nodes}
    focus_path = []
    while focus in by_id and len(focus_path) <= MAX_DEPTH:
        focus_path.append(focus)
        focus = by_id[focus]["parent"]
    _require(focus == root and focus_path, "INPUT_ROUTE_CHANGED")
    focus_path.reverse()
    proof = {"schema": 1, "action": action, "root_id": root, "screen": [1280, 900],
             "shape_version": version, "root_shape": root_shape, "window_identity": identity,
             "root_children": roots, "dialog_tree": nodes, "focus_path": focus_path,
             "focus_revert": revert, "target_route": []}
    proof["target_route"] = _analyze(proof, action)
    # Compare the server's immediate child answers along the same derived route.
    # Coordinates are relative to each window's inner origin; borders are explicit.
    relative = point
    route = proof["target_route"]
    for index, window in enumerate(route):
        node = by_id[window]
        relative = (relative[0] - node["x"] - node["border"],
                    relative[1] - node["y"] - node["border"])
        expected = route[index + 1] if index + 1 < len(route) else 0
        _require(x.child_at(window, relative) == expected, "INPUT_ROUTE_CHANGED")
    _check_time(deadline)
    return validate(proof, action)


def observe(ide_pid, action):
    """Two exact complete samples, within one budget, from the fixed owned display."""
    _integer(ide_pid, 1, 2**31 - 1)
    _target(action)
    display = os.environ.get("DISPLAY", "")
    _require(re.fullmatch(r":[0-9]{1,4}", display) is not None)
    deadline = time.monotonic() + PROBE_SECONDS
    try:
        with _X11(display, deadline) as x:
            first = _observation(x, ide_pid, action, deadline)
            second = _observation(x, ide_pid, action, deadline)
            _require(first == second, "WINDOW_IDENTITY_CHANGED")
            _check_time(deadline)
        _check_time(deadline)
        return second
    except (OSError, AttributeError):
        raise ProofError() from None
