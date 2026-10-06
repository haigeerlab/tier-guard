#!/usr/bin/env python3
"""/tier-label：人工标注 v1 历史记录。只追加到 <数据目录>/labels.jsonl，同一个 id 以最后一次为准。

仅限 v1 记录：v2 路由不再有 R-IRREVERSIBLE 命中与 T1 档，v2 记录一律拒绝并说明（Phase 9）。

  fp / tp          这条 R-IRREVERSIBLE 命中是误报 / 真命中（算误报率）
  reject / accept  这次 T1 子代理的产出被打回 / 验收通过（覆写「重派推断」，算打回率）

标注前核对 id 真实存在且类型对得上 —— 标错一个 id 不会报错，只会让误报率悄悄偏掉。

用法: python3 hooks/tier_label.py <tool_use_id> <fp|tp|reject|accept> [--data DIR]
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tier_report  # noqa: E402
import tier_state  # noqa: E402

LABELS = ("fp", "tp", "reject", "accept")


def main(argv):
    explicit = None
    if "--data" in argv:
        i = argv.index("--data")
        explicit = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 2 or argv[1] not in LABELS:
        print(f"❌ 用法: tier_label.py <tool_use_id> <{'|'.join(LABELS)}>")
        return 1
    tid, label = argv
    ddir = tier_state.data_dir(explicit or None)
    recs, _ = tier_report.load(os.path.join(ddir, "decisions.jsonl"))
    pairs = tier_report.join(recs or [])
    hit = next(((a, s) for a, s in pairs if a.get("tool_use_id") == tid), None)
    if hit is None:
        print(f"❌ 日志里没有 tool_use_id={tid} 的 Agent 判定记录 —— 先跑 /tier-report 抄 id")
        return 1
    a, s = hit
    if a.get("routing_version") == 2:
        print(f"❌ {tid} 是 v2 记录：/tier-label 仅限 v1 历史记录（v2 不再有 R-IRREVERSIBLE / T1 判定）")
        return 1
    if label in ("fp", "tp") and not tier_report._irr(a).get("hit"):
        print(f"❌ {tid} 没有命中 R-IRREVERSIBLE，fp / tp 无从谈起")
        return 1
    if label in ("reject", "accept") and not (s and s.get("actual_tier") == "T1"):
        print(f"❌ {tid} 不是一次实际跑在 T1 的子代理（打回率只算 T1）")
        return 1
    os.makedirs(ddir, mode=0o700, exist_ok=True)
    with open(os.path.join(ddir, "labels.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                             "tool_use_id": tid, "label": label}, ensure_ascii=False) + "\n")
    print(f"✅ 已标注 {tid} = {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
