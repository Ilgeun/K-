"""SQLite 저장소. 확정된 사양·인증만 판정에 쓰이고, 모든 확정은 감사 로그에 남는다."""
import json
import os
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .models import Cert, Product, Project, Requirement, Restriction, Spec

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"                      # 시드·문서·샘플(코드와 함께 배포되는 읽기 전용 자산)
# DB·업로드 파일은 영구 저장소(볼륨)에 둔다. Railway 볼륨을 붙이면 RAILWAY_VOLUME_MOUNT_PATH 가 자동으로 설정된다.
STATE = Path(os.environ.get("MARINE_DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or DATA)
SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
  id TEXT PRIMARY KEY, manufacturer TEXT, model TEXT, lead_time INTEGER, lead_time_source TEXT,
  lead_time_checked_at TEXT, scenario TEXT, expected TEXT, synthetic INTEGER, real_json TEXT, seq INTEGER, part_type TEXT DEFAULT '버터플라이 밸브');
CREATE TABLE IF NOT EXISTS specs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, field TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS certs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, cert_no TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS restrictions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, key TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, json TEXT, reqs_json TEXT, seq INTEGER, seeded INTEGER);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, who TEXT, product_id TEXT, action TEXT, detail TEXT);
"""


def derive_requirements(base: list[Requirement], class_society: str, need_by: str, today: Optional[date] = None,
                        also_accept: Optional[list[str]] = None) -> list[Requirement]:
    """기존 선박의 조건을 복제해 새 선박용으로 조정한다: 인정 선급(주 선급 + 추가 인정 선급), 필요 납기(오늘부터 필요 납기일까지 일수)."""
    accepted = [class_society] + [c for c in dict.fromkeys(also_accept or []) if c != class_society]
    days = max(1, (date.fromisoformat(need_by) - (today or date.today())).days)
    out = []
    for r in base:
        r = r.model_copy(deep=True)
        if r.field == "class_approval":
            r.value = "|".join(accepted)
        elif r.field == "lead_time_days":
            r.value = str(days)
        out.append(r)
    return out


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Optional[Path] = None):
        path = path or STATE / "marine.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        if "part_type" not in {r["name"] for r in self.conn.execute("PRAGMA table_info(products)")}:   # 부품 종류가 없던 이전 DB 이관
            self.conn.execute("ALTER TABLE products ADD COLUMN part_type TEXT DEFAULT '버터플라이 밸브'")
            self.conn.commit()
        if not self.conn.execute("SELECT 1 FROM products LIMIT 1").fetchone():
            self.seed()
        else:
            seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
            with self.lock, self.conn:
                if not self.conn.execute("SELECT 1 FROM projects LIMIT 1").fetchone():   # 프로젝트 기능이 없던 이전 DB 이관
                    self._seed_projects(seed)
                if not self.conn.execute("SELECT 1 FROM restrictions LIMIT 1").fetchone():   # 사용 제한 기능이 없던 이전 DB 이관
                    for sp in seed["products"]:
                        if self.conn.execute("SELECT 1 FROM products WHERE id=?", (sp["id"],)).fetchone():
                            for r in sp.get("restrictions", []):
                                rr = Restriction(**r)
                                self.conn.execute("INSERT INTO restrictions(product_id, key, json) VALUES(?,?,?)", (sp["id"], rr.key, rr.model_dump_json()))

    # ---- 시드 / 초기화
    def seed(self) -> None:
        seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
        with self.lock, self.conn:
            for t in ("products", "specs", "certs", "restrictions", "audit", "projects"):
                self.conn.execute(f"DELETE FROM {t}")
            for n, p in enumerate(seed["products"]):
                self._insert_product(Product(**p), n)
            self._seed_projects(seed)

    def _seed_projects(self, seed: dict) -> None:
        base = [Requirement(**r) for r in seed["requirements"]]
        p1 = Project(**seed["project"])
        p1.ship_type, p1.hull_no = "컨테이너선", "H-0001"
        self._insert_project(p1, base, 0, seeded=True)
        # 두 번째 시연용 가상 선박: 선급이 다르면 같은 후보라도 판정이 달라진다
        p2 = Project(project_id="P002", ship_name="(가상) 벌크선 B호", class_society="KR", system="해수 냉각",
                     part_type="버터플라이 밸브", need_by_date="2027-01-31", ship_type="벌크선", hull_no="H-0002")
        self._insert_project(p2, derive_requirements(base, "KR", p2.need_by_date), 1, seeded=True)

    def _insert_project(self, p: Project, reqs: list[Requirement], seq: int, seeded: bool = False) -> None:
        self.conn.execute("INSERT INTO projects VALUES(?,?,?,?,?)",
                          (p.project_id, p.model_dump_json(),
                           json.dumps([r.model_dump() for r in reqs], ensure_ascii=False), seq, int(seeded)))

    def _insert_product(self, p: Product, seq: int) -> None:
        self.conn.execute(
            "INSERT INTO products(id, manufacturer, model, lead_time, lead_time_source, lead_time_checked_at, scenario, expected, synthetic, real_json, seq, part_type)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.manufacturer, p.model, p.leadTime, p.leadTimeSource, p.leadTimeCheckedAt, p.scenario,
             p.expected, int(p.synthetic), p.real.model_dump_json() if p.real else None, seq, p.partType))
        for s in p.specs:
            self.conn.execute("INSERT INTO specs(product_id, field, json) VALUES(?,?,?)", (p.id, s.field, s.model_dump_json()))
        for c in p.certs:
            self.conn.execute("INSERT INTO certs(product_id, cert_no, json) VALUES(?,?,?)", (p.id, c.certNo, c.model_dump_json()))
        for r in p.restrictions:
            self.conn.execute("INSERT INTO restrictions(product_id, key, json) VALUES(?,?,?)", (p.id, r.key, r.model_dump_json()))

    # ---- 조회
    def products(self) -> list[Product]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM products ORDER BY seq").fetchall()
            return [self._hydrate(r) for r in rows]

    def product(self, pid: str) -> Optional[Product]:
        with self.lock:
            r = self.conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            return self._hydrate(r) if r else None

    def _hydrate(self, r: sqlite3.Row) -> Product:
        specs = [Spec(**json.loads(x["json"])) for x in
                 self.conn.execute("SELECT json FROM specs WHERE product_id=? ORDER BY id", (r["id"],))]
        certs = [Cert(**json.loads(x["json"])) for x in
                 self.conn.execute("SELECT json FROM certs WHERE product_id=? ORDER BY id", (r["id"],))]
        rests = [Restriction(**json.loads(x["json"])) for x in
                 self.conn.execute("SELECT json FROM restrictions WHERE product_id=? ORDER BY id", (r["id"],))]
        return Product(id=r["id"], manufacturer=r["manufacturer"], model=r["model"], leadTime=r["lead_time"],
                       leadTimeSource=r["lead_time_source"] or "", leadTimeCheckedAt=r["lead_time_checked_at"] or "",
                       scenario=r["scenario"] or "", expected=r["expected"], synthetic=bool(r["synthetic"]), partType=r["part_type"] or "버터플라이 밸브",
                       real=json.loads(r["real_json"]) if r["real_json"] else None, specs=specs, certs=certs, restrictions=rests)

    # ---- 선박(프로젝트)
    def projects(self) -> list[Project]:
        with self.lock:
            rows = self.conn.execute("SELECT json, seeded FROM projects ORDER BY seq").fetchall()
            return [Project(**json.loads(r["json"])) for r in rows]

    def requirements(self, pid: str) -> Optional[list[Requirement]]:
        with self.lock:
            r = self.conn.execute("SELECT reqs_json FROM projects WHERE id=?", (pid,)).fetchone()
            return [Requirement(**x) for x in json.loads(r["reqs_json"])] if r else None

    def all_requirements(self) -> dict[str, list[Requirement]]:
        with self.lock:
            return {r["id"]: [Requirement(**x) for x in json.loads(r["reqs_json"])]
                    for r in self.conn.execute("SELECT id, reqs_json FROM projects")}

    def add_project(self, p: Project, reqs: list[Requirement]) -> Project:
        with self.lock, self.conn:
            nums = [int(x["id"][1:]) for x in self.conn.execute("SELECT id FROM projects WHERE id LIKE 'S%'") if x["id"][1:].isdigit()]
            p.project_id = f"S{max(nums, default=0) + 1:03d}"
            p.is_synthetic = "false"
            seq = self.conn.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM projects").fetchone()[0]
            self._insert_project(p, reqs, seq)
            self.audit("system", "-", "create_project", f"{p.project_id} {p.ship_name} ({p.class_society}, {p.system})")
        return next(x for x in self.projects() if x.project_id == p.project_id)

    def set_requirements(self, pid: str, reqs: list[Requirement]) -> None:
        with self.lock, self.conn:
            self.conn.execute("UPDATE projects SET reqs_json=? WHERE id=?",
                              (json.dumps([r.model_dump() for r in reqs], ensure_ascii=False), pid))

    def update_project(self, pid: str, **fields: str) -> Optional[Project]:
        with self.lock, self.conn:
            r = self.conn.execute("SELECT json FROM projects WHERE id=?", (pid,)).fetchone()
            if not r:
                return None
            data = json.loads(r["json"])
            data.update({k: v for k, v in fields.items() if v is not None})
            self.conn.execute("UPDATE projects SET json=? WHERE id=?", (json.dumps(data, ensure_ascii=False), pid))
            self.audit("system", "-", "update_project", f"{pid} {fields}")
        return next(x for x in self.projects() if x.project_id == pid)

    def delete_project(self, pid: str) -> str:
        """삭제 결과: ok | last(마지막 선박은 보호) | missing"""
        with self.lock, self.conn:
            if not self.conn.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
                return "missing"
            if self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] <= 1:
                return "last"
            self.conn.execute("DELETE FROM projects WHERE id=?", (pid,))
            self.audit("system", "-", "delete_project", pid)
            return "ok"

    def delete_product(self, pid: str) -> list[str]:
        """제품과 확정 자료를 삭제하고, 그 제품이 참조하던 문서 파일명을 돌려준다(호출측이 고아 파일을 정리)."""
        with self.lock, self.conn:
            p = self.product(pid)
            if not p:
                return []
            files = sorted({x.file for x in [*p.specs, *p.certs, *p.restrictions] if x.file})
            for t in ("specs", "certs", "restrictions", "products"):
                self.conn.execute(f"DELETE FROM {t} WHERE " + ("id" if t == "products" else "product_id") + "=?", (pid,))
            self.audit("system", pid, "delete_product", f"{p.manufacturer} {p.model}")
            return files

    def referenced_files(self) -> set[str]:
        with self.lock:
            return {f for p in self.products() for f in [*(s.file for s in p.specs), *(c.file for c in p.certs), *(r.file for r in p.restrictions)] if f}

    def delete_spec(self, pid: str, field: str, who: str) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM specs WHERE product_id=? AND field=?", (pid, field))
            if cur.rowcount:
                self.audit(who, pid, "delete_spec", field)
            return bool(cur.rowcount)

    def delete_restriction(self, pid: str, key: str, who: str) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM restrictions WHERE product_id=? AND key=?", (pid, key))
            if cur.rowcount:
                self.audit(who, pid, "delete_restriction", key)
            return bool(cur.rowcount)

    def delete_cert(self, pid: str, cert_no: str, who: str) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM certs WHERE product_id=? AND cert_no=?", (pid, cert_no))
            if cur.rowcount:
                self.audit(who, pid, "delete_cert", cert_no)
            return bool(cur.rowcount)

    # ---- 쓰기
    def add_product(self, manufacturer: str, model: str, part_type: str = "버터플라이 밸브") -> Product:
        with self.lock, self.conn:
            n = self.conn.execute("SELECT COUNT(*) c, COALESCE(MAX(seq),-1) m FROM products").fetchone()
            nums = [int(x["id"][1:]) for x in self.conn.execute("SELECT id FROM products WHERE id LIKE 'U%'") if x["id"][1:].isdigit()]
            pid = f"U{max(nums, default=0) + 1:03d}"
            p = Product(id=pid, manufacturer=manufacturer, model=model, synthetic=False, partType=part_type,
                        scenario="사용자 등록 제품(문서 업로드 기반)")
            self._insert_product(p, n["m"] + 1)
            self.audit("system", pid, "create_product", f"{manufacturer} {model}")
        return self.product(pid)  # type: ignore[return-value]

    def set_lead_time(self, pid: str, days: Optional[int], source: str, who: str) -> None:
        with self.lock, self.conn:
            self.conn.execute("UPDATE products SET lead_time=?, lead_time_source=?, lead_time_checked_at=? WHERE id=?",
                              (days, source, now()[:10], pid))
            self.audit(who, pid, "set_lead_time", f"{days}일 ({source})")

    def confirm(self, pid: str, specs: list[Spec], certs: list[Cert], who: str, restrictions: Optional[list[Restriction]] = None) -> Product:
        at = now()
        with self.lock, self.conn:
            for s in specs:
                s.confirmed, s.confirmedBy, s.confirmedAt = True, who, at
                self.conn.execute("DELETE FROM specs WHERE product_id=? AND field=?", (pid, s.field))  # 같은 항목은 최신 확정값으로 대체
                self.conn.execute("INSERT INTO specs(product_id, field, json) VALUES(?,?,?)", (pid, s.field, s.model_dump_json()))
                self.audit(who, pid, "confirm_spec", f"{s.field}={s.value} ({s.file} p.{s.page}, {s.extractedBy})")
            for c in certs:
                c.confirmed, c.confirmedBy, c.confirmedAt = True, who, at
                self.conn.execute("DELETE FROM certs WHERE product_id=? AND cert_no=?", (pid, c.certNo))
                self.conn.execute("INSERT INTO certs(product_id, cert_no, json) VALUES(?,?,?)", (pid, c.certNo, c.model_dump_json()))
                self.audit(who, pid, "confirm_cert", f"{c.authority} {c.certNo} ~{c.validUntil} ({c.file} p.{c.page}, {c.extractedBy})")
            for r in restrictions or []:
                r.confirmed, r.confirmedBy, r.confirmedAt = True, who, at
                self.conn.execute("DELETE FROM restrictions WHERE product_id=? AND key=?", (pid, r.key))   # 같은 문장은 최신 해석으로 대체
                self.conn.execute("INSERT INTO restrictions(product_id, key, json) VALUES(?,?,?)", (pid, r.key, r.model_dump_json()))
                self.audit(who, pid, "confirm_restriction", f"{r.kind} {'/'.join(r.contexts)} ({r.file} p.{r.page}, {r.extractedBy})")
        return self.product(pid)  # type: ignore[return-value]

    def audit(self, who: str, pid: str, action: str, detail: str) -> None:
        self.conn.execute("INSERT INTO audit(at, who, product_id, action, detail) VALUES(?,?,?,?,?)",
                          (now(), who, pid, action, detail))

    def audit_log(self, pid: Optional[str] = None, limit: int = 100) -> list[dict]:
        with self.lock:
            q = "SELECT at, who, product_id, action, detail FROM audit " + ("WHERE product_id=? " if pid else "") + "ORDER BY id DESC LIMIT ?"
            rows = self.conn.execute(q, (pid, limit) if pid else (limit,)).fetchall()
            return [dict(r) for r in rows]
