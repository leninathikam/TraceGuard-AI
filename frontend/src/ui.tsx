import { ReactNode } from "react";

export const label = (s: string) => s.replace(/_/g, " ");

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

const STATUS_TONE: Record<string, string> = {
  success: "good",
  failure: "bad",
  unknown: "muted",
  validated: "good",
  failed: "bad",
  rejected: "warn",
  not_applicable: "muted",
  supported_by_replay: "good",
  not_supported_by_replay: "bad",
  hypothesis: "warn",
  critical: "bad",
  high: "bad",
  medium: "warn",
  low: "muted",
};

export function Status({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="dim">—</span>;
  return <Badge tone={STATUS_TONE[value] ?? "muted"}>{label(value)}</Badge>;
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <h3>{title}</h3>
          <div className="row">{actions}</div>
        </header>
      )}
      {children}
    </section>
  );
}

export function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

export function Diff({ text }: { text: string }) {
  return (
    <pre className="diff">
      {text.split("\n").map((line, i) => {
        const cls = line.startsWith("+++") || line.startsWith("---") ? "meta"
          : line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : line.startsWith("@@") ? "hunk" : "";
        return <div key={i} className={cls}>{line || " "}</div>;
      })}
    </pre>
  );
}

export const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${(v * 100).toFixed(0)}%`);
export const ms = (v: number | null | undefined) =>
  v == null ? "n/a" : v > 1000 ? `${(v / 1000).toFixed(1)} s` : `${v.toFixed(0)} ms`;
export const usd = (v: number | null | undefined) => (v == null ? "n/a" : `$${v.toFixed(5)}`);
