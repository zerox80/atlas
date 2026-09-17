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
    { field: "notice_period", before: 30, after: null, can_apply: true },
    { field: "value", before: 100, after: 120, can_apply: true },
    { field: "title", before: "Test-Rechnung", after: null, can_apply: false },
  ] },
};

beforeEach(() => { vi.clearAllMocks(); api.post.mockResolvedValue({ data: { ok: true } }); });

describe("ReviewItemCard", () => {
  it("allows explicit removal of an unsupported notice without applying unrelated suggestions", async () => {
    render(<ReviewItemCard item={item} runId="review-id" />);
    expect(screen.getByRole("button", { name: /Korrektur\(en\) übernehmen/ })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Titel übernehmen" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Dokument öffnen" })).toHaveAttribute("href", "/invoices?document_id=9");
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Kündigungsfrist (Tage) übernehmen" }));
    await userEvent.click(screen.getByRole("button", { name: "1 ausgewählte Korrektur(en) übernehmen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/ai/reviews/review-id/items/3/apply", { fields: ["notice_period"] }));
    expect(screen.getByRole("checkbox", { name: "Betrag / Gesamtwert übernehmen" })).not.toBeChecked();
  });

  it("does not offer to apply suggestions without write permission", () => {
    render(<ReviewItemCard item={{ ...item, can_write: false }} runId="review-id" />);
    expect(screen.getByRole("checkbox", { name: "Kündigungsfrist (Tage) übernehmen" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /übernehmen/ })).not.toBeInTheDocument();
  });
});
