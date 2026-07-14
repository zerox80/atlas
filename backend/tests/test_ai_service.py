"""
Tests for the Mistral AI service helpers.
"""
import importlib
from types import SimpleNamespace


def test_ocr_4_is_default_model(monkeypatch):
    monkeypatch.delenv("MISTRAL_OCR_MODEL", raising=False)

    import ai_service

    service = importlib.reload(ai_service)

    assert service.OCR_MODEL == "mistral-ocr-4-0"


def test_medium_3_5_is_default_chat_model(monkeypatch):
    monkeypatch.delenv("MISTRAL_CHAT_MODEL", raising=False)

    import ai_service

    service = importlib.reload(ai_service)

    assert service.MODEL == "mistral-medium-3-5"


def test_imports_current_mistral_client():
    import ai_service

    assert ai_service.Mistral is not None
    assert ai_service.SDKError is not None


def test_build_ocr_options_enable_ocr_4_features(monkeypatch):
    monkeypatch.setenv("MISTRAL_OCR_MODEL", "mistral-ocr-4-0")
    monkeypatch.setenv("MISTRAL_OCR_TABLE_FORMAT", "markdown")
    monkeypatch.setenv("MISTRAL_OCR_INCLUDE_BLOCKS", "true")
    monkeypatch.setenv("MISTRAL_OCR_CONFIDENCE_GRANULARITY", "page")

    import ai_service

    service = importlib.reload(ai_service)

    assert service._build_ocr_options() == {
        "model": "mistral-ocr-4-0",
        "include_blocks": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
    }


def test_format_ocr_text_includes_pages_confidence_and_blocks():
    import ai_service

    ocr_response = SimpleNamespace(
        pages=[
            SimpleNamespace(
                index=0,
                markdown="Vertragstext",
                confidence_scores=SimpleNamespace(
                    average_page_confidence_score=0.97,
                    minimum_page_confidence_score=0.91,
                ),
                blocks=[
                    SimpleNamespace(type="title", content="Rahmenvertrag"),
                    SimpleNamespace(type="signature", content="Max Mustermann"),
                ],
            )
        ]
    )

    text = ai_service._format_ocr_text(ocr_response)

    assert "## Seite 1" in text
    assert "Vertragstext" in text
    assert "OCR-Konfidenz: average=0.97, minimum=0.91" in text
    assert "- title: Rahmenvertrag" in text
    assert "- signature: Max Mustermann" in text
