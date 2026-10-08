# Capability Map: tier-guard —— 按任务分级路由模型

> 由 `/spec` 的 Phase 0 产出。**必须经人工评审后才能往下走。**
> Addy 原文：把图搞错代价很大，评审十行不算什么。

## 目标

在创建子代理时，根据这一次任务的实际需求，选择满足质量要求的最低成本
`model + reasoning_effort`，减少 token 消耗而不牺牲可靠性。主代理的模型不受影响。
给在 Claude Code 与 Codex 中使用 agent-skills 等工作流派子代理的开发者用。

<!-- 这一段是 Epic issue 正文摘要的**唯一来源**，也是它的指纹底本。
     改了这里，phase-guard 会提醒你 Epic 正文过期了（跑 /sync-map 刷新）。
     标题必须是 `## 目标`（或 `## Goal`）—— 指纹脚本按标题定位这一节。 -->

## 模块

| Module id | Responsibility | Depends on |
|---|---|---|
| tier-guard | 动态子代理路由策略（唯一实现）+ Claude / Codex adapter + 可选 agent-skills 上下文 + 审计与校准 | — |

Build order: tier-guard

---

## 评审记录

- [x] 模块边界确认（砍掉或替换一个模块，不需要重写其他模块的需求）
- [x] 依赖方向单向无环（互相依赖 = 它们本来就是一个模块）
- [x] module id 已定稿（kebab-case，之后绝不改名 —— 同一个 id 同时是
      `spec/<id>.md`、`tasks/<id>/`、`state.json`、`feat/<id>` 分支和 issue 标题的名字，
      其中后两处改不动）
- [x] 构建顺序符合依赖拓扑

背景（2026-09-12）：本仓先写了 SPEC 与 plan、做完 Task 0–5，之后才装 spec-guard 约定（local 模式）。
单模块是用户在会话里选定的 —— 按能力拆成多模块要把已评审的 spec 和 plan 拆开重写，
而 Task 0–5 已完成。上面四项仍需人工勾选。

评审人：用户（2026-09-12 会话中明确同意，由 Claude 代勾四项）
日期：2026-09-12
