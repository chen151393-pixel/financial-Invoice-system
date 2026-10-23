import { useState } from "react";
import { useNavigate } from "react-router";
import { writebackRequestPath } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { DemoBanner } from "../components/DemoBanner";
import { NotConnected } from "../components/NotConnected";
import { WriteSwitchStatus } from "../components/WriteSwitchStatus";
import { WritebackFilters } from "../components/WritebackFilters";
import { WritebackTable } from "../components/WritebackTable";
import { useCreatePreview } from "../hooks/useCreatePreview";
import { useWritebackList } from "../hooks/useWritebackList";
import { PHASE_TABS, type WritebackQuery } from "../types";
import "../writeback.css";
import "../writeback-list.css";

const initial: WritebackQuery = {
  phase: "",
  vendor: "",
  invoiceNo: "",
  dateFrom: "",
  dateTo: "",
  page: 1,
  pageSize: 20,
};

export function WritebackListPage() {
  const [query, setQuery] = useState(initial);
  const { status, data, error, refresh } = useWritebackList(query);
  const navigate = useNavigate();
  const preview = useCreatePreview((requestId) => navigate(writebackRequestPath(requestId)));
  if (status === "notConnected") return <NotConnected scope="回写列表暂无可用数据。" />;
  return (
    <div className="wb-stack">
      <DemoBanner />
      {data && <WriteSwitchStatus write={data.write} />}
      <WritebackFilters
        value={query}
        disabled={status === "loading"}
        onSubmit={(filters) => setQuery({ ...query, ...filters, page: 1 })}
      />
      <section className="wb-panel wb-panel--flush" aria-label="回写记录">
        <div className="wb-tabs" role="group" aria-label="按回写状态筛选">
          {PHASE_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className="wb-tab"
              aria-pressed={query.phase === tab.value}
              onClick={() => setQuery({ ...query, phase: tab.value, page: 1 })}
            >
              {tab.label}
              {data?.counts[tab.key] !== undefined && (
                <span className="wb-muted"> {data.counts[tab.key]}</span>
              )}
            </button>
          ))}
        </div>
        {status === "loading" && (
          <p role="status" className="wb-state">
            正在读取回写记录…
          </p>
        )}
        {status === "error" && (
          <div className="wb-state">
            <p role="alert" className="wb-error">
              {error}
            </p>
            <Button onClick={refresh}>重新读取</Button>
          </div>
        )}
        {status === "ready" && data && data.items.length === 0 && (
          <p className="wb-state">当前条件下没有回写记录，可修改条件后重新查询。</p>
        )}
        {status === "ready" && data && data.items.length > 0 && (
          <>
            <WritebackTable
              items={data.items}
              busyInvoice={preview.busyInvoice}
              error={preview.error}
              onPreview={(invoiceId) => void preview.create(invoiceId)}
            />
            <Pagination
              label="回写记录"
              total={data.total}
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[20, 50, 100]}
              onPageChange={(page) => setQuery({ ...query, page })}
              onPageSizeChange={(pageSize) => setQuery({ ...query, pageSize, page: 1 })}
            />
          </>
        )}
      </section>
    </div>
  );
}
