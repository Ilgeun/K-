import { useEffect, useState } from "react";
import type { Evaluation, Metrics, Product, Project, Requirement } from "./types";
import { api } from "./api";
import { CHECK_TEXT, FIELD_LABEL, KIND_TEXT, STATUS_TEXT, reqText } from "./format";
import { overallChip, provenance, statusKind } from "./components";

export function ReportView({ project, reqs, products, evals, selected }: {
  project: Project; reqs: Requirement[]; products: Product[]; evals: Record<string, Evaluation>; selected: string[];
}) {
  const cols = products.filter((p) => selected.includes(p.id) && evals[p.id]);
  const cnt = (o: string) => products.filter((p) => evals[p.id]?.overall === o).length;
  const sources = new Map<string, string>();
  cols.forEach((p) => evals[p.id].items.forEach((i) => i.evidence &&
    sources.set(`${p.model}|${i.evidence.file}|${i.evidence.page}`, `${p.model}: ${i.evidence.file} p.${i.evidence.page}${provenance(i.evidence) ? " — " + provenance(i.evidence) : ""}`)));
  const now = new Date().toLocaleString("ko-KR");
  if (!cols.length) return <section className="panel"><h2>⑤ 검토 보고서</h2><div className="empty">비교할 후보를 먼저 담아주세요.</div></section>;
  return (
    <section className="panel">
      <div className="report-tools no-print"><h2>⑤ 검토 보고서</h2><button className="btn primary" onClick={() => window.print()}>PDF로 저장 / 인쇄</button></div>
      <article className="report">
        <h1>대체 기자재 사전 검토 보고서</h1>
        <div className="muted small">SpecBridge · 생성 {now} · 가상 데이터 + 공개 문서 예시</div>
        <h4>1. 검토 개요</h4>
        <table className="table"><tbody>
          <tr><th>선박</th><td>{project.ship_name}</td><th>인정 선급</th><td>{(reqs.find((r) => r.field === "class_approval")?.value ?? project.class_society).split("|").join(" / ")}</td></tr>
          <tr><th>사용 계통</th><td>{project.system}</td><th>대상 부품</th><td>{project.part_type}</td></tr>
          <tr><th>교체 사유</th><td>{project.replace_model} · {project.replace_reason}</td><th>탐색 결과</th><td>충족 {cnt("MATCH")} · 확인 필요 {cnt("CHECK")} · 제외 {cnt("EXCLUDED")} (총 {products.length})</td></tr>
        </tbody></table>
        <h4>2. 확정 검토 조건</h4>
        <table className="table"><thead><tr><th>항목</th><th>요구</th><th>구분</th></tr></thead><tbody>
          {reqs.map((r) => <tr key={r.id}><td>{FIELD_LABEL[r.field]}</td><td>{reqText(r)}</td><td>{r.field === "lead_time_days" ? "납기(별도 표시)" : r.mandatory ? "필수" : "선택"}</td></tr>)}
        </tbody></table>
        <h4>3. 후보별 비교 결과</h4>
        <table className="table"><thead><tr><th>항목</th>{cols.map((p) => <th key={p.id}>{p.model}<br />{overallChip(evals[p.id].overall)}</th>)}</tr></thead><tbody>
          {evals[cols[0].id].items.map((it) => <tr key={it.req.id}><td>{FIELD_LABEL[it.req.field]}</td>
            {cols.map((p) => { const x = evals[p.id].items.find((i) => i.req.id === it.req.id)!; return <td key={p.id}><span className={`v-${statusKind(x.status)}`}>{CHECK_TEXT[x.status]}</span> · {x.actual}{x.evidence ? <span className="muted small"> ({x.evidence.file} p.{x.evidence.page})</span> : null}</td>; })}</tr>)}
          <tr><td>납기</td>{cols.map((p) => { const d = evals[p.id].delivery; return <td key={p.id}><span className={`v-${statusKind(d.status)}`}>{d.reason}</span><div className="muted small">{d.source}</div></td>; })}</tr>
        </tbody></table>
        {cols.some((p) => evals[p.id].restrictions.length > 0) && <>
          <h4>4. 사용 제한 검토 (사용 계통: {project.system})</h4>
          <ul className="small">{cols.flatMap((p) => evals[p.id].restrictions.map((f, i) =>
            <li key={p.id + i}><b>{p.model}</b> — [{f.level === "BLOCK" ? "제외 사유" : "주의"} · {KIND_TEXT[f.kind]}] {f.summary}<div className="muted">{f.reason} · 원문 “{f.quote}” ({f.file} p.{f.page}){provenance(f) ? ` · ${provenance(f)}` : ""}</div></li>))}</ul></>}
        <h4>{cols.some((p) => evals[p.id].restrictions.length > 0) ? "5" : "4"}. 미해결 항목 · 요청 자료</h4>
        <ul>{cols.map((p) => { const e = evals[p.id]; const need = [...e.unknown.map((u) => `${FIELD_LABEL[u.req.field]} 증빙`), ...(e.delivery.status === "UNKNOWN" ? ["납기 회신"] : [])];
          return <li key={p.id}><b>{p.model}</b> — {need.length ? `공급사에 요청: ${need.join(", ")}` : "추가 요청 자료 없음"}{e.failed.length ? ` · 필수조건 미충족(${e.failed.map((f) => FIELD_LABEL[f.req.field]).join(", ")})` : ""}{e.delivery.status === "FAIL" ? ` · ${e.delivery.reason}` : ""}</li>; })}</ul>
        <h4>{cols.some((p) => evals[p.id].restrictions.length > 0) ? "6" : "5"}. 근거 출처 · 추출/확인 이력</h4>
        <ul className="small">{[...sources.values()].map((f) => <li key={f}>{f}</li>)}</ul>
        <div className="disclaimer">본 보고서는 등록된 문서와 확정 조건 범위 내의 <b>사전 검토 지원 자료</b>입니다. AI·규칙 추출 결과는 담당자 확인을 거쳐야 판정에 반영되며, 최종 적용은 기술 검토와 승인 절차(선급 승인 포함)를 통해 결정합니다. 제품·인증 데이터는 시연용 가상 데이터와 ‘실제 공개 문서 기반’으로 표시된 예시가 함께 사용되었으며, 납기 정보는 모두 가상입니다.</div>
        <div className="sign">담당자 확인: ____________ &nbsp;&nbsp; 검토 승인: ____________</div>
      </article>
    </section>
  );
}

export function MetricsView({ onClose }: { onClose: () => void }) {
  const [m, setM] = useState<Metrics | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.metrics().then(setM).catch((e) => setErr(String(e.message ?? e))); }, []);
  const kpi = m ? ([
    ["필수조건 미충족 오통과", `${m.falsePass}건`, `제외 대상 ${m.excludedCount}건 중`],
    ["적합 후보 오제외", `${m.falseExcluded}건`, "충족·확인 필요 후보 기준"],
    ["자료 누락 → ‘확인 필요’ 정확도", `${m.checkOk}/${m.checkTotal}`, "자료 없는 항목을 추측하지 않음"],
    ["판정 근거 연결률", `${Math.round((m.linked / Math.max(m.judged, 1)) * 100)}%`, `충족·미충족 판정 ${m.judged}건 중`],
    ["정답 기준 전체 일치", `${m.agree}/${m.total}`, "종합 상태 일치 후보 수"],
  ] as [string, string, string][]) : [];
  return (
    <div className="drawer-bg center" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head"><h3>판정 엔진 검증 지표</h3><button className="btn ghost" onClick={onClose}>닫기 ✕</button></div>
        {err && <div className="note">지표를 불러오지 못했습니다: {err}</div>}
        {m && <>
          <div className="kpis">{kpi.map(([t, v, s]) => <div className="kpi" key={t}><b>{v}</b><span>{t}</span><em>{s}</em></div>)}</div>
          <table className="table"><thead><tr><th>후보</th><th>시나리오</th><th>정답</th><th>엔진 판정</th><th></th></tr></thead><tbody>
            {m.rows.map((r) => <tr key={r.id}><td>{r.model}{r.real && <> <span className="chip chip-real">실제</span></>}</td><td className="small">{r.scenario}</td><td>{STATUS_TEXT[r.expected]}</td><td>{overallChip(r.actual)}</td><td>{r.expected === r.actual ? "✓" : "✕"}</td></tr>)}
          </tbody></table></>}
        <div className="note">⚠ 위 수치는 <b>정답 시나리오를 알고 만든 데이터에 대한 규칙 엔진 자체 검증</b>입니다(가상 {m ? m.total - m.rows.filter((r) => r.real).length : "–"}건 + 실제 공개 문서 {m ? m.rows.filter((r) => r.real).length : "–"}건). 실제 PDF에서의 추출 정확도와 검토 시간 단축은 별도로 측정해야 합니다.</div>
      </div>
    </div>
  );
}
