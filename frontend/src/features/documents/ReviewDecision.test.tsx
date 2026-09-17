import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "../../test/utils";
import ReviewItemCard from "./ReviewItemCard";
import type { ReviewItem } from "./reviewTypes";

const api = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../../api", () => ({ default: api }));
const item: ReviewItem = { id: 1, title: "Sammlung", status: "hints", can_write: true,
  result: { changes: [{ field: "value", before: 100, after: 119, can_apply: true, status: "EXPLICIT_CONFLICT" }] } };

beforeEach(() => { vi.clearAllMocks(); api.post.mockResolvedValue({ data: { ok: true } }); });

describe("Ja-/Nein-Prüfvorschläge", () => {
  it.each([true, false])("records the visible whole proposal decision %s", async accept => {
    render(<ReviewItemCard item={item} runId="run" />);
    await userEvent.click(screen.getByRole("button", { name: accept ? "Ja, Vorschlag übernehmen" : "Nein, Vorschlag ablehnen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/run/items/1/decision", { accept }));
    expect(await screen.findByRole("status")).toHaveTextContent(accept ? "Ja bestätigt" : "Nein bestätigt");
  });
  it("offers keeping values when evidence does not support a correction", async () => {
    render(<ReviewItemCard item={{ ...item, result: { changes: [{ field: "value", before: 9752.05, after: 2155.28,
      can_apply: false, status: "WRONG_SCOPE" }] } }} runId="run" />);
    await userEvent.click(screen.getByRole("button", { name: "Ja, Angaben beibehalten" }));
    expect(api.post).toHaveBeenCalledWith("/ai/reviews/run/items/1/decision", { accept: true });
  });
  it("keeps a failed save actionable and shows the server reason", async () => {
    api.post.mockRejectedValue(new Error("offline"));
    render(<ReviewItemCard item={item} runId="run" />);
    await userEvent.click(screen.getByRole("button", { name: "Ja, Vorschlag übernehmen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ja, Vorschlag übernehmen" })).toBeEnabled();
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
