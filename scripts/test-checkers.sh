#!/bin/bash
# ─────────────────────────────────────────────────────────────
# scripts/check-*.py 的回归测试 —— 防线本身也要被测试。
#
# spec-guard 那边这条被违反过四次，形状都一样：判据写完没有当场用真实
# 数据跑一遍。写在说明文件里的规矩是口号，这个套件才是拦截。
#
# 规矩：每个 check-*.py 至少一正一反 —— 喂已知坏输入必须**非零退出**，
# 喂好输入必须**零退出**。反向用例是重点：一个永远返回 0 的校验器和
# 没有校验器没区别。新加 check-*.py 时，一正一反在同一次改动里加进来。
#
# 这些用例能不能真抓到回归，由 scripts/mutation-check.py 反过来验。
# ─────────────────────────────────────────────────────────────
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
PASS=0; FAIL=0

# fail 不只看退出码：还要求输出里有 ❌ —— 校验器崩溃（Traceback）也是非零，
# 但那是「没跑起来」，不是「判对了」。
want() {  # $1=期望(fail|pass) $2=用例名 $3...=命令
  local exp="$1" name="$2"; shift 2
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if { [ "${exp}" = fail ] && [ "${rc}" -ne 0 ] && [[ "${out}" == *❌* ]]; } \
     || { [ "${exp}" = pass ] && [ "${rc}" -eq 0 ]; }; then
    printf '  ✅ %s\n' "${name}"; PASS=$((PASS+1))
  elif [ "${exp}" = fail ] && [ "${rc}" -ne 0 ]; then
    printf '  ❌ %s（退出码 %s 但输出里没有 ❌ —— 崩溃了？）\n' "${name}" "${rc}"; FAIL=$((FAIL+1))
  else
    printf '  ❌ %s（期望 %s，实际退出码 %s）\n' "${name}" "${exp}" "${rc}"; FAIL=$((FAIL+1))
  fi
}

echo "═══ check-*.py 回归 ═══"

# ── check-bash32.py ──
# 坏样本在**运行时拼装**：写成字面量的话，validate.sh 里的 check-bash32
# 会抓本文件自己。靠豁免 test-*.sh 也能过，但会削掉真实覆盖 ——
# 测试脚本本身也得能在 bash 3.2 上跑。
D='$'
printf 'X=1\necho "（#%sX）"\n'   "${D}" > "${TMP}/bad32.sh"
printf 'X=1\necho "（#%s{X}）"\n' "${D}" > "${TMP}/good32.sh"
want fail "bash32: \$VAR 紧跟全角括号 → 报错" python3 "${ROOT}/scripts/check-bash32.py" "${TMP}/bad32.sh"
want pass "bash32: \${VAR} 写法 → 放行"       python3 "${ROOT}/scripts/check-bash32.py" "${TMP}/good32.sh"

# ── check-grep-pipe.py ──
# 坏样本同样运行时拼装，理由同上。
Q='q'
printf 'f(){ head -1 x | grep -%s pat; }\n'    "${Q}"     > "${TMP}/badgp-q.sh"
printf 'f(){ head -1 x | grep -E -%s pat; }\n' "${Q}"     > "${TMP}/badgp-later.sh"
printf 'f(){ head -1 x | grep --%s pat; }\n'   "quiet"    > "${TMP}/badgp-long.sh"
# 好样本三种形状各一行：herestring、逻辑或 `||`、整行注释里讲这个坑
{
  printf 'f(){ grep -%s pat <<<"$(head -1 x)"; }\n' "${Q}"
  printf '[ -f x ] || grep -%s pat x\n' "${Q}"
  printf '# 别写 head -1 x | grep -%s pat\n' "${Q}"
} > "${TMP}/goodgp.sh"
want fail "grep-pipe: 管道接 grep -q → 报错"            python3 "${ROOT}/scripts/check-grep-pipe.py" "${TMP}/badgp-q.sh"
want fail "grep-pipe: 管道接 grep -E -q（-q 不在第一位）→ 报错" python3 "${ROOT}/scripts/check-grep-pipe.py" "${TMP}/badgp-later.sh"
want fail "grep-pipe: 管道接 grep --quiet → 报错"       python3 "${ROOT}/scripts/check-grep-pipe.py" "${TMP}/badgp-long.sh"
want pass "grep-pipe: herestring / || / 注释 → 放行" python3 "${ROOT}/scripts/check-grep-pipe.py" "${TMP}/goodgp.sh"

# ── 零文件不算通过 ──
# 「0 处违规」和「0 个文件」退出码长得一样。validate.sh 靠 find 喂文件，
# find 表达式一旦失配就会全绿。
for c in check-bash32 check-grep-pipe; do
  want fail "${c}: 零个文件 → 不算通过" python3 "${ROOT}/scripts/${c}.py"
done

# ── check-manifests.py ──
mf() {  # $1=仓库目录 $2=claude|codex $3=清单内容（省略 = 不建这份清单）
  mkdir -p "$1"
  [ $# -ge 3 ] || return 0
  mkdir -p "$1/.$2-plugin"
  printf '%s\n' "$3" > "$1/.$2-plugin/plugin.json"
}
GOOD='{"name":"tier-guard","version":"1.2.3"}'
GOOD_CACHEBUSTER='{"name":"tier-guard","version":"1.2.3+codex.local-20260912094401"}'
mf "${TMP}/mf-good"          claude "${GOOD}"
mf "${TMP}/mf-good"          codex  "${GOOD}"
mf "${TMP}/mf-no-codex"      claude "${GOOD}"
mf "${TMP}/mf-version-drift" claude "${GOOD}"
mf "${TMP}/mf-version-drift" codex  '{"name":"tier-guard","version":"1.2.2"}'
mf "${TMP}/mf-name-drift"    claude "${GOOD}"
mf "${TMP}/mf-name-drift"    codex  '{"name":"tier-guard-codex","version":"1.2.3"}'
mf "${TMP}/mf-no-version"    claude '{"name":"tier-guard"}'
mf "${TMP}/mf-no-version"    codex  '{"name":"tier-guard"}'
mf "${TMP}/mf-cachebuster"   claude "${GOOD_CACHEBUSTER}"
mf "${TMP}/mf-cachebuster"   codex  "${GOOD_CACHEBUSTER}"
mf "${TMP}/mf-bad-build"     claude '{"name":"tier-guard","version":"1.2.3+other.local"}'
mf "${TMP}/mf-bad-build"     codex  '{"name":"tier-guard","version":"1.2.3+other.local"}'
want pass "manifests: 两份清单 name / version 一致 → 放行" python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-good"
want fail "manifests: 缺 Codex 清单 → 报错"               python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-no-codex"
want fail "manifests: 版本漂移（只升了 Claude）→ 报错"     python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-version-drift"
want fail "manifests: 名称漂移 → 报错"                    python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-name-drift"
want fail "manifests: 两边都没写 version（None == None）→ 报错" \
  python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-no-version"
want pass "manifests: Codex cachebuster 镜像版本 → 放行" \
  python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-cachebuster"
want fail "manifests: 非 Codex build metadata → 报错" \
  python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-bad-build"
# 声明的 hooks 路径必须存在（Codex 清单靠这个字段装 hook；指错了宿主静默不装）
HOOKSGOOD='{"name":"tier-guard","version":"1.2.3","hooks":"./hooks/codex-hooks.json"}'
mf "${TMP}/mf-hooks-good" claude "${GOOD}"; mf "${TMP}/mf-hooks-good" codex "${HOOKSGOOD}"
mkdir -p "${TMP}/mf-hooks-good/hooks"; printf '{}\n' > "${TMP}/mf-hooks-good/hooks/codex-hooks.json"
mf "${TMP}/mf-hooks-bad"  claude "${GOOD}"; mf "${TMP}/mf-hooks-bad"  codex "${HOOKSGOOD}"
want pass "manifests: 声明的 hooks 文件存在 → 放行"   python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-hooks-good"
want fail "manifests: 声明的 hooks 文件不存在 → 报错" python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mf-hooks-bad"
# marketplace：条目名必须等于插件名，source 必须指向插件根
mkmp() {  # $1=目录 $2=条目名 $3=source
  mf "$1" claude "${GOOD}"; mf "$1" codex "${GOOD}"
  printf '{"name":"m","owner":{"name":"o"},"plugins":[{"name":"%s","source":"%s"}]}\n' "$2" "$3" \
    > "$1/.claude-plugin/marketplace.json"
}
mkmp "${TMP}/mp-good" tier-guard ./
mkmp "${TMP}/mp-name" tier-guard-x ./
mkmp "${TMP}/mp-src"  tier-guard ./plugins/tier-guard
want pass "manifests: marketplace 条目与插件一致 → 放行"      python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mp-good"
want fail "manifests: marketplace 条目名漂移 → 报错"          python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mp-name"
want fail "manifests: marketplace source 指向不存在的插件根 → 报错" python3 "${ROOT}/scripts/check-manifests.py" "${TMP}/mp-src"

# ── check-skill-sync.py ──
# 夹具 = 真仓库那三份文件的副本；坏样本各改一处，改法用 python（sed -i 在 macOS / Linux 上写法不同）
mkskill() {  # $1=目录
  mkdir -p "$1/skills/tier-routing" "$1/config" "$1/hooks"
  cp "${ROOT}/skills/tier-routing/SKILL.md" "$1/skills/tier-routing/SKILL.md"
  cp "${ROOT}/config/routing.catalog.v2.json" "$1/config/routing.catalog.v2.json"
}
sub1() {  # $1=文件 $2=old $3=new —— old 必须恰好出现一次，否则夹具本身就是错的
  python3 - "$1" "$2" "$3" <<'PY2'
import sys
path, old, new = sys.argv[1:4]
s = open(path, encoding="utf-8").read()
assert s.count(old) == 1, f"夹具锚点失效: {old!r}"
open(path, "w", encoding="utf-8").write(s.replace(old, new))
PY2
}
SK=skills/tier-routing/SKILL.md
mkskill "${TMP}/sk-good"
mkskill "${TMP}/sk-effort"; sub1 "${TMP}/sk-effort/${SK}" '`gpt-6.1-sol` / `medium`' '`gpt-6.1-sol` / `high`'
mkskill "${TMP}/sk-nomark"; sub1 "${TMP}/sk-nomark/${SK}" '<!-- candidate-table:begin -->' ''
want pass "skill-sync: 候选能力表与 v2 catalog 一致 → 放行" python3 -B "${ROOT}/scripts/check-skill-sync.py" "${TMP}/sk-good"
want fail "skill-sync: 候选表 Codex effort 漂移 → 报错" python3 -B "${ROOT}/scripts/check-skill-sync.py" "${TMP}/sk-effort"
want fail "skill-sync: 候选表标记丢了 → 报错（不能当成没东西可比）" python3 -B "${ROOT}/scripts/check-skill-sync.py" "${TMP}/sk-nomark"

# ── check-mutation-anchors.py ──
# 夹具 = 一个最小的假仓库：一个被变异的目标文件 + 一份只含几条变异体的 mutation-check.py。
# 不复制真仓库那份（157 条，改一处就要重算），只造刚好够判定的结构。
mkanchor() {  # $1=目录 $2=目标文件内容 $3=M 列表内容
  mkdir -p "$1/scripts" "$1/hooks"
  printf '%s' "$2" > "$1/hooks/sample.py"
  { printf 'TS = "hooks/sample.py"\nSUITE = ("/bin/true",)\n'; printf 'M = [\n%s]\n' "$3"; } \
    > "$1/scripts/mutation-check.py"
}
ANCHOR_OK='def one():
    return 1


def two():
    return 2
'
ANCHOR_DUP='def one():
    return 1


def two():
    return 1
'
MLIST='    ("样本: 把 1 改成 0", TS, SUITE, """    return 1""", """    return 0""", "killed"),
'
mkanchor "${TMP}/anc-good"  "${ANCHOR_OK}"  "${MLIST}"
mkanchor "${TMP}/anc-dup"   "${ANCHOR_DUP}" "${MLIST}"
mkanchor "${TMP}/anc-empty" "${ANCHOR_OK}"  ""
mkanchor "${TMP}/anc-gone"  "${ANCHOR_OK}"  '    ("样本: 锚点早就不在了", TS, SUITE, """def three():""", """def four():""", "killed"),
'
want pass "mutation-anchors: 锚点唯一命中 → 放行" \
  python3 -B "${ROOT}/scripts/check-mutation-anchors.py" "${TMP}/anc-good"
want fail "mutation-anchors: 锚点重复 → 报错（该变异体会被整条跳过，不跑也不报失败）" \
  python3 -B "${ROOT}/scripts/check-mutation-anchors.py" "${TMP}/anc-dup"
want fail "mutation-anchors: 锚点一次都不命中 → 报错" \
  python3 -B "${ROOT}/scripts/check-mutation-anchors.py" "${TMP}/anc-gone"
want fail "mutation-anchors: 零个变异体 → 不算通过（空列表等于没这个检查）" \
  python3 -B "${ROOT}/scripts/check-mutation-anchors.py" "${TMP}/anc-empty"

# ── check-plugin-paths.py ──
mkpp() {  # $1=目录 $2=命令里引用的相对路径
  mkdir -p "$1/commands" "$1/hooks"; : > "$1/hooks/real.py"
  printf -- '---\ndescription: d\n---\n\n```bash\npython3 "%s/%s"\n```\n' '${CLAUDE_PLUGIN_ROOT}' "$2" > "$1/commands/x.md"
}
mkpp "${TMP}/pp-good" hooks/real.py
mkpp "${TMP}/pp-bad"  hooks/renamed-away.py
mkdir -p "${TMP}/pp-empty"
want pass "plugin-paths: 引用的脚本存在 → 放行"      python3 "${ROOT}/scripts/check-plugin-paths.py" "${TMP}/pp-good"
want fail "plugin-paths: 引用的脚本被改名 → 报错"    python3 "${ROOT}/scripts/check-plugin-paths.py" "${TMP}/pp-bad"
want fail "plugin-paths: 一个命令都没有 → 不算通过" python3 "${ROOT}/scripts/check-plugin-paths.py" "${TMP}/pp-empty"
# Codex 侧：hooks/ 下任意 json 里的 ${PLUGIN_ROOT}/… 也要查。
# 夹具里另放一个正常的命令 —— 否则「漏扫 codex-hooks.json」会走「零个文件」那条路照样报错，
# 反例绿了但理由是错的（变异测试抓出来过）。
mkpp "${TMP}/pp-codex" hooks/real.py
printf '{"hooks":{"PreToolUse":[{"matcher":"spawn_agent","hooks":[{"type":"command","command":"/bin/bash %s/hooks/gone.sh"}]}]}}\n' \
  '${PLUGIN_ROOT}' > "${TMP}/pp-codex/hooks/codex-hooks.json"
want fail "plugin-paths: codex-hooks.json 里 \${PLUGIN_ROOT} 指向不存在的脚本 → 报错" \
  python3 "${ROOT}/scripts/check-plugin-paths.py" "${TMP}/pp-codex"

# ── mutation-check.py ──
# 只测不跑变异的那条路径（免费）：一个变异体都没选中不算通过。
want fail "mutation-check: --only 匹配不到 → 不算通过" \
  python3 "${ROOT}/scripts/mutation-check.py" --only 不存在的关键词

echo ""
echo "  总计 ${PASS} 通过 / ${FAIL} 失败"
[ "${PASS}" -gt 0 ] && [ "${FAIL}" -eq 0 ]
