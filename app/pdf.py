"""The single predefined certificate template, drawn with ReportLab."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

NAVY = colors.HexColor("#1f3a5f")
GOLD = colors.HexColor("#b8923a")
GREY = colors.HexColor("#555555")

BOLD = "Helvetica-Bold"
ITALIC = "Helvetica-Oblique"
REGULAR = "Helvetica"


class CertificateRenderError(ValueError):
    """Raised when one certificate cannot be rendered. Only that certificate fails."""


@dataclass(frozen=True)
class CertificateData:
    recipient_name: str
    event_title: str
    issued_by: str
    issue_date: date
    achievement: str | None = None


def _check_encodable(label: str, text: str) -> None:
    # The built-in PDF fonts only cover Latin-1/cp1252. Fail loudly instead of
    # silently printing blank boxes on the certificate.
    try:
        text.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise CertificateRenderError(
            f"{label} contains a character the template font cannot render: "
            f"{text[exc.start]!r}"
        ) from exc


def _fit(label: str, text: str, font: str, size: float, max_width: float, min_size: float) -> float:
    while stringWidth(text, font, size) > max_width:
        size -= 1
        if size < min_size:
            raise CertificateRenderError(f"{label} is too long to fit on the certificate")
    return size


def render_certificate(path: Path, data: CertificateData) -> None:
    """Write a landscape A4 certificate PDF to `path`.

    All checks run before the file is touched, so a failure never leaves a partial PDF.
    """
    width, height = landscape(A4)
    date_text = data.issue_date.strftime("%d %B %Y")
    for label, text in (
        ("recipient name", data.recipient_name),
        ("event title", data.event_title),
        ("issuer", data.issued_by),
        ("achievement", data.achievement or ""),
    ):
        _check_encodable(label, text)

    for_line = f"for {data.achievement}" if data.achievement else "for participating in"
    name_size = _fit("recipient name", data.recipient_name, BOLD, 38, width - 200, 16)
    event_size = _fit("event title", data.event_title, BOLD, 24, width - 160, 12)
    for_size = _fit("achievement", for_line, ITALIC, 14, width - 160, 10)
    issuer_size = _fit("issuer", data.issued_by, REGULAR, 13, 300, 8)

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.setTitle(f"Certificate - {data.recipient_name}")
    c.setAuthor(data.issued_by)

    c.setStrokeColor(NAVY)
    c.setLineWidth(6)
    c.rect(25, 25, width - 50, height - 50)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.rect(38, 38, width - 76, height - 76)

    mid = width / 2

    def centered(text: str, x: float, y: float, font: str, size: float, color=NAVY) -> None:
        c.setFillColor(color)
        c.setFont(font, size)
        c.drawCentredString(x, y, text)

    centered("CERTIFICATE", mid, height - 130, BOLD, 42)
    centered(
        "OF ACHIEVEMENT" if data.achievement else "OF PARTICIPATION",
        mid, height - 165, REGULAR, 16, GOLD,
    )
    centered("This certificate is proudly presented to", mid, height - 225, ITALIC, 14, GREY)
    centered(data.recipient_name, mid, height - 285, BOLD, name_size)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(mid - 250, height - 297, mid + 250, height - 297)
    centered(for_line, mid, height - 335, ITALIC, for_size, GREY)
    centered(data.event_title, mid, height - 375, BOLD, event_size)

    c.setStrokeColor(GREY)
    c.line(90, 110, 390, 110)
    c.line(452, 110, 752, 110)
    centered(date_text, 240, 116, REGULAR, 13, GREY)
    centered(data.issued_by, 602, 116, REGULAR, issuer_size, GREY)
    centered("Date", 240, 94, REGULAR, 10, GREY)
    centered("Issued by", 602, 94, REGULAR, 10, GREY)

    c.showPage()
    c.save()
