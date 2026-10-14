#!/usr/bin/env python3
"""真实引擎云候选超时回归：合成响应、临时词库，不联网、不读取账号。"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
QUERY, TARGET = 'daofantiangang', '倒反天罡'


def mock_proxy():
    config = json.loads(Path(os.environ['VTYPE_REPLAY_CONFIG']).read_text())
    sys.path.insert(0, config['protocol_dir'])
    import 官方同步探针 as p

    class Probe:
        def __init__(self, identity):
            pass

        def request(self, path, raw, *args, **kwargs):
            (Path(config['state_dir']) / 'requested').write_text('1')
            time.sleep(config['delay'])
            if config.get('offline'):
                raise TimeoutError('隔离断网')
            candidate = (p.blob(1, TARGET) + p.blob(3, 'dao,fan,tian,gang') +
                         p.number(6, 4194304) + p.number(8, 0) + p.number(10, 1) + p.number(11, 28))
            body = p.number(1, 0) + p.blob(2, p.number(1, 1) + p.blob(2, candidate)) + p.blob(11, b'')
            return (p.blob(1, p.number(1, 0)) + p.number(2, 2) +
                    p.blob(3, p.one(p.fields(raw), 2)) + p.blob(4, p.number(1, 0)) + p.blob(5, body))

    p.Probe = Probe
    sys.argv = [str(SOURCE / 'cloud/实时云桥接.py')] + sys.argv[2:]
    import runpy
    runpy.run_path(sys.argv[0], run_name='__main__')


def parse(line):
    cells = line.split('\t')
    return int(cells[1][1:]), [(int(x.split(':', 1)[0]), x.split(':', 1)[1]) for x in cells[2:]]


def poll(engine):
    engine.process.stdin.write(b'R\n'); engine.process.stdin.flush()
    while True:
        line = engine.line(3)
        if line == 'UNCHANGED' or line.startswith('CAND\t'):
            return line


def run(args, logs, mode, timeout, delay):
    from test_bionic_daemon import Engine
    with tempfile.TemporaryDirectory(prefix='vtype-timeout-') as directory:
        root = Path(directory)
        (root / 'identity.json').write_text('{}')
        shutil.copyfile(args.shim, root / 'libwetype-cloud.so')
        config = {'enabled': True, 'protocol_dir': str(SOURCE / 'cloud'),
                  'state_dir': str(root), 'shim': str(root / 'libwetype-cloud.so'),
                  'delay': delay, 'offline': mode == 'offline', 'test_queries': [QUERY],
                  'cloud_timeout_ms': timeout}
        (root / 'cloud.json').write_text(json.dumps(config))
        wrapper = root / 'qemu-wrapper'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
            shlex.quote(str(Path(__file__).resolve())) +
            ' --mock-proxy --config "$VTYPE_REPLAY_CONFIG" -- ' +
            shlex.quote(str(args.engine_dir / 'qemu-aarch64-static')) + ' "$@"\n')
        wrapper.chmod(0o700)
        os.environ.update(VTYPE_REPLAY_CONFIG=str(root / 'cloud.json'), WETYPE_CLOUD_TIMEOUT_MS=str(timeout))
        for key in ('WETYPE_GROUP_SYNC', 'WETYPE_UIN', 'WETYPE_SYNC_FD', 'WETYPE_COS_FD', 'QEMU_SET_ENV'):
            os.environ.pop(key, None)
        work = root / 'dict'
        (work / 'userdict/v5').mkdir(parents=True)
        (work / 'userdict/user_hot_word').mkdir(parents=True)
        log_path = logs / f'{mode}-{timeout}-{delay}.log'
        with log_path.open('wb') as log:
            engine = Engine(args.engine_dir, work, False, str(wrapper), log, harness=args.harness)
            try:
                engine.command('OPT spans', 'OK'); engine.command('OPT tokens', 'OK')
                generation, rows = parse(engine.command('B ' + QUERY, 'CAND'))
                assert TARGET not in [x[1] for x in rows], '请使用 APK 原始资源，避免本地已含测试词'
                deadline = time.monotonic() + 3
                while not (root / 'requested').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                if mode == 'clear':
                    engine.command('C', 'OK')
                elif mode == 'replace':
                    engine.command('C', 'OK')
                    _, fresh = parse(engine.command('B nihao', 'CAND'))
                    assert fresh[0][1] == '你好'
                elif mode == 'select':
                    engine.command(f'S 0 {generation}', 'OK')
                event = 'UNCHANGED'
                deadline = time.monotonic() + delay + 1
                while time.monotonic() < deadline:
                    event = poll(engine)
                    if event.startswith('CAND\t'):
                        break
                    time.sleep(.02)
                if mode == 'accept':
                    assert event.startswith('CAND\t'), '应合并有效云候选'
                    generation, cloud = parse(event)
                    index = next(i for i, row in enumerate(cloud) if row[1] == TARGET)
                    engine.command(f'S {index} {generation}', 'OK')
                else:
                    assert event == 'UNCHANGED', (mode, event)
                engine.command('PING', 'PONG')
            finally:
                engine.close()
        text = log_path.read_text(errors='replace')
        assert f'max_timeout_ms_: {timeout}' in text
        if mode == 'baseline':
            assert f'max cost ms is {timeout}' in text
        print(f'PASS {mode}: timeout={timeout}ms, delay={delay}s', flush=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-dir', type=Path, required=True, help='含 APK 原始词库的隔离运行时')
    parser.add_argument('--harness', type=Path, required=True, help='已编译的新宿主')
    parser.add_argument('--shim', type=Path, required=True, help='已编译的 ARM64 云传输库')
    parser.add_argument('--log-dir', type=Path)
    args = parser.parse_args()
    args.engine_dir, args.harness, args.shim = [x.resolve() for x in (args.engine_dir, args.harness, args.shim)]
    with tempfile.TemporaryDirectory(prefix='vtype-cloud-logs-') as directory:
        logs = args.log_dir.resolve() if args.log_dir else Path(directory)
        logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        for mode, timeout, delay in [('baseline', 200, .35), ('accept', 1500, 0),
                ('accept', 1500, .35), ('accept', 1500, .75), ('accept', 1500, 1.1),
                ('baseline', 1500, 1.7), ('clear', 1500, .65), ('replace', 1500, .65),
                ('select', 1500, .65), ('offline', 1500, .35)]:
            run(args, logs, mode, timeout, delay)
    print('E2E_RESULT = PASS; real_network_requests=0')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--mock-proxy':
        mock_proxy()
    else:
        main()
