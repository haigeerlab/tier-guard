# 剩余事项核对（2026-10-08）

基线：`4427fda`。本次核对剩余事项，并按用户已审阅的预览完成历史补正；未运行新增付费派活。

## 已完成的同步

文档治理提交 `4427fda` 已推送至既有 `origin/main`。推送前远端无分叉，推送后远端分支指向完整提交
`4427fda0ba8bc198a87759d479f8a61b530196c0`，本地与远端差异为 0/0。

## Codex 上游阻塞

原有 Task 7、v2 最终检查点与上游前置条件属于同一依赖链。CLI 0.160.0 的
[官方源码](https://raw.githubusercontent.com/openai/codex/rust-v0.160.0/codex-rs/core/src/tools/handlers/multi_agents_spec.rs)
仍将 spawn_agent 的 message 标为 `with_encrypted()`；本次查看
[上游 Issue #33284](https://github.com/openai/codex/issues/33284) 仍为 Open。
这不能单独证明所有未来宿主的行为；现有真实回执见
[目录复验](2026-10-05-catalog-rehost-verification.md)，hook 输入仍为 opaque_token。

本次本机 Codex 生产审计共 25 条派活：24 条 v2，15 条显式记为 opaque_token，其余 10 条缺少
该字段；不能把缺字段解释为可见明文。最近 2026-10-05 的 4 条全部 opaque_token、applied=false。
据此保留阻塞与关闭的 Codex 能力闸门，不重复运行尚不具备前置条件的 Task 7。

## 两项选档观察

原有观察的复评条件是：再次出现真实取舍类降档，或实现类独立自然样本每宿主至少 10 次。
本次 Claude 生产日志共 441 条派活、3387 条 stop；441 条派活为 v2 且任务可见。
日志总量不等于符合条件的自然实现样本；本次未读取任务正文或将 hook 的自分类当作独立标签。
Codex 最近 4 条记录的任务信号均未知，无法据它们认定任务类型或选档正确性。

已存 [Codex L2 实验](2026-10-05-codex-l2-luna-experiment.md) 和
[Claude L2 实验](2026-10-05-l2-cost-experiment.md) 显式指定候选进行质量对照，证明候选能力，
不能代替主代理自然选档统计。当前 Codex L1/L2 都可使用 Luna/high，旧目录下“低一档”的型号
也不能原样套用。现有证据不足以关闭两项观察，亦不足以据此修改 skill、目录或闸门。

后续复评须冻结宿主版本与目录指纹，独立标记任务类型和验收，在自然派活中不预先指定 child
模型，关联实际 model/effort 与质量结果。应分别统计每宿主的实现样本及取舍误选，显式用户 pin
单列；不能仅因 hook 建议保守档而把主代理 pin 判为错误。新增付费实验的范围和用量须另行确认。

## 历史补正设计

依据同批 `2026-10-08-history-audit.json`，唯一未解决 finding 为 timestamp-unverified。
补正只追加 history-correction：legacy/eventIndex=0，checkpoint=19700101T000000Z-0001，
字段 event.at，before=imported，after=unknown。原事件、快照、模块数组与地图哈希均保持原值。
审计时间是本次审计的时间，不能当作 legacy 创建时间。

官方 validate、verify 和 audit 已在临时预测账本上通过。用户于 2026-10-08 确认继续后，
重新核对原基线、审计原字节及报告哈希，使用官方 correct --confirm 追加已审阅记录。
实际账本与预测一致，validate、verify 和 verify-history 通过，实际 audit 为
correctedFindings=1、unresolvedFindings=0；原 initiatives 与能力图哈希不变。
这表示告警已有明确的 unknown 补正，不表示已找回历史时间或模块已完成。

## 本批交付结果

完整 `/bin/bash scripts/validate.sh` 退出 0，diff 检查通过；官方产物检查 3 通过、
0 警告、0 失败，历史核验通过。补正与证据以五文件提交 `2739548` 推送到 origin/main，
远端读回 `2739548482fc0c2ba46a7ca7f463ae061cbe2def`。本节与 todo 的完成记录在
取得该远端结果后补记。原有五个未勾选项仍保留，包括同一 Codex 阻塞链与两项观察。
