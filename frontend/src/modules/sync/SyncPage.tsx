import { useEffect, useState, type ReactNode } from "react";
import { openLocalSession } from "../identity/api";
import { Button } from "../../shared/components/Button";
import { getSources, type Sources, type SourceKind } from "./api";
import "./sync.css";
import { PullPanel } from "./PullPanel";
import { SyncOverview } from "./SyncOverview";

export default function SyncPage({
  source,
  children,
}: {
  source: "ns" | "lemon" | "overview";
  children?: ReactNode;
}) {
  const [pulling, setPulling] = useState(false);
  const [sources, setSources] = useState<Sources | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selectedKind, setSelectedKind] = useState<SourceKind>("customs-declarations");
  useEffect(() => {
    if (source !== "ns") return;
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getSources();
        if (active) {
          setSources(data);
          setError("");
        }
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取配置失败");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [attempt, source]);
  return (
    <div className={`sync-page${source === "ns" ? " sync-page--ns" : ""}`}>
      {source === "overview" && <SyncOverview />}
      {error && (
        <div role="alert" className="sync-page__panel">
          <p>{error}</p>
          <Button
            onClick={() => {
              setError("");
              setAttempt((value) => value + 1);
            }}
          >
            重新加载配置
          </Button>
        </div>
      )}
      {source === "ns" && !sources && !error && <p role="status">正在读取连接配置…</p>}
      {source === "ns" && sources && (
        <div className="sync-page__workspace">
          <fieldset className="sync-page__selector" disabled={pulling}>
            <legend>单据类型</legend>
            <div className="sync-page__choices">
              {sources.sources.map((item) => (
                <label
                  key={item.kind}
                  className="sync-page__choice"
                  htmlFor={`sync-kind-${item.kind}`}
                  aria-label={item.label}
                >
                  <input
                    id={`sync-kind-${item.kind}`}
                    type="radio"
                    name="ns-document-kind"
                    value={item.kind}
                    checked={selectedKind === item.kind}
                    onChange={() => setSelectedKind(item.kind)}
                  />
                  <span>
                    <strong>{item.label}</strong>
                    <small
                      className="sync-page__kind-tag"
                      data-level={item.storageAllowed ? "save" : item.allowed ? "read" : "off"}
                    >
                      {item.storageAllowed ? "可保存" : item.allowed ? "仅读取" : "暂不可拉取"}
                    </small>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {sources.sources.length === 0 && <p role="status">尚未配置可展示的 NS 单据类型。</p>}
          {sources.sources.map((item) => (
            <div key={item.kind} className="sync-page__result-slot" hidden={selectedKind !== item.kind}>
              <PullPanel source={item} onBusyChange={setPulling} />
            </div>
          ))}
        </div>
      )}
      {source !== "overview" && children}
    </div>
  );
}
