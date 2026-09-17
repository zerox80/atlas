import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "../../test/utils";
import ReviewItemCard from "./ReviewItemCard";
import type { ReviewItem } from "./reviewTypes";

const api = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../../api", () => ({ default: api }));
const item: ReviewItem = { id: 1, title: "Sammlung", status: "hints", can_write: true,
  result: { changes: [
    { field: "value", before: 100, after: 119, can_apply: true, status: "EXPLICIT_CONFLICT", recommendation: "update",
      recommendation_reason: "Die Rechnung nennt 119 EUR als Gesamtbrutto." },
    { field: "end_date", before: null, after: "2027-05-31", can_apply: true, status: "NEW_INFORMATION" },
  ] } };

beforeEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); api.post.mockResolvedValue({ data: { ok: true } }); });

describe("Änderungsvorschläge auswählen", () => {
  it("applies only the selected proposal, refreshes related queries and keeps the other proposal available", async () => {
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    render(<ReviewItemCard item={item} runId="run" />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
    expect(screen.getByText("Die Rechnung nennt 119 EUR als Gesamtbrutto.")).toBeVisible();
    await userEvent.click(screen.getByRole("checkbox", { name: "Betrag / Gesamtwert (brutto) übernehmen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ausgewählte Änderungen übernehmen (1)" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/run/items/1/apply", { fields: ["value"] }));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith(["document-reviews"]));
    for (const key of ["contracts", "invoices", "workspace-documents", "protected-contracts", "trash", "tags"])
      expect(invalidate).toHaveBeenCalledWith([key]);
    expect(screen.queryByRole("checkbox", { name: "Betrag / Gesamtwert (brutto) übernehmen" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Enddatum übernehmen" })).toBeEnabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Enddatum übernehmen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ausgewählte Änderungen übernehmen (1)" }));
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith("/ai/reviews/run/items/1/apply", { fields: ["end_date"] }));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("gives keep and leave-empty recommendations without asking for an empty decision", () => {
    render(<ReviewItemCard item={{ ...item, result: { changes: [], checks: [
      { field: "value", before: 9752.05, after: 2155.28, can_apply: false, status: "WRONG_SCOPE", recommendation: "keep",
        recommendation_reason: "Den Gesamtbetrag beibehalten; der kleinere Betrag gehört zu einer Position." },
      { field: "end_date", before: null, after: null, can_apply: false, status: "NOT_EVIDENCED", recommendation: "leave_empty",
        recommendation_reason: "Kein Laufzeitende belegt; das Feld leer lassen." },
    ] } }} runId="run" />);
    expect(screen.getByText("Keine Änderung empfohlen.")).toBeVisible();
    expect(screen.getByText("Betrag / Gesamtwert (brutto): 9.752,05 € beibehalten")).toBeVisible();
    expect(screen.getByText("Enddatum: Leer lassen")).toBeVisible();
    expect(screen.getByText("Kein Laufzeitende belegt; das Feld leer lassen.")).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("keeps a failed save actionable and displays the server error", async () => {
    api.post.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: "Dokument inzwischen geändert." } } });
    render(<ReviewItemCard item={item} runId="run" />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Enddatum übernehmen" }));
    await userEvent.click(screen.getByRole("button", { name: "Ausgewählte Änderungen übernehmen (1)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 409: Dokument inzwischen geändert.");
    expect(screen.getByRole("button", { name: "Ausgewählte Änderungen übernehmen (1)" })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "Enddatum übernehmen" })).toBeChecked();
  });

  it("does not reactivate a historical decision or legacy report", () => {
    const view = render(<ReviewItemCard item={{ ...item, result: { ...item.result, decision: "rejected" } }} runId="run" />);
    expect(screen.getByText(/Prüfvorschlag wurde bereits abgelehnt/)).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    view.rerender(<ReviewItemCard item={{ ...item, result: { ...item.result, legacy_report: true } }} runId="run" />);
    expect(screen.getByText(/Älterer Prüfbericht aus dem vorherigen/)).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it.each(["processing", "pending", "error"])("does not expose stale proposals while the report is %s", status => {
    render(<ReviewItemCard item={{ ...item, status }} runId="run" />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Änderungen übernehmen/ })).not.toBeInTheDocument();
  });

  it("creates only selected independent entries after confirmation", async () => {
    api.post.mockResolvedValue({ data: { created: [{ id: 23, title: "VMware", document_type: "contract" }] } });
    const splitItem: ReviewItem = { ...item, result: { changes: [], split_proposals: [
      { title: "Veeam", document_type: "invoice", pages: [{ document: 1, page: 1 }], reason: "Eigene Rechnung",
        values: { value: 119 }, evidence: { document: 1, page: 1, quote: "Veeam Rechnung" } },
      { title: "VMware", document_type: "contract", pages: [{ document: 1, page: 2 }], reason: "Eigener Vertrag",
        values: {}, evidence: { document: 1, page: 2, quote: "VMware Vertrag" } },
    ] } };
    render(<ReviewItemCard item={splitItem} runId="run" />);
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.getByText(/Original bleibt zusätzlich/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Veeam" }));
    await userEvent.click(screen.getByRole("button", { name: "Ja, 1 Eintrag mit eigenen PDFs erstellen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/run/items/1/split", { accept: true, selected: [1] }));
    expect(await screen.findByRole("link", { name: "VMware" })).toHaveAttribute("href", "/contracts?document_id=23");
    expect(screen.queryByRole("button", { name: /PDFs erstellen/ })).not.toBeInTheDocument();
  });
});
