# Codex L2 候选：GPT-6 Luna 对 GPT-6.1 Sol/medium

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 状态：**已完成——Luna/high 可以承担 L2**　｜　日期：2026-10-05　｜　Task 24（spec「Dispatch economics → Codex 的 L2 候选」）

## 结论

10 个 L2 任务上，`gpt-6-luna/high` 与现行 L2 候选 `gpt-6.1-sol/medium` **质量相同（10/10 对 10/10）**，
每任务成本约为 Sol 的 **1/14**。`luna/xhigh` 同样 10/10，没有额外收益，选 `high`。

## 方法

- 任务：Claude 侧 L2 实验的 10 个任务（[`gen_tasks.py`](2026-10-05-l2-cost-experiment/gen_tasks.py) 原样生成），
  提示词三组逐字相同。
- 每次运行一个独立目录，`codex exec -m <model> -c model_reasoning_effort=<e> --sandbox workspace-write
  --skip-git-repo-check`（CLI 0.160.0，ChatGPT 账号）。**不用** ephemeral 的委托 wrapper，以保留 rollout。
- 评分：原始测试副本在隔离目录重跑，并核对测试文件 SHA-256 是否被改。
- token：按工作目录在 `~/.codex/state_5.sqlite` 线程表找到 rollout，取最后一条 `token_count` 的 `total_token_usage`。
  已核实 `input_tokens` **包含**缓存命中（CLI 打印的 tokens used = 输入 − 缓存 + 输出）。
- 价格（用户提供，2026-10-04）：Luna $0.10/$0.50、Sol $2/$10 每百万 token。缓存输入价未提供，给出两个口径：缓存按 10%
  计、缓存按全价计（最保守）。

## 结果

| 组 | 通过 | 改测试 | 每任务输入（其中缓存） | 每任务输出（其中推理） | 每任务成本（缓存 10%） | 每任务成本（缓存全价） |
|---|---|---|---|---|---|---|
| Sol / medium | 10/10 | 0 | 128,526（108,096） | 650（12） | $0.0690 | $0.2636 |
| **Luna / high** | **10/10** | 0 | 163,347（133,965） | 1,505（668） | **$0.0050** | **$0.0171** |
| Luna / xhigh | 10/10 | 0 | 174,670（144,896） | 2,526（1,476） | $0.0057 | $0.0187 |

Luna 多用约 25–35% 的 token，但单价是 Sol 的 1/20，整体约 1/14（两种缓存口径下都在 1/14–1/15）。
原始数据 [`results.jsonl`](2026-10-05-codex-l2-luna-experiment/results.jsonl)，脚本 `run_one.sh`、`grade.py`。
`luna-high/04-rle` 的线程数为 2：最早的试跑与正式运行在同一目录，评分取最新一条。

## 局限

- **天花板效应**：三组都 10/10，只能证明 Luna 足以胜任典型 L2，不能证明更难的 L2 也行（与 Claude 侧同样的局限）。
- 每格一次。价格与智能指数为用户提供的公开数据，本仓未独立核验；可核对的是通过率与 token 量。
- 只测了 `codex exec`；主代理按 tier-routing 显式派 Luna 的路径，在既有宿主验证里已覆盖（L1 即为 Luna）。

## 对候选目录的含义

满足 spec 设定的条件（质量持平、每任务成本更低），Codex L2 可改为 `gpt-6-luna/high`。这会使 L2→L3 换 slug，需放开
「升档只许动 effort」约束——用户已于 2026-10-05 同意。改目录属于 Task 25，发版前先问。
