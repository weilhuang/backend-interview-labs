#!/usr/bin/env python3
"""Bounded real host RESP roundtrip; only synthetic run-owned CI data."""
import argparse, os, re, socket

def probe(port,marker,read_only=False):
    if os.environ.get('CI')!='true' or not re.fullmatch(r'totalacademy-ci-\d+-\d+',marker):raise ValueError('CI marker required')
    with socket.create_connection(('127.0.0.1',port),timeout=10) as connection:
        stream=connection.makefile('rb')
        def command(*parts):
            parts=[str(value).encode() for value in parts]
            connection.sendall(b'*'+str(len(parts)).encode()+b'\r\n'+b''.join(b'$'+str(len(value)).encode()+b'\r\n'+value+b'\r\n' for value in parts))
            line=stream.readline(4096)
            if line.startswith(b'+'):return line[1:-2].decode()
            if line.startswith(b'$'):
                size=int(line[1:-2]);assert 0<=size<=4096
                value=stream.read(size);assert stream.read(2)==b'\r\n';return value.decode()
            raise ValueError('unexpected RESP response')
        assert command('AUTH',os.environ['REDIS_PASSWORD'])=='OK'
        if not read_only:assert command('SET','academy:ci',marker)=='OK'
        assert command('GET','academy:ci')==marker
    print('REDIS_SMOKE_OK')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--marker',required=True);p.add_argument('--read-only',action='store_true');a=p.parse_args();probe(a.port,a.marker,a.read_only)
