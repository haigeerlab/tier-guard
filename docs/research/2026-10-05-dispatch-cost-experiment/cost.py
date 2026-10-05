import json, glob, os, sys, subprocess, statistics
# (输入, 缓存写 5m, 缓存写 1h, 缓存读, 输出) 每百万 token。主会话用 1h 缓存（2× 输入），子代理用 5m（1.25×）——
# 2026-10-05 更正：初版一律按 1.25× 计，低估了主会话缓存写。
P = {"claude-opus-5-5": (4, 5, 8, 0.2, 20), "claude-sonnet-5-5": (2, 2.5, 4, 0.2, 10), "claude-haiku-4-5-20251001": (1, 1.25, 2, 0.1, 5), "claude-opus-5": (5, 6.25, 10, 0.5, 25)}
E = sys.argv[1]
def account(files):
    best = {}
    for f in files:
        for i, line in enumerate(open(f, encoding="utf-8")):
            m = json.loads(line).get("message") or {}
            if not isinstance(m, dict) or m.get("role") != "assistant" or not isinstance(m.get("usage"), dict): continue
            u = m["usage"]; cc = u.get("cache_creation") or {}
            w1h = cc.get("ephemeral_1h_input_tokens", 0) or 0; w5 = (u.get("cache_creation_input_tokens") or 0) - w1h
            row = (m.get("model"), u.get("input_tokens") or 0, w5, w1h, u.get("cache_read_input_tokens") or 0, u.get("output_tokens") or 0)
            k = (f, m.get("id") or i)
            if k not in best or sum(row[1:]) > sum(best[k][1:]): best[k] = row
    cost = 0.0; models = {}; tok = [0, 0, 0, 0]
    for mo, i, w5, w1h, cr, o in best.values():
        pi, p5, p1h, pcr, po = P[mo]; cost += (i*pi + w5*p5 + w1h*p1h + cr*pcr + o*po) / 1e6
        models[mo] = models.get(mo, 0) + 1
        for j, v in enumerate((i, w5 + w1h, cr, o)): tok[j] += v
    return cost, models, tok, len(best)
rows = []
for name in sorted(os.listdir(E)):
    if not os.path.isdir(f"{E}/{name}") or name.count("-") != 2 or not name.startswith(("small", "large")): continue
    d = [x for x in glob.glob(os.path.expanduser("~/.claude/projects/*")) if x.endswith(f"cost-exp-{name}")][0]
    main = glob.glob(f"{d}/*.jsonl"); subs = glob.glob(f"{d}/*/subagents/*.jsonl")
    cm, mm, tm, nm = account(main); cs, ms, ts, ns = account(subs)
    tests = subprocess.run(["python3", "-m", "unittest", "discover", "-s", "tests"], cwd=f"{E}/{name}", capture_output=True, text=True).stderr.strip().splitlines()[-1]
    commits = len(subprocess.run(["git", "log", "--oneline"], cwd=f"{E}/{name}", capture_output=True, text=True).stdout.splitlines())
    rows.append((name, cm, cs, cm + cs, mm, ms, len(subs), nm, tm, tests, commits))
    print(f"{name:17} 主 ${cm:.3f}（{nm} 条，模型 {mm}） 子 ${cs:.3f}（{len(subs)} 个，{ms}） 合计 ${cm+cs:.3f} | 主会话缓存读 {tm[2]:,} 缓存写 {tm[1]:,} 输出 {tm[3]:,} | 测试 {tests} 提交 {commits}")
print()
for cond in ("small-inline", "small-dispatch", "large-inline", "large-dispatch"):
    v = [r[3] for r in rows if r[0].startswith(cond)]
    print(f"{cond:15} 每次合计：{', '.join(f'${x:.3f}' for x in v)}  均值 ${statistics.mean(v):.3f}")
