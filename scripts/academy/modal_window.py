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
import struct
import time

import trust_window

MAX_PROOF_BYTES = 32768
MAX_ROOT_CHILDREN = 32
MAX_NODES = 64  # Includes the decision window itself.
MAX_DEPTH = 8  # The decision window is depth zero.
MAX_TITLE_BYTES = 1024
MAX_CONVERTED_TITLE_BYTES = 4096  # Includes the terminating NUL during native output scanning.
TITLE_DOMAIN = b"ACADEMY_MODAL_SELECTED_TITLE_V1\0"
PROBE_SECONDS = 2.0
ACTIONS = ("CHECK_ACADEMY_PLUGIN_ONLY", "AGREE_ACADEMY_PLUGIN_ONLY")
_ATTRS = {"window_id", "pid", "title_sha256", "x", "y", "width", "height",
          "border", "window_class", "map_state", "override_redirect",
          "event_mask", "do_not_propagate_mask"}
_FIELDS = {"schema", "action", "root_id", "screen", "shape_version", "root_shape",
           "window_identity", "root_children", "dialog_tree", "focus_path",
           "focus_revert", "target_route"}

# This is a diagnostic wire format, not another source of window authority.
# Only fixed codes and bounded numbers from observations already made above are
# eligible. In particular, exception messages and arbitrary exception attributes
# must never be serialized.
MAX_FAILURE_BYTES = 2048
MAX_FAILURE_FACTS = 12
_FAILURE_FIELDS = {"schema", "reason", "call_site", "exception_class", "facts"}
_FAILURE_REASONS = frozenset({"WINDOW_PROOF_UNAVAILABLE", "INPUT_ROUTE_CHANGED",
                              "WINDOW_OCCLUDED", "WINDOW_IDENTITY_CHANGED"})
_FAILURE_CLASSES = frozenset({"ProofError", "OSError", "AttributeError", "ValueError",
                              "TypeError", "OTHER"})
_FAILURE_SITES = frozenset({
    "UNSPECIFIED", "UNEXPECTED_EXCEPTION", "INTEGER", "IDS", "ACTION", "DEADLINE",
    "ATTR_RECORD", "ATTR_ID", "ATTR_X", "ATTR_Y", "ATTR_WIDTH", "ATTR_HEIGHT",
    "ATTR_BORDER", "ATTR_CLASS", "ATTR_MAP_STATE", "ATTR_EVENT_MASK", "ATTR_DNP_MASK",
    "ATTR_OVERRIDE", "ATTR_PID", "ATTR_TITLE_DIGEST", "ATTR_INPUTONLY_BORDER",
    "ROOT_CHILD_BOUNDS", "ROOT_CHILD_MAP_STATE", "SHAPE_RECORD", "SHAPE_RECTANGLE",
    "SHAPE_COORDINATE", "SHAPE_BOUNDING", "SHAPE_INPUT", "SHAPE_CLIP",
    "SHAPE_INPUTONLY_CLIP", "SHAPE_ORDERS", "SHAPE_ORDER", "ROOT_STACK_OVERLAP",
    "NODE_PID", "NODE_TOPOLOGY", "NODE_PARENT", "NODE_MAP_RELATION",
    "INPUTONLY_INTERSECTION", "FOCUS_MEMBERSHIP", "FOCUS_MAP_STATE", "FOCUS_ANCESTRY",
    "TARGET_CONTAINMENT", "TARGET_CLASS", "TARGET_ROUTE", "PROOF_BYTES",
    "X_OPEN", "X_SYNC", "X_CALL", "X_SHAPE_VERSION", "X_TREE", "X_ATTR_ROOT",
    "X_ROOT_CALL", "X_ATTRIBUTES_CALL", "X_TREE_CALL", "X_FOCUS_CALL", "X_TRANSLATE_CALL",
    "X_SHAPE_EXTENSION", "X_SHAPE_VERSION_CALL",
    "X_ATTR_CLASS_DEPTH", "X_PROPERTY_REPLY", "X_PROPERTY_ABSENT",
    "X_PROPERTY_TYPE", "X_PROPERTY_PID", "X_PROPERTY_TITLE", "X_SHAPE_RECTANGLES",
    "X_TRANSLATION", "OBSERVE_ROOT_GEOMETRY", "OBSERVE_ROOT_TREE", "OBSERVE_MODAL_CHILD",
    "OBSERVE_MODAL_PID", "OBSERVE_IDENTITY", "OBSERVE_MODAL_BORDER", "OBSERVE_NODE_LIMIT",
    "OBSERVE_NODE_PARENT", "OBSERVE_FOCUS_ANCESTRY", "OBSERVE_CHILD_ROUTE", "DISPLAY",
    "OBSERVE_SAMPLES", "OBSERVE_EXCEPTION", "VALIDATE_IDENTITY", "VALIDATE_MODAL_BORDER",
    "TITLE_PROPERTY", "TITLE_ENCODING", "TITLE_CONTROLS", "TITLE_CONVERSION",
    "TITLE_CONVERTED_LIMIT", "TITLE_NATIVE_OUTPUT",
})
_I32 = (-2**31, 2**31 - 1)
_FACT_LIMITS = {
    **{key: _I32 for key in ("x", "y", "width", "height", "border", "actual_x", "actual_y",
                              "actual_width", "actual_height", "depth", "count", "format",
                              "return_code", "window_class", "map_state")},
    "node_index": (0, MAX_NODES), "root_index": (0, MAX_ROOT_CHILDREN),
    "modal_index": (0, MAX_ROOT_CHILDREN), "root_child": (0, 1), "shape_kind": (0, 2),
    "parent_map_state": (0, 2), "focus_depth": (0, MAX_DEPTH + 1),
    "overlap_width": (0, 1280), "overlap_height": (0, 900),
    "child_count": (0, 0xffffffff), "cap": (0, MAX_NODES),
    "property_kind": (0, 1), "remaining_bytes": (0, 0xffffffff),
    "type_matches": (0, 1), "has_pointer": (0, 1), "root_matches": (0, 1),
    "parent_matches": (0, 1), "route_index": (0, MAX_DEPTH),
    "major": (0, 65535), "minor": (0, 65535), "proof_bytes": (0, 2**31 - 1),
    "property_name": (0, 2), "actual_type": (0, 5), "converted_bytes": (0, MAX_CONVERTED_TITLE_BYTES),
}


def failure_document(value):
    """Validate a closed, bounded diagnostic; return a detached canonical copy.

    Validate types and sizes before traversing or encoding any supplied value.
    This intentionally rejects dict/str/int subclasses as well as booleans.
    """
    def valid(ok):
        if not ok:
            raise ValueError("INVALID_FAILURE_DOCUMENT")
    valid(type(value) is dict and len(value) == len(_FAILURE_FIELDS))
    valid(all(type(key) is str and len(key) <= 32 for key in value))
    valid(set(value) == _FAILURE_FIELDS)
    valid(type(value["schema"]) is int and value["schema"] == 1)
    for key, allowed in (("reason", _FAILURE_REASONS), ("call_site", _FAILURE_SITES),
                         ("exception_class", _FAILURE_CLASSES)):
        valid(type(value[key]) is str and len(value[key]) <= 64 and value[key] in allowed)
    facts = value["facts"]
    valid(type(facts) is dict and len(facts) <= MAX_FAILURE_FACTS)
    for key, number in facts.items():
        valid(type(key) is str and len(key) <= 32 and key in _FACT_LIMITS)
        low, high = _FACT_LIMITS[key]
        valid(type(number) is int and low <= number <= high)
    result = {key: value[key] for key in ("schema", "reason", "call_site", "exception_class")}
    result["facts"] = {key: facts[key] for key in sorted(facts)}
    valid(len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode("ascii")) + 1
          <= MAX_FAILURE_BYTES)
    return result


def _numeric_facts(**values):
    """Project only individually safe numeric observations at fixed call sites."""
    return {key: value for key, value in values.items()
            if key in _FACT_LIMITS and type(value) is int
            and _FACT_LIMITS[key][0] <= value <= _FACT_LIMITS[key][1]}


class ProofError(ValueError):
    """Fixed safe reason; never includes X titles, paths, or exception text."""
    def __init__(self, reason="WINDOW_PROOF_UNAVAILABLE", call_site="UNSPECIFIED", facts=None,
                 exception_class="ProofError"):
        document = failure_document({"schema": 1, "reason": reason, "call_site": call_site,
                                     "exception_class": exception_class,
                                     "facts": {} if facts is None else facts})
        self.reason, self.call_site = document["reason"], document["call_site"]
        self.exception_class, self.facts = document["exception_class"], document["facts"]
        super().__init__(self.reason)


def failure_from_exception(exc):
    """Retain validated proof codes, or a fixed type-only fallback; never text."""
    if isinstance(exc, InterruptedError):
        raise exc
    if type(exc) is ProofError:
        try:
            return failure_document({"schema": 1, "reason": exc.reason, "call_site": exc.call_site,
                                     "exception_class": exc.exception_class, "facts": exc.facts})
        except (ValueError, AttributeError):
            pass
    category = {OSError: "OSError", AttributeError: "AttributeError", ValueError: "ValueError",
                TypeError: "TypeError"}.get(type(exc), "OTHER")
    return failure_document({"schema": 1, "reason": "WINDOW_PROOF_UNAVAILABLE",
                             "call_site": "UNEXPECTED_EXCEPTION", "exception_class": category,
                             "facts": {}})


def _require(ok, reason="WINDOW_PROOF_UNAVAILABLE", call_site="UNSPECIFIED", **facts):
    if not ok:
        raise ProofError(reason, call_site, _numeric_facts(**facts))


def _integer(value, low, high, call_site="INTEGER"):
    _require(type(value) is int and low <= value <= high, call_site=call_site)


def _ids(value, cap, minimum=0):
    _require(type(value) is list and minimum <= len(value) <= cap, call_site="IDS")
    for item in value:
        _integer(item, 1, 0xffffffff)
    _require(len(set(value)) == len(value), call_site="IDS")


def _target(action):
    _require(type(action) is str and action in ACTIONS, call_site="ACTION")
    return trust_window.target(action)


def _check_time(deadline):
    _require(time.monotonic() < deadline, call_site="DEADLINE")


def _attrs(value, root_child=False, node_index=0):
    _require(type(value) is dict and set(value) == _ATTRS, call_site="ATTR_RECORD")
    try:
        _integer(value["window_id"], 1, 0xffffffff, "ATTR_ID")
        _integer(value["x"], 0 if root_child else -32768, 1279 if root_child else 32767, "ATTR_X")
        _integer(value["y"], 0 if root_child else -32768, 899 if root_child else 32767, "ATTR_Y")
        _integer(value["width"], 1, 1280, "ATTR_WIDTH")
        _integer(value["height"], 1, 900, "ATTR_HEIGHT")
        _integer(value["border"], 0, 8, "ATTR_BORDER")
        _integer(value["window_class"], 1, 2, "ATTR_CLASS")
        _integer(value["map_state"], 0, 2, "ATTR_MAP_STATE")
        _integer(value["event_mask"], 0, (1 << 25) - 1, "ATTR_EVENT_MASK")
        _integer(value["do_not_propagate_mask"], 0, (1 << 25) - 1, "ATTR_DNP_MASK")
        _require(type(value["override_redirect"]) is bool, call_site="ATTR_OVERRIDE")
        if value["pid"] is not None:
            _integer(value["pid"], 1, 2**31 - 1, "ATTR_PID")
        if value["title_sha256"] is not None:
            _require(type(value["title_sha256"]) is str and
                     re.fullmatch("[0-9a-f]{64}", value["title_sha256"]) is not None,
                     call_site="ATTR_TITLE_DIGEST")
        if value["window_class"] == 2:
            _require(value["border"] == 0, call_site="ATTR_INPUTONLY_BORDER")
        if root_child:
            _require(value["x"] + value["width"] + 2 * value["border"] <= 1280 and
                     value["y"] + value["height"] + 2 * value["border"] <= 900,
                     call_site="ROOT_CHILD_BOUNDS")
            _require(value["map_state"] in (0, 2), call_site="ROOT_CHILD_MAP_STATE")
    except ProofError as exc:
        facts = _numeric_facts(node_index=node_index, root_child=int(root_child),
                               **{key: value[key] for key in
                                  ("x", "y", "width", "height", "border", "window_class", "map_state")})
        raise ProofError(exc.reason, exc.call_site, facts) from None


def _shape(value, width, height, border, window_class, node_index=0):
    _require(type(value) is dict and set(value) == {"bounding", "input", "clip", "orders"},
             call_site="SHAPE_RECORD")
    default = [-border, -border, width + 2 * border, height + 2 * border]
    for kind, shape_kind, site in (("bounding", 0, "SHAPE_BOUNDING"), ("input", 2, "SHAPE_INPUT")):
        rect = value[kind]
        _require(type(rect) is list and len(rect) == 4, call_site="SHAPE_RECTANGLE", shape_kind=shape_kind)
        for coord in rect:
            _integer(coord, -32768, 65535, "SHAPE_COORDINATE")
        _require(rect == default, "INPUT_ROUTE_CHANGED", site,
                 node_index=node_index, shape_kind=shape_kind, width=width, height=height, border=border,
                 actual_x=rect[0], actual_y=rect[1], actual_width=rect[2], actual_height=rect[3])
    if window_class == 1:
        rect = value["clip"]
        _require(type(rect) is list and len(rect) == 4, call_site="SHAPE_RECTANGLE", shape_kind=1)
        for coord in rect:
            _integer(coord, -32768, 65535, "SHAPE_COORDINATE")
        _require(rect == [0, 0, width, height], "INPUT_ROUTE_CHANGED", "SHAPE_CLIP",
                 node_index=node_index, shape_kind=1, width=width, height=height, border=border,
                 actual_x=rect[0], actual_y=rect[1], actual_width=rect[2], actual_height=rect[3])
    else:
        _require(value["clip"] is None, call_site="SHAPE_INPUTONLY_CLIP")
    orders = value["orders"]
    _require(type(orders) is list and len(orders) == (3 if window_class == 1 else 2), call_site="SHAPE_ORDERS")
    for order in orders:
        _integer(order, 0, 3, "SHAPE_ORDER")


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
    try:
        identity = trust_window.validate(proof["window_identity"], action)
    except ValueError:
        raise ProofError(call_site="VALIDATE_IDENTITY") from None
    _require(identity["border"] == 0, call_site="VALIDATE_MODAL_BORDER", border=identity["border"])
    modal_id, pid = identity["window_id"], identity["pid"]
    modal_rect = tuple(identity[k] for k in ("x", "y", "width", "height"))
    roots = proof["root_children"]
    _require(type(roots) is list and 1 <= len(roots) <= MAX_ROOT_CHILDREN)
    for index, record in enumerate(roots):
        _attrs(record, root_child=True, node_index=index)
    root_ids = [record["window_id"] for record in roots]
    _ids(root_ids, MAX_ROOT_CHILDREN, 1)
    _require(proof["root_id"] not in root_ids and modal_id in root_ids)
    modal_index = root_ids.index(modal_id)
    decision = roots[modal_index]
    _require(_identity(decision) == identity and decision["window_class"] == 1 and
             decision["map_state"] == 2 and decision["title_sha256"] is not None)
    for index, record in enumerate(roots[modal_index + 1:], modal_index + 1):
        exterior = (record["x"], record["y"], record["width"] + 2 * record["border"],
                    record["height"] + 2 * record["border"])
        _require(record["map_state"] == 0 or not _overlaps(exterior, modal_rect), "WINDOW_OCCLUDED",
                 "ROOT_STACK_OVERLAP", root_index=index, modal_index=modal_index,
                 window_class=record["window_class"], map_state=record["map_state"],
                 overlap_width=_intersection(exterior, modal_rect)[2],
                 overlap_height=_intersection(exterior, modal_rect)[3])

    tree = proof["dialog_tree"]
    _require(type(tree) is list and 1 <= len(tree) <= MAX_NODES)
    nodes = {}
    for index, node in enumerate(tree):
        _require(type(node) is dict and set(node) == _ATTRS | {"parent", "children", "shape"})
        _attrs({k: node[k] for k in _ATTRS}, node_index=index)
        _integer(node["parent"], 1, 0xffffffff)
        _ids(node["children"], MAX_NODES - 1)
        _shape(node["shape"], node["width"], node["height"], node["border"], node["window_class"], index)
        _require(node["pid"] is None or node["pid"] == pid, "INPUT_ROUTE_CHANGED", "NODE_PID",
                 node_index=index)
        _require(node["window_id"] not in nodes)
        nodes[node["window_id"]] = node
    _require(tree[0]["window_id"] == modal_id and
             {k: tree[0][k] for k in _ATTRS} == decision and
             tree[0]["parent"] == proof["root_id"])
    _require(not (set(nodes) & (set(root_ids) - {modal_id})) and proof["root_id"] not in nodes)
    seen, visible, interiors = [], {}, {}

    def walk(window_id, parent, parent_origin, parent_clip, depth):
        _require(depth <= MAX_DEPTH and window_id in nodes and window_id not in seen,
                 call_site="NODE_TOPOLOGY", depth=depth, count=len(seen))
        node = nodes[window_id]
        _require(node["parent"] == parent, call_site="NODE_PARENT", depth=depth)
        seen.append(window_id)
        if parent in nodes:
            parent_state = nodes[parent]["map_state"]
            _require((parent_state == 2 and node["map_state"] != 1) or
                     (parent_state != 2 and node["map_state"] != 2), call_site="NODE_MAP_RELATION",
                     parent_map_state=parent_state, map_state=node["map_state"], depth=depth)
        border = node["border"]
        outer_x, outer_y = parent_origin[0] + node["x"], parent_origin[1] + node["y"]
        origin = (outer_x + border, outer_y + border)
        exterior = (outer_x, outer_y, node["width"] + 2 * border, node["height"] + 2 * border)
        visible[window_id] = _intersection(parent_clip, exterior)
        interiors[window_id] = _intersection(parent_clip, (*origin, node["width"], node["height"]))
        if node["window_class"] == 2 and node["map_state"] != 0:
            _require(not _overlaps(visible[window_id], modal_rect), "INPUT_ROUTE_CHANGED",
                     "INPUTONLY_INTERSECTION", depth=depth, node_index=len(seen) - 1,
                     x=node["x"], y=node["y"], width=node["width"], height=node["height"],
                     map_state=node["map_state"], window_class=node["window_class"],
                     overlap_width=_intersection(visible[window_id], modal_rect)[2],
                     overlap_height=_intersection(visible[window_id], modal_rect)[3])
        for child in node["children"]:
            walk(child, window_id, origin, interiors[window_id], depth + 1)

    walk(modal_id, proof["root_id"], (0, 0), (0, 0, 1280, 900), 0)
    _require(seen == [node["window_id"] for node in tree])
    _ids(proof["focus_path"], MAX_DEPTH + 1, 1)
    _integer(proof["focus_revert"], 0, 2)
    focus = proof["focus_path"][-1]
    _require(focus in nodes and focus not in (0, 1), "INPUT_ROUTE_CHANGED", "FOCUS_MEMBERSHIP",
             focus_depth=len(proof["focus_path"]))
    focus_path = []
    while focus in nodes:
        _require(nodes[focus]["map_state"] == 2, "INPUT_ROUTE_CHANGED", "FOCUS_MAP_STATE",
                 map_state=nodes[focus]["map_state"], window_class=nodes[focus]["window_class"],
                 focus_depth=len(focus_path), x=nodes[focus]["x"], y=nodes[focus]["y"],
                 width=nodes[focus]["width"], height=nodes[focus]["height"])
        focus_path.append(focus)
        focus = nodes[focus]["parent"]
    focus_path.reverse()
    _require(focus == proof["root_id"] and focus_path == proof["focus_path"], "INPUT_ROUTE_CHANGED",
             "FOCUS_ANCESTRY", root_matches=int(focus == proof["root_id"]), focus_depth=len(focus_path))
    route, current = [modal_id], modal_id
    _require(_contains(visible[current], point), call_site="TARGET_CONTAINMENT")
    while True:
        hit = next((child for child in reversed(nodes[current]["children"])
                    if nodes[child]["map_state"] == 2 and _contains(visible[child], point)), None)
        if hit is None:
            break
        _require(nodes[hit]["window_class"] == 1, "INPUT_ROUTE_CHANGED", "TARGET_CLASS",
                 window_class=nodes[hit]["window_class"], route_index=len(route) - 1)
        route.append(hit)
        current = hit
    return route


def validate(proof, action):
    """Reject any extra keys, loose types, unsupported shapes, or ambiguous route."""
    route = _analyze(proof, action)
    _ids(proof["target_route"], MAX_DEPTH + 1, 1)
    _require(proof["target_route"] == route, "INPUT_ROUTE_CHANGED", "TARGET_ROUTE")
    raw = json.dumps(proof, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    _require(len(raw) + 1 <= MAX_PROOF_BYTES, call_site="PROOF_BYTES", proof_bytes=len(raw) + 1)
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


class _TextProperty(C.Structure):
    _fields_ = [("value", C.c_void_p), ("encoding", C.c_ulong),
                ("format", C.c_int), ("nitems", C.c_ulong)]


def _text_controls(text):
    # This is an output repertoire check, not a complete COMPOUND_TEXT parser.
    _require(all((ord(c) >= 32 or c in '\t\n') and not 127 <= ord(c) <= 159 for c in text),
             call_site="TITLE_CONTROLS")


def _title_digest(name, encoding, raw):
    _require(type(name) is bytes and name in (b"_NET_WM_NAME", b"WM_NAME"), call_site="TITLE_PROPERTY")
    _require(type(encoding) is bytes and encoding in (b"STRING", b"UTF8_STRING", b"COMPOUND_TEXT"), call_site="TITLE_ENCODING")
    _require(type(raw) is bytes and len(raw) <= MAX_TITLE_BYTES, call_site="TITLE_ENCODING")
    framed = TITLE_DOMAIN + struct.pack('>H', len(name)) + name
    framed += struct.pack('>H', len(encoding)) + encoding + struct.pack('>I', len(raw)) + raw
    return hashlib.sha256(framed).hexdigest()


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
            "Xutf8TextPropertyToTextList": ([ptr, p(_TextProperty), p(p(ptr)), p(i)], i),
            "XFreeStringList": ([p(ptr)], None),
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
            _require(bool(self.connection), call_site="X_OPEN")
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
        _require(not self.error, call_site="X_SYNC")

    def call(self, fn, *args, call_site="X_CALL"):
        _check_time(self.deadline)
        result = fn(self.connection, *args)
        self.sync()
        _require(bool(result), call_site=call_site)
        return result

    def root(self):
        return int(self.call(self.x.XDefaultRootWindow, call_site="X_ROOT_CALL"))

    def version(self):
        event, error, major, minor = C.c_int(), C.c_int(), C.c_int(), C.c_int()
        self.call(self.ext.XShapeQueryExtension, C.byref(event), C.byref(error), call_site="X_SHAPE_EXTENSION")
        self.call(self.ext.XShapeQueryVersion, C.byref(major), C.byref(minor), call_site="X_SHAPE_VERSION_CALL")
        _require((major.value, minor.value) >= (1, 1), call_site="X_SHAPE_VERSION",
                 major=major.value, minor=minor.value)
        return [major.value, minor.value]

    def tree(self, window, cap):
        root, parent, count = C.c_ulong(), C.c_ulong(), C.c_uint()
        children = C.POINTER(C.c_ulong)()
        try:
            self.call(self.x.XQueryTree, window, C.byref(root), C.byref(parent), C.byref(children),
                      C.byref(count), call_site="X_TREE_CALL")
            _require(count.value <= cap and (count.value == 0 or bool(children)), call_site="X_TREE",
                     child_count=count.value, cap=cap, has_pointer=int(bool(children)))
            result = [int(children[i]) for i in range(count.value)]
            _ids(result, cap)
            return root.value, parent.value, result
        finally:
            if children:
                self.x.XFree(children)

    def attributes(self, window, root):
        value = _WindowAttributes()
        self.call(self.x.XGetWindowAttributes, window, C.byref(value), call_site="X_ATTRIBUTES_CALL")
        _require(value.root == root and value.override_redirect in (0, 1), call_site="X_ATTR_ROOT",
                 root_matches=int(value.root == root))
        _require((value.window_class == 1 and value.depth in (24, 32)) or
                 (value.window_class == 2 and value.depth == 0), call_site="X_ATTR_CLASS_DEPTH",
                 window_class=value.window_class, depth=value.depth, x=value.x, y=value.y,
                 width=value.width, height=value.height, border=value.border_width, map_state=value.map_state)
        return {"window_id": window, "x": value.x, "y": value.y, "width": value.width,
                "height": value.height, "border": value.border_width, "window_class": value.window_class,
                "map_state": value.map_state, "override_redirect": bool(value.override_redirect),
                "event_mask": value.all_event_masks, "do_not_propagate_mask": value.do_not_propagate_mask,
                "pid": self.property(window, b"_NET_WM_PID", 32, b"CARDINAL"),
                "title_sha256": self.title(window)}

    def _title_type_atoms(self):
        # Fixed names only; never resolve an arbitrary atom name into public text.
        if not hasattr(self, '_title_atoms'):
            self._title_atoms = {}
            for name in (b"STRING", b"UTF8_STRING", b"COMPOUND_TEXT", b"CARDINAL"):
                _check_time(self.deadline)
                self._title_atoms[name] = int(self.x.XInternAtom(self.connection, name, True))
                self.sync()
        return self._title_atoms

    def _compound_text(self, raw, encoding):
        _check_time(self.deadline)
        if not raw:
            return ''
        source = C.create_string_buffer(raw)
        prop = _TextProperty(C.cast(source, C.c_void_p), encoding, 8, len(raw))
        strings, count = C.POINTER(C.c_void_p)(), C.c_int()
        try:
            status = self.x.Xutf8TextPropertyToTextList(self.connection, C.byref(prop), C.byref(strings), C.byref(count))
            _check_time(self.deadline)
            _require(status == 0 and count.value == 1 and bool(strings), call_site="TITLE_CONVERSION",
                     return_code=status, count=count.value, has_pointer=int(bool(strings)))
            address = strings[0]  # c_void_p avoids c_char_p's unbounded automatic string copy.
            _require(bool(address), call_site="TITLE_NATIVE_OUTPUT", has_pointer=int(bool(address)))
            data = C.cast(address, C.POINTER(C.c_ubyte))
            length = 0
            while length < MAX_CONVERTED_TITLE_BYTES and data[length] != 0:
                length += 1
            _require(length < MAX_CONVERTED_TITLE_BYTES, call_site="TITLE_CONVERTED_LIMIT", converted_bytes=length)
            converted = C.string_at(address, length)
            try:
                text = converted.decode('utf-8', errors='strict')
            except UnicodeError:
                raise ProofError(call_site="TITLE_ENCODING") from None
            _text_controls(text)
            _check_time(self.deadline)
            return text
        finally:
            if strings:
                self.x.XFreeStringList(strings)

    def _title_property(self, window, name):
        _require(name in (b"_NET_WM_NAME", b"WM_NAME"), call_site="TITLE_PROPERTY")
        kind = 2 if name == b"_NET_WM_NAME" else 1
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
            _require(code == 0 and remaining.value == 0, call_site="X_PROPERTY_REPLY",
                     property_kind=1, property_name=kind, return_code=code, remaining_bytes=remaining.value)
            if actual.value == 0:
                _require(fmt.value == 0 and count.value == 0, call_site="X_PROPERTY_ABSENT",
                         property_kind=1, property_name=kind, format=fmt.value, count=count.value)
                return None
            atoms = self._title_type_atoms()
            names = (b"STRING", b"UTF8_STRING", b"COMPOUND_TEXT", b"CARDINAL")
            encoding = next((n for n in names if atoms[n] != 0 and atoms[n] == actual.value), None)
            category = names.index(encoding) + 1 if encoding is not None else 5
            allowed = (b"UTF8_STRING",) if kind == 2 else names[:3]
            _require(encoding in allowed and fmt.value == 8, call_site="X_PROPERTY_TYPE",
                     property_kind=1, property_name=kind, actual_type=category,
                     type_matches=int(encoding in allowed), format=fmt.value)
            _require(count.value <= MAX_TITLE_BYTES and (count.value == 0 or bool(data)),
                     call_site="X_PROPERTY_TITLE", property_name=kind, count=count.value, has_pointer=int(bool(data)))
            raw = C.string_at(data, count.value) if count.value else b""
            _require(b'\0' not in raw, call_site="TITLE_ENCODING", property_name=kind, actual_type=category)
            if encoding == b"COMPOUND_TEXT":
                self._compound_text(raw, actual.value)
            else:
                try:
                    text = raw.decode('utf-8' if encoding == b"UTF8_STRING" else 'latin-1', errors='strict')
                except UnicodeError:
                    raise ProofError(call_site="TITLE_ENCODING", facts={'property_name':kind,'actual_type':category}) from None
                _text_controls(text)
            _check_time(self.deadline)
            return _title_digest(name, encoding, raw)
        finally:
            if data:
                self.x.XFree(data)

    def title(self, window):
        # EWMH preference: malformed modern data fails; only absence permits fallback.
        modern = self._title_property(window, b"_NET_WM_NAME")
        return modern if modern is not None else self._title_property(window, b"WM_NAME")

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
            _require(code == 0 and remaining.value == 0, call_site="X_PROPERTY_REPLY",
                     property_kind=int(expected_format != 32), return_code=code, remaining_bytes=remaining.value)
            if actual.value == 0:
                _require(fmt.value == 0 and count.value == 0, call_site="X_PROPERTY_ABSENT",
                         property_kind=int(expected_format != 32), format=fmt.value, count=count.value)
                return None
            expected = self.x.XInternAtom(self.connection, expected_type, True)
            self.sync()
            _require(expected != 0 and actual.value == expected and fmt.value == expected_format,
                     call_site="X_PROPERTY_TYPE", property_kind=int(expected_format != 32),
                     type_matches=int(expected != 0 and actual.value == expected), format=fmt.value)
            if expected_format == 32:
                _require(count.value == 1 and bool(data), call_site="X_PROPERTY_PID",
                         count=count.value, has_pointer=int(bool(data)))
                return int(C.cast(data, C.POINTER(C.c_ulong))[0])
            _require(count.value <= MAX_TITLE_BYTES and (count.value == 0 or bool(data)),
                     call_site="X_PROPERTY_TITLE", count=count.value, has_pointer=int(bool(data)))
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
                _require(count.value == 1 and bool(rectangles), "INPUT_ROUTE_CHANGED", "X_SHAPE_RECTANGLES",
                         shape_kind=kind, count=count.value, window_class=window_class,
                         has_pointer=int(bool(rectangles)))
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
        self.call(self.x.XGetInputFocus, C.byref(focus), C.byref(revert), call_site="X_FOCUS_CALL")
        return focus.value, revert.value

    def child_at(self, window, point):
        x, y, child = C.c_int(), C.c_int(), C.c_ulong()
        self.call(self.x.XTranslateCoordinates, window, window, *point, C.byref(x), C.byref(y),
                  C.byref(child), call_site="X_TRANSLATE_CALL")
        _require((x.value, y.value) == point, call_site="X_TRANSLATION", x=x.value, y=y.value)
        return child.value


def _observation(x, ide_pid, action, deadline):
    _check_time(deadline)
    root = x.root()
    root_attrs = x.attributes(root, root)
    _attrs(root_attrs)
    _require(root_attrs["window_class"] == 1 and root_attrs["map_state"] == 2 and
             [root_attrs[k] for k in ("x", "y", "width", "height", "border")] == [0, 0, 1280, 900, 0],
             call_site="OBSERVE_ROOT_GEOMETRY",
             **{key: root_attrs[key] for key in ("x", "y", "width", "height", "border", "window_class", "map_state")})
    version = x.version()
    root_shape = x.shape(root, 1)
    tree_root, parent, children = x.tree(root, MAX_ROOT_CHILDREN)
    _require(tree_root == root and parent == 0, call_site="OBSERVE_ROOT_TREE",
             root_matches=int(tree_root == root), parent_matches=int(parent == 0))
    roots = [x.attributes(child, root) for child in children]
    for index, record in enumerate(roots):
        _attrs(record, root_child=True, node_index=index)
    point = _target(action)
    modal_id = x.child_at(root, point)
    _require(modal_id in children, call_site="OBSERVE_MODAL_CHILD", child_count=len(children))
    decision = roots[children.index(modal_id)]
    _require(decision["pid"] == ide_pid, call_site="OBSERVE_MODAL_PID")
    identity = _identity(decision)
    try:
        trust_window.validate(identity, action)
    except ValueError:
        raise ProofError(call_site="OBSERVE_IDENTITY") from None
    _require(identity["border"] == 0, call_site="OBSERVE_MODAL_BORDER", border=identity["border"])
    nodes, seen = [], set()

    def walk(record, parent_id, depth):
        _check_time(deadline)
        window = record["window_id"]
        _require(depth <= MAX_DEPTH and len(seen) < MAX_NODES and window not in seen,
                 call_site="OBSERVE_NODE_LIMIT", depth=depth, count=len(seen))
        seen.add(window)
        origin, actual_parent, child_ids = x.tree(window, MAX_NODES - len(seen))
        _require(origin == root and actual_parent == parent_id, call_site="OBSERVE_NODE_PARENT",
                 depth=depth, root_matches=int(origin == root), parent_matches=int(actual_parent == parent_id))
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
    _require(focus == root and focus_path, "INPUT_ROUTE_CHANGED", "OBSERVE_FOCUS_ANCESTRY",
             focus_depth=len(focus_path), root_matches=int(focus == root))
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
        _require(x.child_at(window, relative) == expected, "INPUT_ROUTE_CHANGED", "OBSERVE_CHILD_ROUTE",
                 route_index=index, x=relative[0], y=relative[1])
    _check_time(deadline)
    return validate(proof, action)


def observe(ide_pid, action):
    """Two exact complete samples, within one budget, from the fixed owned display."""
    _integer(ide_pid, 1, 2**31 - 1)
    _target(action)
    display = os.environ.get("DISPLAY", "")
    _require(re.fullmatch(r":[0-9]{1,4}", display) is not None, call_site="DISPLAY")
    deadline = time.monotonic() + PROBE_SECONDS
    try:
        with _X11(display, deadline) as x:
            first = _observation(x, ide_pid, action, deadline)
            second = _observation(x, ide_pid, action, deadline)
            _require(first == second, "WINDOW_IDENTITY_CHANGED", "OBSERVE_SAMPLES")
            _check_time(deadline)
        _check_time(deadline)
        return second
    except InterruptedError:
        raise
    except (OSError, AttributeError) as exc:
        category = "OSError" if isinstance(exc, OSError) else "AttributeError"
        raise ProofError(call_site="OBSERVE_EXCEPTION", exception_class=category) from None
