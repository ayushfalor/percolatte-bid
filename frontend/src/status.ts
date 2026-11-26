import type { Doc, Run } from "./api";

// Where a bid model is in the pipeline, read from the runs list. The UI never computes a bid number;
// it only reads which runs are done.
export type Step = { key: string; title: string; state: "done" | "busy" | "todo" | "failed"; detail: string };
export type Progress = { steps: Step[]; status: string; tone: "ok" | "busy" | "down" | "off"; priced: boolean };

const NAMES: Record<string, string> = { reader: "Read", auditor: "Audited", rival: "Rivals", engine: "Priced" };

export function progressFor(runs: Run[], workbook: Doc | undefined): Progress {
  if (!workbook) return { steps: [], status: "No bid model yet", tone: "off", priced: false };
  const steps: Step[] = ["reader", "auditor", "rival", "engine"].map((kind) => {
    const mine = runs.filter((r) => r.kind === kind && (kind === "rival" || r.document_id === workbook.id) && !r.params?.scenario_id);
    const latest = mine[0];
    if (!latest) return { key: kind, title: NAMES[kind], state: "todo", detail: "not started" };
    if (latest.status === "succeeded") return { key: kind, title: NAMES[kind], state: "done", detail: "done" };
    if (latest.status === "failed") return { key: kind, title: NAMES[kind], state: "failed", detail: (latest.error ?? "failed").split("\n")[0] };
    return { key: kind, title: NAMES[kind], state: "busy", detail: latest.message ?? (latest.status === "queued" ? "waiting for the worker" : "working") };
  });
  const failed = steps.find((s) => s.state === "failed");
  const busy = steps.find((s) => s.state === "busy");
  const priced = steps.every((s) => s.state === "done");
  if (failed) return { steps, status: `Needs attention: ${failed.title.toLowerCase()} failed`, tone: "down", priced };
  if (busy) return { steps, status: `Working: ${busy.title.toLowerCase()}, ${busy.detail}`, tone: "busy", priced };
  if (priced) return { steps, status: "Priced and ready", tone: "ok", priced };
  return { steps, status: "Not started", tone: "off", priced };
}

export function technologyOf(workbook: Doc | undefined): string {
  const t = String(workbook?.meta?.technology ?? "");
  return t ? t[0].toUpperCase() + t.slice(1) : "Renewable";
}
