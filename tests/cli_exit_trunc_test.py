#!/usr/bin/env python3
"""tests/cli_exit_trunc_test.py —— CLI 退出码 / 截断 / envd 错误 / --env 缺失 四类行为的回归测试。

背景（2026-10 审计发现，全部为「静默出错」缺陷）：
  M1 exec/code 把远端退出码打成 stdout 且本机退出 0  → `exec $SID 'zig build' && ./deploy.sh` 照样部署
  M2 响应体超缓冲静默截断（无标记、退出 0、可切坏 UTF-8）→ get 写出残缺文件并打印 saved
  M3 envd 非 2xx 吞掉状态码与 body → 只剩 error: HttpError
  M4 --env=NAME 本机无此变量时静默不注入

本脚本自带 mock（控制面 + envd 数据面，无外部依赖、不联网），断言：
  · 远端 exit 3  → CLI 退出 3，提示走 stderr，stdout 干净（可安全进管道）
  · 远端超长输出  → stderr 有「已截断」+ 非 0 退出
  · get 超长文件  → stderr 有「已截断」+ 非 0 退出
  · envd 500      → stderr 有 `HTTP 500: ...`（状态码与 body 可见）
  · --env=缺失变量 → stderr 有提示

用法： python3 tests/cli_exit_trunc_test.py --bin zig-out/bin/cube-cli
"""
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BIG = 9 << 20  # > CLI 读缓冲（exec 2 MiB / 文件 8 MiB）


def connect_stream(events):
    buf = bytearray()
    for ev in events:
        payload = json.dumps(ev, separators=(",", ":")).encode()
        buf.append(0)
        buf.extend(len(payload).to_bytes(4, "big"))
        buf.extend(payload)
    buf.append(2)
    buf.extend((2).to_bytes(4, "big"))
    buf.extend(b"{}")
    return bytes(buf)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return self.rfile.read(n).decode("utf-8", "replace") if n else ""

    def _send(self, status, content, ctype="application/json"):
        if isinstance(content, str):
            content = content.encode()
        try:
            self.send_response(status)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端读满缓冲就断开（截断用例）属预期

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        body = self._body()
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path

        if p.endswith("/connect"):
            self._send(200, '{"envdAccessToken":"tok","sandboxID":"SID"}')
            return
        if p.endswith("/files"):
            path = (q.get("path") or [""])[0]
            if "errfile" in path:
                self._send(403, "permission denied: /root/errfile", "text/plain")
            elif "bigfile" in path:
                self._send(200, b"x" * BIG, "application/octet-stream")
            else:
                self._send(200, "small file content\n", "application/octet-stream")
            return
        if p.endswith("process.Process/Start"):
            if '"boomfail"' in body:
                self._send(500, "boom: token expired", "text/plain")
                return
            if '"exit3"' in body:
                out = base64.b64encode(b"hello\n").decode()
                self._send(200, connect_stream([{"pid": 7}, {"stdout": out}, {"exitCode": 3}]),
                           "application/connect+json")
            elif '"bigout"' in body:
                out = base64.b64encode(b"A" * (3 << 20)).decode()
                self._send(200, connect_stream([{"pid": 7}, {"stdout": out}, {"exitCode": 0}]),
                           "application/connect+json")
            else:
                out = base64.b64encode(b"ok\n").decode()
                self._send(200, connect_stream([{"pid": 7}, {"stdout": out}, {"exitCode": 0}]), "application/connect+json")
            return
        if p.endswith("process.Process/SendSignal") or p.endswith("process.Process/List"):
            self._send(200, "{}")
            return
        self._send(404, '{"error":"not found"}')


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default="zig-out/bin/cube-cli")
    args = ap.parse_args()

    port = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env.update({
        "CUBESANDBOX_API_URL": base,
        "CUBESANDBOX_PROXY_URL": base,
        "CUBESANDBOX_API_KEY": "k",
    })

    def run(*a):
        r = subprocess.run([args.bin, *a], capture_output=True, text=True, env=env)
        return r.returncode, r.stdout, r.stderr

    fails = []

    def check(name, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" :: {detail}"))
        if not cond:
            fails.append(name)

    print("== M1 exec 退出码透传 ==")
    rc, out, err = run("exec", "SID", "exit3")
    check("远端 exit 3 → 本机退出 3", rc == 3, f"rc={rc}")
    check("stdout 不含（exit 3）（管道不被污染）", "exit 3" not in out, repr(out))
    check("stderr 含（exit 3）提示", "exit 3" in err, repr(err))

    print("== M2 超缓冲截断必须被标记 ==")
    rc, out, err = run("exec", "SID", "bigout")
    check("exec 超长输出 → 非 0 退出", rc != 0, f"rc={rc}")
    check("exec 超长输出 → stderr 提示已截断", "截断" in err, repr(err[:200]))

    rc, out, err = run("get", "SID", "/bigfile", "/tmp/cube_trunc_test.bin")
    check("get 超长文件 → 非 0 退出", rc != 0, f"rc={rc}")
    check("get 超长文件 → stderr 提示已截断", "截断" in err, repr(err[:200]))
    check("get 超长文件 → 不打印 saved", "saved" not in out, repr(out))

    rc, out, err = run("cat", "SID", "/bigfile")
    check("cat 超长文件 → 非 0 退出", rc != 0, f"rc={rc}")
    check("cat 超长文件 → stderr 提示已截断", "截断" in err, repr(err[:200]))

    print("== M3 envd 非 2xx 必须暴露状态码与 body ==")
    rc, out, err = run("exec", "SID", "boomfail")
    check("envd 500 → 非 0 退出", rc != 0, f"rc={rc}")
    check("stderr 含 HTTP 500 与 body", "HTTP 500" in err and "token expired" in err, repr(err[:200]))

    print("== M4 --env=NAME 本机无此变量必须提示 ==")
    rc, out, err = run("exec", "SID", "ok", "--env=CUBE_NO_SUCH_VAR_XYZ")
    check("提示已跳过", "CUBE_NO_SUCH_VAR_XYZ" in err and "跳过" in err, repr(err[:200]))
    check("不因缺变量改写退出码", rc == 0, f"rc={rc}")

    srv.shutdown()
    print(f"\n{'全部通过' if not fails else '失败 %d 项：%s' % (len(fails), fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
