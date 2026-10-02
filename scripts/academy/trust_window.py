"""Bounded read-only X11 identity of one window in the owned validation display."""
import ctypes as C
import hashlib
import os
import re

TARGET=(596,517)  # The reviewed normal Trust Project button; never the parent checkbox.

def require(ok):
    if not ok:raise ValueError('invalid validation window identity')

def validate(value):
    fields={'window_id','pid','x','y','width','height','border','title_sha256'}
    require(type(value) is dict and set(value)==fields)
    limits={'window_id':(1,0xffffffff),'pid':(1,2**31-1),'x':(0,1279),'y':(0,899),
            'width':(1,1280),'height':(1,900),'border':(0,8)}
    for key,(low,high) in limits.items():require(type(value[key]) is int and low<=value[key]<=high)
    require(value['x']+value['width']<=1280 and value['y']+value['height']<=900)
    require(value['x']<=TARGET[0]<value['x']+value['width'] and value['y']<=TARGET[1]<value['y']+value['height'])
    require(type(value['title_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['title_sha256']) is not None)
    return value

def observe(ide_pid):
    """No window-tree traversal, raw titles, arbitrary display or arbitrary target."""
    require(type(ide_pid) is int and 1<=ide_pid<2**31)
    display=os.environ.get('DISPLAY','');require(re.fullmatch(r':[0-9]{1,4}',display) is not None)
    x=C.CDLL('libX11.so.6');ptr=C.c_void_p;u=C.c_ulong;i=C.c_int;ui=C.c_uint
    declarations={
      'XOpenDisplay':([C.c_char_p],ptr),'XCloseDisplay':([ptr],i),'XDefaultRootWindow':([ptr],u),
      'XTranslateCoordinates':([ptr,u,u,i,i,C.POINTER(i),C.POINTER(i),C.POINTER(u)],i),
      'XGetGeometry':([ptr,u,C.POINTER(u),C.POINTER(i),C.POINTER(i),C.POINTER(ui),C.POINTER(ui),C.POINTER(ui),C.POINTER(ui)],i),
      'XInternAtom':([ptr,C.c_char_p,i],u),
      'XGetWindowProperty':([ptr,u,u,C.c_long,C.c_long,i,u,C.POINTER(u),C.POINTER(i),C.POINTER(u),C.POINTER(u),C.POINTER(ptr)],i),
      'XFree':([ptr],i),'XSync':([ptr,i],i)}
    for name,(args,result) in declarations.items():fn=getattr(x,name);fn.argtypes=args;fn.restype=result
    errors=[];callback=C.CFUNCTYPE(i,ptr,ptr)
    handler=callback(lambda *_:errors.append(True) or 0)
    x.XSetErrorHandler.argtypes=[callback];x.XSetErrorHandler.restype=ptr;x.XSetErrorHandler(handler)
    connection=x.XOpenDisplay(display.encode());require(bool(connection))
    def checked(result):
        x.XSync(connection,False);require(not errors and bool(result))
    def prop(window,name,expected_format,expected_type):
        atom=x.XInternAtom(connection,name,True);require(atom!=0)
        actual=u();fmt=i();count=u();remaining=u();data=ptr()
        try:
            code=x.XGetWindowProperty(connection,window,atom,0,256,False,0,C.byref(actual),C.byref(fmt),C.byref(count),C.byref(remaining),C.byref(data))
            x.XSync(connection,False);require(code==0 and not errors and remaining.value==0 and fmt.value==expected_format and bool(data))
            require(actual.value==x.XInternAtom(connection,expected_type,True))
            if expected_format==32:
                require(count.value==1);return C.cast(data,C.POINTER(u))[0]
            require(count.value<=1024);return C.string_at(data,count.value)
        finally:
            if data:x.XFree(data)
    try:
        root=x.XDefaultRootWindow(connection);dest_x=i();dest_y=i();window=u()
        checked(x.XTranslateCoordinates(connection,root,root,*TARGET,C.byref(dest_x),C.byref(dest_y),C.byref(window)))
        require(window.value!=0 and window.value!=root)
        origin=u();left=i();top=i();width=ui();height=ui();border=ui();depth=ui()
        checked(x.XGetGeometry(connection,window,C.byref(origin),C.byref(left),C.byref(top),C.byref(width),C.byref(height),C.byref(border),C.byref(depth)))
        require(origin.value==root)
        child=u();checked(x.XTranslateCoordinates(connection,window,root,0,0,C.byref(left),C.byref(top),C.byref(child)))
        pid=prop(window,b'_NET_WM_PID',32,b'CARDINAL');require(pid==ide_pid)
        # WM_NAME is bounded and hashed only; the human reviews actual title/text pixels.
        title=prop(window,b'WM_NAME',8,b'STRING')
        return validate({'window_id':window.value,'pid':pid,'x':left.value,'y':top.value,
                         'width':width.value,'height':height.value,'border':border.value,
                         'title_sha256':hashlib.sha256(title).hexdigest()})
    finally:x.XCloseDisplay(connection)
