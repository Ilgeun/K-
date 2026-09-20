import type { ReactNode } from "react";
import type { Evaluation, Evidence, Product, Status } from "./types";
import { CHECK_TEXT, STATUS_TEXT } from "./format";
import { docUrl } from "./api";

export const Chip = ({ kind, children }: { kind: "match" | "check" | "excluded" | "neutral"; children: ReactNode }) => (
  <span className={`chip chip-${kind}`}>{children}</span>
);
export const overallChip = (o: Evaluation["overall"]) => (
  <Chip kind={o === "MATCH" ? "match" : o === "CHECK" ? "check" : "excluded"}>{STATUS_TEXT[o]}</Chip>
);
export const statusKind = (s: Status) => (s === "PASS" ? "match" : s === "UNKNOWN" ? "check" : "excluded");
export const StatusDot = ({ s }: { s: Status }) => (
  <span className={`dot dot-${statusKind(s)}`} title={CHECK_TEXT[s]}>{s === "PASS" ? "✓" : s === "FAIL" ? "✕" : "?"}</span>
);
export const deliveryChip = (e: Evaluation) => {
  const d = e.delivery;
  return <Chip kind={statusKind(d.status)}>{d.status === "UNKNOWN" ? "납기: 공급사 확인 필요" : d.status === "PASS" ? `납기 ${d.days}일 · 충족` : `납기 ${d.days}일 · +${(d.days ?? 0) - d.need}일 초과`}</Chip>;
};
export const RealBadge = ({ p }: { p: Product }) => (p.real ? <span className="chip chip-real" title={p.real.label}>실제 공개 문서 기반</span> : null);

export const METHOD_TEXT: Record<string, string> = { rules: "규칙 기반 추출", llm: "Claude API 추출", cli: "Claude CLI 추출", seed: "등록 데이터", manual: "수기 입력" };
export const provenance = (e?: { extractedBy?: string | null; confirmedBy?: string | null; confirmedAt?: string | null } | null) =>
  !e ? "" : [e.extractedBy ? METHOD_TEXT[e.extractedBy] ?? e.extractedBy : "", e.confirmedBy ? `확인: ${e.confirmedBy}${e.confirmedAt ? " · " + e.confirmedAt.slice(0, 16).replace("T", " ") : ""}` : ""].filter(Boolean).join(" · ");

/** 판정 근거 원문 뷰. 실제 PDF가 서버에 있으면 해당 페이지를 열고, 없으면(가상 데이터) 가상 자료 형태로 보여준다. */
export function EvidenceDrawer({ product, ev, docs, onClose }: { product: Product; ev: Evidence; docs: string[]; onClose: () => void }) {
  const hasPdf = docs.includes(ev.file);
  const rows = product.specs.filter((s) => s.file === ev.file && s.page === ev.page);
  const certs = product.certs.filter((c) => c.file === ev.file && c.page === ev.page);
  return (
    <div className="drawer-bg" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div><div className="muted small">근거 원문</div><strong>{ev.file}</strong> <span className="muted">· p.{ev.page}</span></div>
          <button className="btn ghost" onClick={onClose}>닫기 ✕</button>
        </div>
        {hasPdf ? (
          <div className="real-doc">
            <div className="real-quote">
              <span className={`chip ${product.synthetic ? "chip-neutral" : "chip-match"}`}>{product.synthetic ? "가상 샘플 문서" : "실제 문서"}</span>{" "}
              <span className="small muted">판정에 사용된 원문</span>
              <blockquote>{ev.raw}</blockquote>
              {provenance(ev) && <div className="small muted">{provenance(ev)}</div>}
            </div>
            <iframe title="원문 PDF" src={`${docUrl(ev.file)}#page=${ev.page}&view=FitH`} />
            {product.real && <div className="small muted">출처: <a href={product.real.url} target="_blank" rel="noreferrer">{product.real.label}</a> (공개 문서)</div>}
          </div>
        ) : (
          <div className="paper">
            <div className="paper-mark">SYNTHETIC · 시연용 가상 자료</div>
            <h4>{product.manufacturer} {product.model}</h4>
            <div className="muted small">{certs.length ? "CERTIFICATE OF TYPE APPROVAL" : "PRODUCT DATASHEET — BUTTERFLY VALVE"} · Page {ev.page}</div>
            <table className="paper-table"><tbody>
              {rows.map((s, i) => <tr key={i} className={s.raw === ev.raw ? "hl" : ""}><td>{s.field}</td><td>{s.raw}</td></tr>)}
              {certs.map((c, i) => <tr key={"c" + i} className={ev.raw.includes(c.certNo) ? "hl" : ""}><td>approval</td><td>{c.authority} Type Approval · {c.certNo} · valid until {c.validUntil}</td></tr>)}
            </tbody></table>
            <div className="small muted" style={{ marginTop: 12 }}>가상 데이터 제품이라 실제 PDF가 없습니다. 하이라이트는 판정에 사용된 원문 값입니다.</div>
          </div>
        )}
      </aside>
    </div>
  );
}
