import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { DonutChart } from "../../../shared/components/ui";
import type { Workbench } from "../types/workbench";

/** 开票任务节点分布：进行中任务停在哪个开票跟进节点，计数与占比来自后端（与开票跟进页同一判定）。 */
export function WorkbenchNodes({ nodes }: { nodes: NonNullable<Workbench["nodes"]> }) {
  return (
    <section className="wb-panel" aria-labelledby="wb-nodes-title">
      <div className="wb-panel__head">
        <div>
          <h2 id="wb-nodes-title">开票任务节点分布</h2>
          <p className="wb-panel__sub">进行中任务停在哪一步</p>
        </div>
        <Link to={paths.tasks}>去开票跟进 →</Link>
      </div>
      <div className="wb-panel__body">
        <DonutChart
          label="进行中开票任务按节点分布"
          size={168}
          centerLabel="进行中"
          centerValue={String(nodes.total)}
          segments={nodes.nodes.map((node) => ({
            key: node.key,
            label: node.label,
            value: node.count,
            text: `${node.count} · ${node.percent}%`,
          }))}
        />
      </div>
    </section>
  );
}
