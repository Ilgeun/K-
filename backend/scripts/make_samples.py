"""업로드 시연용 가상 샘플 PDF 생성 (모든 내용은 가상, 워터마크 표시)."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent.parent / "data" / "samples"
OUT.mkdir(parents=True, exist_ok=True)
W, H = A4


def page_header(c, title, sub):
    c.setFont("Helvetica-Bold", 16); c.drawString(50, H - 60, title)
    c.setFont("Helvetica", 10); c.setFillGray(0.4); c.drawString(50, H - 78, sub)
    c.setFillColorRGB(0.75, 0.1, 0.1); c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 40, "SYNTHETIC SAMPLE - FICTITIOUS DATA FOR DEMONSTRATION ONLY")
    c.setFillGray(0)


def lines(c, rows, y=H - 120, gap=20):
    c.setFont("Helvetica", 11)
    for r in rows:
        c.drawString(50, y, r); y -= gap
    return y


def datasheet(c, model, rows, rev):
    page_header(c, f"PRODUCT DATASHEET - {model}", f"Marine Butterfly Valve  |  Rev.{rev}  |  Manufacturer: Synthetic Marine Valve Co.")
    lines(c, rows)


def certificate(c, model, cert_no, valid, product="Butterfly Valves"):
    page_header(c, "TYPE APPROVAL CERTIFICATE", "DNV - Ships Pt.4 Ch.6 Piping systems")
    lines(c, [
        "Certificate No:", f"{cert_no}", "",
        "This is to certify:", f"That the {product}", "with type designation(s)", f"{model}", "Issued to Synthetic Marine Valve Co., Ltd.", "",
        "Application: Product(s) approved by this certificate is/are accepted",
        "for installation on all vessels classed by DNV.", "",
        f"This Certificate is valid until {valid}.",
    ])


def build(name, fn):
    c = canvas.Canvas(str(OUT / name), pagesize=A4)
    fn(c)
    c.save()
    print("wrote", name)


def s1(c):
    certificate(c, "OF-BF200-X", "SYN-DNV-0501", "2028-06-30"); c.showPage()


def s2(c):
    datasheet(c, "BS-2000", [
        "Nominal size: DN200", "Design pressure: 16 bar (PN16)",
        "Body: Ni-Al Bronze (NAB)", "Disc: Ni-Al Bronze", "Seat: EPDM",
        "Flange standard: JIS B2220 10K", "Max. operating temperature: 80 C",
        "Operation: Gear operated"], "2 (corrected flange data)"); c.showPage()


def s3(c):
    datasheet(c, "BS-2000-L", [
        "Nominal size: DN200", "Design pressure: 1.6 MPa",
        "Body: Ductile iron, rubber lined", "Flange standard: JIS 10K",
        "Max. working temperature: 70 C"], "1"); c.showPage()
    certificate(c, "BS-2000-L", "SYN-DNV-0701", "2028-03-31"); c.showPage()


build("SYNTHETIC_OF-BF200-X_DNV_certificate.pdf", s1)
build("SYNTHETIC_BS-2000_datasheet_rev2.pdf", s2)
build("SYNTHETIC_BS-2000-L_datasheet_and_DNV_certificate.pdf", s3)


def s4(c):
    certificate(c, "SCV-150", "SYN-DNV-1501", "2028-09-30", product="Check Valve"); c.showPage()


build("SYNTHETIC_CHECK_VALVE_DNV_certificate.pdf", s4)


def s5(c):
    certificate(c, "SBV-LIM", "SYN-DNV-2001", "2028-12-31"); c.showPage()
    page_header(c, "TYPE APPROVAL CERTIFICATE - Application / Limitation", "Certificate No: SYN-DNV-2001  |  Page 2 of 2")
    lines(c, [
        "Valves covered by this certificate shall not be used in:",
        "- Seawater applications",
        "- Ship's side or bottom and on sea chest",
        "",
        "These valves may be used for bilge suction only when fitted in connection with a non-return valve.",
        "Ductile iron bodies may be used in fresh water systems.",
    ])
    c.showPage()


build("SYNTHETIC_BF_seawater_restrictions_certificate.pdf", s5)
