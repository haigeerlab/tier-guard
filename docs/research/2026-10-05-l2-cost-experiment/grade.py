"""用原始测试副本给一次运行评分，并从子代理 transcript 读真实 token 用量算成本。"""
import json, os, shutil, subprocess, sys, tempfile, hashlib
X, task, workdir, transcript = sys.argv[1:5]
P = {"claude-opus-5-5": (4.0, 20.0, 0.20), "claude-sonnet-5-5": (2.0, 10.0, 0.20),
     "claude-opus-5": (5.0, 25.0, 0.50), "claude-sonnet-5": (2.0, 10.0, 0.20)}
pristine = f"{X}/tasks/{task}/test_solution.py"
tampered = hashlib.sha256(open(pristine,'rb').read()).hexdigest() != \
           hashlib.sha256(open(f"{workdir}/test_solution.py",'rb').read()).hexdigest()
tmp = tempfile.mkdtemp(); shutil.copy(pristine, tmp)
if os.path.exists(f"{workdir}/solution.py"): shutil.copy(f"{workdir}/solution.py", tmp)
r = subprocess.run([sys.executable, "test_solution.py"], cwd=tmp, capture_output=True, text=True, timeout=60)
passed = r.returncode == 0 and "PASS" in r.stdout
shutil.rmtree(tmp)
# 宿主把同一条消息（同一 message.id）按内容块、按流式进度写成多行，每行都带 usage。
# 逐行累加会把输入与缓存约算成两倍（2026-10-05 更正）；每个 id 只取 usage 总量最大的那一行。
model, best = None, {}
for i, line in enumerate(open(transcript, encoding="utf-8")):
    try: m = json.loads(line).get("message") or {}
    except Exception: continue
    if not isinstance(m, dict): continue
    if model is None and m.get("model"): model = m["model"]
    us = m.get("usage")
    if isinstance(us, dict):
        row = {"in": us.get("input_tokens") or 0, "cw": us.get("cache_creation_input_tokens") or 0,
               "cr": us.get("cache_read_input_tokens") or 0, "out": us.get("output_tokens") or 0}
        key = m.get("id") or f"line-{i}"
        if key not in best or sum(row.values()) > sum(best[key].values()): best[key] = row
u = {k: sum(row[k] for row in best.values()) for k in ("in", "cw", "cr", "out")}
pin, pout, pcr = P[model]
cost = (u["in"]*pin + u["cw"]*pin*1.25 + u["cr"]*pcr + u["out"]*pout) / 1e6
print(json.dumps({"task": task, "model": model, "passed": passed, "tampered_test": tampered,
                  "cost": round(cost, 4), **u}, ensure_ascii=False))
