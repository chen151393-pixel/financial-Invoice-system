import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server, View, api, Filters, emptyFilters, invoiceApi, FileUpload, UploadResults;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ InvoiceSummary: View } = await server.ssrLoadModule(
    "/src/modules/invoice/components/InvoiceSummary.tsx",
  ));
  api = await server.ssrLoadModule("/src/modules/matching/api/index.ts");
  ({ InvoiceFilters: Filters, emptyFilters } = await server.ssrLoadModule(
    "/src/modules/invoice/components/InvoiceFilters.tsx",
  ));
  invoiceApi = await server.ssrLoadModule("/src/modules/invoice/api/invoice.ts");
  ({ InvoiceFileUploadDialog: FileUpload } = await server.ssrLoadModule(
    "/src/modules/matching/components/InvoiceFileUploadDialog.tsx",
  ));
  ({ BatchUploadResults: UploadResults } = await server.ssrLoadModule(
    "/src/shared/components/ui/BatchUploadResults.tsx",
  ));
});

test("发票上传沿用拖入区和本次结果交互，保留 10 MB、比对通过和不覆盖说明", () => {
  const html = renderToStaticMarkup(
    createElement(FileUpload, { upload: async () => ({ items: [] }), onClose() {} }),
  );
  assert.match(html, /点击选择或拖入发票文件/);
  assert.match(html, /10 MB/);
  assert.match(html, /只归档比对已通过的发票/);
  assert.match(html, /不会覆盖/);
  assert.match(html, /重新打开窗口时清空上次展示/);
  assert.match(html, /type="file" multiple="" accept=".pdf,.jpg,.jpeg,.png"/);
  assert.match(html, /disabled=""[^>]*>开始上传/);
  assert.doesNotMatch(html, /100 MB|选择文件后提交|本次处理结果<\/h4>/);
});

test("发票结果显示真实失败和多处归档路径，路径折叠且仅允许指定状态补号码", () => {
  const result = (index, status) => ({
    index,
    file: null,
    target: "",
    result: {
      filename: `发票${index}.pdf`,
      target: status === "saved" ? "260000000001" : "",
      status,
      reason: status === "saved" ? "已归档两张报关单" : "后端拒绝归档",
      paths: status === "saved" ? ["共享盘/CD870/发票.pdf", "共享盘/CD871/发票.pdf"] : [],
    },
  });
  const props = {
    rows: [result(0, "saved"), result(1, "unmatched"), result(2, "conflict")],
    busy: false,
    targetLabel: "发票号码",
    targetMaxLength: 100,
    statusLabels: { saved: "已保存", unmatched: "未识别发票号码", conflict: "已有不同文件，未覆盖" },
    assignable: ["unmatched", "ambiguous"],
    onAssign() {},
    onRetry() {},
  };
  const html = renderToStaticMarkup(createElement(UploadResults, props));
  assert.match(html, /文件 \/ 发票号码/);
  assert.match(html, /已有不同文件，未覆盖/);
  assert.match(html, /后端拒绝归档/);
  assert.match(html, /共享盘\/CD870\/发票.pdf/);
  assert.match(html, /共享盘\/CD871\/发票.pdf/);
  assert.match(html, /<details class="ui-upload__paths"><summary>查看保存位置/);
  assert.equal((html.match(/指定发票号码/g) || []).length, 1);
  assert.match(html, /min-width:0/);
  assert.match(html, /disabled=""[^>]*>按此编号重新上传/);
  const filled = renderToStaticMarkup(
    createElement(UploadResults, {
      ...props,
      busy: true,
      rows: [{ ...result(1, "unmatched"), target: "260000000002" }],
    }),
  );
  assert.match(filled, /value="260000000002"/);
  assert.match(filled, /disabled=""[^>]*>按此编号重新上传/);
});
after(async () => {
  await server?.close();
});

const data = {
  amounts: [
    {
      currency: "CNY",
      count: 50,
      gross: "2446196.97",
      tax: "281420.89",
      pendingAmount: "120.500001",
      pendingCount: 2,
      reviewAmount: "20.00",
      reviewCount: 1,
    },
  ],
};
const render = (props = {}) =>
  renderToStaticMarkup(createElement(View, { data, loading: false, error: "", ...props }));

test("展示后端全范围金额与计数，不在前端推算或截断小数", () => {
  const html = render();
  for (const value of [
    "2,446,196.97",
    "281,420.89",
    "120.500001",
    "20.00",
    "50 张发票",
    "2 张发票",
    "1 张发票",
  ])
    assert.ok(html.includes(value));
  assert.match(html, />票面税额</);
  assert.match(html, />待复核金额</);
  assert.doesNotMatch(html, /对应业务数据尚未接入|>可抵扣税额</);
});

test("加载和失败隐藏旧数值，空筛选与真实零金额分别显示", () => {
  for (const props of [{ loading: true }, { error: "读取失败" }]) {
    const html = render(props);
    assert.doesNotMatch(html, /2,446,196.97|>0.00</);
    assert.match(html, /正在统计|统计读取失败/);
  }
  assert.match(render({ data: { amounts: [] } }), /当前筛选无发票/);
  assert.match(
    render({ data: { amounts: [{ ...data.amounts[0], pendingAmount: "0", pendingCount: 0 }] } }),
    /¥ 0.00/,
  );
});

test("不同币种分行显示，未知金额不冒充零", () => {
  const html = render({
    data: { amounts: [data.amounts[0], { ...data.amounts[0], currency: "USD", tax: null }] },
  });
  assert.match(html, /USD 2,446,196.97/);
  assert.match(html, /USD —/);
});

test("统计请求只携带已应用筛选，不携带页码或金额", async (t) => {
  let seen;
  t.mock.method(globalThis, "fetch", async (url) => {
    seen = new URL(url, "http://localhost");
    return Response.json(data);
  });
  const result = await api.getInvoiceTotals({
    q: "测试供应商",
    invoice_no: "9501",
    seller_name: "供应商",
    seller_tax_no: "9131",
    account: "professional:account-a",
    status: "normal",
    date_from: "2026-10-01",
    date_to: "2026-10-19",
    page: 2,
    pageSize: 10,
    version: 1,
  });
  assert.deepEqual(result, data);
  assert.equal(seen.pathname, "/api/matching/invoice-totals");
  assert.deepEqual(Object.fromEntries(seen.searchParams), {
    q: "测试供应商",
    invoice_no: "9501",
    seller_name: "供应商",
    seller_tax_no: "9131",
    account: "professional:account-a",
    status: "normal",
    date_from: "2026-10-01",
    date_to: "2026-10-19",
  });
});

test("号码、供应商和税号独立显示并分别更新，清空后不再提示未应用条件", () => {
  const draft = { ...emptyFilters, invoice_no: "9501", seller_name: "供应商", seller_tax_no: "9131" };
  let changed;
  const props = {
    draft,
    applied: emptyFilters,
    loading: false,
    onChange(value) {
      changed = value;
    },
    onSubmit() {},
    onReset() {},
    onRefresh() {},
  };
  const html = renderToStaticMarkup(createElement(Filters, props));
  assert.doesNotMatch(html, /发票 \/ 供应商 \/ 税号/);
  for (const label of ["发票号码", "供应商", "供应商税号"]) assert.match(html, new RegExp(label));
  const form = Filters(props).props.children[0];
  for (const [index, key] of ["invoice_no", "seller_name", "seller_tax_no"].entries()) {
    form.props.children[index].props.children.props.onChange({ target: { value: "新条件" } });
    assert.deepEqual(changed, { ...draft, [key]: "新条件" });
  }
  assert.doesNotMatch(
    renderToStaticMarkup(
      createElement(Filters, {
        ...props,
        draft: emptyFilters,
        applied: emptyFilters,
      }),
    ),
    /当前结果仍对应上次查询/,
  );
});

test("账套筛选展示后端名称、选中项和未应用提示，包含加载及失败状态", () => {
  const props = {
    draft: { ...emptyFilters, account: "account-a" },
    applied: emptyFilters,
    accounts: { items: [{ value: "account-a", label: "测试账套（专业版）" }], loading: false, error: "" },
    onChange() {},
    onSubmit() {},
    onReset() {},
    onRefresh() {},
    loading: false,
  };
  const html = renderToStaticMarkup(createElement(Filters, props));
  assert.match(html, /全部账套/);
  assert.match(html, /value="account-a" selected="">测试账套（专业版）/);
  assert.match(html, /当前结果仍对应上次查询/);
  for (const accounts of [
    { items: [], loading: true, error: "" },
    { items: [], loading: false, error: "账套选项读取失败" },
  ]) {
    const state = renderToStaticMarkup(createElement(Filters, { ...props, draft: emptyFilters, accounts }));
    assert.match(state, /select disabled=""/);
    assert.match(state, /正在读取账套|账套选项读取失败/);
  }
});

test("账套选项使用本地只读接口", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/sync/lemon/invoices/accounts");
    assert.equal(options.method, "GET");
    return Response.json({ items: [] });
  });
  assert.deepEqual(await invoiceApi.getInvoiceAccounts(), { items: [] });
});

test("按匹配状态筛选的列表请求带全部筛选条件与匹配状态，空日期提交 null", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ list: { rows: [] }, counts: { all: 0 }, summaries: [], notice: "" });
  });
  await api.queryInvoiceMatchList({
    ...emptyFilters,
    invoice_no: "9501",
    seller_name: "供应商",
    seller_tax_no: "9131",
    date_from: "2026-10-01",
    matchStatus: "proposed",
    page: 2,
    pageSize: 50,
  });
  assert.match(calls[0].url, /\/api\/matching\/invoices\/query$/);
  assert.deepEqual(calls[0].body, {
    invoice_no: "9501",
    seller_name: "供应商",
    seller_tax_no: "9131",
    account: "",
    status: "",
    date_from: "2026-10-01",
    date_to: null,
    matchStatus: "proposed",
    page: 2,
    page_size: 50,
  });
});

test("不参与比对的发票显示后端文字且不标为待处理", async () => {
  const { InvoiceTable } = await server.ssrLoadModule("/src/modules/invoice/components/InvoiceTable.tsx");
  const row = {
    id: "9",
    number: "26000000000000007703",
    date: "2026-10-10",
    seller: "供应商",
    sellerTaxNo: "",
    type: "数电发票",
    businessType: "",
    status: "作废",
    sourceStatus: "void",
    displayStatus: "void",
    statusNotice: "",
    currency: "CNY",
    net: "8.00",
    tax: "1.04",
    gross: "9.04",
    lineCount: 1,
    importedAt: "2026-10-27T01:00:00Z",
    source: "Excel导入",
  };
  const summary = {
    invoiceId: "9",
    status: "excluded",
    label: "不参与比对",
    tier: null,
    proposed: 0,
    confirmed: 0,
  };
  const html = renderToStaticMarkup(
    createElement(InvoiceTable, {
      rows: [row],
      matching: { 9: summary },
      matchingError: "",
      onMatch() {},
      onDetail() {},
    }),
  );
  assert.match(html, /不参与比对/);
  assert.match(html, /invoice-list__match-state--neutral/);
});
