import subprocess, json, os

LAUNCHER = "C:/Users/Admin/.workbuddy/skills/lemonclaw/launcher/lemonclaw_launcher.py"
PY = "C:/Users/Admin/.workbuddy/binaries/python/versions/3.13.12/python.exe"
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

names = {
    3: "山东米卡乐工贸有限公司",
    4: "上海毅烁供应链管理有限公司",
    8: "上海绎视数码科技有限公司",
}
editions = {3: "专业版", 4: "专业版", 8: "专业版"}


def run_launcher(args, stdin=None):
    cmd = [PY, LAUNCHER] + args
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, timeout=150)
    return p.stdout


def extract_entry(out):
    try:
        data = json.loads(out)
    except Exception as e:
        return None, f"parse-error:{e}", out[:400]
    if not data.get("ok"):
        return None, f"api-error:{data.get('error')}", json.dumps(data, ensure_ascii=False)[:400]
    block = data.get("数据") if "数据" in data else data.get("data", {})
    if isinstance(block, dict):
        total = block.get("总数")
        rows = block.get("data", [])
        count = len(rows) if isinstance(rows, list) else None
    else:
        total, count = None, None
    return total, count, None


results = []
for idx in [3, 4, 8]:
    run_launcher(["account", "select", "--index", str(idx)])
    run_json = json.dumps({
        "query": {},
        "body": {"startDate": "2010-01-01", "endDate": "2030-12-31"},
        "_outputMode": "full",
    }, ensure_ascii=False)
    out = run_launcher(["action", "run", "acc", "invoice-purchase-entry-list", "--json-stdin"], stdin=run_json)
    total, count, err = extract_entry(out)
    results.append({
        "idx": idx,
        "name": names[idx],
        "edition": editions[idx],
        "detail_total": total,
        "detail_rows_page1": count,
        "err": err,
    })
    print(f"[{idx}] {names[idx]} detail_total={total} page1_rows={count} err={err}", flush=True)

with open("D:/ai/feiShu/Financial-Invoice-System/caiwufapiaoxitonghedui/data/lemon_account_detail_count.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("DONE")
