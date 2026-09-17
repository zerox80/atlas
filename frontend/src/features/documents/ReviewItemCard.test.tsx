import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "../../test/utils";
import ReviewItemCard from "./ReviewItemCard";
import type { ReviewItem } from "./reviewTypes";

const api = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../../api", () => ({ default: api }));

const item: ReviewItem = {
  id: 3, contract_id: 9, title: "Test-Rechnung", document_type: "invoice", status: "issues", can_write: true,
  result: { checked_files: 2, warnings: [], changes: [
    { field: "notice_period", before: 30, after: null, can_apply: false, status: "NOT_EVIDENCED" },
    { field: "value", before: 100, after: 120, can_apply: true, status: "EXPLICIT_CONFLICT", reason: "Rechnungssumme brutto weicht ab.",
      document_name: "Rechnung.pdf", evidence: { page: 2, quote: "Gesamt brutto 120,00 EUR" }, evidence_verified: true },
    { field: "start_date", before: "2024-02-22", after: "2024-02-22", can_apply: false, status: "WRONG_SCOPE", reason: "Lieferscheindatum, kein Vertragsbeginn." },
  ], checks: [{ field: "notice_period", before: 30, after: null, can_apply: false, status: "NOT_EVIDENCED" }] },
};

beforeEach(() => { vi.clearAllMocks(); api.post.mockResolvedValue({ data: { ok: true } }); });

describe("ReviewItemCard", () => {
  it("shows concrete selectable changes immediately and recommendations for values to retain", async () => {
    render(<ReviewItemCard item={item} runId="review-id" />);
    const checkbox = screen.getByRole("checkbox", { name: "Betrag / Gesamtwert (brutto) übernehmen" });
    expect(checkbox).toBeVisible();
    expect(checkbox.closest("details")).toBeNull();
    expect(screen.getByText("100 €")).toBeVisible();
    expect(screen.getByText("120 €")).toBeVisible();
    expect(screen.getAllByText("Rechnungssumme brutto weicht ab.")[0]).toBeVisible();
    expect(screen.getByRole("button", { name: "Ausgewählte Änderungen übernehmen (0)" })).toBeDisabled();
    expect(screen.queryByRole("checkbox", { name: "Kündigungsfrist (Tage) übernehmen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Bisheriges Start-/Rechnungsdatum übernehmen" })).not.toBeInTheDocument();
    expect(screen.getByText("Kündigungsfrist (Tage): 30 beibehalten")).toBeVisible();
    expect(screen.getByText("Lieferscheindatum, kein Vertragsbeginn.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Dokument öffnen" })).toHaveAttribute("href", "/invoices?document_id=9");
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(checkbox);
    await userEvent.click(screen.getByRole("button", { name: "Ausgewählte Änderungen übernehmen (1)" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/review-id/items/3/apply", { fields: ["value"] }));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Übernommen: Betrag / Gesamtwert (brutto).");
    expect(screen.getByText("Keine weiteren Änderungen empfohlen.")).toBeVisible();
  });

  it("explains read-only access and retains the visible proposal without controls", () => {
    render(<ReviewItemCard item={{ ...item, can_write: false }} runId="review-id" />);
    expect(screen.getByText("120 €")).toBeVisible();
    expect(screen.getByText(/Nur Ansicht: Du hast keine Schreibberechtigung/)).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /übernehmen/i })).not.toBeInTheDocument();
  });

  it("keeps foreign currency visible with a clear recommendation to retain the EUR amount", () => {
    render(<ReviewItemCard runId="review-id" item={{ ...item, result: { changes: [
      { field: "value", before: 100, after: 120, currency: "USD", can_apply: false, status: "WRONG_SCOPE" },
    ] } }} />);
    expect(screen.getByText("Betrag / Gesamtwert (brutto): 100 € beibehalten")).toBeVisible();
    expect(screen.getByText("Nicht zur Übernahme empfohlen: 120 USD")).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("recommends retaining an ambiguous date with an explanation instead of disabled controls", () => {
    render(<ReviewItemCard runId="review-id" item={{ ...item, result: { changes: [
      { field: "start_date", before: "2019-09-24", after: "2017-02-07", can_apply: false,
        status: "AMBIGUOUS", evidence_verified: false, evidence: { page: 14, quote: "RNW vSphere ..." } },
    ] } }} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("Bisheriges Start-/Rechnungsdatum: 24.09.2019 beibehalten")).toBeVisible();
    expect(screen.getByText(/Dokumentbeleg ist nicht eindeutig verifiziert/)).toBeVisible();
    expect(screen.queryByText(/Übernahme gesperrt|manuell prüfen/i)).not.toBeInTheDocument();
  });

  it("shows the failed stage, exact page checkpoint and configured models", () => {
    render(<ReviewItemCard runId="review-id" item={{ ...item, status: "error", error: "Mistral hat Modell oder Endpunkt nicht gefunden.", result: {
      model: "zai-glm-5-3", ocr_model: "mistral-ocr-4-1",
      diagnostic: { code: "PROVIDER_HTTP_404", stage: "ocr", http_status: 404, message: "Modell nicht gefunden." },
      progress: { completed_pages: 0, ocr_completed_pages: 8, total_pages: 22, document_name: "Vertrag.pdf", first_page: 9, last_page: 12, stage: "ocr" },
    } }} />);
    expect(screen.getByRole("note", { name: "Fehlerdetails" })).toHaveTextContent("PROVIDER_HTTP_404 · OCR-Texterkennung · HTTP 404");
    expect(screen.getByText(/8 von 22 PDF-Seiten gescannt/)).toBeInTheDocument();
    expect(screen.getByText(/Vertrag.pdf · Seiten 9–12/)).toBeInTheDocument();
    expect(screen.getByText(/zai-glm-5-3.*mistral-ocr-4-1/)).toBeInTheDocument();
  });

  it("retains a gross total when the document only gives a product net price", () => {
    render(<ReviewItemCard runId="review-id" item={{ ...item, result: { changes: [
      { field: "value", before: 9752.05, after: 2155.28, currency: "EUR", can_apply: false,
        status: "WRONG_SCOPE", reason: "Positionsnetto ersetzt keinen Bruttogesamtbetrag." },
    ] } }} />);
    expect(screen.getByText("Betrag / Gesamtwert (brutto): 9.752,05 € beibehalten")).toBeVisible();
    expect(screen.getByText("Nicht zur Übernahme empfohlen: 2.155,28 €")).toBeVisible();
    expect(screen.getByText("Positionsnetto ersetzt keinen Bruttogesamtbetrag.")).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/Vertragsbestandteile|Unterverträge/)).not.toBeInTheDocument();
  });
});
