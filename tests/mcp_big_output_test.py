#!/usr/bin/env python3
"""大文本截断的 UTF-8 安全性（主控补充回归测试）。

场景：工具输出超过 4 MiB 文本上限，且截断点正好落在多字节 UTF-8 字符中间。
断言：stdout 该行仍是**合法 UTF-8**（旧实现会劈开汉字 → 客户端逐行解码直接报错）。

用法: python3 tests/mcp_big_output_test.py --bin zig-out/bin/cube-cli
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.mock_cube_server import MockCubeServer

MAX_TEXT = 4 << 20  # mcp_types.max_text_bytes
FAILS = []


def ok(m):
    print(f"  ok   {m}")


def bad(m):
    FAILS.append(m)
    print(f"  FAIL {m}")


def make_payload():
    """长度 = MAX_TEXT-1 个 'A' + 一个 3 字节汉字：截断点必然落在汉字中间。"""
    return "A" * (MAX_TEXT - 1) + "中"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=str(ROOT / "zig-out/bin/cube-cli"))
    args = ap.parse_args()

    srv = MockCubeServer()
    srv.server.file_payload = make_payload()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CUBESANDBOX_")}
    env["CUBESANDBOX_API_URL"] = srv.url
    env["CUBESANDBOX_PROXY_URL"] = srv.url
    p = subprocess.Popen([args.bin, "mcp-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, env=env, bufsize=0)
    try:
        p.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}\n')
        p.stdin.flush()
        p.stdout.readline()
        p.stdin.write(b'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"sandbox_file_read",'
                      b'"arguments":{"sandbox_id":"sbx-test-111","path":"/big.txt"}}}\n')
        p.stdin.flush()
        raw = p.stdout.readline()

        # 1) 严格 UTF-8 解码（旧实现在这里会 UnicodeDecodeError）
        try:
            text = raw.decode("utf-8")
            ok("截断后的 stdout 行是合法 UTF-8")
        except UnicodeDecodeError as e:
            bad(f"stdout 行含非法 UTF-8：{e}")
            return 1

        # 2) 仍是合法 JSON-RPC，且带截断标注
        msg = json.loads(text)
        res = msg["result"]
        body = res["content"][0]["text"]
        if "已截断" in body:
            ok("截断标注存在")
        else:
            bad("未看到截断标注（可能未触发截断路径）")
        if len(body) <= MAX_TEXT + 64:
            ok(f"文本已按上限截断（{len(body)} 字节）")
        else:
            bad(f"文本未截断：{len(body)} 字节")
        if "\ufffd" not in body:
            ok("无替换字符（未产生半个字符）")
        else:
            bad("文本含 U+FFFD 替换字符，说明截断劈开了字符")
    finally:
        p.kill()
        srv.shutdown()

    print(f"-- 大文本 UTF-8 截断：失败 {len(FAILS)} 项 --")
    for f in FAILS:
        print(f"   ! {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
