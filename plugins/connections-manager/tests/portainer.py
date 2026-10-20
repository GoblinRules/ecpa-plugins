"""Native helper MCP checks against a synthetic Portainer HTTP server."""
import json, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def check(api, helper, data):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            seen.append(self.path)
            assert self.headers.get('X-API-Key') == 'synthetic-portainer'
            self.send_response(200);self.end_headers()
            if '/logs?' in self.path:
                body=b'fixture log synthetic-portainer\n'
                self.wfile.write(bytes([1,0,0,0])+len(body).to_bytes(4,'big')+body)
            else:
                self.wfile.write(json.dumps([{'Id':1,'Name':'fixture','Env':['PASSWORD=never-return'],'GitConfig':{'Password':'never-return'},'State':'running'}]).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        connection={'id':'portainer-test','name':'Portainer test','service':'portainer','account_id':'','base_url':f'http://127.0.0.1:{server.server_port}'}
        state=api('save',{'version':api('state')['version'],'connection':connection,'token':'synthetic-portainer'})
        assert api('verify',{'id':'portainer-test'})['service']=='portainer'
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        for name,args in [('portainer_environments',{}),('portainer_stacks',{}),('portainer_containers',{'environment_id':1}),('portainer_logs',{'environment_id':1,'container_id':'abcdef123456'}),('portainer_restart',{}),('portainer_logs',{'environment_id':1,'container_id':'../auth'})]:
            messages.append({'jsonrpc':'2.0','id':len(messages),'method':'tools/call','params':{'name':name,'arguments':args}})
        result=subprocess.run([helper,'--data-dir',str(data),'portainer-mcp','portainer-test'],input='\n'.join(map(json.dumps,messages))+'\n',capture_output=True,text=True,timeout=20)
        assert result.returncode==0,result.stderr
        assert 'synthetic-portainer' not in result.stdout+result.stderr
        assert 'never-return' not in result.stdout
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        assert len(replies)==8 and len(replies[1]['result']['tools'])==4
        assert all(t['annotations']['readOnlyHint'] for t in replies[1]['result']['tools'])
        assert json.loads(replies[5]['result']['content'][0]['text'])['logs']=='fixture log [REDACTED]\n'
        assert replies[6]['result']['isError'] and replies[7]['result']['isError']
        assert len(seen)==5,seen
        api('delete',{'version':state['version'],'id':'portainer-test'})
        print('PASS: Portainer vault save/verify, stdio MCP handshake and four read-only tools, metadata filtering, log framing/redaction, blocked write and traversal requests',flush=True)
    finally:
        server.shutdown();server.server_close();thread.join()
