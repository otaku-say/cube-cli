# cube-cli

**CubeSandbox 控制面**命令行工具，Zig 实现，静态单文件分发：

```bash
cube-cli new --need=code      # 建沙箱（默认 aio-code 镜像）
cube-cli exec <sandboxID> 'zig version' --timeout=300
cube-cli snap <sandboxID> --name=before-refactor
```

覆盖沙箱生命周期、模板画像与选择、快照/分叉、持久卷、沙箱内文件操作（envd 通道），
并以 `mcp-server` 子命令对 Agent 提供 MCP 接口。

## 版本号（始终跟随上游）

版本号**跟随上游 CubeSandbox**，不因本仓库新增特性而单独递增：

| 跟随的上游 | 当前版本 | 对照记录 |
|---|---|---|
| CubeSandbox（`TencentCloud/CubeSandbox`） | `0.7.3` | `scripts/sdk-coverage.json` 的 `synced_version` |

上游发版后同步：先跑 SDK 漂移检查（见下），再同步版本号与命令面。

## 构建

需要 Zig **0.17.0**：

```bash
zig build -Doptimize=ReleaseFast        # → zig-out/bin/cube-cli

# 交叉编译到 arm64（iSH / 手机 / arm64 机器）
zig build -Doptimize=ReleaseFast -Dtarget=aarch64-linux-musl
```

产物名统一 `<tool>-<os>-<arch>[.exe]`。zig 的 `-Dtarget=` 三元组是 zig 的对外契约，原样保留；
与产物名的对照如下（`.github/workflows/build.yml` 的矩阵就是这六行）：

| 目标三元组（zig `-Dtarget=`） | 系统 / 架构 | 产物文件名 |
|---|---|---|
| `aarch64-linux-musl` | linux / arm64 | `cube-cli-linux-arm64` |
| `x86_64-linux-musl` | linux / amd64 | `cube-cli-linux-amd64` |
| `aarch64-macos` | macos / arm64 | `cube-cli-macos-arm64` |
| `x86_64-macos` | macos / amd64 | `cube-cli-macos-amd64` |
| `aarch64-windows-gnu` | windows / arm64 | `cube-cli-windows-arm64.exe` |
| `x86_64-windows-gnu` | windows / amd64 | `cube-cli-windows-amd64.exe` |

六种产物都由 CI 构建（windows / arm64 无可用 runner，只校验编译），并各自在对应平台
真跑一遍 `version` 做冒烟；ReleaseFast + strip 后约 1.2 MB 静态单文件。

## 配置

**所有部署相关取值一律通过环境变量传入，仓库内不含任何主机名、IP 或凭据。**

| 变量 | 必填 | 说明 |
|---|---|---|
| `CUBESANDBOX_API_URL` | 是 | 控制面地址 |
| `CUBESANDBOX_API_KEY` | 否 | 控制面 API Key（部署未启用鉴权时可省略） |
| `CUBESANDBOX_PROXY_URL` | exec / 文件 / ports 必填 | 数据面网关地址（拼沙箱访问 URL 用） |
| `CUBESANDBOX_AGENT_NAME` | 否 | `new` 写入 `metadata.agent` 的默认名字 |

仅支持 CUBESANDBOX_* 新命名（旧名 `CUBE_API_URL` / `CUBE_API_KEY` / `CBS_PROXY_BASE` 不再兼容）。

缺变量不会崩溃：控制面命令会打印「错误：缺少环境变量 …」并以非 0 退出码结束。

## 命令速查：先看 `help`

**`help` 就是权威命令面。** 命令表在 `src/help.zig`，`docs/cube-cli.md` 由
`scripts/gen-docs.py` 从**编译产物**自动生成——**文档随代码走**，改了命令先改 `help.zig`，
再跑一次生成脚本，README 不再重复维护命令清单。

```bash
cube-cli help              # 分组速查（常用命令，保持精简）
cube-cli help all          # 完整命令表，一条一行
cube-cli help <命令>       # 单命令详解：用途 / 用法 / 参数 / 示例 / 注意
cube-cli <命令> --help     # 同上，且**只打印不执行**
cube-cli <命令> -h         # 同上
```

常用：

```bash
cube-cli version                 # 版本 / 仓库地址 / 构建信息
cube-cli health                  # 控制面健康检查
cube-cli tpl-ls                  # 列出模板
cube-cli new --need=code         # 建沙箱（默认就是 aio-code 镜像）
cube-cli ls                      # 列出沙箱
cube-cli exec <sandboxID> 'zig version' --timeout=300
cube-cli snap <sandboxID> --name=before-refactor
```

完整命令面（每条命令一节文档）：[`docs/cube-cli.md`](docs/cube-cli.md)。重新生成：

```bash
zig build -Doptimize=ReleaseFast
python3 scripts/gen-docs.py
```

## 拿到沙箱后交给 aiod-cli

沙箱内部的**数据面遥控**（命令执行 / PTY / 浏览器 / 桌面 / 代码解释器）是另一个独立仓库
[`aiod-cli`](https://github.com/otaku-say/aiod-cli)。`cube-cli new` 输出的
`[sandbox] AIO 网关:` 那行**就是**它的 `SANDBOX_BASE`：

```bash
SID=$(cube-cli new --note=demo)
# 输出里：[sandbox] AIO 网关: https://<网关>/sandbox/<sandboxID>/8080/   ← aiod-cli 的 SANDBOX_BASE
export SANDBOX_BASE="https://<网关>/sandbox/$SID/8080"   # 末尾的 / 无所谓
```

本仓库自身不需要 `SANDBOX_BASE`：`exec` / 文件 / `ports` 都走 `CUBESANDBOX_PROXY_URL` + envd。

## MCP Server（Agent 接口）

`cube-cli mcp-server` 以 **Model Context Protocol (MCP)** 服务运行。MCP Client（如 Claude
Desktop、Cursor、Cline 等）可把二进制作为子进程拉起，走 stdio 传输与 JSON-RPC 2.0 协议闭环
调用沙箱能力。

### 客户端配置示例

Claude Desktop (`claude_desktop_config.json`) / Cursor (`mcp.json`)：

```json
{
  "mcpServers": {
    "cube-control": {
      "command": "/path/to/cube-cli",
      "args": ["mcp-server"],
      "env": {
        "CUBESANDBOX_API_URL": "https://api.example.com",
        "CUBESANDBOX_API_KEY": "your-api-key",
        "CUBESANDBOX_PROXY_URL": "https://proxy.example.com"
      }
    }
  }
}
```

> **缺配置不退出**：启动时缺少环境变量不会崩溃退出，仍能正常响应 `initialize` 与
> `tools/list`；仅在具体工具被调用且缺少对应配置时返回友好的 `isError: true` 错误提示
> （指引补充对应环境变量）。

### 工具分组概览

按照功能分域暴露 37 个 MCP 工具（工具名采用 `snake_case`）：

- **沙箱生命周期**（11）：`sandbox_create`、`sandbox_list`、`sandbox_info`、`sandbox_delete`、`sandbox_pause`、`sandbox_resume`、`sandbox_refresh`、`sandbox_timeout`、`sandbox_net_set`、`sandbox_ports`、`sandbox_clone`
- **进程执行**（6）：`sandbox_exec`、`sandbox_exec_async`、`sandbox_exec_logs`、`sandbox_exec_kill`、`sandbox_exec_stdin`、`sandbox_code`
- **文件操作（envd 通道，8）**：`sandbox_file_read`、`sandbox_file_write`、`sandbox_file_stat`、`sandbox_file_list`、`sandbox_file_mkdir`、`sandbox_file_delete`、`sandbox_file_move`、`sandbox_file_exists`
- **快照**（4）：`snapshot_create`、`snapshot_list`、`snapshot_delete`、`snapshot_rollback`
- **持久卷**（4）：`volume_create`、`volume_list`、`volume_info`、`volume_delete`
- **模板**（3）：`template_list`、`template_info`、`template_pick`
- **原始 API**（1）：`api_call`

### stdout 纯净性承诺

- **绝对无协议外噪音**：stdio 模式下 stdout 只出现「单行、以 `\n` 结尾、可严格被 JSON 解析」的 JSON-RPC 2.0 消息；绝对不输出 banner、进度条、ANSI 颜色代码或任何非协议文本。
- **诊断分流至 stderr**：所有日志、警告与诊断信息均通过 stderr 输出。

### 已知限制

遵循 MCP 规范及设计边界，以下特性在当前版本明确不做：

- **不支持批处理**：JSON-RPC 顶层批量请求数组将返回 `-32600 Invalid Request`（符合最新 MCP 协议规范）。
- **无流式/进度通知**：仅接收客户端 `notifications/*` 通知但不做下发，不支持 resources 和 prompts 能力。
- **无 follow 类工具**：长驻阻塞循环（如 `exec-logs follow`、`pty-read` 等）不暴露为 MCP 工具。
- **仅提供 stdio 传输**：不内置 SSE 或 HTTP 传输，保持单二进制静态分发的纯粹性。

## 测试

```bash
sh tests/run_all.sh             # 一键全量（7 步）：构建 → help 冒烟 → MCP 协议/纯净性 → 工具 mock → 大文本 UTF-8 → 内存稳定性 → 对抗套件
sh tests/help_smoke.sh          # 只跑帮助体系 + new --help 不建沙箱
```

`tests/` 目录（全部只用 Python 3 标准库，不依赖网络）：

| 文件 | 覆盖 |
|---|---|
| `help_smoke.sh` | 帮助体系五入口 + `new --help` 绝不建沙箱 + 未知命令退出码 |
| `mcp_protocol_test.py` | MCP 协议与 stdout 纯净性（版本协商、通知零输出、错误码矩阵、id 保真、畸形输入、32 MiB 边界、200 条顺序一致性…） |
| `mock_cube_server.py` / `mcp_cube_tools_test.py` | 37 个工具：MCP 结果 + mock 实收请求双向断言（含安全门禁「未确认零请求」） |
| `mcp_cube_edge_test.py` | 边界回归：模板别名解析、`pause --wait` 如实超时、可选参数类型错误 |
| `mcp_big_output_test.py` | 超 4 MiB 文本截断的 UTF-8 安全性（截断点落在汉字中间） |
| `mcp_mem_stability_test.py` | 常驻 `mcp-server` 在 3000 次调用下的内存增长门禁 |
| `adv_cube_suite.py` / `adv_cube_defect_probe.py` | 全工具三轴覆盖、参数毒化、并发 1:1 应答、挂死检测、破坏性工具幂等 |
| `adv_cube_live.py` / `mcp_live_smoke.py` | **真实环境**全链路验收（创建→执行→文件往返→快照→销毁），需真实凭据，手工跑 |

## SDK 漂移检查（跟进上游）

一条长期纪律配一把自动尺，脚本在 `scripts/`（仅 Python 3 标准库）：
**cube-cli 始终跟随上游 Python SDK**，对照的签入清单是 `scripts/sdk-coverage.json`
（94 个公开方法 → 命令 / 明确不做+原因）。

```bash
python3 scripts/check-sdk-drift.py --sdk=/path/to/sdk/python
python3 scripts/check-sdk-drift.py --fetch          # 按发布版跟踪：--fetch --ref=v0.7.2
```

判读输出：

- **① 新增方法**（上游有、清单无）= **需要跟进**：给 CLI 补命令，或把清单条目标 `not-planned` + 原因；
- **② 消失方法**（清单有、上游无）= 上游删除/改名 → 复核清单；
- **③ 签名变化** = 方法签名变了 → 复核 CLI 参数是否跟随（`--no-signature-check` 可只看增删）；
- **④ 覆盖统计** = implemented（有命令）/ not-planned（明确不做）计数；
- **退出码**：0 = 无漂移；1 = 有漂移；2 = 拉取/清单错误 —— 可直接进 CI。

清单只由维护者更新（脚本只报告差异、不自动改清单）。`--json` 拿机器可读结果；
检查挂在 `.github/workflows/drift.yml`（每周一 + 手动触发）。

## DNS 容错（iSH 等环境必需）

Zig 标准库的解析器**不会跳过不可达的 nameserver**。若 `/etc/resolv.conf` 把 IPv6
链路本地地址（`fe80::/10`）排在第一位——iSH for iOS 正是如此——它会拿这个地址直接查询，
报文发不出去就整个解析以 `error.NameServerFailure` 收场，每次还要空耗数秒超时。
musl libc 会自动跳过这类地址，所以在同一台机器上 `curl` 一切正常，`cube-cli` 却连
一个域名都解析不出来。

`cube-cli` 内置了 `netfix.zig`：启动时若检测到此类地址，就在**进程内**接管域名解析
（注入 `std.Io` 的 `netLookup`），过滤掉不可达的 nameserver 后用其余地址查询。
**不改系统文件、不依赖 libc、不引入第三方依赖**；配置正常时不安装任何钩子（零开销）。

实现要点（都是踩过的坑，改之前先读）：

- `Io.Threaded` 的 `netLookup` 内部用的是**它自己的 io**（`t.io()`），不是调用方传入的
  那个。因此"把 `/etc/resolv.conf` 重定向到副本"这类文件层做法会被绕过（strace 实证：
  它仍然打开真实文件）。唯一有效的注入点就是 `netLookup` 本身。
- 包装 `std.Io` 时，`Io.userdata` 必须**原样透传**——它是底层实现的私有数据（指向
  `Threaded` 实例）。换成自己的结构体会让其它 vtable 函数解引用错位，直接段错误。
- `hookNetLookup` 内部必须用**包装后的 io**（`g_io`），不能透传未包装的 `g_base`：
  否则 `ResolvConf.init` 的 `File.openAbsolute("/etc/resolv.conf")` 读到的是真身，
  过滤副本形同虚设——链路本地死服务器排第一时每次查询都空耗 5 秒超时。
- DNS 查询把全部 nameserver **一次性并行发送**（musl 同策略），按事务 ID 收包：
  黑洞型服务器（发包成功但不应答，如 iSH 的 198.18.0.1）只占一个在途报文，
  不会让健康服务器串行等待整轮超时。
- 查询实现复用标准库公开件：`HostName.ResolvConf.init(io)`（用我们包装过的 io 读过滤副本）、
  `HostName.DnsResponse`、`HostName.expand`；只有查询报文构造与 UDP 收发是自己写的。

## 为什么是 Zig

这个 CLI 在 iOS 的 iSH（Linux 用户态环境）里频繁调用，**进程启动开销是主要成本**。
同一任务（HTTPS GET + 自定义请求头）的实测：

| 语言 | 纯启动 | 二进制 |
|---|---|---|
| Go | ~170 ms | 5.3 MB |
| **Zig** | **~2 ms** | **~1 MB** |

Go 的 ~170ms 是 runtime 初始化的固定开销（与二进制体积无关：1.3 MB 的 hello world 与 5.3 MB 的完整程序一样慢）。
Zig 静态链接 musl，无 runtime、无 GC，启动接近 C 程序。

其他收益：**零第三方依赖**（HTTP/TLS/JSON 全在标准库）、交叉编译内置
（`-Dtarget=aarch64-linux-musl` 一条命令，无需额外工具链）。

## 注意

- **flag 一律 `--key=value` 等号写法**（`--need=code`）；布尔开关直接写 `--flag`。
- **未知命令**会打印「未知命令：xxx」并以**非 0** 退出码结束。
- `--help` / `-h` / `help <命令>` 三种写法等价，且**绝不触发真实操作**——
  `cube-cli new --help` 只打印帮助、不会真的建沙箱（`tests/help_smoke.sh` 里有回归验证）。
- 文档里标了「源码未实现」的选项确实没有接线（历史上旧文档写过的 `--env=` / `--limit=` /
  `--ref=` 等在当前实现里不存在），别照抄。
- 大文件（> 8 MiB）的读写请用 [`aiod-cli`](https://github.com/otaku-say/aiod-cli) 的
  `put` / `fs-tree-put`；本仓库的 envd 文件通道单文件上限 8 MiB。

Zig 0.17 的标准库与旧版本差异很大（`std.io` → `std.Io`、`std.http.Client` 需注入 `io`、
`main` 签名改为接收 `std.process.Init`）。本仓库代码按 0.17 编写，**不要**参照网上基于 0.11–0.14 的示例。
