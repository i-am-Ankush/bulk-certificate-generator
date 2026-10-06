from datetime import date

import pytest

from app.pdf import CertificateData, CertificateRenderError, render_certificate


def _data(**kw):
    base = dict(
        recipient_name="Asha Rao",
        event_title="Python Bootcamp 2026",
        issued_by="Code Academy",
        issue_date=date(2026, 10, 1),
    )
    base.update(kw)
    return CertificateData(**base)


def test_render_writes_a_valid_pdf(tmp_path):
    out = tmp_path / "nested" / "cert.pdf"
    render_certificate(out, _data(achievement="Top Scorer"))
    assert out.read_bytes().startswith(b"%PDF")
    assert out.stat().st_size > 500


def test_unsupported_characters_are_rejected_without_writing_a_file(tmp_path):
    out = tmp_path / "cert.pdf"
    with pytest.raises(CertificateRenderError, match="cannot render"):
        render_certificate(out, _data(recipient_name="अंकुश कुमार"))
    assert not out.exists()


def test_too_long_text_is_rejected(tmp_path):
    with pytest.raises(CertificateRenderError, match="too long"):
        render_certificate(tmp_path / "c.pdf", _data(recipient_name="W" * 100))


def test_accented_latin_names_work(tmp_path):
    out = tmp_path / "c.pdf"
    render_certificate(out, _data(recipient_name="José Müller"))
    assert out.exists()
