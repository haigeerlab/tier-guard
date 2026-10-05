# tier-guard

按任务动态路由子代理模型的插件（Claude + Codex 双清单）。主代理不换模型；每个未 pin 的子
代理按本次任务选择最低成本的合格 `model + reasoning_effort`，信息不足时保守选择。

动手前按顺序读：

1. `spec/tier-guard.md` —— 规约
2. `tasks/tier-guard/plan.md` —— 任务拆解 + **已定决策表**（表里的不要重新讨论）+ 当前检查点
3. `docs/research/` —— 实测证据；结论必须带可核对出处

## 最容易被推翻的已定决策

完整表格在 plan 里。这几条被推翻过或差点被推翻：

- 独立仓；**运行时**对 agent-skills / spec-guard 零依赖，插件代码不读 `.agent/state.json`
  （本仓的开发流程装了 spec-guard 约定，那是开发工具，不是运行时依赖）
- 交付形态必须是插件，不往 `~/.claude/settings.json` 塞 hook 片段（Cloud 会话不读本地 settings）
- 路由只在创建子代理前运行；显式 `model` 或 `reasoning_effort` 是 pin，绝不改写；audit / guard 仍记录相对起点的建议方向
- 默认配置是 v2 catalog，mode 为 `off` / `audit` / `guard` / `auto`，默认 `guard`（2026-09-13 用户确认推翻「默认 audit」）；
  guard 与 audit 都不改写参数，guard 可直接持久化，auto 仍需质量门槛
- 即使临时设 `TIER_GUARD_MODE=auto`，也只有 catalog 中已实测的
  `host_capabilities.<host>.pre_dispatch_apply=true` 才能实际改写；当前生产目录只有 `claude-code` 为 `true`
- 不可逆、取舍、跨模块或信息不足不能被路由到低能力候选
- 主代理预路由提醒（2026-09-13 用户确认）：宿主 `dispatch_nudge=true` 时，audit 对未 pin 派活只输出
  `additionalContext` 提醒、不改参数；guard（默认）与 auto 每个会话只 deny 第一次未 pin 派活（标记写不进去就降级为提醒），
  只有 auto 会在能力闸门允许时改写参数。
  pin、`plugin:name`、fork、off、闸门关闭一律不提醒；生产目录只开了 `claude-code.dispatch_nudge`（Task 15 达标，
  2026-09-13 用户确认），Codex 仍为 `false`；改动任何闸门前先问
- Codex Desktop 已观察到协作派活进入审计 hook；但未验证 `updatedInput` 被宿主采纳，仍只能建议，不能标成自动路由

## 命令

```bash
/bin/bash scripts/validate.sh            # 仓库校验（含全部回归套件），改完必跑
/bin/bash hooks/test-tier-guard.sh       # Claude 薄壳回归
/bin/bash hooks/test-tier-guard-codex.sh # Codex 薄壳回归
/bin/bash hooks/test-tier-commands.sh    # /tier-mode · /tier-report 回归
/bin/bash hooks/test-tier-observe.sh     # SubagentStop · 打回率 · 误报率 · auto 门槛
/bin/bash scripts/test-checkers.sh       # 校验器自身回归
python3 -B hooks/route_decide.py --selftest
python3 -B scripts/check-mutation-anchors.py  # 变异体锚点是否仍唯一命中（秒级，已进 validate）
python3 scripts/mutation-check.py        # 变异测试（在临时副本里做，慢，不进 validate）
/bin/bash scripts/install-git-hooks.sh   # 装 pre-push（未装，要装先问）
```

## 硬性约束

- 命令、shebang 一律写 `/bin/bash`，不写 `bash` —— macOS 上后者可能是 Homebrew 5.x，3.2 才是要防的版本
- 不写 `$VAR` 紧跟多字节字符，一律 `${VAR}`（bash 3.2 会致命退出，hook 失败是静默的）
- 不写 `cmd | grep -q`（SIGPIPE + pipefail 让判断永远为假），用 herestring 或纯 bash `case`
- 不引入 `jq` 硬依赖；JSON 交给 python3
- 跨平台：不用 `sed -i`（macOS / Linux 写法不同）、不用 `timeout`（macOS 没有）
- 本机 shell 把 `cp` 别名成了 `cp -i`，脚本里用 `command cp`

## 规矩

- **判据只在 `hooks/route_decide.py`。** 薄壳、`/tier-report` 都调它，任何一方内联重写判据 =
  一条关不掉的假警报。改它必须跑 `--selftest` 和两套薄壳断言
- **新加的每个 `check-*.py` 必须同时往 `scripts/test-checkers.sh` 加一正一反**；判据写完当场用真实数据跑一遍
- 新写的断言要进 `scripts/mutation-check.py` 验一遍：「全绿」不等于「有断言」。
  标 `equivalent` 必须写清为什么
- **改完 hook 源码跑一次 `check-mutation-anchors.py`。** 重构会打断锚定在那段代码上的变异体，
  被打断的变异体**整条不跑**——不报错、不算失败，它守的断言从此无人验证。
  `mutation-check.py` 会报「锚点失效 N」，但**只看这个计数会误判归因**：2026-10-05 把自己刚
  造成的两处认成了已知旧账，一条变异体因此几个提交没跑。逐条核对才作数，这个检查几秒就出结果
- 测试里复合条件写成具名函数再交给 `yn`：`$(yn A && B)` 是永远为真的空断言
- 守卫任何异常路径一律放行（退出 0、stdout 空），并在日志里写明是哪条路径
- 日志不记 prompt 原文（可能有密钥），只记长度和 sha256

## 边界（先问）

- `git commit` / 建 remote / push / 发版
- 写入 `~/.claude` 或 `~/.codex` 下的任何文件（跑 `claude -p --plugin-dir` 会写 transcript，也算）
- 从 audit 切到 auto；往不可逆动作词表加词；任何会让守卫返回 deny 的改动


<!-- BEGIN:agent-skills-convention -->
## Agent Skills 集成约定

> 由 `/spec-guard:setup-convention local` 生成。任务托管在**本地 todo.md**（Addy 原生路径）。
> 保留 `<!-- BEGIN/END -->` 标记，`/spec-guard:setup-convention --replace` 靠它升级本块。

- 能力图 `spec/CAPABILITY-MAP.md`，模块 spec `spec/<module-id>.md`（kebab-case，一次选定中途不改名）
- **不要**在项目根建 `SPEC.md` / `SPEC-<module>.md` —— `/build` 只认根 `SPEC.md`、
  `docs/SPEC.md`、`spec/` 三条路径，**只有第三条是通配的**
- 每个模块的产物互相隔离：`tasks/<module-id>/plan.md` + `tasks/<module-id>/todo.md`，
  **不要共用 `tasks/plan.md`**
- `/build` 取任务：读 `.agent/state.json` 的 `activeModule`，从该模块的 `todo.md`
  取第一个未勾选项，**不跨模块取**
- 切换 `activeModule` 前当前模块不能有进行中的 task；切换后重读该模块的 spec 和 plan
- 阶段交接或停止时，加载 `spec-guard:spec-guard-ops` 的共享检查点规则，预告已授权下一步。
<!-- END:agent-skills-convention -->
