#!/usr/bin/env python3
"""One bounded loopback HTTP request, without proxy/redirect support."""
import argparse, json, os, re, urllib.error, urllib.request
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('redirects forbidden')
def call(port,path,value,status,envelope=False):
    if os.environ.get('CI')!='true' or not 1024<=port<=65535 or not re.fullmatch(r'/api/[A-Za-z0-9_/?=.-]+',path) or '..' in path or '//' in path:raise ValueError('unsafe request')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=None if value is None else value.encode(),headers={'Content-Type':'application/json'},method='GET' if value is None else 'POST')
    try:response=opener.open(request,timeout=40)
    except urllib.error.HTTPError as error:response=error
    with response:
        allowed={int(x) for x in str(status).split(',')}
        if not allowed or not allowed<={200,503}:raise ValueError('unexpected allowed status set')
        if response.status not in allowed:raise ValueError('unexpected HTTP status '+str(response.status))
        data=response.read(1024*1024+1)
        if len(data)>1024*1024:raise ValueError('HTTP output too large')
        body=json.loads(data)
        return {'status_code':response.status,'body':body} if envelope else body
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--path',required=True);p.add_argument('--json');p.add_argument('--status',default='200');p.add_argument('--envelope',action='store_true');a=p.parse_args();print(json.dumps(call(a.port,a.path,a.json,a.status,a.envelope),ensure_ascii=False))
