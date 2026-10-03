"""仅为本地传输/进程测试提供RESP假服务。它不执行Lua，绝不是Redis集成测试。"""
import socketserver,threading,time

class State:
    def __init__(self,password='teaching-password'):
        self.password=password; self.data={}; self.lock=threading.Lock();self.mode='ok'
    def apply(self,args):
        command=args[0].upper()
        with self.lock:
            if command=='PING':return 'PONG'
            if command=='HGET':return self.data.get(args[1],{}).get(args[2])
            if command=='EVAL':
                script,key=args[1],args[3]
                if 'academy:c11:seed:v1' in script:
                    if key in self.data:return 0
                    self.data[key]={'schema':'1','stock':'10'};return 1
                if 'academy:c11:reserve:v1' in script:
                    data=self.data.get(key,{})
                    if data.get('schema')!='1':return 'NOT_SEEDED'
                    id,qty=args[4],args[5];field='request:'+id
                    if field+':qty' in data:
                        if data[field+':qty']!=qty:return 'CONFLICT'
                        return 'REPLAY|'+data[field+':remaining']
                    remaining=int(data['stock'])-int(qty)
                    if remaining<0:return 'SOLD_OUT'
                    data.update({'stock':str(remaining),field+':qty':qty,field+':remaining':str(remaining)})
                    return 'CREATED|'+str(remaining)
            raise ValueError('unsupported fake command')

class FakeRedis:
    def __init__(self,password='teaching-password'):
        self.state=State(password)
        state=self.state
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                authenticated=not state.password
                while True:
                    line=self.rfile.readline()
                    if not line:return
                    if not line.startswith(b'*'):return
                    args=[]
                    for _ in range(int(line[1:])):
                        length=int(self.rfile.readline()[1:]);args.append(self.rfile.read(length).decode());self.rfile.read(2)
                    if state.mode=='timeout':time.sleep(1.2);return
                    if state.mode=='malformed':self.wfile.write(b'?bad\r\n');return
                    if args[0]=='AUTH':
                        authenticated=args[1]==state.password
                        self.wfile.write(b'+OK\r\n' if authenticated else b'-WRONGPASS invalid\r\n');continue
                    if not authenticated:self.wfile.write(b'-NOAUTH required\r\n');continue
                    try:result=state.apply(args)
                    except ValueError:self.wfile.write(b'-ERR unsupported\r\n');continue
                    if result is None:self.wfile.write(b'$-1\r\n')
                    elif isinstance(result,int):self.wfile.write(f':{result}\r\n'.encode())
                    else:
                        data=result.encode();self.wfile.write(f'${len(data)}\r\n'.encode()+data+b'\r\n')
        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address=True;daemon_threads=True
        self.server=Server(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    @property
    def port(self):return self.server.server_address[1]
    def start(self):self.thread.start();return self
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
