#!/usr/bin/env python3
"""复制已关闭的隔离词库并补齐快照拼音记录，不接受或替换正式运行目录。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cloud'))
import 官方同步探针 as p
from 快照补齐 import supplement


def validate_source(source):
    live = Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'wetype-ime/dict'
    source = Path(source).resolve()
    if source.is_relative_to(live.resolve()) or not source.is_dir():
        raise ValueError('请使用已正常关闭的隔离词库副本')
    for root,dirs,files in os.walk(source):
        if any((Path(root)/name).is_symlink() for name in dirs+files):
            raise ValueError('词库副本不能包含符号链接')
    return source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',required=True,type=Path,help='已正常关闭、先完成原生内部段导入的词库副本')
    ap.add_argument('--snapshot',required=True,type=Path,help='下载工具生成的snapshot.decrypted')
    ap.add_argument('--state',default=p.STATE,type=Path)
    args = ap.parse_args()
    os.umask(0o077)
    source = validate_source(args.source)
    state = args.state.expanduser().resolve()
    if not state.is_dir():
        raise ValueError('身份目录不存在')
    out = Path(tempfile.mkdtemp(prefix='snapshot-supplement-',dir=state))
    try:
        work = out/'work'
        work.mkdir()
        for name in ('userdict','user_dict'):
            if (source/name).exists():
                shutil.copytree(source/name,work/name)
        result = supplement(work,args.snapshot.expanduser().resolve())
        (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result | {'saved_directory':out.name,'source_dictionary_modified':False},ensure_ascii=False,indent=2))
    except Exception:
        # 仅删除本次新建的失败副本；来源和正式词库均不写入。
        shutil.rmtree(out)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error':type(error).__name__,'message':'补齐未完成；来源词库保持原状，请核对副本、快照格式及LevelDB依赖。'},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
