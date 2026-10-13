"""离线词库工具：只对引擎已关闭的目录使用系统 LevelDB C API。"""
import ctypes as C
import ctypes.util
import os
from pathlib import Path

class DB:
    def __init__(self,path,create=False):
        library=os.environ.get('WETYPE_LEVELDB_LIBRARY') or ctypes.util.find_library('leveldb')
        if not library:raise RuntimeError('找不到 LevelDB；请安装系统库或设置 WETYPE_LEVELDB_LIBRARY')
        self.lib=C.CDLL(library)
        P=C.c_void_p; Z=C.c_size_t; S=C.c_char_p
        signatures={
          'options_create':([],P),'options_destroy':([P],None),
          'options_set_paranoid_checks':([P,C.c_ubyte],None),'options_set_compression':([P,C.c_int],None),
          'options_set_create_if_missing':([P,C.c_ubyte],None),
          'open':([P,S,C.POINTER(P)],P),'close':([P],None),'free':([P],None),
          'readoptions_create':([],P),'readoptions_destroy':([P],None),
          'readoptions_set_verify_checksums':([P,C.c_ubyte],None),
          'writeoptions_create':([],P),'writeoptions_destroy':([P],None),
          'writeoptions_set_sync':([P,C.c_ubyte],None),
          'create_iterator':([P,P],P),'iter_destroy':([P],None),'iter_valid':([P],C.c_ubyte),
          'iter_seek_to_first':([P],None),'iter_next':([P],None),
          'iter_key':([P,C.POINTER(Z)],P),'iter_value':([P,C.POINTER(Z)],P),
          'iter_get_error':([P,C.POINTER(P)],None),
          'compact_range':([P,S,Z,S,Z],None),
          'writebatch_create':([],P),'writebatch_destroy':([P],None),
          'writebatch_put':([P,S,Z,S,Z],None),'writebatch_delete':([P,S,Z],None),'write':([P,P,P,C.POINTER(P)],None),
        }
        for n,(a,r) in signatures.items():
            f=getattr(self.lib,'leveldb_'+n);f.argtypes=a;f.restype=r;setattr(self,'close_native' if n=='close' else n,f)
        self.opt=self.options_create();self.options_set_paranoid_checks(self.opt,1);self.options_set_compression(self.opt,0)
        self.options_set_create_if_missing(self.opt,int(create))
        err=P();self.db=self.open(self.opt,str(path).encode(),C.byref(err));self.check(err)
        assert self.db
        self.ro=self.readoptions_create();self.readoptions_set_verify_checksums(self.ro,1)
        self.wo=self.writeoptions_create();self.writeoptions_set_sync(self.wo,1)
    def check(self,err):
        if err.value:
            msg=C.string_at(err.value).decode();self.free(err.value);raise RuntimeError(msg)
    def items(self):
        it=self.create_iterator(self.db,self.ro)
        try:
            self.iter_seek_to_first(it)
            while self.iter_valid(it):
                n=C.c_size_t();p=self.iter_key(it,C.byref(n));k=C.string_at(p,n.value)
                p=self.iter_value(it,C.byref(n));v=C.string_at(p,n.value)
                yield k,v
                self.iter_next(it)
            err=C.c_void_p();self.iter_get_error(it,C.byref(err));self.check(err)
        finally:self.iter_destroy(it)
    def put_all(self,items):
        self.apply(items,())
    def apply(self,items,deletes):
        batch=self.writebatch_create()
        try:
            for k,v in items:self.writebatch_put(batch,k,len(k),v,len(v))
            for k in deletes:self.writebatch_delete(batch,k,len(k))
            err=C.c_void_p();self.write(self.db,self.wo,batch,C.byref(err));self.check(err)
        finally:self.writebatch_destroy(batch)
    def close(self):
        self.close_native(self.db)
        self.readoptions_destroy(self.ro);self.writeoptions_destroy(self.wo);self.options_destroy(self.opt)
    # 避免 Python close 与 C close 同名。
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def database(work):
    root=(Path(work)/'userdict/v5').resolve()
    path=(root/'db_path.conf').read_text().strip()
    target=(root/path).resolve()
    if not target.is_relative_to(root) or target==root:
        raise ValueError('副本数据库路径越界，拒绝打开')
    if target.is_dir():return target
    choices=[x for x in root.iterdir() if x.is_dir()]
    assert len(choices)==1
    return choices[0]
