"""生成 10 个 L2 任务夹具：每个任务 = 规格说明 + 自动测试。评分时用这里的原始测试副本。"""
import os
import sys

ROOT = sys.argv[1]

TASKS = {}

TASKS["01-duration"] = (
    "实现 parse_duration(s)：把 '1h30m'、'45s'、'2h'、'1h0m5s' 这类字符串转成总秒数（int）。"
    "单位只有 h/m/s，按此顺序可省略任意部分，每个单位最多出现一次。"
    "非法输入（空串、未知单位、顺序颠倒如 '5s1h'、负数、单位重复）抛 ValueError。",
    r'''
from solution import parse_duration
assert parse_duration('1h30m') == 5400
assert parse_duration('45s') == 45
assert parse_duration('2h') == 7200
assert parse_duration('1h0m5s') == 3605
for bad in ['', '5x', '5s1h', '-3s', 'h', '1h1h']:
    try:
        parse_duration(bad)
        raise SystemExit(f'应拒绝 {bad!r}')
    except ValueError:
        pass
''')

TASKS["02-lru"] = (
    "实现 class LRUCache(capacity)：get(key) 命中返回值并标记为最近使用，未命中返回 -1；"
    "put(key, value) 插入或更新（更新也算最近使用），超容量时淘汰最久未使用的项。"
    "get/put 均摊 O(1)。capacity<=0 时 put 不存任何东西。",
    r'''
from solution import LRUCache
c = LRUCache(2); c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)
assert c.get(2) == -1
c.put(4, 4)
assert c.get(1) == -1 and c.get(3) == 3 and c.get(4) == 4
c.put(3, 30); assert c.get(3) == 30
z = LRUCache(0); z.put(1, 1); assert z.get(1) == -1
''')

TASKS["03-semver"] = (
    "实现 normalize_semver(s)：接受 'v1.2.3'、'1.2'、'1'、' 1.2.3 ' 等，"
    "返回规范化的 'MAJOR.MINOR.PATCH'（缺省部分补 0、去掉前导 v 与首尾空白）。"
    "每段必须是非负整数且不能有前导零（'01' 非法，'0' 合法），最多三段。非法输入抛 ValueError。",
    r'''
from solution import normalize_semver as n
assert n('v1.2.3') == '1.2.3'
assert n('1.2') == '1.2.0'
assert n('1') == '1.0.0'
assert n(' 1.2.3 ') == '1.2.3'
assert n('0.0.0') == '0.0.0'
for bad in ['01.2.3', '1.2.3.4', 'a.b.c', '', '1..2', '-1.0.0', 'v']:
    try:
        n(bad)
        raise SystemExit(f'应拒绝 {bad!r}')
    except ValueError:
        pass
''')

TASKS["04-rle"] = (
    "实现 rle_encode(s) 与 rle_decode(s)：编码把连续重复字符写成「次数+字符」"
    "（'aaabcc' -> '3a1b2c'），解码为其逆运算，次数可以是多位数。输入只含字母。"
    "必须满足 rle_decode(rle_encode(x)) == x。解码遇到格式错误（缺字符、以数字结尾、次数为 0）抛 ValueError。",
    r'''
from solution import rle_encode as e, rle_decode as d
assert e('aaabcc') == '3a1b2c'
assert e('') == ''
assert e('a') == '1a'
assert d('3a1b2c') == 'aaabcc'
assert d('12z') == 'z' * 12
for s in ['', 'abc', 'z' * 15, 'aabbaa']:
    assert d(e(s)) == s
for bad in ['3', 'a', '0a', '3a2']:
    try:
        d(bad)
        raise SystemExit(f'应拒绝 {bad!r}')
    except ValueError:
        pass
''')

TASKS["05-intervals"] = (
    "实现 merge_intervals(xs)：输入 [[start,end], ...]（整数，start<=end，无序），"
    "合并所有重叠或首尾相接的区间（[1,3] 与 [3,5] 视为相接，合并为 [1,5]），"
    "返回按 start 升序的结果列表。不得修改输入。",
    r'''
from solution import merge_intervals as m
assert m([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]
assert m([[1, 4], [4, 5]]) == [[1, 5]]
assert m([]) == []
assert m([[5, 6], [1, 2]]) == [[1, 2], [5, 6]]
assert m([[1, 10], [2, 3], [4, 5]]) == [[1, 10]]
src = [[3, 4], [1, 2]]; m(src); assert src == [[3, 4], [1, 2]], '不得修改输入'
''')

TASKS["06-csv"] = (
    "实现 parse_csv_line(line)：解析单行 CSV，返回字段列表。字段可用双引号包裹；"
    "引号内可含逗号；引号内用两个连续双引号表示一个双引号字符。"
    "未包裹的字段原样保留（不去空白）。引号未闭合抛 ValueError。",
    r'''
from solution import parse_csv_line as p
Q = '"'
assert p('a,b,c') == ['a', 'b', 'c']
assert p(Q + 'a,b' + Q + ',c') == ['a,b', 'c']
assert p(Q + 'say ' + Q + Q + 'hi' + Q + Q + Q + ',x') == ['say ' + Q + 'hi' + Q, 'x']
assert p('') == ['']
assert p('a,,c') == ['a', '', 'c']
assert p(' a , b') == [' a ', ' b']
try:
    p(Q + 'open,x')
    raise SystemExit('应拒绝未闭合引号')
except ValueError:
    pass
''')

TASKS["07-roman"] = (
    "实现 to_roman(n) 与 from_roman(s)：整数 1..3999 与标准罗马数字互转"
    "（使用减法记法：IV, IX, XL, XC, CD, CM）。to_roman 越界抛 ValueError；"
    "from_roman 只接受规范写法（'IIII'、'VX'、'IC' 等非规范或非法写法抛 ValueError）。",
    r'''
from solution import to_roman as t, from_roman as f
assert t(1994) == 'MCMXCIV' and t(3999) == 'MMMCMXCIX' and t(4) == 'IV'
assert f('MCMXCIV') == 1994 and f('LVIII') == 58
for i in range(1, 4000):
    assert f(t(i)) == i
for bad in [0, 4000, -1]:
    try:
        t(bad)
        raise SystemExit(f'应拒绝 {bad}')
    except ValueError:
        pass
for bad in ['IIII', 'VX', 'IC', '', 'ABC']:
    try:
        f(bad)
        raise SystemExit(f'应拒绝 {bad!r}')
    except ValueError:
        pass
''')

TASKS["08-bucket"] = (
    "实现 class TokenBucket(capacity, refill_per_sec, clock)：clock 是无参可调用对象，"
    "返回当前时间（秒，float），用于可测试性。try_take(n=1) 先按经过时间补充令牌"
    "（不超过 capacity），够则扣除并返回 True，否则返回 False 且不扣。初始为满。"
    "n 大于 capacity 永远返回 False。",
    r'''
from solution import TokenBucket
now = [0.0]
clk = lambda: now[0]
b = TokenBucket(3, 1.0, clk)
assert b.try_take() and b.try_take() and b.try_take()
assert not b.try_take()
now[0] = 1.0; assert b.try_take(); assert not b.try_take()
now[0] = 100.0; assert b.try_take(3); assert not b.try_take()
assert not TokenBucket(2, 1.0, clk).try_take(5)
now[0] = 0.0; c = TokenBucket(5, 2.0, clk); assert c.try_take(5)
now[0] = 1.0; assert c.try_take(2) and not c.try_take(1)
''')

TASKS["09-dictdiff"] = (
    "实现 dict_diff(old, new)：返回 {'added': {...}, 'removed': {...}, "
    "'changed': {k: (old_v, new_v)}}。只比较顶层键；值相等判定用 ==。"
    "三个子字典即使为空也必须存在。不得修改输入。",
    r'''
from solution import dict_diff as d
r = d({'a': 1, 'b': 2, 'c': 3}, {'a': 1, 'b': 20, 'd': 4})
assert r == {'added': {'d': 4}, 'removed': {'c': 3}, 'changed': {'b': (2, 20)}}
assert d({}, {}) == {'added': {}, 'removed': {}, 'changed': {}}
assert d({'x': [1]}, {'x': [1]}) == {'added': {}, 'removed': {}, 'changed': {}}
o, n = {'k': 1}, {'k': 2}; d(o, n); assert o == {'k': 1} and n == {'k': 2}
''')

TASKS["10-ini"] = (
    "实现 parse_ini(text)：解析 INI 文本，返回 {section: {key: value}}。规则："
    "'[name]' 开启节；'key = value' 或 'key=value'，键和值都去首尾空白；"
    "以 ';' 或 '#' 开头的行与空行忽略；节外的键值对归入 '' 节（仅当确实有这类键时才出现 '' 节）；"
    "同一节重复的键以后者为准；同名节重复出现时合并；不符合任何格式的非空行抛 ValueError。",
    r'''
from solution import parse_ini as p
t = "; c\ntop = 1\n[db]\nhost = localhost\nport=5432\n# x\n[db]\nport = 6543\n"
assert p(t) == {'': {'top': '1'}, 'db': {'host': 'localhost', 'port': '6543'}}
assert p('[a]\nk=v') == {'a': {'k': 'v'}}
assert p('') == {}
try:
    p('[a]\ngarbage line')
    raise SystemExit('应拒绝无法解析的行')
except ValueError:
    pass
''')

for name, (spec, test) in TASKS.items():
    d = os.path.join(ROOT, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "task.md"), "w", encoding="utf-8") as fh:
        fh.write(spec + "\n")
    with open(os.path.join(d, "test_solution.py"), "w", encoding="utf-8") as fh:
        fh.write(test.lstrip("\n") + "print('PASS')\n")
print(f"生成 {len(TASKS)} 个任务")
