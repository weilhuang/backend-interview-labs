"""Bounded root-window observations on the existing private Xvfb only."""
import ctypes as C
import hashlib
import os
import re


def require(ok):
    if not ok:
        raise ValueError('PROFILE_WINDOW_UNVERIFIED')


def validate(value):
    require(type(value) is dict and set(value)=={'window_id','pid','x','y','width','height','border','title_sha256'})
    for key,low,high in [('window_id',1,2**32-1),('pid',1,2**31-1),('x',0,1279),('y',0,899),
                         ('width',1,1280),('height',1,900),('border',0,8)]:
        require(type(value[key]) is int and low<=value[key]<=high)
    require(value['x']+value['width']<=1280 and value['y']+value['height']<=900)
    require(type(value['title_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['title_sha256']) is not None)
    return value


def inventory(value, pid=None):
    require(type(value) is list and 1<=len(value)<=4)
    seen=set()
    for row in value:
        validate(row); require(row['window_id'] not in seen); seen.add(row['window_id'])
        if pid is not None:require(row['pid']==pid)
    return value


def point(value, window):
    require(type(value) is list and len(value)==2 and all(type(n) is int for n in value))
    require(window['x']<=value[0]<window['x']+window['width'] and window['y']<=value[1]<window['y']+window['height'])
    return value


class Attributes(C.Structure):
    _fields_=[('x',C.c_int),('y',C.c_int),('width',C.c_int),('height',C.c_int),('border_width',C.c_int),
              ('depth',C.c_int),('visual',C.c_void_p),('root',C.c_ulong),('class_',C.c_int),
              ('bit_gravity',C.c_int),('win_gravity',C.c_int),('backing_store',C.c_int),
              ('backing_planes',C.c_ulong),('backing_pixel',C.c_ulong),('save_under',C.c_int),
              ('colormap',C.c_ulong),('map_installed',C.c_int),('map_state',C.c_int),
              ('all_event_masks',C.c_long),('your_event_mask',C.c_long),('do_not_propagate_mask',C.c_long),
              ('override_redirect',C.c_int),('screen',C.c_void_p)]


def focused_window(focus, terminal, parent):
    """Read only one bounded focus ancestry, never change focus or walk a subtree."""
    seen=set()
    for _ in range(8):
        require(type(focus) is int and 1<focus<2**32 and focus not in seen)
        if focus==terminal:return
        seen.add(focus);focus=parent(focus)
    raise ValueError('PROFILE_WINDOW_UNVERIFIED')


def observe(expected_pid=None, terminal_pid=None):
    """One root query, max32 candidates/max4 visible windows, no recursion or raw titles."""
    display=os.environ.get('DISPLAY','');require(re.fullmatch(r':[0-9]{1,4}',display) is not None)
    if expected_pid is not None:require(type(expected_pid) is int and 0<expected_pid<2**31)
    if terminal_pid is not None:require(type(terminal_pid) is int and 0<terminal_pid<2**31 and terminal_pid!=expected_pid)
    x=C.CDLL('libX11.so.6');ptr=C.c_void_p;u=C.c_ulong;i=C.c_int
    declarations={
      'XOpenDisplay':([C.c_char_p],ptr),'XCloseDisplay':([ptr],i),'XDefaultRootWindow':([ptr],u),
      'XQueryTree':([ptr,u,C.POINTER(u),C.POINTER(u),C.POINTER(C.POINTER(u)),C.POINTER(C.c_uint)],i),
      'XGetInputFocus':([ptr,C.POINTER(u),C.POINTER(i)],i),
      'XGetWindowAttributes':([ptr,u,C.POINTER(Attributes)],i),
      'XTranslateCoordinates':([ptr,u,u,i,i,C.POINTER(i),C.POINTER(i),C.POINTER(u)],i),
      'XInternAtom':([ptr,C.c_char_p,i],u),
      'XGetWindowProperty':([ptr,u,u,C.c_long,C.c_long,i,u,C.POINTER(u),C.POINTER(i),C.POINTER(u),C.POINTER(u),C.POINTER(ptr)],i),
      'XFree':([ptr],i),'XSync':([ptr,i],i)}
    for name,(args,result) in declarations.items():fn=getattr(x,name);fn.argtypes=args;fn.restype=result
    errors=[];callback=C.CFUNCTYPE(i,ptr,ptr);handler=callback(lambda *_:errors.append(True) or 0)
    x.XSetErrorHandler.argtypes=[callback];x.XSetErrorHandler.restype=ptr;x.XSetErrorHandler(handler)
    connection=x.XOpenDisplay(display.encode());require(bool(connection))
    def checked(result):
        x.XSync(connection,False);require(bool(result) and not errors)
    def prop(window,name,fmt_value,type_name):
        atom=x.XInternAtom(connection,name,True);require(atom!=0)
        actual=u();fmt=i();count=u();remaining=u();data=ptr()
        try:
            code=x.XGetWindowProperty(connection,window,atom,0,256,False,0,C.byref(actual),C.byref(fmt),C.byref(count),C.byref(remaining),C.byref(data))
            x.XSync(connection,False)
            require(code==0 and not errors and remaining.value==0 and fmt.value==fmt_value and bool(data))
            require(actual.value==x.XInternAtom(connection,type_name,True))
            if fmt_value==32:
                require(count.value==1);return C.cast(data,C.POINTER(u))[0]
            require(count.value<=1024);return C.string_at(data,count.value)
        finally:
            if data:x.XFree(data)
    listing=C.POINTER(u)()
    try:
        root=x.XDefaultRootWindow(connection);parent=u();returned_root=u();count=C.c_uint()
        checked(x.XQueryTree(connection,root,C.byref(returned_root),C.byref(parent),C.byref(listing),C.byref(count)))
        require(returned_root.value==root and count.value<=32)
        rows=[]
        for at in range(count.value):
            window=listing[at];attrs=Attributes();checked(x.XGetWindowAttributes(connection,window,C.byref(attrs)))
            if attrs.map_state!=2:continue  # Only IsViewable windows can enter the public image.
            require(attrs.root==root)
            pid=prop(window,b'_NET_WM_PID',32,b'CARDINAL')
            if expected_pid is not None:require(pid in (expected_pid,terminal_pid))  # No unrelated/authentication process windows.
            left=i();top=i();child=u();checked(x.XTranslateCoordinates(connection,window,root,0,0,C.byref(left),C.byref(top),C.byref(child)))
            title=prop(window,b'WM_NAME',8,b'STRING')
            rows.append(validate({'window_id':window,'pid':pid,'x':left.value,'y':top.value,
                'width':attrs.width,'height':attrs.height,'border':attrs.border_width,'title_sha256':hashlib.sha256(title).hexdigest()}))
        result=inventory(sorted(rows,key=lambda row:row['window_id']),expected_pid if terminal_pid is None else None)
        if terminal_pid is not None:
            terminals=[row for row in result if row['pid']==terminal_pid];require(len(terminals)==1)
            focus=u();revert=i();checked(x.XGetInputFocus(connection,C.byref(focus),C.byref(revert)))
            def parent_of(window):
                ancestor=u();top=u();members=C.POINTER(u)();size=C.c_uint()
                try:
                    checked(x.XQueryTree(connection,window,C.byref(top),C.byref(ancestor),C.byref(members),C.byref(size)))
                    require(top.value==root and size.value<=32);return int(ancestor.value)
                finally:
                    if members:x.XFree(members)
            focused_window(int(focus.value),terminals[0]['window_id'],parent_of)
        return result
    finally:
        if listing:x.XFree(listing)
        x.XCloseDisplay(connection)
