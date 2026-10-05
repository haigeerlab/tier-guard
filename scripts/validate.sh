#!/bin/bash
# 仓库完整性校验。本地和 pre-push 共用。
# 只放不花钱、秒级的检查；变异测试太慢，不在这里（scripts/mutation-check.py）。
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
F=0
say(){ printf '  %s %s\n' "$1" "$2"; }

# 文件清单。bash 3.2 没有 mapfile，而空数组配 set -u 会报 unbound variable，
# 所以展开一律写 ${ARR[@]+"${ARR[@]}"}。清单为空时交给检查器去报
# 「什么都没查」，这里不许静默跳过 —— 「0 个文件」和「0 处违规」退出码一样。
SH=(); while IFS= read -r f; do SH+=("${f}"); done < <(find . -name '*.sh' -not -path './.git/*' | LC_ALL=C sort)
JS=(); while IFS= read -r f; do JS+=("${f}"); done < <(find . -name '*.json' -not -path './.git/*' | LC_ALL=C sort)

echo "═══ 结构 ═══"
for p in .claude-plugin/plugin.json .codex-plugin/plugin.json \
         scripts/check-bash32.py scripts/check-grep-pipe.py scripts/check-manifests.py \
         scripts/test-checkers.sh scripts/mutation-check.py scripts/install-git-hooks.sh \
         config/routing.default.json config/routing.catalog.v2.json hooks/route_decide.py hooks/test-route-contract.py \
         hooks/hooks.json hooks/tier-guard.sh hooks/claude_hook.py hooks/test-tier-guard.sh \
         skills/tier-routing/SKILL.md scripts/check-skill-sync.py scripts/check-plugin-paths.py scripts/check-mutation-anchors.py \
         hooks/tier_state.py hooks/tier_report.py hooks/tier_doctor.py hooks/test-tier-commands.sh hooks/test-tier-doctor.sh \
         commands/tier-mode.md commands/tier-report.md commands/tier-doctor.md commands/tier-label.md \
         hooks/tier_label.py hooks/test-tier-observe.sh \
         hooks/codex-hooks.json hooks/tier-guard-codex.sh hooks/codex_hook.py hooks/test-tier-guard-codex.sh; do
  if [ -f "${p}" ]; then say "✅" "${p}"; else say "❌" "${p} 缺失"; F=1; fi
done

echo ""
echo "═══ JSON 语法 ═══"
for j in ${JS[@]+"${JS[@]}"}; do
  if python3 -m json.tool "${j}" >/dev/null 2>&1; then say "✅" "${j}"; else say "❌" "${j} 解析失败"; F=1; fi
done

echo ""
echo "═══ Claude ↔ Codex 清单一致性 ═══"
python3 scripts/check-manifests.py || F=1

echo ""
echo "═══ Shell 语法（/bin/bash -n，即 macOS 的 3.2）═══"
for s in ${SH[@]+"${SH[@]}"}; do
  if /bin/bash -n "${s}" 2>/dev/null; then say "✅" "${s}"; else say "❌" "${s} 语法错误"; F=1; fi
done

echo ""
echo "═══ 可执行位 ═══"
for s in ${SH[@]+"${SH[@]}"}; do
  if [ -x "${s}" ]; then say "✅" "${s}"; else say "⚠️ " "${s} 缺执行位（chmod +x ${s}）"; fi
done

echo ""
echo "═══ bash 3.2 兼容（\$VAR 紧跟多字节字符）═══"
python3 scripts/check-bash32.py ${SH[@]+"${SH[@]}"} || F=1

echo ""
echo "═══ 管道 + grep -q（SIGPIPE 陷阱）═══"
python3 scripts/check-grep-pipe.py ${SH[@]+"${SH[@]}"} || F=1

echo ""
echo "═══ SKILL.md ↔ 配置 / 合同文本 ═══"
python3 -B scripts/check-skill-sync.py || F=1

echo ""
echo "═══ 命令 / skill / hooks.json 引用的脚本都存在 ═══"
python3 scripts/check-plugin-paths.py || F=1

echo ""
echo "═══ 变异体锚点是否仍唯一命中 ═══"
python3 -B scripts/check-mutation-anchors.py || F=1

echo ""
# 判据被三方共用（两个薄壳 + /tier-report）—— 它自己判错，表现是一条关不掉的
# 假警报或一次悄悄的欠配。免费，所以进这一层。
echo "═══ 判据自检（route_decide --selftest）═══"
python3 -B hooks/route_decide.py --selftest || F=1

echo ""
echo "═══ v2 路由契约 ═══"
python3 -B hooks/test-route-contract.py || F=1

echo ""
echo "═══ Claude 薄壳回归（tier-guard.sh）═══"
/bin/bash hooks/test-tier-guard.sh || F=1

echo ""
echo "═══ Codex 薄壳回归（tier-guard-codex.sh）═══"
/bin/bash hooks/test-tier-guard-codex.sh || F=1

echo ""
echo "═══ /tier-mode · /tier-report 回归 ═══"
/bin/bash hooks/test-tier-commands.sh || F=1

echo ""
echo "═══ /tier-doctor 回归 ═══"
/bin/bash hooks/test-tier-doctor.sh || F=1

echo ""
echo "═══ 可观测性回归（SubagentStop · 打回率 · 误报率 · auto 门槛）═══"
/bin/bash hooks/test-tier-observe.sh || F=1

echo ""
echo "═══ 校验器自身的回归 ═══"
/bin/bash scripts/test-checkers.sh || F=1

echo ""
if [ "${F}" -eq 0 ]; then echo "校验通过 ✅"; else echo "校验失败 ❌"; fi
exit "${F}"
