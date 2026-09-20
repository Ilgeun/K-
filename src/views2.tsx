import { useState } from "react";
import type { Evaluation, Evidence, Product, Requirement } from "./types";
import { CHECK_TEXT, FIELD_LABEL, KIND_TEXT, ctxText, reqShort } from "./format";
import { Chip, EvidenceDrawer, RealBadge, StatusDot, deliveryChip, overallChip, provenance, statusKind } from "./components";

type Evals = Record<string, Evaluation>;
const ORDER = { MATCH: 0, CHECK: 1, EXCLUDED: 2 } as const;

export const rank = (evals: Evals, ps: Product[]) =>
  [...ps].filter((p) => evals[p.id]).sort((a, b) =>
    ORDER[evals[a.id].overall] - ORDER[evals[b.id].overall] || (a.leadTime ?? 999) - (b.leadTime ?? 999));

export function CandidatesView({ products, partType, evals, selected, toggle, goCompare, onRegister, onDelete }: {
  products: Product[]; partType: string; evals: Evals; selected: string[]; toggle: (id: string) => void; goCompare: () => void; onRegister: () => void; onDelete: (p: Product) => void;
}) {
  const [tab, setTab] = useState<"ALL" | "MATCH" | "CHECK" | "EXCLUDED">("ALL");
  const cnt = (o: string) => products.filter((p) => evals[p.id]?.overall === o).length;
  const list = rank(evals, products).filter((p) => (tab === "ALL" ? evals[p.id].overall !== "EXCLUDED" : evals[p.id].overall === tab));
  const tabs: [typeof tab, string, number][] = [["ALL", "검토 대상", cnt("MATCH") + cnt("CHECK")], ["MATCH", "조건 충족", cnt("MATCH")], ["CHECK", "확인 필요", cnt("CHECK")], ["EXCLUDED", "제외됨", cnt("EXCLUDED")]];
  return (
    <section className="panel">
      <div className="head-row"><h2>③ 대체 후보 탐색</h2><button className="btn ghost sm" onClick={onRegister}>+ 제품 등록 (문서 업로드)</button></div>
      <p className="lead">등록된 {partType} {products.length}개를 이 선박의 요구조건으로 대조했습니다. 필수조건 미충족 후보는 기본 목록에서 제외하고, 사유를 확인할 수 있습니다.</p>
      <div className="summary">
        <div className="sum match"><b>{cnt("MATCH")}</b><span>현재 자료상 조건 충족</span></div>
        <div className="sum check"><b>{cnt("CHECK")}</b><span>추가 확인 필요</span></div>
        <div className="sum excl"><b>{cnt("EXCLUDED")}</b><span>필수조건 미충족(제외)</span></div>
      </div>
      <div className="tabs">{tabs.map(([k, t, n]) => (
        <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t} <em>{n}</em></button>))}</div>
      <div className="cards">{list.map((p) => {
        const e = evals[p.id];
        return (
          <article key={p.id} className={`cand ${e.overall.toLowerCase()}`}>
            <header>
              <div><div className="muted small">{p.manufacturer}</div><h3>{p.model}</h3></div>
              {overallChip(e.overall)}
            </header>
            <div className="chips"><RealBadge p={p} />{!p.synthetic && !p.real && <Chip kind="neutral">사용자 등록</Chip>}{deliveryChip(e)}{e.optionalMiss.length > 0 && <Chip kind="neutral">선택조건 {e.optionalMiss.length}건 미달</Chip>}</div>
            <ul className="checklist">{e.items.map((i) => (
              <li key={i.req.id}><StatusDot s={i.status} /><span>{FIELD_LABEL[i.req.field]}</span><em className={`v-${statusKind(i.status)}`}>{i.actual}</em></li>))}</ul>
            {e.overall === "EXCLUDED" && <div className="why">제외 사유: {e.failed.map((f) => f.reason).join(" · ")}</div>}
            {e.overall === "CHECK" && <div className="why warn">부족 자료: {e.unknown.map((f) => FIELD_LABEL[f.req.field]).join(", ")}</div>}
            <footer>
              <label className="sel"><input type="checkbox" checked={selected.includes(p.id)} onChange={() => toggle(p.id)} /> 비교에 담기</label>
              <span><button className="link danger" onClick={() => onDelete(p)}>삭제</button>{" "}
                <button className="btn ghost sm" onClick={() => { if (!selected.includes(p.id)) toggle(p.id); goCompare(); }}>상세 비교 →</button></span>
            </footer>
          </article>);
      })}</div>
      {products.length === 0 && <div className="empty">‘{partType}’로 등록된 제품이 없습니다. 위의 <b>+ 제품 등록</b>으로 제조사 문서(PDF)를 올려 기자재 DB에 추가하세요.</div>}
      {products.length > 0 && list.length === 0 && <div className="empty">해당하는 후보가 없습니다.</div>}
      <div className="actions"><span className="muted">{selected.length}개 선택됨 (최대 3개)</span><button className="btn primary" disabled={!selected.length} onClick={goCompare}>비교 · 근거 보기 →</button></div>
    </section>
  );
}

export function CompareView({ products, evals, selected, docs, toggle, openUpload, setLead, goReport, onDeleteSpec, onDeleteCert, onDeleteRestriction, contexts, system }: {
  products: Product[]; evals: Evals; selected: string[]; docs: string[]; toggle: (id: string) => void; contexts: Record<string, string>; system: string;
  onDeleteRestriction: (p: Product, key: string) => void;
  openUpload: (p: Product) => void; setLead: (p: Product, days: number) => void; goReport: () => void;
  onDeleteSpec: (p: Product, field: string) => void; onDeleteCert: (p: Product, certNo: string) => void;
}) {
  const [ev, setEv] = useState<{ p: Product; e: Evidence } | null>(null);
  const [lead, setLeadInput] = useState<Record<string, string>>({});
  const cols = products.filter((p) => selected.includes(p.id) && evals[p.id]);
  const pool = rank(evals, products).filter((p) => evals[p.id].overall !== "EXCLUDED");
  if (!cols.length) return <section className="panel"><h2>④ 후보 비교 · 근거</h2><div className="empty">③에서 비교할 후보를 담아주세요.</div></section>;
  const fields: Requirement[] = evals[cols[0].id].items.map((i) => i.req);
  return (
    <section className="panel">
      <h2>④ 후보 비교 · 근거 확인</h2>
      <p className="lead">항목마다 판정 근거가 원문(문서·페이지)에 연결됩니다. 자료가 없는 항목은 추측하지 않고 <b>‘확인 필요’</b>로 남깁니다.</p>
      <div className="pick">{pool.slice(0, 10).map((p) => (
        <button key={p.id} className={selected.includes(p.id) ? "on" : ""} onClick={() => toggle(p.id)}>{p.model}</button>))}</div>
      <div className="scroll"><table className="matrix">
        <thead><tr><th>비교 항목 / 요구</th>{cols.map((p) => (
          <th key={p.id}><div className="muted small">{p.manufacturer}</div><div>{p.model}</div>{overallChip(evals[p.id].overall)} <RealBadge p={p} /></th>))}</tr></thead>
        <tbody>
          {fields.map((r) => (
            <tr key={r.id}>
              <th><b>{FIELD_LABEL[r.field]}</b>{!r.mandatory && <span className="muted small"> (선택)</span>}<div className="muted small">{r.field === "usage_restriction" ? `선박 사용 계통(${system}) 기준: ${ctxText(contexts, r.value.split("|").filter((x) => x !== "-")) || "해당 상황 없음"}` : `요구: ${reqShort(r)}`}</div></th>
              {cols.map((p) => {
                const it = evals[p.id].items.find((i) => i.req.id === r.id)!;
                return <td key={p.id} className={`cell cell-${statusKind(it.status)}`}>
                  <div className="cell-top"><StatusDot s={it.status} /><b>{it.actual}</b></div>
                  <div className="muted small">{CHECK_TEXT[it.status]}</div>
                  {it.evidence ? <><button className="link" onClick={() => setEv({ p, e: it.evidence! })}>원문 · p.{it.evidence.page}</button>
                    <div className="small muted prov">{provenance(it.evidence)}</div></> : it.req.field === "usage_restriction" ? <span className="small muted">{it.status === "UNKNOWN" ? "문서를 업로드해 제한 조건을 분석하세요" : "확정된 제한 중 해당 없음"}</span> : <span className="small warn-t">근거 자료 없음</span>}
                </td>;
              })}
            </tr>))}
          <tr className="sep"><th><b>납기</b><div className="muted small">기술 적합성과 별도 표시</div></th>
            {cols.map((p) => { const d = evals[p.id].delivery; return <td key={p.id} className={`cell cell-${statusKind(d.status)}`}>
              <div className="cell-top"><StatusDot s={d.status} /><b>{d.days == null ? "공급사 확인 필요" : `${d.days}일`}</b></div>
              <div className="muted small">{d.reason}</div><div className="muted small">{d.source}</div></td>; })}
          </tr>
        </tbody>
      </table></div>

      {cols.some((p) => evals[p.id].restrictions.length > 0) && <>
        <h3 className="mt">사용 제한 상세 <span className="muted small">— 이 선박의 사용 계통({system})에 해당하는 문서상의 제한</span></h3>
        <div className="supp">{cols.map((p) => { const fs = evals[p.id].restrictions; return (
          <div className="card" key={p.id}><b>{p.model}</b> <span className="muted small">확정된 제한 {evals[p.id].restrictionsReviewed}건 검토</span>
            {fs.length === 0 && <p className="muted small">이 계통에 해당하는 제한이 없습니다.</p>}
            {fs.map((f, i) => <div key={i} className={`finding ${f.level.toLowerCase()}`}>
              <div><Chip kind={f.level === "BLOCK" ? "excluded" : "check"}>{f.level === "BLOCK" ? "제외 사유" : "주의"}</Chip> <Chip kind="neutral">{KIND_TEXT[f.kind]}</Chip> <b>{f.summary}</b></div>
              <div className="small muted">{f.reason}</div>
              <div className="small q3">“{f.quote}”</div>
              <div><button className="link" onClick={() => setEv({ p, e: { file: f.file, page: f.page, raw: f.quote, extractedBy: f.extractedBy, confirmedBy: f.confirmedBy, confirmedAt: f.confirmedAt } })}>원문 · p.{f.page}</button>
                <span className="small muted prov"> {provenance(f)}</span></div></div>)}
          </div>); })}</div></>}

      <h3 className="mt">자료 보완 · 재평가</h3>
      <p className="muted small">제조사 문서(PDF)를 올리면 사양·인증·유효기간을 추출합니다. <b>담당자가 확인한 값만</b> 판정에 반영됩니다.</p>
      <div className="supp">{cols.map((p) => {
        const e = evals[p.id];
        return <div className="card" key={p.id}>
          <b>{p.model}</b> {overallChip(e.overall)}
          {e.unknown.length === 0 && !e.failed.length && <p className="muted small">보완이 필요한 필수 항목이 없습니다.</p>}
          {e.failed.length > 0 && <p className="small">미충족: {e.failed.map((f) => FIELD_LABEL[f.req.field]).join(", ")}</p>}
          {e.unknown.length > 0 && <p className="small">필요 자료: <b>{e.unknown.map((f) => FIELD_LABEL[f.req.field]).join(", ")}</b></p>}
          <button className="btn primary sm" onClick={() => openUpload(p)}>문서 업로드 · 추출 →</button>
          {(() => { const mine = [...p.specs.filter((x) => x.extractedBy !== "seed").map((x) => ({ k: "s:" + x.field, t: FIELD_LABEL[x.field] ?? x.field, v: x.display ?? x.value, d: () => onDeleteSpec(p, x.field) })),
                                  ...p.certs.filter((x) => x.extractedBy !== "seed").map((x) => ({ k: "c:" + x.certNo, t: "선급 형식승인", v: `${x.authority} ${x.certNo}`, d: () => onDeleteCert(p, x.certNo) })),
                                  ...p.restrictions.filter((x) => x.extractedBy !== "seed").map((x) => ({ k: "r:" + x.key, t: `사용 제한(${KIND_TEXT[x.kind]})`, v: x.summary, d: () => onDeleteRestriction(p, x.key) }))];
            return mine.length > 0 && <details className="mine"><summary>내가 확정한 자료 {mine.length}건 (삭제하면 ‘확인 필요’로 되돌아감)</summary>
              {mine.map((m) => <div key={m.k} className="mine-row"><span><b>{m.t}</b> · {m.v}</span><button className="link danger" onClick={m.d}>삭제</button></div>)}</details>; })()}
          {e.delivery.status === "UNKNOWN" && (
            <div className="lead-in"><input className="num" type="number" placeholder="납기(일)" value={lead[p.id] ?? ""} onChange={(x) => setLeadInput({ ...lead, [p.id]: x.target.value })} />
              <button className="btn ghost sm" disabled={!lead[p.id]} onClick={() => setLead(p, parseInt(lead[p.id]))}>공급사 회신 납기 입력</button></div>)}
        </div>; })}</div>
      <div className="actions"><button className="btn primary" onClick={goReport}>검토 보고서 생성 →</button></div>
      {ev && <EvidenceDrawer product={ev.p} ev={ev.e} docs={docs} onClose={() => setEv(null)} />}
    </section>
  );
}
