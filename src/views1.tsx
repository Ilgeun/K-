import { useState } from "react";
import type { Project, Requirement } from "./types";
import { AUTHORITIES, FIELD_LABEL, FLANGES, MATERIALS, label } from "./format";

export const REASONS = ["납품 지연", "단종", "품질 이슈", "원가 절감", "기타"];

export function ProjectView({ projects, current, classesOf, contexts, systemContexts, partTypes, reqCount, partCount, onSelect, onNew, onDelete, onUpdate, onNext }: {
  projects: Project[]; current: Project; classesOf: (id: string) => string; contexts: Record<string, string>; systemContexts: Record<string, string[]>; partTypes: string[]; reqCount: number; partCount: number;
  onSelect: (id: string) => void; onNew: () => void; onDelete: (p: Project) => void;
  onUpdate: (patch: { part_type: string; replace_model: string; replace_reason: string }) => Promise<void>; onNext: () => void;
}) {
  const p = current;
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({ part_type: p.part_type, replace_model: p.replace_model, replace_reason: p.replace_reason });
  const [busy, setBusy] = useState(false);
  const open = () => { setF({ part_type: p.part_type, replace_model: p.replace_model, replace_reason: p.replace_reason }); setEdit(true); };
  const save = async () => { setBusy(true); try { await onUpdate(f); setEdit(false); } finally { setBusy(false); } };
  return (
    <section className="panel">
      <div className="head-row"><h2>① 선박 · 교체 부품 선택</h2><button className="btn primary sm" onClick={onNew}>+ 새 선박 등록</button></div>
      <p className="lead">건조 중인 선박을 선택하면 그 선박의 선급·사용 계통·필요 납기에 맞는 요구조건을 불러옵니다. 선박마다 조건이 따로 저장됩니다.</p>
      <div className="ships">{projects.map((s) => (
        <div key={s.project_id} className={`ship ${s.project_id === p.project_id ? "on" : ""}`} onClick={() => onSelect(s.project_id)} role="button" tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter") onSelect(s.project_id); }}>
          <div className="ship-top"><b>{s.ship_name}</b>{s.project_id === p.project_id && <span className="chip chip-match">선택됨</span>}</div>
          <div className="muted small">{[s.hull_no, s.ship_type].filter(Boolean).join(" · ") || "—"}</div>
          <div className="chips"><span className="chip chip-neutral" title="인정하는 선급(하나라도 유효하면 충족)">선급 {classesOf(s.project_id).split("|").join(" / ")}</span><span className="chip chip-neutral">{s.system}</span></div>
          <div className="small muted">교체: {s.part_type} · 필요 납기일 {s.need_by_date}</div>
          <div className="ship-foot">{s.is_synthetic === "true" ? <span className="chip chip-neutral">시연용 가상</span> : <span className="chip chip-real">내가 등록한 선박</span>}
            {projects.length > 1 && <button className="link danger" onClick={(e) => { e.stopPropagation(); onDelete(s); }}>삭제</button>}</div>
        </div>))}
        <button className="ship add" onClick={onNew}><span>＋</span>새 선박 등록</button>
      </div>
      <div className="grid2 mt">
        <div className="card selected">
          <div className="muted small">선택한 선박</div>
          <h3>{p.ship_name}</h3>
          <dl className="kv">
            <dt>호선번호</dt><dd>{p.hull_no || "—"}</dd>
            <dt>선종</dt><dd>{p.ship_type || "—"}</dd>
            <dt>인정 선급</dt><dd>{classesOf(p.project_id).split("|").join(" / ")}<span className="muted small"> (주 선급 {p.class_society})</span></dd>
            <dt>사용 계통</dt><dd>{p.system}<div className="small muted" title="문서의 사용 제한과 대조할 때 쓰는 사용 상황입니다. 계통→상황 매핑은 개발팀의 가정이므로 현업 확인이 필요합니다.">사용 제한 대조 기준: {(systemContexts[p.system] ?? []).map((c) => contexts[c] ?? c).join("·") || "해당 상황 없음"}</div></dd>
            <dt>필요 납기일</dt><dd>{p.need_by_date}</dd>
          </dl>
        </div>
        <div className="card">
          <div className="head-row"><div className="muted small">교체 대상 기자재</div>{!edit && <button className="link" onClick={open}>변경</button>}</div>
          {!edit ? <>
            <h3>{p.part_type}</h3>
            <dl className="kv">
              <dt>기존 모델</dt><dd>{p.replace_model}</dd>
              <dt>교체 사유</dt><dd><span className="chip chip-excluded">{p.replace_reason}</span></dd>
              <dt>등록 조건</dt><dd>{reqCount}개 (이 선박 전용)</dd>
              <dt>후보 제품</dt><dd>{partCount}개 {partCount === 0 && <span className="chip chip-check">등록 필요</span>}</dd>
            </dl>
          </> : <>
            <label className="field">부품 종류<select value={f.part_type} onChange={(e) => setF({ ...f, part_type: e.target.value })}>{partTypes.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="field">기존 모델<input value={f.replace_model} onChange={(e) => setF({ ...f, replace_model: e.target.value })} placeholder="예: A사 SMV-200" /></label>
            <label className="field">교체 사유<select value={f.replace_reason} onChange={(e) => setF({ ...f, replace_reason: e.target.value })}>{REASONS.map((x) => <option key={x}>{x}</option>)}</select></label>
            <div className="actions" style={{ marginTop: 8 }}><button className="btn ghost sm" onClick={() => setEdit(false)}>취소</button><button className="btn primary sm" disabled={busy} onClick={save}>저장</button></div>
          </>}
          <div className="note">선박 종류는 검색의 시작점일 뿐, 실제 비교는 <b>사용 위치(계통)와 구체 조건</b>으로 합니다. 후보는 <b>선택한 부품 종류로 등록된 제품</b>만 나옵니다. 부품 종류를 바꿔도 요구조건은 그대로이니 ②에서 확인하세요.</div>
        </div>
      </div>
      <div className="actions"><button className="btn primary" onClick={onNext}>이 선박의 요구조건 보기 →</button></div>
    </section>
  );
}

export function RequirementsView({ reqs, setReqs, onNext, ship }: { reqs: Requirement[]; setReqs: (r: Requirement[]) => void; onNext: () => void; ship: string }) {
  const upd = (id: string, patch: Partial<Requirement>) => setReqs(reqs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const input = (r: Requirement) => {
    if (["nominal_diameter", "design_pressure", "temp_max", "lead_time_days"].includes(r.field))
      return <><input className="num" type="number" value={r.value} onChange={(e) => upd(r.id, { value: e.target.value })} /> <span className="muted">{r.unit.replace("degC", "°C").replace("day", "일")}</span></>;
    if (r.field === "flange_standard")
      return <select value={r.value} onChange={(e) => upd(r.id, { value: e.target.value })}>{FLANGES.map((f) => <option key={f} value={f}>{label(f)}</option>)}</select>;
    if (r.field === "class_approval") {   // 인정하는 선급을 여러 개 고를 수 있다(하나 이상 필수)
      const on = r.value.split("|");
      return <div className="checks">{AUTHORITIES.map((a) => (
        <label key={a}><input type="checkbox" checked={on.includes(a)} disabled={on.length === 1 && on[0] === a}
          onChange={(e) => upd(r.id, { value: (e.target.checked ? [...on, a] : on.filter((x) => x !== a)).sort((x, y) => AUTHORITIES.indexOf(x) - AUTHORITIES.indexOf(y)).join("|") })} /> {a}</label>
      ))}<span className="muted small">— 선택한 선급 중 하나의 유효한 형식승인이 있으면 충족</span></div>;
    }
    const sel = r.value.split("|");
    return <div className="checks">{MATERIALS.map((m) => (
      <label key={m}><input type="checkbox" checked={sel.includes(m)} onChange={(e) => upd(r.id, { value: (e.target.checked ? [...sel, m] : sel.filter((x) => x !== m)).join("|") })} /> {label(m)}</label>
    ))}</div>;
  };
  return (
    <section className="panel">
      <h2>② 검색 조건 확인 <span className="muted small">— {ship}</span></h2>
      <p className="lead">프로젝트에 등록된 요구조건을 자동으로 불러왔습니다. 담당자가 확인·수정하면 후보가 즉시 재판정되고, 이 선박에 자동 저장됩니다.</p>
      <table className="table">
        <thead><tr><th>항목</th><th>요구 값</th><th>구분</th><th>비고</th></tr></thead>
        <tbody>{reqs.map((r) => (
          <tr key={r.id}>
            <td><b>{FIELD_LABEL[r.field]}</b></td>
            <td>{r.op === "gte" ? "≥ " : r.op === "lte" ? "≤ " : ""}{input(r)}</td>
            <td>{r.field === "lead_time_days"
              ? <span className="chip chip-neutral">기술 판정과 별도 표시</span>
              : <button className={`toggle ${r.mandatory ? "on" : ""}`} onClick={() => upd(r.id, { mandatory: !r.mandatory })}>{r.mandatory ? "필수" : "선택"}</button>}</td>
            <td className="muted small">{r.note}</td>
          </tr>))}</tbody>
      </table>
      <div className="note">💡 값을 바꿔 보세요 — 예: 구경을 150으로 바꾸면 결과가 즉시 달라집니다. 수치·단위·필수조건은 <b>AI가 아닌 정해진 규칙</b>으로 대조합니다.</div>
      <div className="actions"><button className="btn primary" onClick={onNext}>후보 탐색 →</button></div>
    </section>
  );
}
