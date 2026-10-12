"""验证同步代理的本地应答：43/91 不联网直接回成功，组号不符的 43 和未核对的子命令被拒。"""
import json,socket,struct,sys,tempfile,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cloud'))
import 官方同步探针 as p
from 实时云桥接 import SYNC_MAGIC,sync_service

UIN,GROUP=1001,2002

class LocalAck(unittest.TestCase):
    def call(self,sub,body,group=GROUP):
        with tempfile.TemporaryDirectory() as temp:
            host,client=socket.socketpair()
            threading.Thread(target=sync_service,args=(p,host,UIN,group,Path(temp)/'log.jsonl'),daemon=True).start()
            client.sendall(struct.pack('<5I',SYNC_MAGIC,1,4814,sub,len(body))+body)
            magic,task,code,size=struct.unpack('<IIiI',client.recv(16))
            response=client.recv(size) if size else b'';client.close()
            log=[json.loads(x) for x in (Path(temp)/'log.jsonl').read_text().splitlines()]
            return code,response,log[-1]

    def test_full_state_report(self):
        body=p.blob(1,p.number(1,UIN))+p.number(2,GROUP)
        code,response,entry=self.call(43,body)
        self.assertEqual((code,response,entry.get('local_ack')),(0,p.number(1,0),True))
        code,_,entry=self.call(43,body,group=GROUP+1)
        self.assertEqual((code,entry.get('refused')),(-1,'local_ack_uin_or_group'))

    def test_emit_input_report(self):
        code,response,entry=self.call(91,b'\x0a\x00')
        self.assertEqual((code,response,entry.get('local_ack')),(0,b'',True))

    def test_unknown_subcommand(self):
        code,_,entry=self.call(99,b'')
        self.assertEqual((code,entry.get('refused')),(-1,'subcommand'))

if __name__=='__main__':unittest.main()
