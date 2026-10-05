#!/usr/bin/env python3
"""静态核对 mutation-check.py 里每个变异体的 old 锚点在目标文件中恰好出现一次。

锚点失效的变异体会被整条跳过 —— 它不报错、不算失败，只是**再也不跑了**，而它守的那条断言
从此无人验证。实测一天内发生三次：每次重构 hook 源码，锚定在那段代码上的变异体就被打断。
`mutation-check.py` 自己会报「锚点失效 N」，但只看这个计数很容易把自己刚造成的误认成已知旧账
（2026-10-05 本仓就这么误判过一次，一条变异体因此几个提交没跑）。

本检查只读文件、不跑任何套件，几秒出结果，所以进 validate；全量变异测试太慢，仍不进。

用法：check-mutation-anchors.py [仓库根]
"""
import importlib.util
import os
import sys

TARGET = os.path.join("scripts", "mutation-check.py")


def load_mutants(root):
    """导入 mutation-check.py 并取出变异体列表 M。"""
    path = os.path.join(root, TARGET)
    spec = importlib.util.spec_from_file_location("mutation_check_under_audit", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    saved = sys.argv
    # 该模块目前只在 __main__ 下解析 argv；塞一个不匹配任何变异体的 --only 作为防御，
    # 这样它将来真的在导入期解析 argv 也不会误跑或误退出。
    sys.argv = [path, "--only", "\0no-such-mutant\0"]
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        pass
    finally:
        sys.argv = saved
    mutants = getattr(module, "M", None)
    if not isinstance(mutants, list):
        raise AttributeError(f"{TARGET} 里没有变异体列表 M")
    return mutants


def main(argv):
    root = argv[0] if argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        mutants = load_mutants(root)
    except (OSError, ImportError, AttributeError, SyntaxError) as exc:
        print(f"  ❌ 读不到变异体列表：{exc}")
        return 1
    # 零个变异体不算通过：空列表会让每条锚点检查都「通过」，和删掉这个检查没有区别。
    if not mutants:
        print(f"  ❌ {TARGET} 的变异体列表为空 —— 不算通过")
        return 1

    sources, bad = {}, []
    for mutant in mutants:
        desc, rel, old = mutant[0], mutant[1], mutant[3]
        if rel not in sources:
            try:
                with open(os.path.join(root, rel), encoding="utf-8") as fh:
                    sources[rel] = fh.read()
            except OSError as exc:
                bad.append((desc, rel, f"读不到目标文件：{exc}"))
                sources[rel] = None
        text = sources[rel]
        if text is None:
            continue
        hits = text.count(old)
        if hits != 1:
            bad.append((desc, rel, f"锚点出现 {hits} 次，应为 1"))

    for desc, rel, why in bad:
        print(f"  ❌ {why}：{desc}  [{rel}]")
    if bad:
        print(f"  ❌ {len(mutants)} 个变异体中 {len(bad)} 个锚点失效 —— 这些变异体不会被执行")
        return 1
    print(f"  ✅ {len(mutants)} 个变异体的锚点都唯一命中")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
