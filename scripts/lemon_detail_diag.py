import subprocess, json, os

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
top = data.get("data", {})
print("TOP data type:", type(top))
if isinstance(top, dict):
    print("TOP data keys:", list(top.keys()))
    for k, v in top.items():
        if k != "数据" and k != "data":
            print(f"  {k} = {v!r}")
        else:
            print(f"  {k} type={type(v).__name__} len={len(v) if hasattr(v,'__len__') else 'n/a'}")
    # 若 数据 是 dict，再下一层
    sub = top.get("数据")
    if isinstance(sub, dict):
        print("  数据(dict) keys:", list(sub.keys()))
        print("  数据.总数 =", sub.get("总数"))
        print("  数据.data len =", len(sub.get("data", [])) if isinstance(sub.get("data"), list) else "n/a")
        rows = sub.get("data", [])
        if rows:
            print("  sample row:", json.dumps(rows[0], ensure_ascii=False)[:300])
    elif isinstance(sub, list):
        print("  数据(list) len =", len(sub))
        if sub:
            print("  sample row:", json.dumps(sub[0], ensure_ascii=False)[:300])
else:
    print("top not dict:", str(top)[:300])
