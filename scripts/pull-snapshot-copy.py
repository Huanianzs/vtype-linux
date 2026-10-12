"""隔离验证官方全量下载：只读网络，临时本设备待拉取标记仅写入已关闭副本。
不改变服务器元数据、不上传副本词库；原生引擎完成快照解密、导入与合并。
"""
import argparse,hashlib,json,os,re,selectors,shutil,socket,struct,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/'cloud'))
import 官方同步探针 as p
import 实时云桥接 as bridge
import 离线词库工具 as dbtools
RT=Path.home()/'.local/lib/wetype-ime/arm64'
ENGINE_SHA256='6002395d6509b49bc7551a4c970aee79b1400f5ee3814fe5da3d6626ffe421d3'

def mark_full_pull(work,peer,backup):
    """一次性补导旧缺口，只设置同步控制标记；不解释或修改各 kind 的词库数据。"""
    work=Path(work).resolve();assert work.is_relative_to(p.STATE)
    with dbtools.DB(dbtools.database(work)) as db:
        value=dict(db.items())[b'!dcsc!CurrentInfoV3']
        assert len(value)>=208 and int.from_bytes(value[:8],'little')==1
        count=int.from_bytes(value[144:152],'little');assert count<=256
        key_offset=192+count*64;assert key_offset+8<=len(value)
        key_len=int.from_bytes(value[key_offset:key_offset+8],'little');assert key_len in (0,16,24,32)
        offset=key_offset+8+key_len;assert offset+8<=len(value)
        size=int.from_bytes(value[offset:offset+8],'little');assert offset+8+size==len(value)
        old=p.fields(value[offset+8:]) if size else {}
        detail=b''.join(p.number(k,v) if isinstance(v,int) else p.blob(k,v)
                        for k,values in old.items() if k!=9 for v in values)
        if not old:detail=p.number(1,1)
        detail+=p.number(9,peer)
        Path(backup).write_bytes(value);Path(backup).chmod(0o600)
        data=bytearray(value[:offset])
        # 清除这次补拉的限流时间，保留云端游标、本地已上传序号和已有成员进度。
        data[48:56]=bytes(8);data[64:72]=bytes(8);data[104:120]=bytes(16)
        data+=len(detail).to_bytes(8,'little')+detail
        db.put_all([(b'!dcsc!CurrentInfoV3',bytes(data))])

def summary(work):
    from collections import Counter
    with dbtools.DB(dbtools.database(work)) as db:
        counts=Counter();info=b''
        for k,v in db.items():
            if k.startswith(b'!'):counts[k.split(b'!')[1].decode(errors='replace')]+=1
            if k==b'!dcsc!CurrentInfoV3':info=v
    return {'namespaces':dict(counts),'cloud_cursor':int.from_bytes(info[8:16],'little'),
            'local_cursor':int.from_bytes(info[16:24],'little'),'sync_state_bytes':len(info)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True,help='已关闭的词库副本；不接受正式运行目录');ap.add_argument('--runtime',type=Path,default=RT);ap.add_argument('--peer',type=int,help='要补拉的官方设备编号；省略时用配对结果');ap.add_argument('--seconds',type=int,default=110)
    ap.add_argument('--work',help='继续使用已关闭的隔离工作目录')
    ap.add_argument('--bootstrap',action='store_true',help='在已关闭副本写入一次性待补拉标记')
    ap.add_argument('--refresh-incremental',action='store_true',help='仅在副本清除增量限流时间，验证导入后的真实拉取')
    args=ap.parse_args();os.umask(0o077)
    global_runtime=args.runtime.expanduser().resolve()
    globals()['RT']=global_runtime
    live=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'wetype-ime/dict'
    source=Path(args.source).resolve()
    if source.is_relative_to(live.resolve()):raise ValueError('请先正常关闭输入法并复制词库，本工具不接受正式运行目录')
    for root,dirs,files in os.walk(source):
        if any((Path(root)/name).is_symlink() for name in dirs+files):raise ValueError('词库副本包含软链接，拒绝访问潜在运行目录')
    assert hashlib.sha256((RT/'lib/libwxhld.so').read_bytes()).hexdigest()==ENGINE_SHA256,'固定引擎版本已变化，需重新核对状态格式'
    out=p.STATE/('full-native-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir();work=Path(args.work).resolve() if args.work else out/'work'
    if not args.work:
        work.mkdir()
        if args.source:
            for name in ('userdict','user_dict'):
                src=Path(args.source)/name
                if src.exists():shutil.copytree(src,work/name,symlinks=True)
    assert work.is_relative_to(p.STATE)
    identity=json.loads((p.STATE/'identity.json').read_text());uin=identity['uin']
    groupinfo=p.fields(p.one(p.fields((p.STATE/'group-sync-response.pb').read_bytes()),1,b''))
    group=p.one(groupinfo,1);switch=p.one(groupinfo,5);hot=p.one(p.fields(p.one(groupinfo,4,b'')),1)
    if args.bootstrap:
        mac=args.peer or int(json.loads((p.STATE/'pair-result.json').read_text())['peer']['uin'])
        mark_full_pull(work,mac,out/'sync-state-before.bin')
    elif args.refresh_incremental:
        with dbtools.DB(dbtools.database(work)) as db:
            value=dict(db.items())[b'!dcsc!CurrentInfoV3'];data=bytearray(value)
            (out/'sync-state-before.bin').write_bytes(value)
            data[48:56]=bytes(8);data[64:72]=bytes(8)
            db.put_all([(b'!dcsc!CurrentInfoV3',bytes(data))])
    sync_host,sync_guest=socket.socketpair();cos_host,cos_guest=socket.socketpair()
    cloud_host,cloud_guest=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    threading.Thread(target=bridge.sync_service,args=(p,sync_host,uin,group,out/'requests.jsonl',True,True),daemon=True).start()
    threading.Thread(target=bridge.cos_service,args=(cos_host,work,out/'downloads.jsonl'),daemon=True).start()
    def cloud():
        while True:
            try:
                raw=cloud_host.recv(65536)
                if not raw:return
                magic,job,*_=struct.unpack('<5I',raw[:20]);cloud_host.send(struct.pack('<IIiI',magic,job,-2,0))
            except OSError:return
    threading.Thread(target=cloud,daemon=True).start()
    build=RT
    env=os.environ.copy();env.update(LD_LIBRARY_PATH=str(RT/'lib'),WETYPE_DICT_DIR=str(RT/'dicts'),WETYPE_ASSET_DIR=str(RT/'dicts'),
        WETYPE_WORK_DIR=str(work),QEMU_CPU='cortex-a72',QEMU_SET_ENV='LD_PRELOAD='+str(build/'libwetype-cloud.so'),
        WETYPE_CLOUD_FD=str(cloud_guest.fileno()),WETYPE_CLOUD_NATIVE='1',WETYPE_SYNC_FD=str(sync_guest.fileno()),
        WETYPE_COS_FD=str(cos_guest.fileno()),WETYPE_UIN=str(uin),WETYPE_GROUP_SYNC=f'{group},{switch},{hot}')
    cmd=[str(RT/'qemu-aarch64-static'),'-L',str(RT/'sysroot'),str(build/'wetype-harness'),str(RT/'lib/libwxhld_jni.so'),'--daemon']
    with (out/'engine.log').open('wb') as err:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,env=env,cwd=out,
                              pass_fds=(sync_guest.fileno(),cos_guest.fileno(),cloud_guest.fileno()),bufsize=0)
        sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ);buf=b'';ready=False
        deadline=time.monotonic()+args.seconds;completed_at=None
        while time.monotonic()<deadline and proc.poll() is None:
            for _ in sel.select(.25):
                data=os.read(proc.stdout.fileno(),65536)
                if not data:break
                buf+=data
                while b'\n' in buf:
                    line,buf=buf.split(b'\n',1)
                    if line==b'READY':ready=True
            if ready and (out/'downloads.jsonl').exists():
                log=(out/'engine.log').read_bytes()
                kinds={int(x) for x in re.findall(rb'Full merge dict count \d+, type (\d+)',log)}
                if {128,131,133,138,157}<=kinds and b'After CosJobCompleted, DataSyncCompleteEvent, state: 0, job size: 0' in log:
                    if completed_at is None:completed_at=time.monotonic()
                    if time.monotonic()-completed_at>=5:break
        if proc.poll() is None:
            proc.stdin.write(b'PING\nQ\n');proc.stdin.flush()
        try:proc.wait(timeout=45)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    (out/'stdout.log').write_bytes(buf+proc.stdout.read())
    result={'dir':str(out),'work':str(work),'ready':ready,'returncode':proc.returncode,'after':summary(work),
            'requests':[json.loads(x) for x in (out/'requests.jsonl').read_text().splitlines()] if (out/'requests.jsonl').exists() else []}
    result['downloads']=[json.loads(x) for x in (out/'downloads.jsonl').read_text().splitlines()] if (out/'downloads.jsonl').exists() else []
    result['native_full_merge_counts']={str(int(kind)):int(count) for count,kind in re.findall(rb'Full merge dict count (\d+), type (\d+)',(out/'engine.log').read_bytes())}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='requests'}|{'request_count':len(result['requests']),
          'refused':[r.get('refused') for r in result['requests'] if r.get('refused')]},ensure_ascii=False))

if __name__=='__main__':main()
