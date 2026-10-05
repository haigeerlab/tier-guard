"""参考实现：只用来验证测试夹具本身可被通过，不给子代理看。"""
import re
from collections import OrderedDict

ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
         (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]

REF = {}

REF["01-duration"] = '''
import re
def parse_duration(s):
    m = re.fullmatch(r"(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?", s or "")
    if not s or not m or not any(m.groups()):
        raise ValueError(s)
    h, mi, se = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mi * 60 + se
'''

REF["02-lru"] = '''
from collections import OrderedDict
class LRUCache:
    def __init__(self, capacity):
        self.cap = capacity; self.d = OrderedDict()
    def get(self, k):
        if k not in self.d: return -1
        self.d.move_to_end(k); return self.d[k]
    def put(self, k, v):
        if self.cap <= 0: return
        self.d[k] = v; self.d.move_to_end(k)
        if len(self.d) > self.cap: self.d.popitem(last=False)
'''

REF["03-semver"] = '''
def normalize_semver(s):
    s = (s or "").strip()
    if s.startswith("v"): s = s[1:]
    parts = s.split(".")
    if not s or len(parts) > 3: raise ValueError(s)
    for p in parts:
        if not p.isdigit() or (len(p) > 1 and p[0] == "0"): raise ValueError(s)
    parts += ["0"] * (3 - len(parts))
    return ".".join(parts)
'''

REF["04-rle"] = '''
import re
def rle_encode(s):
    return "".join(f"{len(m.group(0))}{m.group(1)}" for m in re.finditer(r"(.)\\1*", s))
def rle_decode(s):
    if s == "": return ""
    if not re.fullmatch(r"(?:\\d+[a-zA-Z])+", s): raise ValueError(s)
    out = []
    for n, c in re.findall(r"(\\d+)([a-zA-Z])", s):
        if int(n) == 0: raise ValueError(s)
        out.append(c * int(n))
    return "".join(out)
'''

REF["05-intervals"] = '''
def merge_intervals(xs):
    out = []
    for a, b in sorted([list(x) for x in xs]):
        if out and a <= out[-1][1]: out[-1][1] = max(out[-1][1], b)
        else: out.append([a, b])
    return out
'''

REF["06-csv"] = '''
def parse_csv_line(line):
    out, cur, i, q = [], [], 0, False
    while i < len(line):
        c = line[i]
        if q:
            if c == '"':
                if i + 1 < len(line) and line[i + 1] == '"': cur.append('"'); i += 1
                else: q = False
            else: cur.append(c)
        else:
            if c == '"': q = True
            elif c == ",": out.append("".join(cur)); cur = []
            else: cur.append(c)
        i += 1
    if q: raise ValueError(line)
    out.append("".join(cur))
    return out
'''

REF["07-roman"] = '''
R = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
     (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
def to_roman(n):
    if not isinstance(n, int) or not 1 <= n <= 3999: raise ValueError(n)
    out = []
    for v, s in R:
        while n >= v: out.append(s); n -= v
    return "".join(out)
def from_roman(s):
    vals = {s2: v for v, s2 in R}
    i, total = 0, 0
    while i < len(s):
        if s[i:i+2] in vals: total += vals[s[i:i+2]]; i += 2
        elif s[i] in vals: total += vals[s[i]]; i += 1
        else: raise ValueError(s)
    if not s or not 1 <= total <= 3999 or to_roman(total) != s: raise ValueError(s)
    return total
'''

REF["08-bucket"] = '''
class TokenBucket:
    def __init__(self, capacity, refill_per_sec, clock):
        self.cap, self.rate, self.clock = capacity, refill_per_sec, clock
        self.tokens, self.t = float(capacity), clock()
    def try_take(self, n=1):
        now = self.clock()
        self.tokens = min(self.cap, self.tokens + (now - self.t) * self.rate); self.t = now
        if n > self.cap or n > self.tokens: return False
        self.tokens -= n; return True
'''

REF["09-dictdiff"] = '''
def dict_diff(old, new):
    return {"added": {k: new[k] for k in new if k not in old},
            "removed": {k: old[k] for k in old if k not in new},
            "changed": {k: (old[k], new[k]) for k in old if k in new and old[k] != new[k]}}
'''

REF["10-ini"] = '''
def parse_ini(text):
    out, sec = {}, ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in ";#": continue
        if line.startswith("[") and line.endswith("]"):
            sec = line[1:-1]; out.setdefault(sec, {}); continue
        if "=" not in line: raise ValueError(raw)
        k, v = line.split("=", 1)
        out.setdefault(sec, {})[k.strip()] = v.strip()
    return out
'''
