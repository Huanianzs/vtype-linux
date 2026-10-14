"""只在关闭的副本补齐拼音与缺失索引；保留本地值、其他内部段及同步状态。"""
import collections
import struct
from pathlib import Path
from 离线词库工具 import DB, database
from 快照文件 import MAGIC


def split_values(value):
    rows = []
    pos = 0
    while pos < len(value):
        if len(value)-pos < 51 or value[pos] != 0:
            raise ValueError('拼音记录格式不兼容')
        size = struct.unpack_from('<H', value, pos+1)[0]
        end = pos+51+size
        if end > len(value):
            raise ValueError('拼音记录截断')
        value[pos+51:end].decode('utf-8')
        rows.append(value[pos:end])
        pos = end
    return rows


def sections(data):
    if len(data) < 80 or struct.unpack_from('<II',data) != (MAGIC,2):
        raise ValueError('快照头无效')
    end = len(data)-48
    if struct.unpack_from('<I',data,end)[0] != MAGIC or struct.unpack_from('<I',data,len(data)-20)[0] != MAGIC:
        raise ValueError('快照尾标无效')
    pos, seen = 32, set()
    while pos < end:
        if pos+8 > end:
            raise ValueError('段头截断')
        marker, kind, reserved = struct.unpack_from('<HHI',data,pos)
        if marker != 65535 or reserved or kind in seen:
            raise ValueError('快照段格式不兼容')
        seen.add(kind)
        pos += 8
        rows = []
        while pos < end:
            if pos+2 > end:
                raise ValueError('记录长度截断')
            size = struct.unpack_from('<H',data,pos)[0]
            if size == 65535:
                break
            pos += 2
            if pos+size+2 > end:
                raise ValueError('记录键截断')
            key = data[pos:pos+size]
            pos += size
            size = struct.unpack_from('<H',data,pos)[0]
            pos += 2
            if pos+size > end:
                raise ValueError('记录值截断')
            value = data[pos:pos+size]
            pos += size
            if kind == 128 and (len(split_values(value)) != 1 or not value):
                raise ValueError('源拼音记录格式不兼容')
            rows.append((key,value))
        yield kind,rows
    if pos != end:
        raise ValueError('快照长度不兼容')


def plan(before, snapshot):
    official = dict(sections(snapshot))
    if not official.get(128):
        raise ValueError('源快照缺少拼音记录')
    groups = collections.defaultdict(dict)
    for key,value in official[128]:
        old = groups[key].get(value[51:])
        if old is None or struct.unpack_from('<I',value,7)[0] > struct.unpack_from('<I',old,7)[0]:
            groups[key][value[51:]] = value
    changes = {}
    local_records = 0
    words = {word for group in groups.values() for word in group}
    for key,value in before.items():
        if key.startswith(b'!v2u!'):
            rows = split_values(value)
            local_records += len(rows)
            words.update(row[51:] for row in rows)
    added = 0
    for key,values in groups.items():
        target = b'!v2u!'+key
        previous = before.get(target,b'')
        local_words = {row[51:] for row in split_values(previous)}
        missing = [value for word,value in values.items() if word not in local_words]
        if missing:
            changes[target] = previous+b''.join(missing)
            added += len(missing)
    prefixes = 0
    for key,value in official.get(133,[]):
        target = b'!user_prefix2!'+key
        if key in words and target not in before and target not in changes:
            if len(value) != 24:
                raise ValueError('源前缀索引格式不兼容')
            changes[target] = value
            prefixes += 1
    return changes, {'source_unique_records':sum(len(x) for x in groups.values()),
                     'local_records_before':local_records,'pinyin_records_added':added,
                     'prefix_records_added':prefixes}


def supplement(work, snapshot):
    snapshot = Path(snapshot).read_bytes()
    with DB(database(work)) as db:
        before = dict(db.items())
        changes, result = plan(before,snapshot)
        if changes:
            db.put_all(changes.items())
            db.compact_range(db.db,None,0,None,0)
        after = dict(db.items())
        if any(after.get(k) != v for k,v in changes.items()):
            raise RuntimeError('写入回读不一致')
        for key,value in before.items():
            actual = after.get(key,b'')
            if key.startswith(b'!v2u!'):
                if not actual.startswith(value):
                    raise RuntimeError('原有拼音记录改变')
            elif actual != value:
                raise RuntimeError('原有内部数据或同步状态改变')
        source = {(key,value[51:]) for kind,rows in sections(snapshot) if kind == 128 for key,value in rows}
        actual = {(key[5:],row[51:]) for key,value in after.items() if key.startswith(b'!v2u!') for row in split_values(value)}
        missing = len(source-actual)
        if missing:
            raise RuntimeError('仍有源词条未写入')
        return result | {'merged_records':len(actual),'source_records_missing':missing,
                         'all_local_values_preserved':True,'all_written_values_verified':True}
