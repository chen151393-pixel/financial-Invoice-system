import subprocess, json, os

LAUNCHER = "C:/Users/Admin/.workbuddy/skills/lemonclaw/launcher/lemonclaw_launcher.py"
PY = "C:/Users/Admin/.workbuddy/binaries/python/versions/3.13.12/python.exe"
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run_launcher(args, stdin=None):
    cmd = [PY, LAUNCHER] + args
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, timeout=150)
    return p.stdout


# 选书 8（上海绎视数码）做结构诊断
run_launcher(["account", "select", "--index", "8"])
run_json = json.dumps({"query": {}, "body": {"startDate": "2010-01-01", "endDate": "2030-12-31"}, "_outputMode": "full"}, ensure_ascii=False)
out = run_launcher(["action", "run", "acc", "invoice-purchase-paging-list", "--json-stdin"], stdin=run_json)
data = json.loads(out)
print("TOP KEYS:", list(data.keys()))
print("data keys:", list(data.get("data", {}).keys()))
d = data.get("数据") if "数据" in data.get("data", {}) else data.get("data")
print("数据 block type:", type(d))
if isinstance(d, dict):
    print("数据 block keys:", list(d.keys()))
    for k, v in d.items():
        if k != "data":
            print(f"  {k} = {v!r}")
        else:
            print(f"  data (rows) len = {len(v) if isinstance(v, list) else 'n/a'}")
