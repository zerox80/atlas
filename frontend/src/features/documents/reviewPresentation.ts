import type { ReviewChange, ReviewItem } from "./reviewTypes";
import { formatGermanNumber } from "../../utils/formatUtils";

export const labels: Record<string, string> = {
  title: "Titel", description: "Beschreibung", value: "Betrag / Gesamtwert (brutto)",
  annual_value: "Jahreswert", start_date: "Bisheriges Start-/Rechnungsdatum", end_date: "Enddatum",
  notice_period: "Kündigungsfrist (Tage)", tags: "Kategorien",
};
export const scopeLabels: Record<string, string> = {
  ...labels, legacy_amount: "Bisheriger Betrag – Bedeutung unbekannt", legacy_date: "Bisheriges Datum – Bedeutung unbekannt",
  contract_value_net: "Vertragswert netto", contract_value_gross: "Vertragswert brutto",
  invoice_total_net: "Rechnungssumme netto", invoice_total_gross: "Rechnungssumme brutto",
  recurring_amount: "Wiederkehrendes Entgelt", line_item_net: "Positionsbetrag netto", line_item_gross: "Positionsbetrag brutto",
  unit_price: "Einzelpreis", currency: "Währung", tax_rate: "Umsatzsteuer (%)", billing_interval: "Abrechnungsintervall",
  contract_start_date: "Vertragsbeginn", service_start_date: "Leistungsbeginn", invoice_date: "Rechnungsdatum",
  order_date: "Bestelldatum", delivery_date: "Liefer-/Lieferscheindatum", contract_end_date: "Laufzeitende",
};
export const checkLabels: Record<string, string> = {
  CONFIRMED: "Bestätigt", EXPLICIT_CONFLICT: "Echter Widerspruch", NOT_EVIDENCED: "Im Dokument nicht belegt",
  NEW_INFORMATION: "Ergänzung verfügbar", AMBIGUOUS: "Nicht eindeutig belegt", DERIVED: "Abgeleiteter Vorschlag", WRONG_SCOPE: "Angabe für ein anderes Feld",
};
export const stageLabels: Record<string, string> = {
  read: "Datei lesen", prepare: "PDF vorbereiten", ocr: "OCR-Texterkennung", analysis: "KI-Auswertung",
  waiting: "Nächste Seiten scannen", analysis_pending: "Scan vollständig · Gesamtauswertung ausstehend", complete: "Abgeschlossen", unknown: "Unbekannter Schritt",
};
export const sourceLabels: Record<string, string> = {
  invoice: "Rechnung", contract: "Vertrag", amendment: "Nachtrag", order_confirmation: "Auftragsbestätigung",
  delivery_note: "Lieferschein", unknown: "Unbekannter Dokumenttyp",
};
export const proposalKey = (change: ReviewChange) => JSON.stringify([change.field, change.before, change.after]);
export function reviewFields(result: ReviewItem["result"]): ReviewChange[] {
  return Array.from(new Map([...(result?.checks || []), ...(result?.changes || [])]
    .map(change => [change.field, change])).values());
}
export function canApply(change: ReviewChange): boolean {
  return change.can_apply && change.after != null && (!change.recommendation || change.recommendation === "update")
    && ["EXPLICIT_CONFLICT", "NEW_INFORMATION", "DERIVED"].includes(change.status || "");
}
export function recommendationFor(change: ReviewChange): "update" | "keep" | "leave_empty" {
  if (canApply(change)) return "update";
  return change.before == null || change.before === "" || (Array.isArray(change.before) && !change.before.length)
    ? "leave_empty" : "keep";
}
export function recommendationReason(change: ReviewChange): string {
  if (change.status === "NOT_EVIDENCED") return "Die KI-Auswertung hat für dieses Feld keine belegte Angabe geliefert.";
  if (change.recommendation_reason) return change.recommendation_reason;
  if (change.reason) return change.reason;
  if (change.evidence_verified === false) return "Der Dokumentbeleg ist nicht eindeutig verifiziert und rechtfertigt keine Änderung.";
  if (change.status === "CONFIRMED") return "Die gespeicherte Angabe stimmt mit dem Dokument überein.";
  if (change.status === "WRONG_SCOPE") return "Die Dokumentangabe gehört zu einem anderen Feld und ersetzt diesen Wert nicht.";
  if (change.status === "AMBIGUOUS") return "Wert oder Zuordnung sind nicht eindeutig belegt; eine Änderung ist nicht empfohlen.";
  if (canApply(change)) return "Die Dokumentangabe ist ausreichend belegt und wird zur Übernahme empfohlen.";
  return "Es gibt keinen ausreichend belegten anderen Wert für dieses Feld.";
}
export function valueText(value: ReviewChange["before"], field: string, currency: string | null = "EUR"): string {
  if (value == null) return "Keine Angabe";
  if (Array.isArray(value)) return value.join(", ") || "Keine";
  if (typeof value === "string" && field.endsWith("date") && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value.split("-").reverse().join(".");
  const unit = field === "value" || field === "annual_value" ? ` ${currency === "EUR" ? "€" : currency || "(Währung unbekannt)"}` : "";
  return typeof value === "number" ? `${formatGermanNumber(value)}${unit}` : value;
}
