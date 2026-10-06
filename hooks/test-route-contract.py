#!/usr/bin/env python3
"""v2 路由契约的纯函数回归；不调用宿主 hook 或外部服务。"""
import copy
import hashlib
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
    # terra 更贵更弱已移出；L1 用 gpt-6-luna（半价、分数持平）。2026-10-05 Task 25：L2 也移到 Luna/high
    # （10/10 对 10/10，每任务约 1/14 成本，见 docs/research/2026-10-05-codex-l2-luna-experiment.md），
    # 所以 sol-medium 候选已删除，L2→L3 现在换 slug。
    assert [(c["id"], c["model"], c["reasoning_effort"])
            for c in rd.catalog_candidates(disk_catalog, "codex-cli")] == [
        ("codex-luna-high", "gpt-6-luna", "high"),
        ("codex-sol-xhigh", "gpt-6.1-sol", "xhigh"),
    ], rd.catalog_candidates(disk_catalog, "codex-cli")
    # catalog25：L2（implementation + bounded_change，明确验收）在 Codex 上路由到 luna；L3 仍是 sol/xhigh。
    codex_l2 = rd.route({
        "task": "实现 parse_duration，只动 util.py。\n验收：tests/test_util.py 全部通过。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {"side_effect": "reversible_write", "acceptance": "explicit",
                    "scope": "bounded", "decision_load": "implementation"},
    }, disk_catalog)
    assert codex_l2["requirements"] == ["implementation", "bounded_change"], codex_l2
    assert codex_l2["target"] == {"id": "codex-luna-high", "model": "gpt-6-luna",
                                  "reasoning_effort": "high"}, codex_l2
    codex_l3 = rd.route({
        "task": "比较两种迁移方案的风险、成本与回滚取舍。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {"side_effect": "reversible_write", "acceptance": "explicit",
                    "scope": "cross_cutting", "decision_load": "tradeoff"},
    }, disk_catalog)
    assert codex_l3["requirements"] == ["tradeoff", "cross_cutting"], codex_l3
    assert codex_l3["target"]["id"] == "codex-sol-xhigh", codex_l3
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

    # Task 16：上游档位标记 —— 解析、信封 v2、与 tier_source。每个降级路径各一条断言。
    READONLY = "只读检查配置，禁止修改任何文件。\n验收：报告所有键名。"        # 推断 L1
    BOUNDED = "按 spec 第 3 节实现缓存层，只动 cache.py。\n验收：pytest 全绿。"   # 推断 L2

    def tier_route(task, optional_context=None):
        request = {"task": task, "host": "codex-cli", "requested": {"pinned": False}, "signals": {}}
        if optional_context is not None:
            request["optional_context"] = optional_context
        return rd.route(request, CATALOG)

    def envelope(version, tier=None):
        env = {"source": "agent-skills", "schema_version": version,
               "signals": {"side_effect": "read_only", "acceptance": "explicit",
                           "scope": "small", "decision_load": "mechanical"}}
        if tier is not None:
            env["tier"] = tier
        return env

    def marker_error(task):
        parsed = rd.parse_tier_marker(task)
        return (parsed["status"], parsed.get("error"))

    baseline = tier_route(READONLY)
    assert baseline["tier_source"] == "inferred" and baseline["requirements"] == ["mechanical", "read_only"], baseline

    raised = tier_route(READONLY + "\n<!-- tier-guard: tier=L2 -->")
    assert raised["tier_source"] == "upstream", raised
    assert raised["requirements"] == ["implementation", "bounded_change"], raised
    assert raised["target"]["id"] == "codex-terra-high", raised
    assert raised["upstream_tier"] == {"status": "accepted", "source": "marker", "tier": "L2",
                                       "reason_present": False}, raised

    same_tier = tier_route(BOUNDED + "\n<!-- tier-guard: tier=L2 -->")
    assert same_tier["tier_source"] == "upstream", same_tier
    assert same_tier["requirements"] == ["implementation", "bounded_change"], same_tier
    assert same_tier["upstream_tier"]["status"] == "accepted", same_tier

    lower_tier = tier_route(BOUNDED + "\n<!-- tier-guard: tier=L1 -->")  # Task 17：无 floor 时 tier 可低于推断
    assert lower_tier["tier_source"] == "upstream", lower_tier
    assert lower_tier["requirements"] == ["mechanical", "read_only"], lower_tier
    assert lower_tier["target"]["id"] == "codex-luna-medium", lower_tier
    assert "tier_conflict" not in lower_tier, lower_tier

    absent = tier_route(READONLY)
    assert absent["upstream_tier"] == {"status": "absent"}, absent

    assert marker_error(READONLY + "\n<!-- tier-guard: tier=L1 -->\n<!-- tier-guard: tier=L2 -->") \
        == ("unavailable", "multiple-markers")
    assert marker_error("先做这件事 <!-- tier-guard: tier=L2 -->") == ("unavailable", "not-own-line")
    assert marker_error("<!-- tier-guard: tier=L2 --> 然后做这件事") == ("unavailable", "not-own-line")
    assert marker_error("\n   <!-- tier-guard: tier=L2 -->   \n")[0] == "accepted"  # 前后允许空白
    assert marker_error("<!-- tier-guard: tier=l2 -->") == ("unavailable", "bad-tier")
    assert marker_error("<!-- tier-guard: tier=L4 -->") == ("unavailable", "bad-tier")
    assert marker_error("<!-- tier-guard: tier= -->") == ("unavailable", "bad-tier")
    assert marker_error("<!-- tier-guard: tier=L1 failures=-1 -->") == ("unavailable", "bad-failures")
    assert marker_error("<!-- tier-guard: tier=L1 failures=x -->") == ("unavailable", "bad-failures")
    assert marker_error("<!-- tier-guard: tier=L1 failures=1.5 -->") == ("unavailable", "bad-failures")
    assert marker_error("<!-- tier-guard: tier=L1 color=red -->") == ("unavailable", "bad-syntax")
    assert marker_error("<!-- tier-guard: failures=1 tier=L1 -->") == ("unavailable", "bad-syntax")
    assert marker_error("<!-- tier-guard: tier=L1 reason=a --> <!-- other -->") == ("unavailable", "bad-syntax")
    assert marker_error("<!-- tier-guard: -->") == ("unavailable", "bad-syntax")

    with_failures = rd.parse_tier_marker("<!-- tier-guard: tier=L1 failures=2 -->")
    assert with_failures["failures"] == 2 and with_failures["tier"] == "L1", with_failures
    assert "failures" not in rd.parse_tier_marker("<!-- tier-guard: tier=L1 -->")
    assert rd.parse_tier_marker("<!-- tier-guard: tier=L1 failures=0 -->")["failures"] == 0
    # Phase 9 D3：写在 reason 之后的 failures 会被 reason 吃掉；与其悄悄丢掉（错过收回），不如整个标记判非法
    assert marker_error("<!-- tier-guard: tier=L2 reason=a failures=2 -->") == ("unavailable", "failures-in-reason")
    assert marker_error("<!-- tier-guard: tier=L2 reason=上次 failures=1 -->") == ("unavailable", "failures-in-reason")
    assert marker_error("<!-- tier-guard: tier=L2 reason=no failures yet -->")[0] == "accepted"
    assert marker_error("<!-- tier-guard: tier=L2 failures=1 reason=retry -->")[0] == "accepted"

    # Phase 9 D2：只读标记与实现标记同现时不按只读处理（用生产目录的词表复现评审给出的两句）
    prod = rd.load_catalog()
    for mixed in ("先只读代码库了解结构，然后实现缓存层并修改 cache.py。",
                  "Do a read-only review first, then implement the fix in auth.py."):
        sig = rd._text_signals(mixed, prod)
        assert sig["side_effect"] != "read_only" and sig["decision_load"] == "unknown", (mixed, sig)
        routed = rd.route({"task": mixed, "host": "claude-code", "requested": {"pinned": False}, "signals": {}}, prod)
        assert routed["requirements"] != ["mechanical", "read_only"], (mixed, routed)
    pure = rd._text_signals("只读审查配置，禁止修改任何文件。", prod)
    assert pure["side_effect"] == "read_only" and pure["decision_load"] == "mechanical", pure

    SECRET_REASON = "按 spec 第3节实现 secret-reason-9f3a"
    with_reason = tier_route(READONLY + f"\n<!-- tier-guard: tier=L2 failures=1 reason={SECRET_REASON} -->")
    assert with_reason["upstream_tier"]["reason_present"] is True, with_reason
    assert with_reason["upstream_tier"]["reason_sha256"] == hashlib.sha256(SECRET_REASON.encode("utf-8")).hexdigest(), with_reason
    assert with_reason["upstream_tier"]["failures"] == 1, with_reason
    assert "secret-reason-9f3a" not in json.dumps(with_reason, ensure_ascii=False), with_reason
    assert "reason_sha256" not in rd.parse_tier_marker("<!-- tier-guard: tier=L2 -->")

    env_v2 = tier_route(READONLY, envelope(2, "L2"))
    assert env_v2["optional_context"] == {"status": "accepted", "source": "agent-skills", "schema_version": 2}, env_v2
    assert env_v2["tier_source"] == "upstream" and env_v2["requirements"] == ["implementation", "bounded_change"], env_v2
    assert env_v2["upstream_tier"]["source"] == "envelope", env_v2

    env_v2_no_tier = tier_route(READONLY, envelope(2))
    assert env_v2_no_tier["optional_context"]["status"] == "accepted", env_v2_no_tier
    assert env_v2_no_tier["tier_source"] == "inferred", env_v2_no_tier

    for bad_tier in ("l2", "L4", None, 2):
        env_bad = envelope(2)
        env_bad["tier"] = bad_tier
        bad_route = tier_route(READONLY, env_bad)
        assert bad_route["optional_context"] == {"status": "unavailable", "reason": "tier-value"}, bad_route
        assert bad_route["tier_source"] == "inferred" and bad_route["fallback"] is None, bad_route

    env_v1 = tier_route(READONLY, envelope(1))
    assert env_v1["optional_context"] == {"status": "accepted", "source": "agent-skills", "schema_version": 1}, env_v1
    assert env_v1["tier_source"] == "inferred", env_v1

    env_v1_tier = tier_route(READONLY, envelope(1, "L2"))  # v1 不允许 tier 字段
    assert env_v1_tier["optional_context"] == {"status": "unavailable", "reason": "envelope-fields"}, env_v1_tier
    assert env_v1_tier["tier_source"] == "inferred", env_v1_tier

    disagree = tier_route(READONLY + "\n<!-- tier-guard: tier=L3 -->", envelope(2, "L2"))
    assert disagree["upstream_tier"] == {"status": "unavailable", "error": "tier-sources-disagree"}, disagree
    assert disagree["tier_source"] == "inferred" and disagree["requirements"] == ["mechanical", "read_only"], disagree

    agree = tier_route(READONLY + "\n<!-- tier-guard: tier=L2 -->", envelope(2, "L2"))
    assert agree["upstream_tier"]["status"] == "accepted" and agree["upstream_tier"]["source"] == "marker+envelope", agree
    assert agree["tier_source"] == "upstream", agree

    for degraded in (
        tier_route(READONLY + "\n<!-- tier-guard: tier=L1 -->\n<!-- tier-guard: tier=L1 -->"),
        tier_route(READONLY + " <!-- tier-guard: tier=L2 -->"),
        tier_route(READONLY + "\n<!-- tier-guard: tier=L9 -->"),
        tier_route(READONLY + "\n<!-- tier-guard: tier=L2 failures=x -->"),
        tier_route(READONLY + "\n<!-- tier-guard: tier=L2 -->", envelope(2, "L1")),
        tier_route(READONLY, envelope(2, "L9")),
    ):
        assert degraded["fallback"] is None and degraded["tier_source"] == "inferred", degraded
        assert degraded["action"] != "pass" and degraded["target"]["id"] == "codex-luna-medium", degraded

    bad_marker_good_envelope = tier_route(READONLY + "\n<!-- tier-guard: tier=L9 -->", envelope(2, "L2"))
    assert bad_marker_good_envelope["upstream_tier"] == {"status": "unavailable", "error": "bad-tier"}, bad_marker_good_envelope
    assert bad_marker_good_envelope["tier_source"] == "inferred", bad_marker_good_envelope
    assert bad_marker_good_envelope["fallback"] is None, bad_marker_good_envelope

    # ── Task 17：pin > floor > tier > 推断 ──
    IRREV = "完成后 git push 到 origin。\n验收：远端分支可见。"   # 命中不可逆 floor
    UNKNOWN = "处理这个问题。"                                    # 全 unknown：低置信保守档，不是 floor（D2）
    L1_MARK, L3_MARK = "\n<!-- tier-guard: tier=L1 -->", "\n<!-- tier-guard: tier=L3 -->"

    def tier_route_signals(task, signals, pinned=False, cfg=CATALOG):
        requested = {"model": "gpt-5.6-terra", "reasoning_effort": "high", "pinned": True} if pinned else {"pinned": False}
        return rd.route({"task": task, "host": "codex-cli", "requested": requested, "signals": signals}, cfg)

    forged = tier_route(IRREV + L1_MARK)  # 伪造：不可逆任务写 tier=L1
    assert forged["target"]["id"] == "codex-terra-xhigh", forged
    assert forged["tier_conflict"] == {"upstream": "L1", "floor": "L3"}, forged
    assert forged["tier_source"] == "floor", forged
    assert forged["requirements"] == ["tradeoff", "cross_cutting"], forged

    irrev_plain = tier_route(IRREV)
    assert "tier_conflict" not in irrev_plain, irrev_plain
    assert irrev_plain["tier_source"] == "floor", irrev_plain

    l3_on_readonly = tier_route(READONLY + L3_MARK)
    assert l3_on_readonly["target"]["id"] == "codex-terra-xhigh", l3_on_readonly
    assert l3_on_readonly["tier_source"] == "upstream" and "tier_conflict" not in l3_on_readonly, l3_on_readonly

    l3_on_irrev = tier_route(IRREV + L3_MARK)
    assert l3_on_irrev["tier_source"] == "upstream" and "tier_conflict" not in l3_on_irrev, l3_on_irrev
    assert l3_on_irrev["target"]["id"] == "codex-terra-xhigh", l3_on_irrev

    unknown_plain = tier_route(UNKNOWN)
    assert unknown_plain["confidence"] == "low" and unknown_plain["tier_source"] == "inferred", unknown_plain
    d2 = tier_route(UNKNOWN + L1_MARK)  # D2：合法上游 tier 可低于信息不足的保守档
    assert d2["target"]["id"] == "codex-luna-medium", d2
    assert d2["tier_source"] == "upstream" and "tier_conflict" not in d2, d2
    assert d2["confidence"] == "low" and d2["fallback"] is None, d2

    for danger in ({"side_effect": "external_or_irreversible"}, {"acceptance": "missing_or_ambiguous"},
                   {"scope": "cross_cutting"}, {"decision_load": "tradeoff"}):
        name = next(iter(danger))
        with_marker = tier_route_signals(UNKNOWN + L1_MARK, danger)
        assert with_marker["tier_conflict"] == {"upstream": "L1", "floor": "L3"}, (name, with_marker)
        assert with_marker["tier_source"] == "floor" and with_marker["target"]["id"] == "codex-terra-xhigh", (name, with_marker)
        without_marker = tier_route_signals(UNKNOWN, danger)
        assert without_marker["tier_source"] == "floor" and "tier_conflict" not in without_marker, (name, without_marker)

    env_ambiguous = envelope(2, "L1")
    env_ambiguous["signals"] = {"side_effect": "reversible_write", "acceptance": "missing_or_ambiguous",
                                "scope": "bounded", "decision_load": "implementation"}
    ambiguous_via_envelope = tier_route(UNKNOWN, env_ambiguous)
    assert ambiguous_via_envelope["tier_conflict"] == {"upstream": "L1", "floor": "L3"}, ambiguous_via_envelope
    assert ambiguous_via_envelope["tier_source"] == "floor", ambiguous_via_envelope

    # 只读 + 小范围 + 机械由 _requirements 第一支接走（v1 只读豁免），验收缺失也不构成 floor
    readonly_exempt = tier_route_signals(READONLY, {"acceptance": "missing_or_ambiguous"})
    assert readonly_exempt["requirements"] == ["mechanical", "read_only"], readonly_exempt
    assert readonly_exempt["tier_source"] == "inferred", readonly_exempt

    for marker in ("", L1_MARK):  # pin：有无标记都报 pin，且仍照常算 recommended
        for mode in ("audit", "guard"):
            cfg_ = copy.deepcopy(CATALOG)
            cfg_["mode"] = mode
            pinned_route = tier_route_signals(READONLY + marker, {}, pinned=True, cfg=cfg_)
            assert pinned_route["tier_source"] == "pin", (mode, marker, pinned_route)
            assert pinned_route["target"] is None and pinned_route["fallback"] is None, (mode, marker, pinned_route)
            assert pinned_route["recommended"]["id"] == "codex-luna-medium", (mode, marker, pinned_route)
            assert pinned_route["action"] == "lower", (mode, marker, pinned_route)
    pinned_conflict = tier_route_signals(IRREV + L1_MARK, {}, pinned=True)
    assert pinned_conflict["tier_source"] == "pin", pinned_conflict
    assert pinned_conflict["tier_conflict"] == {"upstream": "L1", "floor": "L3"}, pinned_conflict
    assert pinned_conflict["recommended"]["id"] == "codex-terra-xhigh" and pinned_conflict["target"] is None, pinned_conflict
    auto_cfg = copy.deepcopy(CATALOG)
    auto_cfg["mode"] = "auto"
    assert tier_route_signals(IRREV + L1_MARK, {}, pinned=True, cfg=auto_cfg)["action"] == "pinned"

    assert tier_route(READONLY)["tier_source"] == "inferred"
    assert tier_route(BOUNDED)["tier_source"] == "inferred"

    # 记录冲突不改动作语义：除 requirements 之外，与「无标记」的同一请求逐项一致，且不 deny / 不 fallback
    assert forged["fallback"] is None and forged["action"] in ("select", "raise", "lower", "keep"), forged
    for field in ("action", "target", "recommended", "requirements", "confidence", "fallback"):
        assert forged[field] == irrev_plain[field], (field, forged, irrev_plain)

    # ── Task 19：失败计数 → 升档（L1→L2）与收回记录（L2 ≥ 2 次） ──
    def fmark(tier, failures=None, reason=None):
        body = f"tier={tier}" + (f" failures={failures}" if failures is not None else "") \
            + (f" reason={reason}" if reason is not None else "")
        return f"\n<!-- tier-guard: {body} -->"

    esc = tier_route(READONLY + fmark("L1", 1))
    assert esc["target"]["id"] == "codex-terra-high", esc
    assert esc["escalation"] == {"from": "L1", "to": "L2", "consecutive_failures": 1}, esc
    assert esc["tier_source"] == "upstream" and "tier_conflict" not in esc and "reclaim" not in esc, esc

    assert "escalation" not in tier_route(READONLY + fmark("L1", 0))
    assert tier_route(READONLY + fmark("L1", 0))["target"]["id"] == "codex-luna-medium"
    assert "escalation" not in tier_route(READONLY + fmark("L1"))
    assert "escalation" not in tier_route(READONLY, envelope(2, "L1"))  # 信封不携带失败计数

    esc_floor = tier_route(IRREV + fmark("L1", 1))
    assert esc_floor["target"]["id"] == "codex-terra-xhigh", esc_floor
    assert esc_floor["escalation"] == {"from": "L1", "to": "L3", "consecutive_failures": 1}, esc_floor
    assert esc_floor["tier_conflict"] == {"upstream": "L1", "floor": "L3"}, esc_floor
    assert esc_floor["tier_source"] == "floor", esc_floor

    l2_one = tier_route(BOUNDED + fmark("L2", 1))
    assert "escalation" not in l2_one and "reclaim" not in l2_one, l2_one
    l2_zero = tier_route(BOUNDED + fmark("L2", 0))
    assert "escalation" not in l2_zero and "reclaim" not in l2_zero, l2_zero

    l2_two = tier_route(BOUNDED + fmark("L2", 2))
    assert l2_two["reclaim"] == {"tier": "L2", "consecutive_failures": 2}, l2_two
    assert "escalation" not in l2_two, l2_two
    for field in ("action", "target", "recommended", "requirements", "confidence", "tier_source", "fallback"):
        assert l2_two[field] == l2_one[field], (field, l2_two, l2_one)
    assert tier_route(BOUNDED + fmark("L2", 5))["reclaim"] == {"tier": "L2", "consecutive_failures": 5}
    assert tier_route(IRREV + fmark("L2", 2))["reclaim"] == {"tier": "L2", "consecutive_failures": 2}  # 以声明档为准
    assert "reclaim" not in tier_route(READONLY + fmark("L1", 3))

    l3_many = tier_route(READONLY + fmark("L3", 3))
    assert "escalation" not in l3_many and "reclaim" not in l3_many, l3_many

    pinned_esc = tier_route_signals(READONLY + fmark("L1", 1), {}, pinned=True)
    assert pinned_esc["escalation"] == {"from": "L1", "to": "L2", "consecutive_failures": 1}, pinned_esc
    assert pinned_esc["tier_source"] == "pin" and pinned_esc["target"] is None, pinned_esc
    pinned_reclaim = tier_route_signals(BOUNDED + fmark("L2", 2), {}, pinned=True)
    assert pinned_reclaim["reclaim"] == {"tier": "L2", "consecutive_failures": 2} and pinned_reclaim["tier_source"] == "pin", pinned_reclaim

    esc_secret = tier_route(READONLY + fmark("L1", 1, "secret-reason-19b7"))
    assert "secret-reason-19b7" not in json.dumps(esc_secret, ensure_ascii=False), esc_secret
    assert esc_secret["fallback"] is None and "escalation" in esc_secret, esc_secret
    assert esc_floor["fallback"] is None and l2_two["fallback"] is None

    # 单调性：任何已接受的 tier × failures × 是否命中 floor，有效档都不低于声明档与 floor
    for task, floored in ((READONLY, False), (IRREV, True)):
        for tier in ("L1", "L2", "L3"):
            for failures in (0, 1, 2, 7):
                decision = tier_route(task + fmark(tier, failures))
                assert decision["fallback"] is None, decision
                got = next(t for t in ("L1", "L2", "L3") if rd.TIER_REQUIREMENTS[t] == decision["requirements"])
                assert got >= tier and (not floored or got == "L3"), (task, tier, failures, decision)

    print("route contract: OK")


if __name__ == "__main__":
    main()
