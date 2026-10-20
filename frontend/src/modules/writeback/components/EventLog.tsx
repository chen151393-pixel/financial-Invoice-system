import { writebackTime, type WritebackRequest } from "../types";

/** 预览、确认、提交、核实的审计记录，按后端顺序展示。 */
export function EventLog({ events }: { events: WritebackRequest["events"] }) {
  if (events.length === 0) return null;
  return (
    <section className="wb-panel" aria-labelledby="wb-events-title">
      <h2 id="wb-events-title" className="wb-section-title">
        执行记录
      </h2>
      <ol className="wb-events">
        {events.map((event, index) => (
          <li key={`${event.at}:${index}`}>
            <time dateTime={event.at}>{writebackTime(event.at)}</time>
            <strong>{event.action}</strong>
            <span className="wb-muted">
              {event.actor}
              {event.detail && ` · ${event.detail}`}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
