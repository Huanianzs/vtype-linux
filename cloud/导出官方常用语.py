"""将官方常用语只读载荷导出为 Linux 桥接私有缓存；原子更新，不上传。"""
import argparse,fcntl,json,os,struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT));import 官方同步探针 as p

def entries(data):
    out=[];unsupported=0
    for raw in p.fields(data).get(2,[]):
        row=p.fields(raw)
        if p.one(row,9):continue
        key=p.one(row,2,b'').decode('utf-8');words=p.one(row,3,b'').decode('utf-8')
        if not words:continue
        assert len(key.encode())<=128 and len(words.encode())<=65536
        # 当前 Linux 插件只支持 ASCII 字母/数字快捷键；忽略不支持的项，
        # 避免一条中文或符号快捷键让整批常用语都无法导出。
        if key and not (key.isascii() and key.isalnum()):
            unsupported+=1
            continue
        out.append((key.lower(),words))
    return out,unsupported

def export(path,refresh):
    os.umask(0o077)
    if refresh:
        with (p.STATE/'identity.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            identity=json.loads((p.STATE/'identity.json').read_text());client=p.Probe(identity)
            raw=client.api(34,p.number(1,identity['uin'])+p.number(2,1)+p.number(3,4)+p.number(5,0))
            group=p.fields(p.one(p.fields(raw),1,b''));hot=p.fields(p.one(group,4,b''));data=p.one(hot,2,b'')
            assert data,'官方未返回常用语载荷'
            p.save_private('common-words-payload.bin',data)
            p.save_private('common-words-version.json',json.dumps({'version':p.one(hot,1)}).encode())
    else:data=(p.STATE/'common-words-payload.bin').read_bytes()
    rows,unsupported=entries(data);raw=bytearray(b'WXP1'+struct.pack('<I',len(rows)))
    for key,words in rows:
        k=key.encode();v=words.encode();raw.extend(struct.pack('<II',len(k),len(v))+k+v)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.common-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {'active_text_phrases':len(rows),'unsupported_shortcuts':unsupported,'letter_shortcuts':sum(k.isalpha() for k,v in rows),'numeric_shortcuts':sum(k.isdigit() for k,v in rows),'bytes':len(raw),'official_data_changed':False}
if __name__=='__main__':
    q=argparse.ArgumentParser();q.add_argument('output',type=Path);q.add_argument('--refresh',action='store_true');args=q.parse_args()
    print(json.dumps(export(args.output.resolve(),args.refresh),ensure_ascii=False,indent=2))
