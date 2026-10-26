#!/usr/bin/env python3
"""scripts/gen-docs.py —— 从**已编译的二进制**生成 docs/cube-cli.md。

为什么从二进制生成：docs 要与实际能跑的命令面逐字一致。手写文档必然漂移，
而 `<cmd> --help` 的内容就是 src/help.zig 里的命令表，编译后即事实。

用法（在仓库根目录执行，二进制要先 zig build 好）：
    zig build -Doptimize=ReleaseFast
    python3 scripts/gen-docs.py
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BINARY = REPO / "zig-out" / "bin" / "cube-cli"
OUT = REPO / "docs" / "cube-cli.md"

ALL_RE = re.compile(r"^【(.+?)】\s*$")
ROW_RE = re.compile(r"^  (\S+)\s+(.*)$")


def run(binary, *args):
    p = subprocess.run([binary, *args], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"{binary} {' '.join(args)} 退出码 {p.returncode}\n{p.stderr}")
    return p.stdout


def parse_table(binary):
    """`help all` → [(分组, 命令名, 别名, 一句话)]"""
    out = []
    group = None
    for line in run(binary, "help", "all").splitlines():
        m = ALL_RE.match(line)
        if m:
            group = m.group(1)
            continue
        m = ROW_RE.match(line)
        if m and group:
            names = m.group(1).split("|")
            out.append((group, names[0], names[1] if len(names) > 1 else "", m.group(2).strip()))
    return out


def slug(name):
    """锚点保留连字符（### tpl-ls → #tpl-ls）；别名只取 | 前首名。"""
    return name.split("|")[0]


def build_doc(binary, title, intro_md, table, extra_head_md):
    lines = [
        f"# {title}",
        "",
        "> **本文档由 `scripts/gen-docs.py` 从编译产物自动生成，请勿手工编辑。**",
        "> 权威命令面是 `<cli> help`（表在 `src/help.zig`）；文档随代码走，改命令先改 help。",
        "> 重新生成：",
        ">",
        "> ```bash",
        "> zig build -Doptimize=ReleaseFast",
        "> python3 scripts/gen-docs.py",
        "> ```",
        "",
        intro_md,
        "",
    ]
    lines += extra_head_md
    lines += ["", "## 命令索引", ""]
    cur = None
    for group, name, alias, brief in table:
        if group != cur:
            cur = group
            lines.append(f"- **{group}**")
        a = f"（同义词 `{alias}`）" if alias else ""
        lines.append(f"  - [`{name}`](#{slug(name)}) —— {brief}{a}")
    lines.append("")

    cur = None
    for group, name, alias, brief in table:
        if group != cur:
            cur = group
            lines.append(f"## {group}")
            lines.append("")
        lines.append(f"### {name}")
        lines.append("")
        detail = run(binary, "help", name)
        lines.append("```text")
        lines.append(detail.rstrip("\n"))
        lines.append("```")
        lines.append("")
        if "示例:" not in detail and "示例：" not in detail:
            sys.exit(f"{binary} help {name} 缺少可复制运行的示例")
    return "\n".join(lines) + "\n"


CUBE_INTRO = """`cube-cli` 是 **CubeSandbox 控制面** CLI：建/查/销毁沙箱、选模板、打快照与回滚、
持久卷、以及沙箱内文件操作（envd 通道）。

- 数据面遥控（执行 / PTY / 浏览器 / 桌面）是另一个工具
  [`aiod-cli`](https://github.com/otaku-say/aiod-cli)。
- 源码：[`src/`](https://github.com/otaku-say/cube-cli/tree/main/src)，命令表
  [`src/help.zig`](https://github.com/otaku-say/cube-cli/blob/main/src/help.zig)。"""

CUBE_HEAD = [
    "## 环境变量",
    "",
    "仓库内**不含任何主机名 / IP / 凭据**，全部从环境变量读取。只有 `CUBESANDBOX_*` 这四个"
    "（旧命名 `CUBE_API_URL` / `CUBE_API_KEY` / `CBS_PROXY_BASE` 已彻底移除，不再兼容）。",
    "",
    "| 变量 | 必填 | 用途 |",
    "|---|---|---|",
    "| `CUBESANDBOX_API_URL` | 是 | 控制面地址。缺失时任何控制面命令报「错误：缺少环境变量 CUBESANDBOX_API_URL」。 |",
    "| `CUBESANDBOX_API_KEY` | 否 | 控制面 API Key（`X-API-KEY` 头）。本部署未启用鉴权时可省略。 |",
    "| `CUBESANDBOX_PROXY_URL` | exec/文件/ports 必填 | 数据面网关。缺失时报「错误：缺少环境变量 CUBESANDBOX_PROXY_URL」。 |",
    "| `CUBESANDBOX_AGENT_NAME` | 否 | `new` 写入 `metadata.agent` 的默认名字，不设则记 `cube-cli`。 |",
    "",
    "## 构建与产物名",
    "",
    "需要 Zig **0.17.0**。两种架构都要能编过：",
    "",
    "```bash",
    "# 本机架构",
    "zig build -Doptimize=ReleaseFast",
    "# 交叉编译到 arm64（iSH / 手机 / arm64 机器）",
    "zig build -Doptimize=ReleaseFast -Dtarget=aarch64-linux-musl",
    "```",
    "",
    "产物名统一为 `<tool>-<os>-<arch>`；zig 的 `-Dtarget=` 三元组原样保留（它是 zig 的对外契约），"
    "对照如下：",
    "",
    "| 目标三元组（zig `-Dtarget=`） | 架构 | 产物文件名 |",
    "|---|---|---|",
    "| `aarch64-linux-musl` | arm64 / linux | `cube-cli-linux-arm64` |",
    "| `x86_64-linux-musl` | amd64 / linux | `cube-cli-linux-amd64` |",
    "",
    "产物在 `zig-out/bin/cube-cli`，ReleaseFast + strip 后约 1.2 MB 静态单文件。",
    "",
    "## 拿到沙箱后交给 aiod-cli",
    "",
    "`cube-cli new` 输出的 `[sandbox] AIO 网关:` 那行**就是** `aiod-cli` 的 `SANDBOX_BASE`"
    "（[`aiod-cli`](https://github.com/otaku-say/aiod-cli) 负责沙箱内数据面遥控）：",
    "",
    "```bash",
    "SID=$(cube-cli new --note=demo)",
    "# 输出里：[sandbox] AIO 网关: https://<网关>/sandbox/<sandboxID>/8080/   ← aiod-cli 的 SANDBOX_BASE",
    "```",
    "",
    "## 帮助怎么用",
    "",
    "```bash",
    "cube-cli help              # 分组速查（常用命令）",
    "cube-cli help all          # 完整命令表，一条一行",
    "cube-cli help new          # 单命令详解（本文档对应小节）",
    "cube-cli new --help        # 同上，**只打印不建沙箱**",
    "cube-cli new -h            # 同上",
    "```",
    "",
    "未知命令会打印「未知命令：xxx」并以退出码 1 结束。所有取值型 flag 一律写"
    "**`--key=value`** 等号形式；布尔开关直接写 `--flag`（不要写 `--flag=true`）。",
]


def main():
    if not BINARY.is_file():
        sys.exit(f"找不到二进制 {BINARY}，先跑 zig build -Doptimize=ReleaseFast")
    doc = build_doc(str(BINARY), "cube-cli 命令手册", CUBE_INTRO,
                    parse_table(str(BINARY)), CUBE_HEAD)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}  {len(doc.splitlines())} 行")


if __name__ == "__main__":
    main()
