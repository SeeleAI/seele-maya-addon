import json, os, sys, threading, unittest
from http.client import HTTPConnection
sys.path.insert(0,os.path.abspath('SeeleMaya/scripts'))
import seele_maya.bridge.server as server

class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.ALLOWED_ORIGINS=('https://app.test',)
        cls.httpd=server.BoundedHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls): cls.httpd.shutdown(); cls.httpd.server_close(); cls.thread.join(2)
    def request(self,path,origin):
        conn=HTTPConnection('127.0.0.1',self.httpd.server_port,timeout=3); conn.request('GET',path,headers={'Origin':origin}); response=conn.getresponse(); body=json.loads(response.read() or b'{}'); conn.close(); return response.status,body
    def test_health_mock_not_ready(self):
        status,body=self.request('/v1/health','https://app.test')
        self.assertEqual(200,status); self.assertEqual([],body['data']['formats']); self.assertFalse(body['data']['capabilities']['importers']['fbx']['ready'])
    def test_origin_rejected(self): self.assertEqual(403,self.request('/v1/health','https://evil.test')[0])
    def test_unknown_transfer(self): self.assertEqual(404,self.request('/v1/transfers/missing','https://app.test')[0])
    def test_receiver_lifecycle(self):
        old_port=server.PORT
        try:
            server.PORT=0; self.assertTrue(server.start()['running']); self.assertTrue(server.status()['running']); self.assertFalse(server.stop()['running'])
        finally: server.PORT=old_port
    def test_cancel_unknown_without_body(self):
        conn=HTTPConnection('127.0.0.1',self.httpd.server_port,timeout=3); conn.request('POST','/v1/transfers/missing/cancel',headers={'Origin':'https://app.test'}); response=conn.getresponse(); response.read(); conn.close(); self.assertEqual(404,response.status)
    def test_envelope_version_required(self):
        health_status,health=self.request('/v1/health','https://app.test'); self.assertEqual(200,health_status)
        body=json.dumps({'receiverId':server.RECEIVER_ID,'challenge':health['data']['challenge'],'manifest':{}})
        conn=HTTPConnection('127.0.0.1',self.httpd.server_port,timeout=3); conn.request('POST','/v1/transfers',body=body,headers={'Origin':'https://app.test','Content-Type':'application/json'}); response=conn.getresponse(); payload=json.loads(response.read()); conn.close()
        self.assertEqual(400,response.status); self.assertEqual('UNSUPPORTED_PROTOCOL',payload['error']['code'])
    def test_busy_returns_json_503(self):
        class NoSlots(object):
            def acquire(self,value): return False
        first,second=__import__('socket').socketpair(); original=self.httpd._slots; self.httpd._slots=NoSlots()
        try:
            self.httpd.process_request(first,('127.0.0.1',1)); raw=second.recv(4096)
            self.assertIn(b'503 Service Unavailable',raw); self.assertIn(b'"code": "SERVER_BUSY"',raw)
        finally:
            self.httpd._slots=original; second.close()
