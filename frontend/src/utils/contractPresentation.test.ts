import { afterEach, describe, expect, it, vi } from "vitest";
import type { Contract } from "../types";
import { getCancellationDeadline, getContractState, getDaysUntilCancellation } from "./contractPresentation";

const contract: Contract = {
  id: 1, title: "Vertrag", end_date: "2026-10-01T00:00:00Z", uploaded_at: "2026-01-01", tags: [],
  file_extension: ".pdf", document_type: "contract", is_protected: false,
  can_read: true, can_write: true, can_delete: true, can_manage_protection: true,
};
afterEach(() => vi.useRealTimers());

describe("cancellation presentation", () => {
  it("does not invent a deadline for a null or missing notice", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-17T12:00:00Z"));
    for (const notice_period of [null, undefined]) {
      const unknown = { ...contract, notice_period };
      expect(getCancellationDeadline(unknown)).toBeNull();
      expect(getDaysUntilCancellation(unknown)).toBe(Infinity);
      expect(getContractState(unknown)).toMatchObject({ key: "active", label: "Frist unbekannt" });
    }
  });

  it("keeps an explicit zero-day notice and calendar-day subtraction across DST", () => {
    expect(getCancellationDeadline({ ...contract, notice_period: 0 })).toBe("2026-10-01");
    expect(getCancellationDeadline({ ...contract, end_date: "2026-04-01T10:00:00Z", notice_period: 7 })).toBe("2026-03-25");
  });

  it("still recognizes an expired contract without a known notice", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-02T12:00:00Z"));
    expect(getContractState(contract).key).toBe("expired");
  });
});
