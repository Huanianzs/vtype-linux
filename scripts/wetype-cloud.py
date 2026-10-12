#!/usr/bin/env python3
"""源码目录和已安装运行时共用的云扩展命令入口。"""
import sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here / 'cloud' if (here / 'cloud').is_dir() else here.parent / 'cloud'))
from 配置与配对 import main
if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('操作未完成：' + str(error), file=sys.stderr)
        sys.exit(1)
