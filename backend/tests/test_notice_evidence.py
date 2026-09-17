import pytest

from ai_evidence import enforce_notice_evidence


@pytest.mark.parametrize("days,quote,expected", [
    (30, "Die Kündigungsfrist beträgt 30 Tage.", 30),
    (14, "Sie können mit einer Frist von zwei Wochen kündigen.", 14),
    (0, "Der Vertrag ist ohne Kündigungsfrist kündbar.", 0),
    (30, "Die Kündigungsfrist beträgt einen Monat.", None),
    (90, "Die Kündigungsfrist beträgt drei Monate.", None),
    (30, "Die Kündigungsfrist beträgt zwei Wochen.", None),
    (30, "Widerruf und Kündigung sind innerhalb von 30 Tagen möglich.", None),
    (30, "Die Rechnung ist innerhalb von 30 Tagen zu zahlen.", None),
    (True, "Die Kündigungsfrist beträgt einen Tag.", None),
    (30, "Kündigungsfrist: entweder 30 Tage oder zwei Wochen.", None),
    (30, "Innerhalb von 30 Tagen zu zahlen. Kündigungsfrist nicht vereinbart.", None),
    (14, "Außerordentliche Kündigung innerhalb von 14 Tagen nach Erhöhung.", None),
    (30, "Die Kündigungsfrist darf 30 Tage nicht unterschreiten.", None),
])
def test_only_verified_explicit_day_periods_survive(days, quote, expected):
    result = enforce_notice_evidence({"notice_period": days, "notice_period_evidence": quote}, "Vertrag\n" + quote)
    assert result["notice_period"] == expected


@pytest.mark.parametrize("source", [None, "Anderer Text"])
def test_invented_evidence_and_images_cannot_establish_notice(source):
    result = enforce_notice_evidence({"notice_period": 30, "notice_period_evidence": "Kündigungsfrist 30 Tage"}, source)
    assert result["notice_period"] is None
    assert result["notice_period_evidence"] is None
    assert result["analysis_warnings"]


def test_whitespace_ocr_line_breaks_are_normalized():
    result = enforce_notice_evidence({"notice_period": 14, "notice_period_evidence": "Kündigungsfrist: zwei Wochen."},
                                    "Kündigungsfrist:\n zwei\tWochen.")
    assert result["notice_period"] == 14
