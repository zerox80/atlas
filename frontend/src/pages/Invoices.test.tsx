import { describe, expect, it, vi } from "vitest";
import { screen, render } from "../test/utils";
import type { Contract } from "../types";
import Invoices from "./Invoices";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("../api", () => ({
  default: { get: mocks.get },
  fetchContractPage: () =>
    mocks.get().then((response: { data: Contract[] }) => {
      const items = response.data;
      const totalValue = items.reduce(
        (sum: number, item: { value?: number | null }) =>
          sum + (item.value ?? 0),
        0,
      );
      return {
        items,
        summary: {
          all: items.length,
          active: items.length,
          attention: 0,
          expired: 0,
          total_value: totalValue,
          current_month_value: totalValue,
        },
        has_more: false,
        next_cursor_uploaded_at: null,
        next_cursor_id: null,
      };
    }),
}));

vi.mock("../components/UploadModal", () => ({
  default: () => null,
}));

describe("Invoices", () => {
  it("renders compact invoice details and every permitted action", async () => {
    mocks.get.mockResolvedValueOnce({
      data: [
        {
          id: 1,
          title: "Telekom · Juni 2026",
          description: null,
          start_date: "2026-06-15",
          uploaded_at: "2026-06-15T12:00:00Z",
          value: 50,
          tags: [{ name: "Telekom", color: "#77a7ff" }],
          file_extension: "pdf",
          document_type: "invoice",
          is_protected: false,
          can_read: true,
          can_write: true,
          can_delete: true,
          can_manage_protection: false,
        },
      ],
    });

    render(<Invoices />);

    expect(await screen.findByText("Telekom · Juni 2026")).toBeInTheDocument();
    expect(screen.getAllByText("Datum")).toHaveLength(2);
    expect(screen.getAllByText("Status")).toHaveLength(2);
    expect(screen.getAllByText("Betrag")).toHaveLength(2);
    expect(screen.getAllByText("50 €")).toHaveLength(3);
    expect(screen.getByTitle("Herunterladen")).toBeEnabled();
    expect(screen.getByTitle("Bearbeiten")).toBeEnabled();
    expect(screen.getByTitle("Löschen")).toBeEnabled();
  });
});
