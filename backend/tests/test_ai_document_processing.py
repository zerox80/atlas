"""Tests for bounded local PDF rasterization."""

from types import SimpleNamespace

import fitz
import pytest

import ai_document_processing as processing


def _pdf_bytes(page_sizes: list[tuple[float, float]]) -> bytes:
    with fitz.open() as pdf_doc:
        for width, height in page_sizes:
            pdf_doc.new_page(width=width, height=height)
        return pdf_doc.tobytes()


def test_image_mode_rejects_oversized_page_geometry(monkeypatch):
    monkeypatch.setattr(processing, "use_ocr_mode", lambda: False)
    oversized_width = (
        processing.MAX_IMAGE_PDF_RENDER_WIDTH + 1
    ) / processing._IMAGE_PDF_RENDER_SCALE
    pdf_bytes = _pdf_bytes([(oversized_width, 72)])

    with pytest.raises(ValueError, match="Rasterlimit"):
        processing._validate_pdf_limits(pdf_bytes)


def test_image_mode_rejects_excessive_aggregate_pixels(monkeypatch):
    monkeypatch.setattr(processing, "use_ocr_mode", lambda: False)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_RENDER_WIDTH", 200)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_RENDER_HEIGHT", 200)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_PAGE_PIXELS", 30_000)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_TOTAL_PIXELS", 40_000)
    monkeypatch.setattr(
        processing, "MAX_IMAGE_PDF_TOTAL_DECODED_BYTES", 1_000_000
    )
    pdf_bytes = _pdf_bytes([(72, 72), (72, 72)])

    with pytest.raises(ValueError, match="gesamte Rasterlimit"):
        processing._validate_pdf_limits(pdf_bytes)


def test_image_mode_rejects_excessive_decoded_bytes(monkeypatch):
    monkeypatch.setattr(processing, "use_ocr_mode", lambda: False)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_RENDER_WIDTH", 200)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_RENDER_HEIGHT", 200)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_PAGE_PIXELS", 30_000)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_TOTAL_PIXELS", 1_000_000)
    monkeypatch.setattr(
        processing, "MAX_IMAGE_PDF_TOTAL_DECODED_BYTES", 160_000
    )
    pdf_bytes = _pdf_bytes([(72, 72), (72, 72)])

    with pytest.raises(ValueError, match="gesamte Rasterlimit"):
        processing._validate_pdf_limits(pdf_bytes)


def test_image_mode_rejects_excessive_page_pixels(monkeypatch):
    monkeypatch.setattr(processing, "use_ocr_mode", lambda: False)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_RENDER_WIDTH", 200)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_RENDER_HEIGHT", 200)
    monkeypatch.setattr(processing, "MAX_IMAGE_PDF_PAGE_PIXELS", 20_000)
    pdf_bytes = _pdf_bytes([(72, 72)])

    with pytest.raises(ValueError, match="Rasterlimit"):
        processing._validate_pdf_limits(pdf_bytes)


def test_rasterization_preflights_limits_before_get_pixmap(monkeypatch):
    raster_called = False

    class OversizedPage:
        rect = SimpleNamespace(
            width=(processing.MAX_IMAGE_PDF_RENDER_WIDTH + 1)
            / processing._IMAGE_PDF_RENDER_SCALE,
            height=72,
        )

        def get_pixmap(self, *, matrix):
            nonlocal raster_called
            raster_called = True
            raise AssertionError("oversized page must not be rasterized")

    class FakePdf:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def __len__(self):
            return 1

        def __getitem__(self, index):
            assert index == 0
            return OversizedPage()

    monkeypatch.setattr(fitz, "open", lambda **kwargs: FakePdf())

    with pytest.raises(ValueError, match="Rasterlimit"):
        processing._process_pdf_to_images(b"pdf", max_pages=1)

    assert raster_called is False


def test_bounded_page_still_rasterizes(monkeypatch):
    monkeypatch.setattr(processing, "use_ocr_mode", lambda: False)
    pdf_bytes = _pdf_bytes([(72, 72)])

    processing._validate_pdf_limits(pdf_bytes)
    images = processing._process_pdf_to_images(pdf_bytes, max_pages=1)

    assert len(images) == 1
    assert images[0].startswith("data:image/jpeg;base64,")


def test_ocr_mode_does_not_apply_local_raster_limits(monkeypatch):
    monkeypatch.setattr(processing, "use_ocr_mode", lambda: True)
    oversized_width = (
        processing.MAX_IMAGE_PDF_RENDER_WIDTH + 1
    ) / processing._IMAGE_PDF_RENDER_SCALE
    pdf_bytes = _pdf_bytes([(oversized_width, 72)])

    processing._validate_pdf_limits(pdf_bytes)
