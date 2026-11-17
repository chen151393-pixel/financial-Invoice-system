import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { createServer } from "vite";

let server, Table, api;
before(async () => {
  server = await createServer({
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: "custom",
    logLevel: "error",
  });
  ({ MatchStatusTable: Table } = await server.ssrLoadModule(
    "/src/modules/matching/components/MatchStatusTable.tsx",
  ));
  api = await server.ssrLoadModule("/src/modules/matching/api/index.ts");
});
after(async () => {
  await server?.close();
});

test("未生成建议 / 已审核通过列表展示后端状态并进入比对详情", () => {
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(Table, {
        rows: [
          {
            id: "7",
            number: "26000000000000000007",
            date: "2026-11-09",
            seller: "供应商甲",
            currency: "CNY",
            gross: "100.00",
          },
        ],
        summaries: [
          { invoiceId: "7", status: "confirmed", label: "已匹配", tier: null, proposed: 0, confirmed: 2 },
        ],
      }),
    ),
  );
  assert.match(html, /26000000000000000007/);
  assert.match(html, /100.00 CNY/);
  assert.match(html, /已匹配/);
  assert.match(html, /href="\/matching\/7"/);
});

test("审核队列把视图与置信度分段交给后端", async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), body: JSON.parse(init.body) });
    return new Response(JSON.stringify({ rows: [] }), { headers: { "content-type": "application/json" } });
  };
  try {
    await api.getMatchingQueue({
      tier: "high",
      view: "auto",
      anomaly: "all",
      supplierId: "",
      invoiceNo: "",
      supplierName: "",
      invoiceFrom: "",
      invoiceTo: "",
      page: 1,
      pageSize: 20,
    });
  } finally {
    globalThis.fetch = original;
  }
  assert.match(calls[0].url, /\/api\/matching\/invoice-queue\/query/);
  assert.equal(calls[0].body.view, "auto");
  assert.equal(calls[0].body.tier, "high");
  assert.equal(calls[0].body.invoiceFrom, null);
});
