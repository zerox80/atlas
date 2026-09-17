"""One extraction format for bounded review sections, independent of stored values."""

import json

from ai_prompts import UNTRUSTED_DOCUMENT_NOTICE
from review_schema import ReviewExtraction

SEMANTIC_RULES = """
Das Fehlen eines gespeicherten Vertragswertes im aktuell geprüften Dokument stellt keinen Widerspruch dar.
Ein Konflikt erfordert ausdrücklich unterschiedliche Werte für dasselbe semantische Feld,
dieselbe Bedeutung, Währung, Bezugsperiode und denselben Geltungsbereich.
Vergleiche keine Werte unterschiedlicher semantischer Ebenen.
Unterscheide Positionsnetto/-brutto, Rechnungsnetto/-brutto, Vertragsnetto/-brutto,
wiederkehrendes Entgelt, Jahreswert und Einzelpreis. Ein Positionsbetrag ist kein Gesamtwert.
Unterscheide Vertragsbeginn, Leistungsbeginn, Rechnungsdatum, Bestelldatum, Lieferdatum und Laufzeitende.
Ein Lieferscheindatum ist weder Vertragsbeginn noch Rechnungsdatum.
Fehlende Werte weglassen. Keine Ersatzwerte, gesetzlichen oder üblichen Kündigungsfristen erfinden.
Eine Kündigungsfrist erfordert eine wörtliche ordentliche Kündigungsklausel mit Tagen/Wochen;
Kalendermonate nicht pauschal umrechnen. Widersprüchliche Aussagen als ambiguous kennzeichnen.
Rechnung allein belegt keine vollständigen Vertragsbedingungen. Dokumenttyp anhand des Inhalts bestimmen.
Jede explizite Angabe braucht einen wörtlichen kurzen Beleg samt Seite. Für Rechnungsbeträge
muss der Beleg die Bezeichnung (Netto/Brutto/Gesamt/Position) einschließen, für Daten das zugehörige Label.
Geldwerte als JSON-Zahlen, Datum als YYYY-MM-DD. currency als ISO-Code, Unsicherheit nie verschweigen.
Berechnete Werte als derived kennzeichnen, Rechnung im reason nennen; keine ungenannten Laufzeiten erfinden.
Eine Zusammenfassung oder neue Formulierung eines Titels ist derived, kein ausdrücklicher Widerspruch.
Titel und Beschreibung müssen alle hier erkennbaren Vertragsbestandteile abdecken;
eine einzelne Upgrade-Position darf vorhandene Maintenance-Leistungen nicht aus der Zusammenfassung verdrängen.
Mehrere Positionen zunächst auf gemeinsame Bestellung/Vertragsbindung prüfen und als components erfassen.
Alle Maintenance-/Wartungspositionen berücksichtigen. Niemals automatisch Unterverträge erzeugen.
Geräte-/Lizenzpreis und Support-/Wartungskosten als unterschiedliche Vertragsbestandteile erfassen;
Supportkosten nicht als Gerätepreis oder Gesamtvertragswert behandeln. Technische Seitengrenzen
begründen keine inhaltliche Trennung oder eigenständige Verträge.
Nur starke eigenständige Vertragsmerkmale als separate_contract_reasons vorschlagen;
ein anderer Betrag oder eine andere Position allein genügt nicht.
entity=document nur für Angaben des geprüften Gesamtvertrags/der Rechnung;
einzelne Positionen als component und eigenständige Vertragsverhältnisse als other_contract kennzeichnen.
Du siehst möglicherweise nur einen Abschnitt. Nenne alle hier belegten Angaben, auch widersprüchliche.
Erfinde keine Aussagen zu anderen Abschnitten. Das System führt die Abschnitte anschließend zusammen.
"""

REVIEW_SYSTEM_PROMPT = f"{UNTRUSTED_DOCUMENT_NOTICE}\n{SEMANTIC_RULES}"


def extraction_prompt(text: str, document_number: int, first_page: int, last_page: int) -> str:
    return (
        f"Dokument {document_number}, Originalseiten {first_page}–{last_page}. "
        "Extrahiere ausschließlich aus dem folgenden OCR-Abschnitt. "
        "Antworte mit einem vollständigen JSON-Objekt gemäß diesem Schema:\n"
        f"{json.dumps(ReviewExtraction.model_json_schema(), ensure_ascii=False)}\n"
        "<untrusted_document_text>\n" + text + "\n</untrusted_document_text>"
    )
