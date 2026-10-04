#!/usr/bin/env python3
"""v2 路由契约的纯函数回归；不调用宿主 hook 或外部服务。"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_decide as rd


CATALOG = {
    "schema_version": 2,
    "mode": "audit",
    "routing": {"pin_policy": "respect", "unknown_requirement": "conservative"},
    "host_capabilities": {
        "codex-cli": {"pre_dispatch_apply": False},
    },
    "classification": {
        "readonly_markers": ["禁止修改任何文件", "只读"],
        "acceptance_markers": ["验收"],
        "irreversible_words": ["git push", "deploy"],
        "tradeoff_words": ["权衡", "取舍", "比较"],
        "implementation_markers": ["实现", "implement"],
        "bounded_scope_markers": ["只动", "only touch"],
    },
    "candidates": [
        {"id": "codex-luna-medium", "host": "codex-cli", "model": "gpt-5.6-luna",
         "reasoning_effort": "medium", "cost_rank": 1, "auto_eligible": True,
         "capabilities": ["mechanical", "read_only"]},
        {"id": "codex-terra-high", "host": "codex-cli", "model": "gpt-5.6-terra",
         "reasoning_effort": "high", "cost_rank": 2, "auto_eligible": True,
         "capabilities": ["implementation", "bounded_change"]},
        {"id": "codex-terra-xhigh", "host": "codex-cli", "model": "gpt-5.6-terra",
         "reasoning_effort": "xhigh", "cost_rank": 3, "auto_eligible": True,
         "capabilities": ["tradeoff", "cross_cutting"]},
    ],
}


def expect_error(cfg, contains):
    try:
        rd.check_config(cfg)
    except rd.ConfigError as exc:
        assert contains in str(exc), str(exc)
    else:
        raise AssertionError("expected ConfigError")


def main():
    rd.check_config(CATALOG)
    candidates = rd.catalog_candidates(CATALOG, "codex-cli")
    assert [c["id"] for c in candidates] == [
        "codex-luna-medium", "codex-terra-high", "codex-terra-xhigh"
    ]
    assert all(c["auto_eligible"] for c in candidates)
    assert rd.host_auto_enabled(CATALOG, "codex-cli") is False
    assert rd.host_nudge_enabled(CATALOG, "codex-cli") is False  # nudge: 字段缺失默认 false

    nudge_on = copy.deepcopy(CATALOG)
    nudge_on["host_capabilities"]["codex-cli"]["dispatch_nudge"] = True
    assert rd.host_nudge_enabled(nudge_on, "codex-cli") is True  # nudge: 显式 true 生效

    bad_nudge = copy.deepcopy(CATALOG)
    bad_nudge["host_capabilities"]["codex-cli"]["dispatch_nudge"] = "yes"
    expect_error(bad_nudge, "dispatch_nudge")  # nudge: 非布尔值被拒

    verified = copy.deepcopy(CATALOG)
    verified["host_capabilities"]["codex-cli"]["pre_dispatch_apply"] = True
    assert rd.host_auto_enabled(verified, "codex-cli") is True

    missing_host_capability = copy.deepcopy(CATALOG)
    del missing_host_capability["host_capabilities"]
    expect_error(missing_host_capability, "host_capabilities")

    duplicate = copy.deepcopy(CATALOG)
    duplicate["candidates"].append(copy.deepcopy(duplicate["candidates"][0]))
    expect_error(duplicate, "重复")

    malformed = copy.deepcopy(CATALOG)
    del malformed["candidates"][0]["cost_rank"]
    expect_error(malformed, "cost_rank")

    bad_pin = copy.deepcopy(CATALOG)
    bad_pin["routing"]["pin_policy"] = "rewrite"
    expect_error(bad_pin, "pin_policy")

    legacy_catalog = copy.deepcopy(CATALOG)
    del legacy_catalog["classification"]["implementation_markers"]
    del legacy_catalog["classification"]["bounded_scope_markers"]
    rd.check_config(legacy_catalog)
    assert rd.route({
        "task": "按 spec 第 3 节实现缓存层，只动 cache.py。\n验收：pytest 全绿。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, legacy_catalog)["target"]["id"] == "codex-terra-xhigh"

    assert rd.catalog_candidates(CATALOG, "codex-desktop") == []

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "routing.catalog.v2.json"), encoding="utf-8") as fh:
        disk_catalog = json.load(fh)
    assert rd.load_catalog(os.path.join(root, "config", "routing.catalog.v2.json"))["schema_version"] == 2
    # 生产 Codex 候选（2026-10 价格/能力更新，见 docs/research/2026-10-model-catalog-update.md）：
    # terra 更贵更弱已移出；L1 用 gpt-6-luna（半价、分数持平），L2/L3 同 slug 只动 effort。
    assert [(c["id"], c["model"], c["reasoning_effort"])
            for c in rd.catalog_candidates(disk_catalog, "codex-cli")] == [
        ("codex-luna-high", "gpt-6-luna", "high"),
        ("codex-sol-medium", "gpt-6.1-sol", "medium"),
        ("codex-sol-xhigh", "gpt-6.1-sol", "xhigh"),
    ], rd.catalog_candidates(disk_catalog, "codex-cli")
    # Claude Code 的 Agent 工具没有 effort 通道（2.1.289 schema：model 是 sonnet/opus/haiku/fable
    # 四值枚举，无 reasoning_effort 字段），所以 Claude 候选一律 effort=None，且只能写别名不能写完整 ID。
    assert [(c["id"], c["model"], c["reasoning_effort"])
            for c in rd.catalog_candidates(disk_catalog, "claude-code")] == [
        ("claude-haiku", "haiku", None),
        ("claude-sonnet", "sonnet", None),
        ("claude-opus", "opus", None),
    ], rd.catalog_candidates(disk_catalog, "claude-code")
    assert rd.host_auto_enabled(disk_catalog, "claude-code") is True
    assert rd.host_auto_enabled(disk_catalog, "codex-cli") is False
    # nudge: 生产目录只为 Task 15 达标的 Claude Code CLI 打开 dispatch_nudge（2026-09-13 用户确认）；Codex 保持关闭
    expected_nudge = {"claude-code": True, "codex-cli": False}
    assert set(disk_catalog["host_capabilities"]) == set(expected_nudge), disk_catalog["host_capabilities"]
    for host, want in expected_nudge.items():
        assert disk_catalog["host_capabilities"][host].get("dispatch_nudge") is want, (host, disk_catalog["host_capabilities"][host])
        assert rd.host_nudge_enabled(disk_catalog, host) is want, host
    try:
        rd.load_catalog(os.path.join(root, "config", "routing.default.json"))
    except rd.ConfigError as exc:
        assert "v1" in str(exc), str(exc)
    else:
        raise AssertionError("legacy config must not enter the v2 route path")

    simple = rd.route({
        "task": "只读检查配置，禁止修改任何文件。\n验收：报告所有键名。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-terra", "reasoning_effort": "xhigh", "pinned": False},
        "signals": {"side_effect": "read_only", "acceptance": "explicit",
                    "scope": "small", "decision_load": "mechanical"},
    }, CATALOG)
    assert simple["action"] == "lower", simple
    assert simple["target"] == {"id": "codex-luna-medium", "model": "gpt-5.6-luna",
                                "reasoning_effort": "medium"}, simple
    assert simple["confidence"] == "high", simple

    text_only_simple = rd.route({
        "task": "只读检查配置，禁止修改任何文件。\n验收：报告所有键名。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, CATALOG)
    assert text_only_simple["target"]["id"] == "codex-luna-medium", text_only_simple
    assert text_only_simple["confidence"] == "high", text_only_simple

    readonly_without_acceptance = rd.route({
        "task": "只读代码审查，禁止修改任何文件，只报告问题。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-terra", "reasoning_effort": "high", "pinned": True},
        "signals": {},
    }, CATALOG)
    assert readonly_without_acceptance["action"] == "lower", readonly_without_acceptance
    assert readonly_without_acceptance["target"] is None, readonly_without_acceptance
    assert readonly_without_acceptance["recommended"]["id"] == "codex-luna-medium", readonly_without_acceptance

    bounded_implementation = rd.route({
        "task": "按 spec 第 3 节实现缓存层，只动 cache.py。\n验收：pytest 全绿。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-terra", "reasoning_effort": "high", "pinned": True},
        "signals": {},
    }, CATALOG)
    assert bounded_implementation["action"] == "keep", bounded_implementation
    assert bounded_implementation["target"] is None, bounded_implementation
    assert bounded_implementation["recommended"]["id"] == "codex-terra-high", bounded_implementation

    inherited_unpinned = rd.route({
        "task": "改完后 git push 到 origin。\n验收：CI 绿。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, CATALOG)
    assert inherited_unpinned["action"] == "select", inherited_unpinned
    assert inherited_unpinned["target"]["id"] == "codex-terra-xhigh", inherited_unpinned

    out_of_catalog_pin = rd.route({
        "task": "改完后 git push 到 origin。\n验收：CI 绿。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-sol", "reasoning_effort": "high", "pinned": True},
        "signals": {},
    }, CATALOG)
    assert out_of_catalog_pin["action"] == "select", out_of_catalog_pin
    assert out_of_catalog_pin["target"] is None, out_of_catalog_pin
    assert out_of_catalog_pin["recommended"]["id"] == "codex-terra-xhigh", out_of_catalog_pin

    markdown_acceptance = rd.route({
        "task": "只读检查配置，禁止修改任何文件。\n- 验收：报告所有键名。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, CATALOG)
    assert markdown_acceptance["target"]["id"] == "codex-luna-medium", markdown_acceptance
    assert markdown_acceptance["signals"]["acceptance"] == "explicit", markdown_acceptance

    equal = rd.route({
        "task": "只读检查配置，禁止修改任何文件。\n验收：报告所有键名。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-luna", "reasoning_effort": "medium", "pinned": False},
        "signals": {"side_effect": "read_only", "acceptance": "explicit",
                    "scope": "small", "decision_load": "mechanical"},
    }, CATALOG)
    assert equal["action"] == "keep" and equal["target"]["id"] == "codex-luna-medium", equal

    complex_task = rd.route({
        "task": "比较两种缓存架构并权衡后选一个实现。\n验收：给出取舍理由。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-terra", "reasoning_effort": "high", "pinned": False},
        "signals": {"side_effect": "reversible_write", "acceptance": "explicit",
                    "scope": "cross_cutting", "decision_load": "tradeoff"},
    }, CATALOG)
    assert complex_task["action"] == "raise", complex_task
    assert complex_task["target"]["id"] == "codex-terra-xhigh", complex_task

    text_only_complex = rd.route({
        "task": "比较两种缓存架构并权衡后选一个实现。\n验收：给出取舍理由。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, CATALOG)
    assert text_only_complex["target"]["id"] == "codex-terra-xhigh", text_only_complex

    irreversible = rd.route({
        "task": "完成后 git push 到 origin。\n验收：远端分支可见。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, CATALOG)
    assert irreversible["target"]["id"] == "codex-terra-xhigh", irreversible
    assert irreversible["signals"]["side_effect"] == "external_or_irreversible", irreversible

    unknown = rd.route({
        "task": "处理这个问题。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, CATALOG)
    assert unknown["target"]["id"] == "codex-terra-xhigh", unknown
    assert unknown["confidence"] == "low", unknown

    pinned = rd.route({
        "task": "完成后 git push 到 origin。\n验收：远端分支可见。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-terra", "reasoning_effort": "high", "pinned": True},
        "signals": {"side_effect": "external_or_irreversible", "acceptance": "explicit",
                    "scope": "bounded", "decision_load": "tradeoff"},
    }, CATALOG)
    assert pinned["action"] == "raise", pinned
    assert pinned["target"] is None and pinned["recommended"]["id"] == "codex-terra-xhigh", pinned

    auto_catalog = copy.deepcopy(CATALOG)
    auto_catalog["mode"] = "auto"
    auto_pinned = rd.route({
        "task": "完成后 git push 到 origin。\n验收：远端分支可见。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-terra", "reasoning_effort": "high", "pinned": True},
        "signals": {"side_effect": "external_or_irreversible", "acceptance": "explicit",
                    "scope": "bounded", "decision_load": "tradeoff"},
    }, auto_catalog)
    assert auto_pinned["action"] == "pinned" and auto_pinned["target"] is None, auto_pinned

    no_context = rd.route({
        "task": "实现这个已定义的配置解析改动。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }, CATALOG)
    assert no_context["optional_context"] == {"status": "absent"}, no_context
    assert no_context["semantic_provider"] == {"status": "disabled"}, no_context
    assert no_context["target"]["id"] == "codex-terra-xhigh", no_context

    agent_skills_context = rd.route({
        "task": "实现这个已定义的配置解析改动。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
        "optional_context": {
            "source": "agent-skills", "schema_version": 1,
            "signals": {"side_effect": "reversible_write", "acceptance": "explicit",
                        "scope": "bounded", "decision_load": "implementation"},
        },
    }, CATALOG)
    assert agent_skills_context["optional_context"] == {"status": "accepted", "source": "agent-skills",
                                                         "schema_version": 1}, agent_skills_context
    assert agent_skills_context["target"]["id"] == "codex-terra-high", agent_skills_context
    assert agent_skills_context["confidence"] == "high", agent_skills_context

    malformed_context = rd.route({
        "task": "实现这个已定义的配置解析改动。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
        "optional_context": {"source": "agent-skills", "schema_version": 1, "signals": "not-an-object"},
    }, CATALOG)
    assert malformed_context["optional_context"]["status"] == "unavailable", malformed_context
    assert malformed_context["target"]["id"] == "codex-terra-xhigh", malformed_context

    foreign_context = rd.route({
        "task": "实现这个已定义的配置解析改动。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
        "optional_context": {"source": "other-plugin", "schema_version": 1, "signals": {}},
    }, CATALOG)
    assert foreign_context["optional_context"]["status"] == "unavailable", foreign_context
    assert foreign_context["target"]["id"] == "codex-terra-xhigh", foreign_context

    enabled_provider = copy.deepcopy(CATALOG)
    enabled_provider["semantic_provider"] = {"mode": "remote"}
    expect_error(enabled_provider, "semantic_provider")

    # Task 13：guard profile —— 生产目录默认 guard，且 guard 是合法的目录 mode
    assert disk_catalog["mode"] == "guard", disk_catalog
    guard_catalog = copy.deepcopy(CATALOG)
    guard_catalog["mode"] = "guard"
    rd.check_config(guard_catalog)

    print("route contract: OK")


if __name__ == "__main__":
    main()
