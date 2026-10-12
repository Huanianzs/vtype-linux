"""验证快照宿主传输：成功落盘、截断失败、越界路径、非官方地址和符号链接。全程不联网。"""
import io,json,os,socket,stat,struct,tempfile,threading,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cloud'))
from 实时云桥接 import COS_MAGIC,cos_service

class Response(io.BytesIO):
    def __init__(self,data,length):super().__init__(data);self.headers={'Content-Length':str(length)}
class HTTP:
    def __init__(self):self.calls=0;self.truncated=False
    def open(self,*args,**kwargs):
        self.calls+=1;return Response(b'snapshot',20 if self.truncated else 8)

def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);work=root/'work';work.mkdir();target=work/'snapshot.bin'
        host,client=socket.socketpair();http=HTTP();results=[]
        with patch('urllib.request.build_opener',return_value=http),patch('subprocess.run'):
            thread=threading.Thread(target=cos_service,args=(host,work,root/'log.jsonl'),daemon=True);thread.start()
            def request(path,url='https://bucket.cos.ap-shanghai.myqcloud.com/key?signature=test'):
                fields=[b'bucket',str(path).encode(),b'key',url.encode()]
                client.sendall(struct.pack('<6I',COS_MAGIC,len(results)+1,*map(len,fields))+b''.join(fields))
                raw=b''
                while len(raw)<12:raw+=client.recv(12-len(raw))
                magic,job,code=struct.unpack('<IIi',raw);assert magic==COS_MAGIC;results.append(code);return code
            assert request(target)==0 and target.read_bytes()==b'snapshot'
            assert stat.S_IMODE(target.stat().st_mode)==0o600
            http.truncated=True
            assert request(target)==-1 and target.read_bytes()==b'snapshot'
            assert not list(work.glob('.cos-download-*'))
            calls=http.calls
            assert request(root/'outside.bin')==-1 and not (root/'outside.bin').exists()
            assert request(target,'https://example.com/key?signature=test')==-1
            outside=root/'outside-target';outside.write_bytes(b'keep');link=work/'link';link.symlink_to(outside)
            assert request(link)==-1 and outside.read_bytes()==b'keep'
            assert http.calls==calls
            client.shutdown(socket.SHUT_RDWR);client.close();thread.join(timeout=2);assert not thread.is_alive()
        print(json.dumps({'checks':5,'passed':True,'real_network_requests':0,'file_mode':'600','partial_file_removed':True}))

if __name__=='__main__':main()
