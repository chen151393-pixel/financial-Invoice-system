import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { queryParties, uploadStamp } from "../api";
import { PartyDialog } from "../components/PartyDialog";
import type { Party } from "../types";
import "../components/settlement.css";
import "../components/parties.css";

type State = { kind: "loading" } | { kind: "ready"; items: Party[] } | { kind: "error"; message: string };

/** 合同抬头：销售合同买卖双方的名称、地址、电话与印章。 */
export function SettlementPartiesPage() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState<{ party: Party | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const stampInput = useRef<HTMLInputElement>(null);
  const stampTarget = useRef<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    queryParties(controller.signal)
      .then((result) => setState({ kind: "ready", items: result.items }))
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setState({ kind: "error", message: reason instanceof Error ? reason.message : "加载失败" });
      });
    return () => controller.abort();
  }, [refresh]);

  const reload = () => setRefresh((n) => n + 1);

  async function stamp(file: File) {
    if (stampTarget.current === null) return;
    setBusy(true);
    setError("");
    try {
      await uploadStamp(stampTarget.current, file);
      reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "印章上传失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<Party>[] = [
    {
      key: "name",
      header: "匹配名称",
      width: "22%",
      render: (party) => (
        <div className="settlement-cell">
          <strong>{party.name}</strong>
          <span>{party.updatedBy} 维护</span>
        </div>
      ),
    },
    {
      key: "contract",
      header: "合同名称",
      width: "24%",
      render: (party) => (
        <div className="settlement-cell">
          {party.nameEn}
          <span>{party.nameCn || "—"}</span>
        </div>
      ),
    },
    {
      key: "address",
      header: "地址 / 电话",
      render: (party) => (
        <div className="settlement-cell">
          {party.addressEn}
          {party.addressCn && <span>{party.addressCn}</span>}
          <span>电话：{party.phone || "未填写"}</span>
        </div>
      ),
    },
    {
      key: "stamp",
      header: "印章",
      width: "90px",
      render: (party) =>
        party.hasStamp ? (
          <a href={party.stampUrl} target="_blank" rel="noreferrer" aria-label={`查看 ${party.name} 的印章`}>
            <img className="settlement-stamp" src={party.stampUrl} alt="" />
          </a>
        ) : (
          <Badge tone="warning">未上传</Badge>
        ),
    },
    {
      key: "actions",
      header: "操作",
      width: "196px",
      render: (party) => (
        <div className="settlement-party-actions">
          <Button size="sm" disabled={busy} onClick={() => setDialog({ party })}>
            修改
          </Button>
          <Button
            size="sm"
            disabled={busy}
            onClick={() => {
              stampTarget.current = party.id;
              stampInput.current?.click();
            }}
          >
            {party.hasStamp ? "更换印章" : "上传印章"}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="settlement-page settlement-parties">
      <Card>
        <CardHeader
          title="合同抬头与印章"
          description="买方匹配海关回执的境外收货人，卖方匹配 NS 申报抬头。印章建议使用透明底 PNG；资料变更后，已有合同需重新生成。"
          actions={
            <Button variant="primary" size="sm" disabled={busy} onClick={() => setDialog({ party: null })}>
              新增抬头
            </Button>
          }
        />
        <CardContent flush>
          <input
            ref={stampInput}
            type="file"
            accept="image/png,image/jpeg"
            hidden
            aria-label="选择印章图片"
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (file) void stamp(file);
            }}
          />
          {error && (
            <Alert tone="danger" title="印章未上传">
              {error}
            </Alert>
          )}
          {state.kind === "loading" && <Skeleton rows={3} label="正在读取合同抬头" />}
          {state.kind === "error" && (
            <ErrorState
              title="合同抬头读取失败"
              message={state.message}
              action={<Button onClick={reload}>重试</Button>}
            />
          )}
          {state.kind === "ready" &&
            (state.items.length ? (
              <DataTable
                label="合同抬头"
                columns={columns}
                rows={state.items}
                rowKey={(party) => String(party.id)}
                minWidth={1040}
              />
            ) : (
              <EmptyState
                title="还没有合同抬头"
                description="添加对应境外收货人与 NS 申报抬头的名称、地址，供系统匹配销售合同买卖方。"
              />
            ))}
        </CardContent>
      </Card>
      {dialog && (
        <PartyDialog
          party={dialog.party}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            reload();
          }}
        />
      )}
    </div>
  );
}
