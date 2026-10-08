# 使用与配置参考

[中文](reference.md) | [English](reference.en.md) · [返回 README](../README.md)

适用于 0.2.7 的默认 v2 目录。用户命令与脚本调用不同；下面的 shell 路径需替换成实际安装路径，不能把占位路径直接执行。

工具运行输出目前以中文为主；两版参考解释相同的模式、字段和验收依据，日志中的结构化字段名称保持一致。

## 1. Claude Code 命令

在 Claude Code 会话内使用：

| 命令 | 参数 | 读写行为 |
|---|---|---|
| `/tier-guard:tier-mode` | 无参数：模式与来源；`off` / `audit` / `guard`：持久设置；`auto`：v2 拒绝 | show 只读；set 写 `mode` |
| `/tier-guard:tier-report` | `--share [天数]`；省略天数为 7 | 只读日志；可回读 Claude 转录；share 额外扫描 Claude 项目转录 |
| `/tier-guard:tier-doctor` | 无参数 | 只读配置和日志；不能读取 Codex 信任状态 |
| `/tier-guard:tier-label` | `<tool_use_id> <fp\|tp\|reject\|accept>` | 追加 `labels.jsonl`；只接受用户给出的 v1 判定 |

`fp` / `tp` 表示历史不可逆信号的误报 / 真命中；`reject` / `accept` 表示历史 T1 产出被打回 / 验收。不存在的 ID、类型不匹配和 v2 记录均拒绝。它不是当前 v2 的质量校准工具。

## 2. Codex 与普通 shell 入口

Codex 不从 `commands/*.md` 获得 Claude slash 命令。先运行 `codex plugin list --available --json`，定位 `tier-guard` 的版本、启用状态及来源路径，再确认该插件根下确实存在 `hooks/tier_state.py` 和清单。若输出只指向 marketplace，需定位其 tier-guard 插件目录；不要固定复制某个旧版本缓存路径。

下面的 `TIER_GUARD_PLUGIN_ROOT` 是**本示例的 shell 变量**，不是插件自动读取的环境变量：

```bash
TIER_GUARD_PLUGIN_ROOT="/absolute/path/to/tier-guard"
TIER_GUARD_DATA_DIR="$HOME/.codex/plugins/data/tier-guard-tier-guard"
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_state.py" show --data "$TIER_GUARD_DATA_DIR"
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_doctor.py" --data "$TIER_GUARD_DATA_DIR"
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_report.py" --data "$TIER_GUARD_DATA_DIR"
```

需要启用审计时，用户执行：

```bash
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_state.py" set audit --data "$TIER_GUARD_DATA_DIR"
```

恢复关闭时，把 `audit` 改为 `off`。这会修改指定目录中的模式文件，不代表所有宿主都已配置：命令与 hook 必须使用同一目录。若环境变量覆盖了模式，需在启动宿主的环境中处理覆盖并开启新会话。

脚本接口：

| 脚本 | 参数 | 默认与用途 |
|---|---|---|
| `tier_state.py` | `show` 或 `set <mode>`；`--data DIR`；`--config PATH` | 无动作时等同 show；默认读取插件 v2 目录 |
| `tier_doctor.py` | `--data DIR`；`--config PATH` | 诊断路径、有效模式、日志及 Codex spawn 记录 |
| `tier_report.py` | `--config PATH`；`--data DIR`；`--recent N`；`--share [天数]`；`--projects DIR` | recent 默认 10；share 默认 7 天；projects 默认 `~/.claude/projects`，不是 Codex 总用量统计 |
| `tier_label.py` | `<tool_use_id> <fp\|tp\|reject\|accept>`；`--data DIR` | 仅 v1 人工标注 |

这些是实际支持的参数，不表示脚本会对任意缺失或非法参数友好恢复。按表提供完整合法值。

## 3. 配置来源与优先级

| 配置 | 优先级 / 范围 |
|---|---|
| 数据目录 | 脚本 `--data` → `TIER_GUARD_LOG_DIR` → 宿主注入的 `CLAUDE_PLUGIN_DATA` → `~/.local/state/tier-guard` |
| 模式 | `TIER_GUARD_MODE` → `<数据目录>/mode` → 所读取配置的 `mode` |
| hook 候选目录 | `TIER_GUARD_CONFIG` → 插件 `config/routing.catalog.v2.json` |
| state 配置 | 脚本 `--config` → 插件默认 v2 目录；**不自动读取 `TIER_GUARD_CONFIG`** |
| doctor / report 配置 | 脚本 `--config` → 插件默认 v2 目录；**不自动读取 `TIER_GUARD_CONFIG`** |

宿主正常安装一般会注入自己的插件数据路径；普通 shell 不会自动知道应使用 Claude 还是 Codex 数据，因此显式传 `--data`。

旧持久模式与环境覆盖可能保留。v2 下旧 `dry-run` 模式文件会回退到目录默认值；不要手工编辑模式文件来绕过 `auto` 拒绝。自定义候选目录时，state、doctor 和 report 均需显式传相同 `--config PATH`。doctor/report 要求合法 v2 目录；文件缺失、JSON 损坏、契约无效或参数缺值/重复均明确报错并非零退出，不静默回退。state 保留显式 v1 支持，report 保留 v1 历史统计。诊断需同时核对实际 hook 记录的 `catalog_identity`。

自定义 hook 目录时，显式传入其实际路径（以下命令只读）：

```sh
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_doctor.py" --data "$TIER_GUARD_DATA_DIR" --config /path/to/catalog.json
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_report.py" --data "$TIER_GUARD_DATA_DIR" --config /path/to/catalog.json
```

目录的关键字段：

- `schema_version: 2`、`mode`：契约版本和出厂模式。
- `routing.pin_policy: respect`：保持显式 pin；`unknown_requirement: conservative`：未知需求保守选择。
- `candidates`：`id`、`host`、`model`、`reasoning_effort`、`cost_rank`、`auto_eligible`、`capabilities`。在合格候选中按 `cost_rank`、再按 `id` 选取。
- `host_capabilities.<host>.pre_dispatch_apply`：是否有宿主自动改写证据；`dispatch_nudge`：是否启用提醒 / 拦截。
- `classification`：规则信号；`semantic_provider.mode: disabled`：当前没有外部语义 provider 实现。

能力闸门不是普通用户开关。临时 `auto` 不能绕过关闭的闸门或不透明任务输入。扩大候选、改变 pin 或新宿主支持需先验证设计和真实行为。

## 4. 上游档位、升档与收回

上游或主代理可在子任务文本中放入恰好一个独占一行的标记：

```text
<!-- tier-guard: tier=L2 failures=1 reason=按已确认设计实现，验收明确 -->
```

| 字段 | 要求 |
|---|---|
| `tier` | 必填；大小写敏感的 `L1`、`L2` 或 `L3` |
| `failures` | 可选；同一任务此前连续失败的非负整数；插件不自行判断失败 |
| `reason` | 可选；必须在最后，只给人读，不参与路由；正文不写入审计 |

字段顺序为 tier → failures → reason。重复标记、不独占一行、非法取值或 reason 中夹入 `failures=N` 均令标记不可用，回到推断。结果不确定是否计为失败由上游负责，插件不读取或转发失败日志。

- 优先级：pin → floor → 上游档位 → 推断。合法标记可低于信息不足时的保守档，不能低于 floor。
- floor 由核心的风险信号与最终所需能力共同确定；明确机械、小范围、只读任务有既有豁免，不能把任何单个关键词理解为必然 L3。
- `tier=L1` 且 `failures>=1`：有效档至少升至 L2；可能再受 floor 抬高。
- `tier=L2` 且 `failures>=2`：主代理应收回处理或重新界定任务。Claude hook 在 guard / auto、未 pin 且闸门开启时 deny；audit 提醒。收回不依赖 session ID，也不消耗首次派活拦截标记。
- Codex hook 看不到标记；skill 是主代理遵守这些规则的入口。off、pin、关闭闸门和无法判断 pin 时，hook 不执行收回拦截。

## 5. 数据与权限

| 文件 / 来源 | 作用 |
|---|---|
| `decisions.jsonl` | 路由与事件审计；包含模型、effort、时间、会话 / 工具标识、目录指纹及决策 |
| `mode` | 持久模式 |
| `nudge-denied/` | 每会话一次拦截标记，文件名由 session ID 的 SHA-256 派生 |
| `labels.jsonl` | v1 用户人工标注；同 ID 最后一次为准 |
| Claude agent 定义、宿主转录 | 核对 pin、实际执行和用量；report 可回读转录，share 会扫描项目转录 |

新版本记录的 prompt、description、task_name 使用长度和 SHA-256，不持久化正文；上游 reason 只记存在性及摘要。**这不等于日志不含敏感元数据**：转录路径、会话标识和旧版本历史记录仍需检查。报告的 v1 片段可从原始转录临时读取并遮蔽长 token，遮蔽不是全面脱敏保证。

新建审计目录与主日志分别请求 0700 / 0600 权限；这不修复已有文件权限，也不保证所有状态文件都具有相同权限。没有自动轮转或保留期限配置，用户负责备份与清理。

hook 异常尽量放行、尽量写 fallback；数据目录不可写时日志也可能缺失。目录默认 off 与模式文件 off 仍需要可工作的 Python / 配置解析才能被识别；环境 `TIER_GUARD_MODE=off` 有 shell 快速退出路径。不要把“异常放行”理解为所有故障都能留下日志。

## 6. 诊断与验收步骤

1. 查看插件清单，核对安装、启用、版本、路径和新会话加载。
2. 用 state / doctor 核对数据目录及模式来源；若自定义目录，核对配置差异。
3. 在用户希望审计时设置 audit，并用宿主原生派活；记录派发前后的日志变化。
4. 核对 `routing_version`、事件、`requested`、`decision`、`catalog_identity` 和 `applied`；Codex 同时查看 `task_visibility`。
5. 若需要证明实际模型，核对宿主回执或转录。Claude 别名与实际型号不同不一定是错误；缺少数据不等于零用量。

Codex CLI 的 `/hooks` 负责信任审核；doctor 无法证明信任。Desktop 必须通过原生派活检查，不用绕过宿主 hook 的协作 API 代替。report 按现行配置显示当前模式，空日志或旧日志不改变其来源；v1 门槛仅作历史统计。详见[兼容性](compatibility.md)。

## 7. 临时 auto 的实验边界

仅限用户明确选择的受控 Claude Code 实验；会消耗模型用量，并可能输出派发参数改写：

```bash
TIER_GUARD_MODE=auto claude
```

启动后用 `/tier-guard:tier-mode` 核对环境来源。命令前缀只作用于该进程；退出后新启动的 Claude 会按其正常环境与持久模式工作。它不持久启用 auto、不覆盖 pin，也不为 Codex 开启自动路由。不要让代理在模式命令拒绝后自行运行这个示例。
