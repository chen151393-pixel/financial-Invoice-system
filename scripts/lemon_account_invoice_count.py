import subprocess, json, os, sys

LAUNCHER = "C:/Users/Admin/.workbuddy/skills/lemonclaw/launcher/lemonclaw_launcher.py"
PY = "C:/Users/Admin/.workbuddy/binaries/python/versions/3.13.12/python.exe"
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

names = {
    1: "上海绎色数码科技有限公司",
    2: "上海亦络文化传媒有限公司",
    3: "山东米卡乐工贸有限公司",
    4: "上海毅烁供应链管理有限公司",
    5: "上海驿川供应链管理有限公司",
    6: "上海毅鑫实业有限公司",
    7: "上海泽尔电子商务有限公司",
    8: "上海绎视数码科技有限公司",
}
editions = {1: "免费版", 2: "免费版", 3: "专业版", 4: "专业版", 5: "专业版", 6: "专业版", 7: "专业版", 8: "专业版"}


def run_launcher(args, stdin=None):
    cmd = [PY, LAUNCHER] + args
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, timeout=150)
    return p.stdout, p.stderr, p.returncode


def extract_total(out):
    try:
        data = json.loads(out)
    except Exception as e:
        return None, f"parse-error:{e}", out[:400]
    if not data.get("ok"):
        return None, f"api-error:{data.get('error')}", json.dumps(data, ensure_ascii=False)[:400]
    block = data.get("data", {})
    total = block.get("总数")
    rows = block.get("数据")
    if isinstance(rows, list):
        count = len(rows)
    elif isinstance(rows, dict):
        count = len(rows.get("data", []))
    else:
        count = None
    return total, count, None


results = []
for idx in [1, 2, 3, 4, 5, 6, 7, 8]:
    sel_out, sel_err, sel_rc = run_launcher(["account", "select", "--index", str(idx)])
    run_json = json.dumps({
        "query": {},
        "body": {"startDate": "2010-01-01", "endDate": "2030-12-31"},
        "_outputMode": "full",
    }, ensure_ascii=False)
    out, err, rc = run_launcher(["action", "run", "acc", "invoice-purchase-paging-list", "--json-stdin"], stdin=run_json)
    total, count, errmsg = extract_total(out)
    results.append({
        "idx": idx,
        "name": names[idx],
        "edition": editions[idx],
        "total": total,
        "count": count,
        "err": errmsg,
        "select_rc": sel_rc,
    })
    print(f"[{idx}] {names[idx]} total={total} count={count} err={errmsg}", flush=True)

with open("D:/ai/feiShu/Financial-Invoice-System/caiwufapiaoxitonghedui/data/lemon_account_invoice_count.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("DONE")
