import subprocess, json, os
from collections import Counter

LAUNCHER = "C:/Users/Admin/.workbuddy/skills/lemonclaw/launcher/lemonclaw_launcher.py"
PY = "C:/Users/Admin/.workbuddy/binaries/python/versions/3.13.12/python.exe"
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run_launcher(args, stdin=None):
    cmd = [PY, LAUNCHER] + args
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, timeout=150)
    return p.stdout


run_launcher(["account", "select", "--index", "3"])
run_json = json.dumps({"query": {}, "body": {"startDate": "2010-01-01", "endDate": "2030-12-31"}, "_outputMode": "full"}, ensure_ascii=False)
out = run_launcher(["action", "run", "acc", "invoice-purchase-entry-list", "--json-stdin"], stdin=run_json)
data = json.loads(out)
inner = data.get("data", {})
rows = inner.get("数据", {}).get("data", [])
print("total in data.总数 =", inner.get("总数"), "rows fetched =", len(rows))

dates = []
for r in rows:
    d = r.get("开票日期") or r.get("invoiceDate") or ""
    if d:
        # invoiceDate may be ISO datetime; 开票日期 is yyyy-mm-dd
        d = str(d)[:10]
        dates.append(d)

if dates:
    dates_sorted = sorted(dates)
    print("MIN 开票日期 =", dates_sorted[0])
    print("MAX 开票日期 =", dates_sorted[-1])
    ym = Counter(d[:7] for d in dates)
    print("月份分布 (yyyy-mm: 明细行数):")
    for k in sorted(ym):
        print(f"  {k}: {ym[k]}")
    # 去重发票视角
    inv = set((r.get("发票号码"), r.get("开票日期")) for r in rows)
    print("去重发票数(发票号码+开票日期) =", len(inv))
else:
    print("no dates found")
