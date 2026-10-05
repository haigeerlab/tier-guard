#!/usr/bin/env python3
"""tier-guard 判据的唯一一份实现。

被三方调用：Claude 薄壳、Codex 薄壳、/tier-report。**任何一方内联重写判据，
表现都是一条关不掉的假警报。** 改这里必须跑 --selftest 和两套薄壳的断言。

默认运行的是 v2 `route()`：按任务需求筛选候选、选择最低成本合格配置，显式 pin 不改写，未知
输入保守处理。v1 `decide()` 与 T0/T1/T2/floor 规则只保留为显式 `routing.default.json` 兼容层，
用于读取历史日志与迁移测试，不是产品默认策略。

共同约束：
  - 只输出决策，不输出宿主编码：updatedInput 怎么写是薄壳的事
    （Codex 要求 updatedInput 必须配 permissionDecision:"allow"，Claude 没这条）。
  - 纯函数。守卫自己不能崩：任何异常 → action=pass，fallback 里写清是哪条路径。

用法:
  python3 hooks/route_decide.py --selftest
  python3 hooks/route_decide.py [--config PATH] [--ctx JSON] < payload.json
  python3 hooks/route_decide.py --task [--ctx JSON] < 任务文本     # 纯文本当 prompt
    以下 ctx 与 `decide()` 输入是 v1 兼容接口：mode / executor(claude|codex) / agent_model / session_model /
              requested_tier / codex_model / codex_effort / consecutive_failures
    codex_model + codex_effort: 实际要派的 -m / effort，与某一档完全一致才认得出起点
    agent_model: 调用方解析 agent 文件得到的 frontmatter model；
                 文件里没有 model: → null；没解析 → 不传（R2 不判）
"""
import copy
import hashlib
import json
import os
import re
import sys

TIERS = ("T0", "T1", "T2")
MODES = ("off", "dry-run", "auto")
ROUTING_PROFILES = ("off", "audit", "guard", "auto")
EXECUTORS = ("claude", "codex")
# OpenAI 自己定义的单调序列 —— 升档只踩这根有一手依据的杠杆
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
SENTENCE_ENDS = "。！？；!?;\n"
DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "config", "routing.default.json")
DEFAULT_CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "config", "routing.catalog.v2.json")
OPTIONAL_CLASSIFICATION_FIELDS = ("implementation_markers", "bounded_scope_markers")
# Codex 当前在 native collaboration.spawn_agent 的 hook 边界传递这类宿主包装令牌，
# 而非原始子任务文字。只记录“不可见”，绝不尝试识别其内容或解码。
OPAQUE_TASK_TOKEN_RE = re.compile(r"^gAAAA[A-Za-z0-9_-]{32,}={0,2}$")


class ConfigError(ValueError):
    pass


def task_visibility(task):
    """返回 hook 能否直接读取任务语义；不透明令牌不可用于文本分类。"""
    if isinstance(task, str) and OPAQUE_TASK_TOKEN_RE.fullmatch(task):
        return "opaque_token"
    return "visible"


def rank(tier):
    return TIERS.index(tier)


def _check_catalog(cfg):
    """校验 v2 的模型能力目录；不在这里决定某个任务该用哪个候选。"""
    if cfg.get("schema_version") != 2:
        raise ConfigError("schema_version 必须是 2")
    if cfg.get("mode") not in ROUTING_PROFILES:
        raise ConfigError(f"mode 必须是 {ROUTING_PROFILES}")
    routing = cfg.get("routing")
    if not isinstance(routing, dict):
        raise ConfigError("routing 必须是对象")
    if routing.get("pin_policy") != "respect":
        raise ConfigError("pin_policy 目前只能是 respect")
    if routing.get("unknown_requirement") != "conservative":
        raise ConfigError("unknown_requirement 目前只能是 conservative")
    provider = cfg.get("semantic_provider", {"mode": "disabled"})
    if not isinstance(provider, dict) or provider.get("mode") != "disabled":
        raise ConfigError("semantic_provider 当前只能是 mode=disabled；外部 provider 需单独批准")
    classification = cfg.get("classification")
    if not isinstance(classification, dict):
        raise ConfigError("classification 必须是对象")
    for field in ("readonly_markers", "acceptance_markers", "irreversible_words", "tradeoff_words"):
        values = classification.get(field)
        if not isinstance(values, list) or not values or not all(isinstance(x, str) and x for x in values):
            raise ConfigError(f"classification.{field} 必须是非空字符串数组")
    for field in OPTIONAL_CLASSIFICATION_FIELDS:
        if field not in classification:
            continue
        values = classification[field]
        if not isinstance(values, list) or not values or not all(isinstance(x, str) and x for x in values):
            raise ConfigError(f"classification.{field} 必须是非空字符串数组")
    candidates = cfg.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ConfigError("candidates 必须是非空数组")
    seen = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ConfigError("candidate 必须是对象")
        ident = candidate.get("id")
        if not isinstance(ident, str) or not ident:
            raise ConfigError("candidate.id 必须是非空字符串")
        if ident in seen:
            raise ConfigError(f"candidate.id 重复：{ident}")
        seen.add(ident)
        for field in ("host", "model"):
            if not isinstance(candidate.get(field), str) or not candidate[field]:
                raise ConfigError(f"candidate.{field} 必须是非空字符串")
        effort = candidate.get("reasoning_effort")
        if effort is not None and effort not in EFFORTS:
            raise ConfigError(f"candidate.reasoning_effort {effort!r} 不合法")
        cost_rank = candidate.get("cost_rank")
        if isinstance(cost_rank, bool) or not isinstance(cost_rank, (int, float)) or cost_rank <= 0:
            raise ConfigError("candidate.cost_rank 必须是正数")
        if not isinstance(candidate.get("auto_eligible"), bool):
            raise ConfigError("candidate.auto_eligible 必须是布尔值")
        capabilities = candidate.get("capabilities")
        if not isinstance(capabilities, list) or not all(isinstance(x, str) and x for x in capabilities):
            raise ConfigError("candidate.capabilities 必须是字符串数组")
    host_capabilities = cfg.get("host_capabilities")
    hosts = {candidate["host"] for candidate in candidates}
    if not isinstance(host_capabilities, dict) or set(host_capabilities) != hosts:
        raise ConfigError("host_capabilities 必须恰好覆盖候选宿主")
    for host, capabilities in host_capabilities.items():
        if not isinstance(capabilities, dict) or not isinstance(capabilities.get("pre_dispatch_apply"), bool):
            raise ConfigError(f"host_capabilities.{host}.pre_dispatch_apply 必须是布尔值")
        if "dispatch_nudge" in capabilities and not isinstance(capabilities["dispatch_nudge"], bool):
            raise ConfigError(f"host_capabilities.{host}.dispatch_nudge 必须是布尔值")


def catalog_candidates(cfg, host):
    """返回一个宿主允许自动选择的候选，成本相同时按稳定 id 排序。"""
    _check_catalog(cfg)
    return sorted((c for c in cfg["candidates"] if c["host"] == host and c["auto_eligible"]),
                  key=lambda c: (c["cost_rank"], c["id"]))


def host_auto_enabled(cfg, host):
    """仅当该宿主已用真实派活证据验证可拦截，v2 auto 才允许实际改写参数。"""
    _check_catalog(cfg)
    return cfg["host_capabilities"].get(host, {}).get("pre_dispatch_apply", False)


def host_nudge_enabled(cfg, host):
    """仅当宿主已实测支持在 PreToolUse 注入提醒/deny，才允许输出主代理预路由提醒。"""
    _check_catalog(cfg)
    return cfg["host_capabilities"].get(host, {}).get("dispatch_nudge", False)


_SIGNALS = {
    "side_effect": {"read_only", "reversible_write", "external_or_irreversible", "unknown"},
    "acceptance": {"explicit", "missing_or_ambiguous", "unknown"},
    "scope": {"small", "bounded", "cross_cutting", "unknown"},
    "decision_load": {"mechanical", "implementation", "tradeoff", "unknown"},
}


def _text_signals(task, cfg):
    rules = cfg["classification"]
    low = task.lower()
    readonly = any(marker.lower() in low for marker in rules["readonly_markers"])
    irreversible = any(word.lower() in low for word in rules["irreversible_words"])
    tradeoff = any(word.lower() in low for word in rules["tradeoff_words"])
    implementation = any(marker.lower() in low for marker in rules.get("implementation_markers", ()))
    bounded = any(marker.lower() in low for marker in rules.get("bounded_scope_markers", ()))
    acceptance = any(line.lstrip(" \t-*#>").lower().startswith(
        tuple(marker.lower() for marker in rules["acceptance_markers"]))
        for line in task.splitlines())
    return {
        "side_effect": "external_or_irreversible" if irreversible else (
            "read_only" if readonly else ("reversible_write" if implementation and bounded else "unknown")),
        "acceptance": "explicit" if acceptance else "unknown",
        "scope": "cross_cutting" if tradeoff else ("small" if readonly else ("bounded" if bounded else "unknown")),
        "decision_load": "tradeoff" if tradeoff else (
            "mechanical" if readonly else ("implementation" if implementation else "unknown")),
    }


def _optional_context(request):
    """验证可选 agent-skills 信封；无效输入只降级为不可用，绝不使核心失败。

    返回 (signals, status, tier)。v1 信封字段严格为 {source, schema_version, signals}；v2 在其上
    只多允许一个可选 `tier`（L1/L2/L3）。tier 非法则整个信封按 unavailable 处理。"""
    raw = request.get("optional_context")
    if raw is None:
        return {}, {"status": "absent"}, None
    if not isinstance(raw, dict):
        return {}, {"status": "unavailable", "reason": "envelope-not-object"}, None
    version = raw.get("schema_version")
    base_fields = {"source", "schema_version", "signals"}
    allowed_fields = base_fields | {"tier"} if version == 2 else base_fields
    if not base_fields.issubset(raw) or not set(raw).issubset(allowed_fields):
        return {}, {"status": "unavailable", "reason": "envelope-fields"}, None
    if raw.get("source") != "agent-skills" or version not in (1, 2):
        return {}, {"status": "unavailable", "reason": "source-or-version"}, None
    signals = raw.get("signals")
    if not isinstance(signals, dict) or set(signals) != set(_SIGNALS):
        return {}, {"status": "unavailable", "reason": "signals-fields"}, None
    for name, allowed in _SIGNALS.items():
        if signals.get(name) not in allowed:
            return {}, {"status": "unavailable", "reason": "signals-values"}, None
    tier = raw.get("tier")
    if "tier" in raw and tier not in UPSTREAM_TIERS:
        return {}, {"status": "unavailable", "reason": "tier-value"}, None
    return dict(signals), {"status": "accepted", "source": "agent-skills", "schema_version": version}, tier


# 上游档位词汇 → 已有能力标签（spec「上游档位信号」）；与 _requirements 的三条出口一一对应。
UPSTREAM_TIERS = ("L1", "L2", "L3")
TIER_REQUIREMENTS = {
    "L1": ["mechanical", "read_only"],
    "L2": ["implementation", "bounded_change"],
    "L3": ["tradeoff", "cross_cutting"],
}
TIER_MARKER_PREFIX = "<!-- tier-guard:"
_TIER_MARKER_BODY_RE = re.compile(r"tier=(\S*)(?:\s+failures=(\S*))?(?:\s+reason=(.*))?")


def parse_tier_marker(task):
    """解析任务文本里的上游档位标记。任何不满足都降级为 unavailable，绝不抛异常、绝不返回 reason 原文。"""
    count = task.count(TIER_MARKER_PREFIX)
    if count == 0:
        return {"status": "absent"}
    if count >= 2:
        return {"status": "unavailable", "error": "multiple-markers"}
    line = next(ln for ln in task.splitlines() if TIER_MARKER_PREFIX in ln).strip()
    if not (line.startswith(TIER_MARKER_PREFIX) and line.endswith("-->")):
        return {"status": "unavailable", "error": "not-own-line"}
    inner = line[len(TIER_MARKER_PREFIX):-3].strip()
    match = _TIER_MARKER_BODY_RE.fullmatch(inner)
    if "-->" in inner or match is None:
        return {"status": "unavailable", "error": "bad-syntax"}
    tier, failures, reason = match.groups()
    if tier not in UPSTREAM_TIERS:
        return {"status": "unavailable", "error": "bad-tier"}
    if failures is not None and re.fullmatch(r"[0-9]+", failures) is None:
        return {"status": "unavailable", "error": "bad-failures"}
    reason = reason.strip() if reason is not None else ""
    result = {"status": "accepted", "source": "marker", "tier": tier, "reason_present": bool(reason)}
    if failures is not None:
        result["failures"] = int(failures)
    if reason:
        result["reason_sha256"] = hashlib.sha256(reason.encode("utf-8")).hexdigest()
    return result


def _upstream_tier(task, envelope_tier):
    """合并标记与信封里的 tier：两者都给且不一致 → unavailable；标记非法 → 整体 unavailable（保守）。"""
    marker = parse_tier_marker(task)
    if marker["status"] == "unavailable" or envelope_tier is None:
        return marker
    if marker["status"] == "absent":
        return {"status": "accepted", "source": "envelope", "tier": envelope_tier, "reason_present": False}
    if marker["tier"] != envelope_tier:
        return {"status": "unavailable", "error": "tier-sources-disagree"}
    return dict(marker, source="marker+envelope")


def _route_signals(request, cfg, task, context_signals=None):
    raw = request.get("signals") or {}
    if not isinstance(raw, dict):
        raise ValueError("signals 必须是对象")
    derived = _text_signals(task, cfg)
    values = dict(derived)
    for name, value in (context_signals or {}).items():
        if value != "unknown":
            values[name] = value
    for name, allowed in _SIGNALS.items():
        value = raw.get(name, "unknown")
        if value not in allowed:
            raise ValueError(f"signals.{name} 不合法：{value!r}")
        if value != "unknown":
            values[name] = value
    return values


def _danger_signals(signals):
    """不可逆 / 歧义 / 跨模块 / 取舍：floor 的唯一判据，_requirements 与 _floor_hit 共用，只写这一处。"""
    return (signals["side_effect"] == "external_or_irreversible"
            or signals["acceptance"] == "missing_or_ambiguous"
            or signals["scope"] == "cross_cutting" or signals["decision_load"] == "tradeoff")


def _requirements(signals):
    """从任务需求而非请求起点导出候选能力；未知一律走保守分支。"""
    if (signals["side_effect"] == "read_only" and signals["scope"] == "small"
            and signals["decision_load"] == "mechanical"):
        return ["mechanical", "read_only"], "high" if signals["acceptance"] == "explicit" else "medium"
    if (signals["side_effect"] == "reversible_write" and signals["acceptance"] == "explicit"
            and signals["scope"] == "bounded" and signals["decision_load"] == "implementation"):
        return ["implementation", "bounded_change"], "high"
    if _danger_signals(signals):
        return ["tradeoff", "cross_cutting"], "medium"
    return ["tradeoff", "cross_cutting"], "low"


# v2 里唯一可能的 floor 档。信息不足（全 unknown）的保守档不是 floor（D2）。
FLOOR_TIER = "L3"


def _floor_hit(signals, required):
    """危险信号命中且推断确实落在 L3。只读 + 小范围 + 机械的任务由 _requirements 第一支先接走（沿用
    v1 的只读豁免），此时即便验收缺失也不构成 floor。"""
    return _danger_signals(signals) and required == TIER_REQUIREMENTS[FLOOR_TIER]


def _candidate_view(candidate):
    return {"id": candidate["id"], "model": candidate["model"],
            "reasoning_effort": candidate["reasoning_effort"]}


def _requested_candidate(candidates, requested):
    return next((c for c in candidates
                 if c["model"] == requested.get("model")
                 and c["reasoning_effort"] == requested.get("reasoning_effort")), None)


def _comparison_action(recommended, actual):
    """建议候选相对本次请求的方向；请求不在目录时只能报告 select。"""
    if actual is None:
        return "select"
    if recommended["cost_rank"] < actual["cost_rank"]:
        return "lower"
    if recommended["cost_rank"] > actual["cost_rank"]:
        return "raise"
    return "keep"


def _route(request, cfg):
    _check_catalog(cfg)
    if not isinstance(request, dict):
        raise ValueError("RouteRequest 必须是对象")
    task = request.get("task")
    host = request.get("host")
    requested = request.get("requested") or {}
    if not isinstance(task, str) or not task.strip():
        raise ValueError("RouteRequest.task 必须是非空字符串")
    if not isinstance(host, str) or not host:
        raise ValueError("RouteRequest.host 必须是非空字符串")
    if not isinstance(requested, dict) or not isinstance(requested.get("pinned", False), bool):
        raise ValueError("RouteRequest.requested.pinned 必须是布尔值")
    context_signals, context_status, envelope_tier = _optional_context(request)
    upstream = _upstream_tier(task, envelope_tier)
    signals = _route_signals(request, cfg, task, context_signals)
    required, confidence = _requirements(signals)
    # 优先级 pin > floor > tier > 推断：上游 tier 可低于推断（含 D2 的信息不足保守档），
    # 但不能压到 floor 之下；低于 floor 时按 floor 取并记录冲突。
    floor = _floor_hit(signals, required)
    tier_source = "floor" if floor else "inferred"
    tier_conflict = None
    if upstream["status"] == "accepted":
        if floor and UPSTREAM_TIERS.index(upstream["tier"]) < UPSTREAM_TIERS.index(FLOOR_TIER):
            tier_conflict = {"upstream": upstream["tier"], "floor": FLOOR_TIER}
        else:
            required = list(TIER_REQUIREMENTS[upstream["tier"]])
            tier_source = "upstream"
    if requested.get("pinned") is True:
        tier_source = "pin"
    candidates = catalog_candidates(cfg, host)
    eligible = [c for c in candidates if set(required).issubset(c["capabilities"])]
    base = {"profile": cfg["mode"], "host": host, "requirements": required,
            "confidence": confidence, "signals": signals, "requested": requested,
            "optional_context": context_status, "semantic_provider": {"status": "disabled"},
            "upstream_tier": upstream, "tier_source": tier_source}
    if tier_conflict is not None:
        base["tier_conflict"] = tier_conflict
    if not eligible:
        return dict(base, action="unsupported", target=None, recommended=None,
                    fallback="没有满足需求的自动候选")
    recommended = eligible[0]
    actual = _requested_candidate(candidates, requested)
    action = _comparison_action(recommended, actual)
    if requested.get("pinned", False):
        # audit/guard 要能审计“若未 pin 会往哪边路由”；target 仍为空，薄壳无从改写。
        if cfg["mode"] in ("audit", "guard"):
            return dict(base, action=action, target=None, recommended=_candidate_view(recommended), fallback=None)
        return dict(base, action="pinned", target=None, recommended=_candidate_view(recommended), fallback=None)
    return dict(base, action=action, target=_candidate_view(recommended),
                recommended=_candidate_view(recommended), fallback=None)


def route(request, cfg):
    """v2 纯路由入口；任何契约错误都显式返回不可应用的 fallback。"""
    try:
        return _route(request, cfg)
    except Exception as exc:
        return {"action": "pass", "target": None, "recommended": None,
                "confidence": "unknown", "fallback": f"{type(exc).__name__}: {exc}"}


NUDGE_REMIND_TEXT = "tier-guard：创建未 pin 的子代理前，请先按 tier-routing skill 判断本次子任务所需能力，并在派活参数中显式传入候选目录里最低成本合格的 model（Codex 另传 reasoning_effort）。显式参数视为 pin，不会被改写。"
NUDGE_DENY_TEXT = "tier-guard（auto）：本会话第一次未 pin 的派活已被拦下。请先加载 tier-routing skill，按本次子任务选择候选目录中最低成本合格的 model（Codex 另传 reasoning_effort），带上显式参数后重新派活；本会话之后不会再拦截。"


def catalog_summary(cfg, host):
    """把该宿主的候选目录（catalog_candidates 已按成本排序）压成一行摘要，供 nudge 文案附带 ——
    提醒/拦截原文本身不带候选信息，主代理容易凭记忆报出目录外的组合。没有候选时返回空串。"""
    candidates = catalog_candidates(cfg, host)
    if not candidates:
        return ""
    parts = []
    for c in candidates:
        target = c["model"]
        if c["reasoning_effort"] is not None:
            target += f" / {c['reasoning_effort']}"
        parts.append("+".join(c["capabilities"]) + f" → {target}")
    return (f"候选目录（{host}，按成本从低到高）：" + "；".join(parts) +
            "。信息不足、取舍、跨模块或不可逆动作一律选高能力候选，不要自行降档或使用目录外的组合。")


def nudge_text(action, summary=""):
    """把 nudge_decision 的 action 编码为具体文案；remind/deny 附带候选目录摘要（可为空），
    其余 action（none/deny 之外……）没有对应文案。"""
    base = {"remind": NUDGE_REMIND_TEXT, "deny": NUDGE_DENY_TEXT}.get(action)
    if base is None:
        return None
    return base + summary if summary else base


def nudge_decision(profile, pinned, host_gate, session_id, already_denied, summary=""):
    """主代理预路由提醒的纯判据。只产出 action/text，宿主编码（deny 要不要配
    permissionDecision 之类）留给薄壳；异常交给调用方按放行处理。"""
    if profile not in ROUTING_PROFILES:
        raise ValueError(f"未知 profile {profile!r}")
    if profile == "off":
        return {"action": "none", "text": None}
    if host_gate is not True:
        return {"action": "none", "text": None}
    if pinned is not False:
        # True（真 pin）或 None（插件 agent 判不出，比如 plugin:name）都不提醒。
        return {"action": "none", "text": None}
    if profile == "audit":
        return {"action": "remind", "text": nudge_text("remind", summary)}
    # profile in ("guard", "auto")：同一 session 第一次未 pin 派活 deny，之后只 remind。
    if isinstance(session_id, str) and session_id and already_denied is not True:
        return {"action": "deny", "text": nudge_text("deny", summary)}
    return {"action": "remind", "text": nudge_text("remind", summary)}


def check_config(cfg):
    """配置自身的不变量。v1 保留至迁移完成；v2 使用模型目录契约。"""
    if not isinstance(cfg, dict):
        raise ConfigError("配置必须是对象")
    if "schema_version" in cfg:
        return _check_catalog(cfg)
    # v1 兼容路径：Task 2 才替换其起点档与只升逻辑。
    tiers = cfg["tiers"]
    if sorted(tiers) != list(TIERS):
        raise ConfigError(f"tiers 必须恰好是 {TIERS}")
    never = cfg["never_auto"]
    for t in TIERS:
        cx = tiers[t]["codex"]
        if cx["model"] in never["codex_models"]:
            raise ConfigError(f"{t} 映射到了禁止自动选的 {cx['model']}")
        if cx["effort"] not in EFFORTS or cx["effort"] in never["codex_efforts"]:
            raise ConfigError(f"{t} 的 effort {cx['effort']!r} 不合法或禁止自动选")
    if tiers["T1"]["codex"]["model"] != tiers["T2"]["codex"]["model"]:
        raise ConfigError("T1→T2 升档只许动 effort，不许换 slug")
    efforts = [EFFORTS.index(tiers[t]["codex"]["effort"]) for t in TIERS]
    if efforts != sorted(efforts):
        raise ConfigError("Codex effort 必须随档位单调不降")
    if cfg["mode"] not in MODES:
        raise ConfigError(f"默认 mode {cfg['mode']!r} 不在 {MODES}")
    rules = cfg["floor_rules"]
    for key, field in (("R-IRREVERSIBLE", "words"), ("R-AMBIGUOUS", "ac_markers"),
                       ("R-TRADEOFF", "words")):
        if not rules[key][field]:
            raise ConfigError(f"{key}.{field} 为空 —— 空词表等于这条规则永不命中")


def _family_tier(name, cfg):
    low = name.lower()
    for fam, tier in cfg["claude_families"].items():
        if fam in low:
            return tier
    return None


def _start(ti, ctx, cfg, executor):
    """起点档 → (tier 或 None, 来源)。来源 unknown-model 表示不许碰。"""
    if executor == "codex":
        req = ctx.get("requested_tier")
        if req in TIERS:
            return req, "requested"
        flags = (ctx.get("codex_model"), ctx.get("codex_effort"))
        if flags == (None, None):
            return None, "inherit"          # 走 ~/.codex/config.toml 默认，档位未知
        for t in TIERS:
            cx = cfg["tiers"][t]["codex"]
            if flags == (cx["model"], cx["effort"]):
                return t, "flags"
        return None, "unknown-model"        # 表外组合（如 sol / 默认 medium），排不出强弱
    explicit = ti.get("model")
    if explicit:
        tier = _family_tier(str(explicit), cfg)
        return (tier, "model") if tier else (None, "unknown-model")
    agent_model = ctx.get("agent_model")
    if agent_model and agent_model != "inherit":
        tier = _family_tier(str(agent_model), cfg)
        return (tier, "agent") if tier else (None, "unknown-model")
    session = ctx.get("session_model")
    if session:
        tier = _family_tier(str(session), cfg)
        return (tier, "session") if tier else (None, "unknown-model")
    return None, "inherit"


def _is_mention(low, idx, verbs):
    """同一句里、动作词前面出现了「检查 / 有没有 …」→ 只是提到，不是要做。"""
    start = max(low.rfind(c, 0, idx) for c in SENTENCE_ENDS) + 1
    prefix = low[start:idx]
    return any(v.lower() in prefix for v in verbs)


def _irreversible(prompt, rule):
    low = prompt.lower()
    matches, mentions = [], []
    for w in rule["words"]:
        wl = w.lower()
        i = low.find(wl)
        while i != -1:
            matches.append(w)
            mentions.append(_is_mention(low, i, rule["mention_verbs"]))
            i = low.find(wl, i + 1)
    hit = bool(matches)
    return {"rule": "R-IRREVERSIBLE", "hit": hit, "effect": "lock-T2" if hit else "none",
            "matches": sorted(set(matches)),
            "suspected_false_positive": hit and all(mentions)}


def _ambiguous(prompt, rule):
    """没有验收行 → 锁 T2。只读任务豁免：SPEC 的 T0 行只要求「只读 · 无持久影响」，
    不要求验收行（2026-09-12 定，真实数据里 8/12 条是只读 Review）。
    只读声明用整句，不用单独的「只读」—— 那会误中「只读取配置然后实现 X」。"""
    markers = [m.lower() for m in rule["ac_markers"]]
    has_ac = any(line.lstrip(" \t-*#>").lower().startswith(tuple(markers))
                 for line in prompt.splitlines())
    low = prompt.lower()
    readonly = [m for m in rule.get("readonly_markers", []) if m.lower() in low]
    hit = not has_ac and not readonly
    return {"rule": "R-AMBIGUOUS", "hit": hit, "effect": "lock-T2" if hit else "none",
            "readonly_exempt": readonly}


def _tradeoff(prompt, rule):
    low = prompt.lower()
    matches = [w for w in rule["words"] if w.lower() in low]
    return {"rule": "R-TRADEOFF", "hit": bool(matches),
            "effect": "lock-T2" if matches else "none", "matches": matches}


def _decide(payload, cfg, ctx, d):
    check_config(cfg)
    d["mode"] = ctx.get("mode") or cfg["mode"]
    if d["mode"] not in MODES:
        raise ConfigError(f"未知 mode {d['mode']!r}")
    if d["executor"] not in EXECUTORS:
        raise ConfigError(f"未知 executor {d['executor']!r}")
    if d["mode"] == "off":
        d["why"].append({"rule": "MODE", "hit": True, "effect": "off：不判"})
        return
    if not isinstance(payload, dict):
        raise ValueError("payload 不是 JSON 对象")
    if d["executor"] == "claude" and payload.get("tool_name") != "Agent":
        d["why"].append({"rule": "SCOPE", "hit": True, "effect": "不是 Agent 调用，不判"})
        return
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        raise ValueError("payload 缺 tool_input")
    if ti.get("subagent_type") == "fork":
        d["why"].append({"rule": "SCOPE", "hit": True, "effect": "fork 继承父模型，不判"})
        return
    prompt = ti.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("tool_input 缺 prompt")

    # ① 定档：floor 只能往上抬
    start, source = _start(ti, ctx, cfg, d["executor"])
    d["start_tier"] = start
    rules = cfg["floor_rules"]
    floors = [_irreversible(prompt, rules["R-IRREVERSIBLE"]),
              _ambiguous(prompt, rules["R-AMBIGUOUS"]),
              _tradeoff(prompt, rules["R-TRADEOFF"])]
    d["why"].extend(floors)
    locked = any(f["hit"] for f in floors)
    if locked:
        d["tier"] = "T2"
    else:
        d["tier"] = start

    if (d["executor"] == "claude" and not ti.get("model") and "agent_model" in ctx
            and ctx["agent_model"] in (None, "inherit")):
        d["why"].append({"rule": "R2", "hit": True,
                         "effect": "hint：agent 没钉 model 且调用未传，继承父模型，零节省"})

    if source == "unknown-model":
        d["why"].append({"rule": "START", "hit": True,
                         "effect": "起点是不认识的模型，排不出强弱，不动"})
        d["tier"] = None
        return

    # ② 收益门槛 / 防抖：只产出建议，撤不回 ① 的升档
    if locked and (start is None or rank(start) < rank("T2")):
        d["action"] = "raise"
    elif int(ctx.get("consecutive_failures") or 0) >= cfg["debounce"]["max_consecutive_failures"]:
        d["action"] = "defer"
    elif len(prompt.strip()) < cfg["benefit"]["min_prompt_chars"]:
        d["action"] = "local"

    # ③ 落参
    if d["tier"] is not None:
        target = cfg["tiers"][d["tier"]][d["executor"]]
        if d["executor"] == "codex":
            d["target_model"], d["target_reasoning_effort"] = target["model"], target["effort"]
        else:
            d["target_model"] = target


def decide(payload, cfg, ctx=None):
    ctx = ctx or {}
    d = {"tier": None, "start_tier": None, "action": "pass",
         "executor": ctx.get("executor", "claude"), "target_model": None,
         "target_reasoning_effort": None, "why": [], "mode": ctx.get("mode"), "fallback": None}
    try:
        _decide(payload, cfg, ctx, d)
    except Exception as e:  # 守卫自己不能崩：放行，并说清是哪条路径失败的
        d.update(tier=None, action="pass", target_model=None,
                 target_reasoning_effort=None, fallback=f"{type(e).__name__}: {e}")
    return d


def load_config(path=DEFAULT_CONFIG):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_config_with_fingerprint(path=DEFAULT_CONFIG):
    """读取一份配置并返回实际被解析内容的 SHA-256 指纹。"""
    with open(path, "rb") as fh:
        raw = fh.read()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def load_catalog(path=DEFAULT_CATALOG):
    """读取 v2 目录；旧 v1 配置只能继续走迁移期的旧 adapter，不能混入新路由。"""
    cfg = load_config(path)
    if not isinstance(cfg, dict) or "schema_version" not in cfg:
        raise ConfigError("v1 配置不能用于 v2 路由；请迁移到 schema_version=2 的模型目录")
    _check_catalog(cfg)
    return cfg


# ─────────────────────────────── selftest ───────────────────────────────

CONTRACT = """遇到以下任一情况，立即停止并把现状交回，不要自行决定：
① 测试改不红 / 构建坏了且没有显然修法
② 验收标准有歧义，或需要做规约没覆盖的决定
③ 需要做任何不可逆的事（push / 合并 / 删除 / 迁移 / 动密钥 / 建外部记录）
④ 你发现这活比派活时描述的复杂"""
# 升级触发（闸二）的观测口径：子代理最后一条回复引用了合同的某一条（①–④）并说了交回 / 停止。
# 只用于报表计数（标「疑似」），不参与定档。标记从合同文本本身取，合同改了这里跟着变。
CONTRACT_MARKS = tuple(line[0] for line in CONTRACT.splitlines()[1:])


def escalated(text):
    return (isinstance(text, str) and any(m in text for m in CONTRACT_MARKS)
            and ("交回" in text or "停止" in text))


PAD = "\n背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛，不含任何判据词。" * 3
AC = "\n验收：python3 -m pytest 全绿"


def _agent(prompt, model=None, subagent_type="executor", tool="Agent"):
    ti = {"description": "t", "prompt": prompt, "subagent_type": subagent_type}
    if model:
        ti["model"] = model
    return {"tool_name": tool, "tool_input": ti}


def _rule(d, name):
    return next((w for w in d["why"] if w["rule"] == name), None)


def selftest():
    cfg = load_config()
    ok, bad = [], []

    def case(name, cond):
        (ok if cond else bad).append(name)
        print(f"  {'✅' if cond else '❌'} {name}")

    def run(prompt, model=None, cfg_=None, **kw):
        tool = kw.pop("tool", "Agent")
        st = kw.pop("subagent_type", "executor")
        return decide(_agent(prompt, model, st, tool), cfg_ or cfg, kw)

    print("═══ route_decide --selftest ═══")
    case("默认配置满足全部不变量", check_config(cfg) is None)

    # R-IRREVERSIBLE
    d = run("改完后 git push 到 origin。" + AC + PAD, "sonnet")
    case("IRREVERSIBLE 正：动作词 + sonnet → 锁 T2 并 raise",
         d["tier"] == "T2" and d["action"] == "raise" and d["target_model"] == "opus")
    case("IRREVERSIBLE 正：真在做的动作不标疑似误报",
         _rule(d, "R-IRREVERSIBLE")["suspected_false_positive"] is False)
    d = run("改完后跑一遍测试。" + AC + PAD, "sonnet")
    case("IRREVERSIBLE 反：无动作词 + 有验收 → 保持 T1、不 raise",
         d["tier"] == "T1" and d["action"] == "pass" and not _rule(d, "R-IRREVERSIBLE")["hit"])
    d = run("改完后 git push 到 origin。" + AC + PAD, "opus")
    case("IRREVERSIBLE 反：动作词 + opus → 不算违规（不 raise）",
         d["tier"] == "T2" and d["action"] == "pass")
    d = run("drop table users 之后重建。" + AC + PAD, "sonnet")
    case("IRREVERSIBLE 正：大小写不敏感（drop table）", _rule(d, "R-IRREVERSIBLE")["hit"])
    d = run("检查有没有人写了 git push。" + AC + PAD, "sonnet")
    r = _rule(d, "R-IRREVERSIBLE")
    case("疑似误报：只是提到动作词 → 仍锁 T2 并 raise",
         d["tier"] == "T2" and d["action"] == "raise")
    case("疑似误报：打上 suspected_false_positive 标记", r["suspected_false_positive"] is True)
    d = run("检查一下测试。然后 git push。" + AC + PAD, "sonnet")
    case("疑似误报反：提到动词在前一句 → 不标", _rule(d, "R-IRREVERSIBLE")["suspected_false_positive"] is False)

    # R-AMBIGUOUS
    d = run("把函数 foo 改名为 bar。" + PAD, "sonnet")
    case("AMBIGUOUS 正：没有验收行 → 锁 T2 并 raise",
         _rule(d, "R-AMBIGUOUS")["hit"] and d["action"] == "raise")
    d = run("把函数 foo 改名为 bar。\n- **验收**：grep 不到 foo" + PAD, "sonnet")
    case("AMBIGUOUS 反：markdown 列表里的验收行也算", not _rule(d, "R-AMBIGUOUS")["hit"])
    d = run("把函数 foo 改名为 bar。\n" + CONTRACT + PAD, "sonnet")
    case("AMBIGUOUS 正：合同里的「验收标准有歧义」不算验收行", _rule(d, "R-AMBIGUOUS")["hit"])
    d = run("把函数 foo 改名为 bar。" + AC + "\n" + CONTRACT + PAD, "sonnet")
    case("合同文本本身不触发任何 floor（验收 + 合同 + sonnet → T1 pass）",
         d["tier"] == "T1" and d["action"] == "pass")
    d = run("在做只读代码 Review，绝对禁止修改任何文件，只报告问题。" + PAD, "sonnet")
    case("只读豁免：只读 Review 没有验收行 → 不锁（T1 pass）",
         not _rule(d, "R-AMBIGUOUS")["hit"] and d["action"] == "pass")
    d = run("只读取 config.json，然后实现缓存层。" + PAD, "sonnet")
    case("只读豁免反：「只读取…然后实现」不算只读声明 → 仍锁", _rule(d, "R-AMBIGUOUS")["hit"])
    d = run("把 User.id 字段改成 read-only。" + PAD, "sonnet")
    case("只读豁免反：「改成 read-only」不算只读声明 → 仍锁", _rule(d, "R-AMBIGUOUS")["hit"])
    d = run("只读代码 Review，禁止修改任何文件。顺便确认能 git push。" + PAD, "sonnet")
    case("只读豁免只管验收行：动作词照样锁 T2", d["action"] == "raise")

    # R-TRADEOFF
    d = run("缓存层有两种做法，权衡后选一个实现。" + AC + PAD, "sonnet")
    case("TRADEOFF 正：取舍词 → 锁 T2 并 raise",
         _rule(d, "R-TRADEOFF")["hit"] and d["action"] == "raise")
    d = run("按 spec 第 3 节实现缓存层。" + AC + PAD, "sonnet")
    case("TRADEOFF 反：无取舍词 → 不命中", not _rule(d, "R-TRADEOFF")["hit"])

    # 起点档
    d = run("跑一遍测试。" + AC + PAD, None, agent_model="haiku")
    case("起点：未传 model 时用 agent frontmatter（haiku → T0）", d["start_tier"] == "T0")
    d = run("git push。" + AC + PAD, None)
    case("起点：继承且档位未知 + floor → raise 到 opus",
         d["start_tier"] is None and d["action"] == "raise" and d["target_model"] == "opus")
    d = run("git push。" + AC + PAD, "fable")
    case("起点：不认识的 model → 不动（排不出强弱）", d["action"] == "pass" and d["tier"] is None)

    # ② 收益门槛 / 防抖
    d = run("改个常量。" + AC, "sonnet")
    case("收益门槛：短 prompt 且无 floor → local", d["action"] == "local")
    d = run("git push。" + AC, "sonnet")
    case("收益门槛撤不回升档：短 prompt + floor → 仍 raise", d["action"] == "raise")
    d = run("改完后跑一遍测试。" + AC + PAD, "sonnet", consecutive_failures=2)
    case("防抖：连续失败 2 次 → defer", d["action"] == "defer")
    d = run("改完后跑一遍测试。" + AC + PAD, "sonnet", consecutive_failures=1)
    case("防抖反：失败 1 次 → 不 defer", d["action"] == "pass")
    d = run("git push。" + AC + PAD, "sonnet", consecutive_failures=5)
    case("防抖撤不回升档：连续失败 + floor → 仍 raise", d["action"] == "raise")

    # R2
    d = run("跑一遍测试。" + AC + PAD, None, agent_model=None)
    case("R2 正：agent 没钉 model 且未传 → hint", _rule(d, "R2") is not None)
    d = run("跑一遍测试。" + AC + PAD, None, agent_model="sonnet")
    case("R2 反：agent 钉了 model → 不提示", _rule(d, "R2") is None)

    # 范围 / 模式 / 放行
    d = run("git push。" + PAD, "sonnet", subagent_type="fork")
    case("fork → 原样放行", d["action"] == "pass" and d["tier"] is None)
    d = run("git push。" + PAD, "sonnet", tool="Bash")
    case("不是 Agent 调用 → 放行", d["action"] == "pass" and d["tier"] is None)
    d = run("git push。" + PAD, "sonnet", mode="off")
    case("mode=off → 不判", d["action"] == "pass" and d["tier"] is None)
    d = run("git push。" + PAD, "sonnet", mode="dry-run")
    case("dry-run 照常给出决策（改不改由薄壳按 mode 定）", d["action"] == "raise" and d["mode"] == "dry-run")
    d = decide({"tool_name": "Agent", "tool_input": {"subagent_type": "x"}}, cfg)
    case("payload 缺 prompt → 放行 + fallback", d["action"] == "pass" and d["fallback"])
    d = decide("not-a-dict", cfg)
    case("payload 不是对象 → 放行 + fallback", d["action"] == "pass" and d["fallback"])
    d = decide(_agent("git push。" + PAD, "sonnet"), None)
    case("配置读不到 → 放行 + fallback", d["action"] == "pass" and d["fallback"])
    d = run("git push。" + PAD, "sonnet", mode="deny")
    case("未知 mode → 放行 + fallback", d["action"] == "pass" and d["fallback"])

    # 配置不变量
    def broken(mut):
        c = copy.deepcopy(cfg)
        mut(c)
        return run("git push。" + PAD, "sonnet", c)
    # 用 T0：T1/T2 改 slug 会先被「同 slug」那道检查拦下，验不到 never_auto 本身
    case("配置：T0 映射到 gpt-5.6-sol → 拒绝（never_auto，放行 + fallback）",
         broken(lambda c: c["tiers"]["T0"]["codex"].update(model="gpt-5.6-sol"))["fallback"])
    case("配置：effort=ultra → 拒绝",
         broken(lambda c: c["tiers"]["T2"]["codex"].update(effort="ultra"))["fallback"])
    case("配置：T1、T2 的 Codex slug 不同 → 拒绝（升档只许动 effort）",
         broken(lambda c: c["tiers"]["T1"]["codex"].update(model="gpt-5.6-luna"))["fallback"])
    case("配置：effort 随档位下降 → 拒绝",
         broken(lambda c: c["tiers"]["T1"]["codex"].update(effort="low"))["fallback"])
    case("配置：动作词表为空 → 拒绝",
         broken(lambda c: c["floor_rules"]["R-IRREVERSIBLE"].update(words=[]))["fallback"])

    # Codex 落参
    d = run("git push。" + AC + PAD, None, executor="codex", requested_tier="T1")
    case("Codex：floor → T2 = terra / xhigh（只动 effort）",
         (d["target_model"], d["target_reasoning_effort"]) == ("gpt-5.6-terra", "xhigh"))
    d = run("改完后跑一遍测试。" + AC + PAD, None, executor="codex", requested_tier="T1")
    case("Codex 反：无 floor → 保持 T1 = terra / high",
         (d["tier"], d["target_reasoning_effort"]) == ("T1", "high"))
    d = run("改完后跑一遍测试。" + AC + PAD, None, executor="codex",
            codex_model="gpt-5.6-terra", codex_effort="high")
    case("Codex 起点：实际 flags 与 T1 完全一致 → 认出 T1、不 raise",
         (d["start_tier"], d["action"]) == ("T1", "pass"))
    d = run("git push。" + AC + PAD, None, executor="codex",
            codex_model="gpt-5.6-terra", codex_effort="high")
    case("Codex 起点：T1 flags + floor → raise 到 xhigh",
         (d["action"], d["target_reasoning_effort"]) == ("raise", "xhigh"))
    d = run("git push。" + AC + PAD, None, executor="codex",
            codex_model="gpt-5.6-sol", codex_effort="high")
    case("Codex 起点：表外组合（sol）→ 不动", d["action"] == "pass" and d["tier"] is None)

    # 升级触发（观测口径）
    case("升级触发：合同标记从合同文本取到四个", CONTRACT_MARKS == ("①", "②", "③", "④"))
    case("升级触发正：引用 ② 并交回", escalated("② 验收标准有歧义，我先停止，把现状交回。"))
    case("升级触发反：正常完成的回复", not escalated("改完了，pytest 全绿。"))
    case("升级触发反：只出现编号、没说交回", not escalated("① 已补测试 ② 已改实现"))

    # 不变量扫一遍：档位永远不低于起点
    sweep = [run(p, m) for p in ("git push。" + AC + PAD, "跑测试。" + AC + PAD, "跑测试。" + PAD)
             for m in ("haiku", "sonnet", "opus")]
    case("不变量：任何决策的档位都不低于起点",
         all(x["tier"] is None or x["start_tier"] is None or rank(x["tier"]) >= rank(x["start_tier"])
             for x in sweep))

    # 主代理预路由提醒 nudge_decision
    case("nudge：文本常量固定不变", NUDGE_REMIND_TEXT.startswith("tier-guard：") and NUDGE_DENY_TEXT.startswith("tier-guard（auto）："))
    case("nudge：profile=off → none",
         nudge_decision("off", False, True, "s1", False) == {"action": "none", "text": None})
    case("nudge：host_gate=False → none",
         nudge_decision("audit", False, False, "s1", False) == {"action": "none", "text": None})
    case("nudge：host_gate=None（宿主未声明）→ none",
         nudge_decision("audit", False, None, "s1", False) == {"action": "none", "text": None})
    case("nudge：pinned=True → none",
         nudge_decision("audit", True, True, "s1", False) == {"action": "none", "text": None})
    case("nudge：pinned=None（插件 agent 判不出）→ none",
         nudge_decision("audit", None, True, "s1", False) == {"action": "none", "text": None})
    case("nudge：audit + 未 pin + 宿主支持 → remind",
         nudge_decision("audit", False, True, "s1", False) == {"action": "remind", "text": NUDGE_REMIND_TEXT})
    case("nudge：auto + 有 session_id + 本会话未 deny 过 → deny",
         nudge_decision("auto", False, True, "s1", False) == {"action": "deny", "text": NUDGE_DENY_TEXT})
    case("nudge：auto + 本会话已 deny 过 → remind",
         nudge_decision("auto", False, True, "s1", True) == {"action": "remind", "text": NUDGE_REMIND_TEXT})
    case("nudge：auto + session_id 为空串 → remind",
         nudge_decision("auto", False, True, "", False) == {"action": "remind", "text": NUDGE_REMIND_TEXT})
    case("nudge：auto + session_id 为 None → remind",
         nudge_decision("auto", False, True, None, False) == {"action": "remind", "text": NUDGE_REMIND_TEXT})

    def nudge_raises():
        try:
            nudge_decision("deny", False, True, "s1", False)
        except ValueError:
            return True
        return False
    case("nudge：未知 profile → 抛 ValueError（适配层失败即放行）", nudge_raises())

    # Task 13：guard profile —— nudge 行为等同今天的 auto，audit 保持只提醒
    case("nudge：ROUTING_PROFILES 包含 guard", "guard" in ROUTING_PROFILES)
    case("nudge：guard + 有 session_id + 本会话未 deny 过 → deny",
         nudge_decision("guard", False, True, "s1", False) == {"action": "deny", "text": NUDGE_DENY_TEXT})
    case("nudge：guard + 本会话已 deny 过 → remind",
         nudge_decision("guard", False, True, "s1", True) == {"action": "remind", "text": NUDGE_REMIND_TEXT})
    case("nudge：guard + session_id 为空串 → remind",
         nudge_decision("guard", False, True, "", False) == {"action": "remind", "text": NUDGE_REMIND_TEXT})
    case("nudge：guard + session_id 为 None → remind",
         nudge_decision("guard", False, True, None, False) == {"action": "remind", "text": NUDGE_REMIND_TEXT})
    case("nudge：guard + host_gate=False → none",
         nudge_decision("guard", False, False, "s1", False) == {"action": "none", "text": None})
    case("nudge：guard + pinned=True → none",
         nudge_decision("guard", True, True, "s1", False) == {"action": "none", "text": None})

    # Task 13：route() 下 guard 与 audit 的决策必须一致（只有 profile 字段本身不同）
    catalog = load_catalog()
    audit_catalog = copy.deepcopy(catalog)
    audit_catalog["mode"] = "audit"
    guard_catalog = copy.deepcopy(catalog)
    guard_catalog["mode"] = "guard"

    def _same_except_profile(a, b):
        a, b = dict(a), dict(b)
        a.pop("profile", None)
        b.pop("profile", None)
        return a == b

    guard_pinned_req = {
        "task": "改完后 git push 到 origin。\n验收：CI 绿。",
        "host": "codex-cli",
        "requested": {"model": "gpt-5.6-terra", "reasoning_effort": "high", "pinned": True},
        "signals": {},
    }
    guard_unpinned_req = {
        "task": "只读检查配置，禁止修改任何文件。\n验收：报告所有键名。",
        "host": "codex-cli",
        "requested": {"pinned": False},
        "signals": {},
    }
    audit_pinned = route(guard_pinned_req, audit_catalog)
    guard_pinned = route(guard_pinned_req, guard_catalog)
    case("route：guard 下 pin 请求与 audit 一致（除 profile 外）",
         guard_pinned["profile"] == "guard" and audit_pinned["profile"] == "audit"
         and _same_except_profile(guard_pinned, audit_pinned))
    audit_unpinned = route(guard_unpinned_req, audit_catalog)
    guard_unpinned = route(guard_unpinned_req, guard_catalog)
    case("route：guard 下未 pin 请求与 audit 一致（除 profile 外）",
         guard_unpinned["profile"] == "guard" and audit_unpinned["profile"] == "audit"
         and _same_except_profile(guard_unpinned, audit_unpinned))

    # catalog_summary：nudge 文案附带的候选目录摘要，只从 catalog_candidates 派生

    def _in_order(text, subs):
        start = 0
        for s in subs:
            i = text.find(s, start)
            if i == -1:
                return False
            start = i + len(s)
        return True

    claude_summary = catalog_summary(catalog, "claude-code")
    codex_summary = catalog_summary(catalog, "codex-cli")
    case("catalog_summary：claude-code 候选按成本从低到高出现（haiku→sonnet→opus）",
         _in_order(claude_summary, ["haiku", "sonnet", "opus"]))
    case("catalog_summary：claude-code 摘要不含 codex 候选 model",
         not any(m in claude_summary for m in ("gpt-6-luna", "gpt-6.1-sol")))
    case("catalog_summary：codex-cli 候选按成本从低到高出现，且带 effort",
         _in_order(codex_summary, ["gpt-6-luna / high", "gpt-6.1-sol / medium", "gpt-6.1-sol / xhigh"]))
    case("catalog_summary：codex-cli 摘要不含 claude 候选 model",
         not any(m in codex_summary for m in ("haiku", "sonnet", "opus")))
    case("catalog_summary：两个宿主都带保守兜底句",
         "不要自行降档或使用目录外的组合" in claude_summary and "不要自行降档或使用目录外的组合" in codex_summary)
    case("catalog_summary：未知宿主 → 空字符串", catalog_summary(catalog, "no-such-host") == "")

    # nudge_text / nudge_decision(summary=...)：remind/deny 文案附带摘要，summary 为空时恰好是常量本身
    SUMMARY_TEST = "候选摘要TEST"
    case("nudge_text：none 动作 → None", nudge_text("none") is None)
    case("nudge_text：remind 附带 summary", nudge_text("remind", SUMMARY_TEST) == NUDGE_REMIND_TEXT + SUMMARY_TEST)
    case("nudge_text：deny 附带 summary", nudge_text("deny", SUMMARY_TEST) == NUDGE_DENY_TEXT + SUMMARY_TEST)
    case("nudge_text：summary 为空 → 恰好是常量本身", nudge_text("remind") == NUDGE_REMIND_TEXT)
    case("nudge：summary 非空时 remind 文本 = 常量 + summary",
         nudge_decision("audit", False, True, "s1", False, SUMMARY_TEST)
         == {"action": "remind", "text": NUDGE_REMIND_TEXT + SUMMARY_TEST})
    case("nudge：summary 非空时 deny 文本 = 常量 + summary",
         nudge_decision("auto", False, True, "s1", False, SUMMARY_TEST)
         == {"action": "deny", "text": NUDGE_DENY_TEXT + SUMMARY_TEST})
    case("nudge：summary 为空串时 remind 恰好等于基础常量",
         nudge_decision("audit", False, True, "s1", False, "") == {"action": "remind", "text": NUDGE_REMIND_TEXT})

    print("")
    print(f"  总计 {len(ok)} 通过 / {len(bad)} 失败")
    return 0 if ok and not bad else 1


def main(argv):
    if argv[:1] == ["--selftest"]:
        return selftest()
    cfg_path, ctx = DEFAULT_CONFIG, {}
    try:
        if "--config" in argv:
            cfg_path = argv[argv.index("--config") + 1]
        if "--ctx" in argv:
            ctx = json.loads(argv[argv.index("--ctx") + 1])
    except (IndexError, ValueError):
        ctx = {}
    try:
        cfg = load_config(cfg_path)
    except Exception:
        cfg = None               # decide 会把它转成放行 + fallback
    try:
        raw = sys.stdin.read()
        payload = ({"tool_name": "Agent", "tool_input": {"prompt": raw}} if "--task" in argv
                   else json.loads(raw))
    except Exception:
        payload = None
    print(json.dumps(decide(payload, cfg, ctx if isinstance(ctx, dict) else {}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
