# 开发、贡献与反馈

[中文](contributing.md) | [English](contributing.en.md) · [返回 README](../README.md)

## 1. 开发准备

克隆仓库，准备 Git、python3 与 `/bin/bash`，不需要第三方 Python 包或 jq：

```bash
git clone https://github.com/haigeerlab/tier-guard.git
cd tier-guard
/bin/bash scripts/validate.sh
```

贡献建议使用单独分支，例如 `codex/docs-bilingual`。开始前阅读 [CLAUDE.md](../CLAUDE.md)、[规约](../spec/tier-guard.md)、[模块计划](../tasks/tier-guard/plan.md) 和[待办](../tasks/tier-guard/todo.md)。这些是维护者与代理的开发契约，原文以中文为主；当前用户入口和本指南均有英文版。

## 2. 实现结构与约束

- `hooks/route_decide.py` 是唯一判据；Claude / Codex adapter 和报告复用核心，不复制策略。
- `config/routing.catalog.v2.json` 是当前目录；`routing.default.json` 用于历史 v1 和迁移测试。
- `commands/` 是 Claude 命令；`skills/` 是派活前指令；两份插件清单的名称和版本需一致。
- Shell 使用 `/bin/bash`，兼容 macOS 3.2；多字节字符前用 `${VAR}`，不引入 `cmd | grep -q`、`sed -i`、`timeout` 或 jq 硬依赖。
- 修改范围与需求对应；运行时不依赖 `.agent/state.json` 或其他插件的私有文件。
- 不把任务原文、描述原文、失败日志或密钥写入审计。报告回读历史转录时也需考虑披露风险。

## 3. 验证

完整免费回归是所有改动的交付检查：

```bash
/bin/bash scripts/validate.sh
```

定向入口：

```bash
python3 -B hooks/route_decide.py --selftest
python3 -B hooks/test-route-contract.py
/bin/bash hooks/test-tier-guard.sh
/bin/bash hooks/test-tier-guard-codex.sh
/bin/bash hooks/test-tier-commands.sh
/bin/bash hooks/test-tier-doctor.sh
/bin/bash hooks/test-tier-observe.sh
/bin/bash scripts/test-checkers.sh
```

新增 check 脚本时给校验器自身添加正反用例。修改 hook 或测试断言时，检查变异锚点并运行相关变异；完整变异测试较慢，不在 validate 中：

```bash
python3 -B scripts/check-mutation-anchors.py
python3 scripts/mutation-check.py
```

文档改动同时核对两种语言、相对链接、命令、默认值和宿主差异；不要修改历史实验数字来迎合当前实现。

## 4. 真实宿主验证与权限

真实 CLI / Desktop 派活可能写宿主配置或转录并消耗模型用量，应事先取得相应授权。不要用付费真实派活代替免费回归。Codex 的真实预路由脚本需在交互式 Terminal/TUI 中运行，并保留隔离目录和回执：

```bash
/bin/bash scripts/codex-cli-preroute-smoke.sh
```

该脚本启动真实宿主，会使用账号、写宿主会话数据；需要 Codex、Git、python3、交互式终端及宿主可读的线程数据库。执行前阅读脚本，不把普通协作 API 当作原生 hook 验收；历史非交互 exec 的失败不代表所有新版本仍有相同限制。完整变异测试使用 Python 3.7 起提供的 subprocess 接口。

提交、推送、发版、写入用户 `~/.claude` / `~/.codex`、开启 auto、修改宿主能力闸门或 deny 行为，均按项目约定先确认。`scripts/install-git-hooks.sh` 会安装本地 pre-push，也应先确认。

## 5. 提交贡献与反馈

[Issues](https://github.com/haigeerlab/tier-guard/issues) 用于问题与建议，[Pull Requests](https://github.com/haigeerlab/tier-guard/pulls) 用于提交修改。先查现有讨论，PR 说明具体问题、修改后的行为、验证结果与尚未验证的宿主。

反馈建议包含：

- 插件版本、宿主名称与版本、操作系统。
- 有效模式及来源、默认或自定义候选目录、相关环境覆盖是否存在。
- 最小脱敏复现、预期与实际结果、是否使用原生派活。
- 可分享的事件字段或测试输出；去掉密钥、账号信息、会话 ID、个人路径和任务正文。

不要把原始日志、转录或整个环境变量列表直接上传。若问题涉及敏感内容，先提交不含敏感信息的描述，再与维护者确认合适的报告渠道；本仓没有声明专用安全邮箱。

## 6. 文档与许可

用户文档以中文为基线，英文保持相同结构、参数和限制。新增行为同步 README、参考、兼容性与 CHANGELOG；技能和命令执行指令以仓库原文为准。历史研究按日期和被测版本保留，通过导航说明后续变化。

贡献遵循项目 [Apache License 2.0](../LICENSE)，完整条款以许可证为准。
