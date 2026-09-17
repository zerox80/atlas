import { describe, expect, it } from "vitest";
import { reviewRequestError } from "./reviewRequestError";

describe("Review request errors", () => {
  it("explains the local rate limit rather than showing only the generic failure", () => {
    const error = { response: { status: 429, data: { error: "Bitte nach einer Minute erneut versuchen." } } };
    expect(reviewRequestError(error, "Prüflauf konnte nicht angelegt werden.")).toContain("Bitte nach einer Minute");
    expect(reviewRequestError(error, "Prüflauf konnte nicht angelegt werden.")).toContain("vor dem Start");
  });
  it("preserves actionable server details for stale reports", () => {
    const error = { response: { status: 409, data: { detail: "Dokument inzwischen geändert." } } };
    expect(reviewRequestError(error, "Speichern fehlgeschlagen.")).toBe("HTTP 409: Dokument inzwischen geändert.");
  });
});
