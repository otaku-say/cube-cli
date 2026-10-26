#!/bin/sh
# tests/run_all.sh —— cube-cli 一键全量测试套件
#
# 步骤：
#   1. zig build cube-cli (Debug)
#   2. tests/help_smoke.sh 帮助体系冒烟测试
#   3. tests/mcp_protocol_test.py 协议 + 纯净性测试
#   4. tests/mcp_cube_tools_test.py mock cube 工具套件（若文件不存在则打印 SKIP 并跳过）
#   5. tests/mcp_big_output_test.py 大文本截断的 UTF-8 安全性
#   6. tests/mcp_mem_stability_test.py MCP Server 内存增长稳定性回归测试
#   7. 对抗测试套件（mock 侧：全工具覆盖 + 缺陷探针 + 边界）
#   8. CLI 退出码 / 截断 / envd 错误 / --env 缺失 的回归（tests/cli_exit_trunc_test.py）
#
# 失败即非 0 退出；输出能一眼看出哪一步失败。

set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CUBE="$ROOT/zig-out/bin/cube-cli"

echo "=================================================="
echo "== [1/8] 编译 cube-cli (Debug) =="
echo "=================================================="
(cd "$ROOT" && zig build)
echo "[PASS] cube-cli 编译成功"
echo ""

echo "=================================================="
echo "== [2/8] 帮助体系冒烟测试 (tests/help_smoke.sh) =="
echo "=================================================="
CUBE="$CUBE" sh "$ROOT/tests/help_smoke.sh"
echo "[PASS] help_smoke.sh 全部通过"
echo ""

echo "=================================================="
echo "== [3/8] MCP 协议与纯净性测试 (tests/mcp_protocol_test.py) =="
echo "=================================================="
python3 "$ROOT/tests/mcp_protocol_test.py" --bin "$CUBE" --tools-min 37
echo "[PASS] mcp_protocol_test.py 全部通过"
echo ""

echo "=================================================="
echo "== [4/8] mock cube 工具测试套件 =="
echo "=================================================="
if [ -f "$ROOT/tests/mcp_cube_tools_test.py" ]; then
    python3 "$ROOT/tests/mcp_cube_tools_test.py" --bin "$CUBE"
    echo "[PASS] mcp_cube_tools_test.py 全部通过"
else
    echo "[SKIP] tests/mcp_cube_tools_test.py 尚不存在，跳过"
fi
echo ""

echo "=================================================="
echo "== [5/8] 大文本截断的 UTF-8 安全性 =="
echo "=================================================="
python3 "$ROOT/tests/mcp_big_output_test.py" --bin "$CUBE"
echo "[PASS] mcp_big_output_test.py 全部通过"
echo ""

echo "=================================================="
echo "== [6/8] MCP Server 内存稳定性回归 (tests/mcp_mem_stability_test.py) =="
echo "=================================================="
python3 "$ROOT/tests/mcp_mem_stability_test.py" --bin "$CUBE" --iters "${MEM_ITERS:-3000}"
echo "[PASS] mcp_mem_stability_test.py 全部通过"
echo ""

echo "=================================================="
echo "== [7/8] 对抗测试套件（mock 侧：全工具覆盖 + 缺陷探针 + 边界） =="
echo "=================================================="
python3 "$ROOT/tests/adv_cube_suite.py"
python3 "$ROOT/tests/adv_cube_defect_probe.py"
python3 "$ROOT/tests/mcp_cube_edge_test.py" --bin "$CUBE"
echo "[PASS] 对抗测试套件全部通过"
echo ""

echo "=================================================="
echo "== [8/8] CLI 退出码 / 截断 / envd 错误回归 =="
echo "=================================================="
python3 "$ROOT/tests/cli_exit_trunc_test.py" --bin "$CUBE"
echo "[PASS] cli_exit_trunc_test.py 全部通过"
echo ""

echo "=================================================="
echo "== 全量测试完成：全部步骤成功通过！ =="
echo "=================================================="
