"""验证缺失记录补齐、本地冲突保留、重复执行及格式错误的写入前拒绝。"""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cloud'))
import 快照补齐 as m


def value(word,freq=1):
    word=word.encode();header=bytearray(51)
    struct.pack_into('<H',header,1,len(word));struct.pack_into('<I',header,3,freq)
    return bytes(header)+word


def snapshot(rows,prefix=()):
    data=struct.pack('<II',m.MAGIC,2)+bytes(24)
    for kind,items in [(128,rows),(133,prefix)]:
        data+=struct.pack('<HHI',65535,kind,0)
        for key,val in items:
            data+=struct.pack('<H',len(key))+key+struct.pack('<H',len(val))+val
    footer=bytearray(48);struct.pack_into('<I',footer,0,m.MAGIC);struct.pack_into('<I',footer,28,m.MAGIC)
    return data+footer


class Supplement(unittest.TestCase):
    def test_local_value_and_record_order_preserved(self):
        local=value('你好',999)+value('本地专用',9)
        before={b'!v2u!ni,hao':local,b'!dcsc!CurrentInfoV3':b'sync-state',b'!dcact!pending':b'learning',b'!u_d_v_p!patch':b'patch'}
        source=snapshot([(b'ni,hao',value('你好')),(b'ni,hao',value('拟好'))])
        changes,result=m.plan(before,source)
        self.assertEqual(changes,{b'!v2u!ni,hao':local+value('拟好')})
        self.assertEqual(result['pinyin_records_added'],1)
        self.assertEqual(m.plan(before|changes,source)[0],{})

    def test_empty_dictionary_receives_all_source_records(self):
        source=snapshot([(b'ni,hao',value('你好')),(b'zhong,guo',value('中国'))])
        changes,result=m.plan({},source)
        self.assertEqual(result['source_unique_records'],2)
        self.assertEqual(result['pinyin_records_added'],2)
        self.assertEqual(len(changes),2)

    def test_existing_prefix_kept_and_unrelated_prefix_not_added(self):
        source=snapshot([(b'ni,hao',value('你好'))],[(b'other',b'X'*24),('你好'.encode(),b'S'*24)])
        existing=b'!user_prefix2!'+ '你好'.encode()
        changes,result=m.plan({existing:b'L'*24},source)
        self.assertNotIn(existing,changes)
        self.assertNotIn(b'!user_prefix2!other',changes)
        self.assertEqual(result['prefix_records_added'],0)

    def test_bad_snapshot_and_local_value_refused(self):
        valid=snapshot([(b'ni,hao',value('你好'))])
        for data in [valid[:-1],bytes(80),snapshot([(b'ni,hao',b'bad')])]:
            with self.assertRaises(ValueError):m.plan({},data)
        with self.assertRaises(ValueError):m.plan({b'!v2u!ni,hao':b'bad'},valid)
        with self.assertRaises(ValueError):m.plan({},snapshot([(b'ni,hao',value('你好'))],[('你好'.encode(),b'bad')]))

    def test_duplicate_source_pair_imported_once(self):
        changes,result=m.plan({},snapshot([(b'ni,hao',value('你好')),(b'ni,hao',value('你好'))]))
        self.assertEqual(result['source_unique_records'],1)
        self.assertEqual(len(m.split_values(changes[b'!v2u!ni,hao'])),1)

    def test_formal_path_and_symlink_source_refused(self):
        spec=importlib.util.spec_from_file_location('supplement_cli',Path(__file__).resolve().parents[1]/'scripts/supplement-snapshot-copy.py')
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'XDG_DATA_HOME':tmp}):
            root=Path(tmp);live=root/'wetype-ime/dict';live.mkdir(parents=True)
            with self.assertRaises(ValueError):cli.validate_source(live)
            source=root/'copy';source.mkdir();(source/'redirect').symlink_to(live)
            with self.assertRaises(ValueError):cli.validate_source(source)


if __name__=='__main__':unittest.main()
