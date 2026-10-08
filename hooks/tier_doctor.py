#!/usr/bin/env python3
"""/tier-doctor：只读诊断 tier-guard 的日志和 Codex hook 可观察性。

它故意不尝试读取 Codex 的 hook 信任状态：那是宿主的交互式权限状态，插件不能也不该
伪造。没有记录时只列出可能的链路断点；只有实际出现 codex-spawn 记录才声明 hook
曾被调用过。

用法: python3 hooks/tier_doctor.py [--data DIR] [--config PATH]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tier_state  # noqa: E402


def load_records(path):
    records, broken = [], 0
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return records, broken
    with fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError
                records.append(record)
            except ValueError:
                broken += 1
    return records, broken


def cmd_doctor(ddir, data_from_host, config_path=None):
    if config_path is not None:
        try:
            cfg = tier_state.rd.load_catalog(config_path)
        except Exception:
            print("❌ 指定的 v2 路由配置不可用；请检查路径、JSON 与目录契约。")
            return 1
    else:
        cfg = tier_state._config()
    # 与 hook 用同一组允许值：v2 下旧模式（如 dry-run）回退默认，doctor 不能报一个 hook 根本不用的值
    allowed = tier_state.rd.ROUTING_PROFILES if (cfg or {}).get("schema_version") == 2 else None
    mode, source = tier_state.read_mode(ddir, (cfg or {}).get("mode"), allowed)
    path = os.path.join(ddir, "decisions.jsonl")
    records, broken = load_records(path)
    codex = [record for record in records if record.get("event") == "codex-spawn"]

    print("# tier-guard 诊断（只读）")
    print(f"插件根目录：{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")
    print(f"数据目录：{ddir}")
    print(f"当前 mode：{mode}（来源：{source}）")
    print(f"判定日志：{path}")
    print(f"Codex spawn hook 记录：{len(codex)}")
    if codex and codex[-1].get("ts"):
        print(f"最后一次 Codex spawn：{codex[-1]['ts']}")
    if broken:
        print(f"坏记录：{broken} 行")
    if not data_from_host:
        print("提示：调用进程未提供数据目录；如在普通 shell 诊断 Codex，请显式传 --data。")

    if codex:
        print("结论：当前数据目录已观察到 Codex PreToolUse hook 至少触发过一次。")
    else:
        print("结论：当前数据目录没有 Codex spawn hook 记录；不能区分未安装、未信任或调用绕过 hook。")
        if mode == "off":
            print("补充：当前 mode=off 按设计不写判定日志；先切回 guard 或 audit 再做验证。")

    print("\n下一步：")
    print("- 此命令不能读取或证明 Codex 的 hook 信任状态。")
    print("- 验证 ChatGPT 桌面版：先在 Codex CLI 用 /hooks 审核当前 hook 信任记录；再从原生桌面界面派一次带唯一标记的子代理。")
    print("- 协作代理 API 不会进入 Codex PreToolUse hook，不能作为桌面 hook 冒烟。")
    return 0


def main(argv):
    options = {"--data": None, "--config": None}
    for flag in options:
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                print(f"❌ {flag} 需要完整的路径。")
                return 1
            options[flag] = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    if argv:
        print("❌ 用法: tier_doctor.py [--data DIR] [--config PATH]（参数不得重复）")
        return 1
    explicit = options["--data"]
    data_from_host = bool(explicit or os.environ.get("TIER_GUARD_LOG_DIR")
                          or os.environ.get("CLAUDE_PLUGIN_DATA"))
    return cmd_doctor(tier_state.data_dir(explicit), data_from_host, options["--config"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
