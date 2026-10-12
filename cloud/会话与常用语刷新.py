"""原生词库同步启用后的轻量定时任务：刷新会话密钥、设备组信息和官方常用语缓存。

个人词库由官方引擎自身同步（经 cloud_proxy 的同步通道），本任务不读写词库、不交接引擎。
使用已有身份，不注册新设备；组信息请求不含剪贴板位。
"""
import fcntl,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import 官方同步探针 as p
from 运行支持 import refresh_client,write_doc,PROD

STATUS=p.STATE/'native-sync-live'


def main():
    os.umask(0o077);started=time.monotonic();STATUS.mkdir(mode=0o700,exist_ok=True)
    try:
        refresh_client()
        with (p.STATE/'identity.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            identity=json.loads((p.STATE/'identity.json').read_text());client=p.Probe(identity)
            # 设备/常用语/词典信息，与研究探针相同的过滤位 1|4|8，不含剪贴板。
            raw=client.api(34,p.number(1,identity['uin'])+p.number(2,1)+p.number(3,13)+p.number(5,0))
        group=p.fields(p.one(p.fields(raw),1,b''))
        assert p.one(group,1),'组信息缺失'
        old=p.fields(p.one(p.fields((p.STATE/'group-sync-response.pb').read_bytes()),1,b''))
        p.save_private('group-sync-response.pb',raw)
        hot=p.fields(p.one(group,4,b''));payload=p.one(hot,2,b'')
        phrases=None
        if payload:
            p.save_private('common-words-payload.bin',payload)
            from 导出官方常用语 import export
            phrases=export(PROD.parent/'common-phrases.bin',False)['active_text_phrases']
        # 组号/功能开关变化时，运行中的引擎要到下次启动才拿到新值；这里只登记。
        changed=[k for k in (1,5) if p.one(old,k)!=p.one(group,k)]
        result={'ok':True,'common_phrases':phrases,'group_info_changed':bool(changed),
                'elapsed_seconds':round(time.monotonic()-started,2)}
    except Exception as error:
        result={'ok':False,'error_type':type(error).__name__}
    write_doc(STATUS/'refresh-status.json',result)
    print(json.dumps(result,ensure_ascii=False));return 0 if result['ok'] else 1


if __name__=='__main__':sys.exit(main())
