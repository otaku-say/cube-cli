#!/usr/bin/env python3
"""tests/exit_code_test.py —— exec 退出码是否按上游 exitCode 透传（纯标准库，三平台可跑）

为什么需要它：远端命令失败而 CLI 退出 0（或反之），会让 `cube-cli exec $SID 'make' && ./deploy.sh`
继续部署。这条规则之前没有任何断言守着，改坏了不会有人发现。

上游契约（CubeSandbox SDK 的 CommandResult.exit_code 是 int）所以本进程退出码必须一致：
    exit_code >  0 → 原样（1-255）
    exit_code == 0 → 0
    exit_code <  0 → 1（上游没给合法 shell 码）
    超时（envd 报 deadline_exceeded）→ 124（同 timeout(1)）

退出码由 mock 的 `exec_exit_code` 全局开关控制，用例逐档改写它。

用法：
    python3 tests/exit_code_test.py --bin zig-out/bin/cube-cli
    python3 tests/exit_code_test.py --bin zig-out/bin/cube-cli.exe
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mock_cube_server as M  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    args = ap.parse_args()
    binary = os.path.abspath(args.bin)
    if not os.path.isfile(binary):
        print(f"[SKIP] 找不到二进制: {binary}")
        return 0

    srv = M.MockCubeServer("127.0.0.1", 0)
    env = dict(os.environ)
    env["CUBESANDBOX_API_URL"] = srv.url
    env["CUBESANDBOX_API_KEY"] = "test"
    env["CUBESANDBOX_PROXY_URL"] = srv.url

    cases = [
        ("成功 exit_code=0", 0, 0),
        ("失败 exit_code=7", 7, 7),
        ("失败 exit_code=250", 250, 250),
        ("exit_code=-1（被信号杀死）", -1, 1),
    ]
    fails = 0
    try:
        for name, code, want in cases:
            M.exec_exit_code = code
            p = subprocess.run([binary, "exec", "sbx-1", "true"],
                               capture_output=True, text=True, timeout=60, env=env)
            if p.returncode == want:
                print(f"  ok   {name} → 退出码 {p.returncode}")
            else:
                fails += 1
                print(f"  FAIL {name} → 退出码 {p.returncode}，期望 {want}；stderr={p.stderr[:160]!r}")
            if code != 0 and "（exit" in p.stdout:
                fails += 1
                print(f"  FAIL {name}: 「（exit N）」进了 stdout：{p.stdout[:120]!r}")
    finally:
        srv.shutdown()

    print(f"-- 退出码语义：{len(cases) - fails} 通过 / {fails} 失败 --")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
