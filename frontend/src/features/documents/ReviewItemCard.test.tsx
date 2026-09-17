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
  it("offers only meaningful corrections and preserves missing or differently scoped values", async () => {
    render(<ReviewItemCard item={item} runId="review-id" />);
    expect(screen.getByRole("button", { name: /Korrektur\(en\) übernehmen/ })).toBeDisabled();
    expect(screen.queryByRole("checkbox", { name: "Kündigungsfrist (Tage) übernehmen" })).not.toBeInTheDocument();
    expect(screen.getByText(/gespeicherte Werte bleiben erhalten/)).toBeInTheDocument();
    expect(screen.getByText("Echter Widerspruch")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Bisheriges Start-/Rechnungsdatum übernehmen" })).toBeDisabled();
    expect(screen.getByText(/Übernahme gesperrt: Diese Angabe gehört nicht/)).toBeInTheDocument();
    expect(screen.getByText("Rechnung.pdf · Seite 2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dokument öffnen" })).toHaveAttribute("href", "/invoices?document_id=9");
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Betrag / Gesamtwert (brutto) übernehmen" }));
    await userEvent.click(screen.getByRole("button", { name: "1 ausgewählte Korrektur(en) übernehmen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/review-id/items/3/apply", { fields: ["value"] }));
    expect(screen.getByRole("checkbox", { name: "Betrag / Gesamtwert (brutto) übernehmen" })).not.toBeChecked();
  });

  it("does not offer to apply suggestions without write permission", () => {
    render(<ReviewItemCard item={{ ...item, can_write: false }} runId="review-id" />);
    expect(screen.getByRole("checkbox", { name: "Betrag / Gesamtwert (brutto) übernehmen" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /übernehmen/ })).not.toBeInTheDocument();
  });

  it("keeps a foreign currency visible without offering to overwrite EUR", () => {
    render(<ReviewItemCard runId="review-id" item={{ ...item, result: { changes: [
      { field: "value", before: 100, after: 120, currency: "USD", can_apply: false, status: "WRONG_SCOPE" },
    ] } }} />);
    expect(screen.getByText("100 €")).toBeInTheDocument();
    expect(screen.getByText("120 USD")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("shows a disabled selection and the reason for an unverified date from another source", () => {
    render(<ReviewItemCard runId="review-id" item={{ ...item, result: { changes: [
      { field: "start_date", before: "2019-09-24", after: "2017-02-07", can_apply: false,
        status: "AMBIGUOUS", evidence_verified: false, evidence: { page: 14, quote: "RNW vSphere ..." } },
    ] } }} />);
    const checkbox = screen.getByRole("checkbox", { name: "Bisheriges Start-/Rechnungsdatum übernehmen" });
    expect(checkbox).toBeDisabled();
    expect(checkbox).toHaveAccessibleDescription("Übernahme gesperrt: Beleg nicht verifiziert – Originaldokument prüfen.");
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

  it("keeps a product price from replacing the gross total without proposing subcontracts", () => {
    render(<ReviewItemCard runId="review-id" item={{ ...item, result: { changes: [
      { field: "value", before: 9752.05, after: 2155.28, currency: "EUR", can_apply: false,
        status: "WRONG_SCOPE", reason: "Positionsnetto ersetzt keinen Bruttogesamtbetrag." },
    ] } }} />);
    expect(screen.getByText("9.752,05 €")).toBeInTheDocument();
    expect(screen.getByText("2.155,28 €")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.queryByText(/Vertragsbestandteile|Unterverträge/)).not.toBeInTheDocument();
  });
});
