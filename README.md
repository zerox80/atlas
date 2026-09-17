# Atlas

Dieses Projekt ist eine KI gestützte Plattform zur Verwaltung und Analyse von Verträgen. Es kombiniert ein modernes Web Interface mit leistungsstarken KI Funktionen zur automatischen Datenextraktion und Dokumenteninteraktion.

## Hauptfunktionen

Das System bietet umfassende Werkzeuge für das Vertragsmanagement:

* Automatisierte Vertragsanalyse: Mithilfe von Mistral Medium 3.5 werden wichtige Daten wie Laufzeiten, Beträge und Kündigungsfristen automatisch aus PDF Dokumenten extrahiert.
* Rechnungsverwaltung: Rechnungen können unabhängig von Verträgen hochgeladen, mit OCR/KI ausgelesen und separat verwaltet werden.
* Mehrere Dateien pro Vertrag: Ein Hauptdokument und bis zu neun Anhänge (jeweils maximal 10 MiB) werden gemeinsam gespeichert. Im Upload-Dialog lässt sich die PDF für die KI-Analyse separat auswählen. Beim Bearbeiten lassen sich Hauptdokument und Anhänge einzeln über „Ersetzen“ austauschen, Anhänge mit „×“ entfernen und weitere Dateien ergänzen. Die Änderungen gelten erst nach „Änderungen speichern“; das Vertrags-Item und die übrigen Dateien bleiben erhalten. Anhänge sind in den Details herunterladbar und in Datensicherung sowie Papierkorb enthalten.
* Interaktiver Chat: Nutzer können spezifische Fragen zu Vertragsinhalten stellen und erhalten präzise Antworten basierend auf dem Dokument.
* Benutzer und Rollenmanagement: Eine integrierte Administration ermöglicht die Steuerung von Zugriffsrechten und Rollen.
* Sicherheit: Das System implementiert eine Zwei Faktor Authentifizierung (TOTP) sowie detaillierte Audit Logs zur Nachverfolgbarkeit aller Aktionen.
* Dashboard: Eine übersichtliche Darstellung bietet schnellen Zugriff auf alle Verträge sowie Filter und Tagging Funktionen.

## Technische Basis

Die Anwendung nutzt eine moderne Architektur:

* Backend: Entwickelt mit FastAPI und SQLModel für hohe Performance und einfache Datenbankinteraktion.
* Frontend: Eine reaktive Weboberfläche für optimale Benutzererfahrung.
* KI Service: Integration der Mistral AI API für fortgeschrittene Sprachverarbeitung.
* Infrastruktur: Containerisierung mittels Docker und Docker Compose für eine schnelle Bereitstellung.

## Installation

Bei Updates für Mehrdatei-Uploads muss auch ein bereits eingerichteter externer
Nginx-Proxy `client_max_body_size 101M;` verwenden. Die mitgelieferten Vorlagen
und das Setup-Skript berücksichtigen dies; die Grenze pro einzelner Datei bleibt
10 MiB. Die zusätzliche Datenbanktabelle für Anhänge wird beim Backend-Start
automatisch angelegt, vorhandene Hauptdokumente bleiben erhalten.

### Interaktives Nginx- und HTTPS-Setup

Auf Debian- und Ubuntu-Servern richtet das folgende Skript Docker auf
`127.0.0.1`, den Host-Nginx und optional HTTPS interaktiv ein:

```bash
sudo python3 scripts/setup_nginx_proxy.py
```

Zur Auswahl stehen ein internes LAN-Setup mit lokaler CA und IP-Zertifikat
sowie ein externes Setup mit Certbot/Let's Encrypt oder vorhandenen
Zertifikaten. Im lokalen Modus erkennt das Skript die Server-IP und das dazu
gehörende Netzwerkinterface automatisch, unabhängig davon, ob es beispielsweise
`eth0`, `ens18`, `enp1s0` oder anders heißt. Ist UFW aktiv, wird außerdem die
echte SSH-Client-IP erkannt und für die Nginx-Ports `80`/`443` freigegeben; der
Docker-Port `8080` bleibt ausschließlich an `127.0.0.1` gebunden. Die automatisch
erkannte Quell-IP kann bei der Abfrage durch ein CIDR-Netz ersetzt werden.
Vorhandene `.env`-, Compose- und Nginx-Dateien werden gesichert.

#### Lokale CA per Gruppenrichtlinie verteilen

Beim lokalen HTTPS-Modus müssen die Windows-Clients der von Atlas erzeugten CA
vertrauen. Verteilt wird ausschließlich das öffentliche CA-Zertifikat. Der
private Schlüssel `/etc/nginx/atlas-tls/atlas-local-ca.key` darf niemals den
Server verlassen.

Zunächst wird das PEM-Zertifikat auf dem Atlas-Server in eine für den
Windows-Import geeignete DER-Datei umgewandelt und für den Download lesbar
gemacht:

```bash
sudo openssl x509 \
  -in /etc/nginx/atlas-tls/atlas-local-ca.crt \
  -outform DER \
  -out /tmp/atlas-local-ca.cer
sudo chmod 0644 /tmp/atlas-local-ca.cer
```

Anschließend wird die Datei auf einem Windows-Administrationsrechner mit `scp`
in das aktuelle Verzeichnis kopiert. Benutzername und Server-IP sind bei Bedarf
anzupassen:

```powershell
scp dashboard@192.168.1.128:/tmp/atlas-local-ca.cer .
```

Die Datei liegt danach im aktuellen Verzeichnis. Soll stattdessen `C:\Temp`
verwendet werden, muss der Ordner vor dem Kopieren existieren:

```powershell
mkdir C:\Temp
scp dashboard@192.168.1.128:/tmp/atlas-local-ca.cer C:\Temp\atlas-local-ca.cer
```

Die Verteilung erfolgt anschließend über die Gruppenrichtlinienverwaltung:

1. `gpmc.msc` öffnen und eine neue GPO, beispielsweise `Atlas Local CA Trust`,
   erstellen.
2. Die GPO mit der OU verknüpfen, in der sich die **Computerobjekte** der
   Zielgeräte befinden. Eine Verknüpfung auf Domänenebene gilt entsprechend für
   alle einbezogenen Domänencomputer.
3. Die GPO bearbeiten und zu
   `Computerkonfiguration > Richtlinien > Windows-Einstellungen >`
   `Sicherheitseinstellungen > Richtlinien für öffentliche Schlüssel >`
   `Vertrauenswürdige Stammzertifizierungsstellen` navigieren.
4. Dort `atlas-local-ca.cer` über **Importieren** hinzufügen. Nicht das
   Serverzertifikat `atlas.crt` importieren.
5. Auf einem Client die Richtlinie sofort aktualisieren und danach den Browser
   vollständig neu starten:

   ```powershell
   gpupdate /force
   ```

6. Die Installation auf dem Client kontrollieren:

   ```powershell
   Get-ChildItem Cert:\LocalMachine\Root |
       Where-Object Subject -eq 'CN=Atlas Local CA' |
       Format-List Subject, Thumbprint, NotAfter
   ```

Chrome und Edge verwenden den Windows-Zertifikatsspeicher. Aktuelle
Firefox-Versionen übernehmen durch Windows beziehungsweise GPO installierte
Root-CAs ebenfalls. Die aufgerufene IP muss weiterhin exakt mit der IP im
Atlas-Serverzertifikat übereinstimmen, beispielsweise `https://192.168.1.128`.
Der offizielle Ablauf ist außerdem in der
[Microsoft-Dokumentation zur Zertifikatsverteilung per GPO](https://learn.microsoft.com/en-us/windows-server/identity/ad-fs/deployment/distribute-certificates-to-client-computers-by-using-group-policy)
beschrieben.

Für den Betrieb ist die Konfiguration der Umgebungsvariablen in einer .env Datei erforderlich, insbesondere der MISTRAL_API_KEY.

### Mistral-Modelle, Thinking und OCR 4

Die KI Analyse nutzt standardmäßig Mistral OCR 4 über das Modell `mistral-ocr-4-0`. Der OCR Aufruf extrahiert Markdown, Tabellen im Markdown Format, strukturierte OCR 4 Blöcke sowie Seiten Konfidenzwerte. Diese Defaults können per `.env` angepasst werden:

```env
MISTRAL_CHAT_MODEL=mistral-medium-3-5
MISTRAL_REASONING_EFFORT=high
MISTRAL_REQUEST_TIMEOUT_SECONDS=900
MISTRAL_OCR_MODEL=mistral-ocr-4-0
MISTRAL_OCR_TABLE_FORMAT=markdown
MISTRAL_OCR_INCLUDE_BLOCKS=true
MISTRAL_OCR_CONFIDENCE_GRANULARITY=page
MISTRAL_USE_OCR=true
MISTRAL_MAX_PDF_PAGES=100
MISTRAL_MAX_IMAGE_PDF_PAGES=8
MISTRAL_DOCUMENT_PROCESSING_ENABLED=true
```

Analyse und Vertragschat verwenden für Mistral Medium 3.5 standardmäßig `reasoning_effort="high"`, dessen höchste Reasoning-Stufe. Mit `MISTRAL_REASONING_EFFORT=none` lässt sich der ausführliche Thinking-Modus deaktivieren. Thinking-Blöcke werden getrennt von der eigentlichen Antwort verarbeitet; JSON-Auswertung und Chat zeigen nur den Antworttext. Details: [Mistral Reasoning](https://docs.mistral.ai/studio/conversations/reasoning).

Alternativ unterstützt Atlas **GLM 5.3 als von Mistral gehostetes Modell**. Dafür ersetzen Sie die entsprechenden Werte in Ihrer `.env`:

```env
MISTRAL_CHAT_MODEL=zai-glm-5-3
MISTRAL_REASONING_EFFORT=max
MISTRAL_REQUEST_TIMEOUT_SECONDS=900
MISTRAL_USE_OCR=true
```

Beide Chatmodelle und OCR verwenden ausschließlich `https://api.mistral.ai` mit demselben `MISTRAL_API_KEY`. Laut [Mistrals Modellbeschreibung](https://docs.mistral.ai/models/zai-glm-5-3) ist `zai-glm-5-3` ein Textmodell. Atlas benötigt deshalb für PDFs `MISTRAL_USE_OCR=true`; bei deaktiviertem OCR wird diese Kombination vor einem API-Aufruf abgelehnt.

Atlas sendet für GLM 5.3 `reasoning_effort="max"` unverändert an Mistral. Für Medium 3.5 wird `max` abgelehnt. Mit `MISTRAL_REASONING_EFFORT=auto` oder ohne gesetzte Variable wählt Atlas modellabhängig `max` für `zai-glm-5-3` **und `zai-glm-latest`** und `high` für Medium 3.5. Der Alias aus dem Mistral-Playground wird auch bei der OCR-Pflicht und im Transport erkannt; `5.3` allein ist keine Modellkennung. Explizite Werte haben Vorrang: Beim Wechsel von Medium zu GLM müssen Sie ein vorhandenes `high` deshalb auf `max` oder `auto` ändern. Die GLM-Übertragung von `max` wird mit dem echten Mistral-SDK und simulierten HTTP-Antworten getestet; eine Live-Bestätigung durch Mistrals API steht aus.

### Einzelne oder alle Verträge und Rechnungen prüfen

Unter **KI-Prüfung** startet ein Prüflauf für alle zugänglichen Verträge und Rechnungen, unabhängig von Listenfiltern und Seitengröße. Geschützte Dokumente und PDF-Anlagen sind eingeschlossen, Papierkorb ist ausgeschlossen. Nicht unterstützte Hauptdateien werden als nicht geprüft ausgewiesen; nicht unterstützte Anlagen erzeugen einen Hinweis.

Für eine **Einzelprüfung** in den Vertrags- oder Rechnungsdetails **Dieses Dokument mit KI prüfen** anklicken. Am gespeicherten Prüfergebnis gibt es außerdem **Nur dieses Dokument erneut prüfen**. Beide starten einen neuen Lauf ausschließlich für dieses Dokument einschließlich seiner PDF-Anlagen und öffnen direkt dessen Fortschritt. Andere Dokumente werden dabei nicht geprüft. Der ausgewählte Lauf bleibt über `?run_id=…` auch nach Neuladen geöffnet. Ein bereits aktiver anderer Lauf muss zuerst pausiert und seine laufende Anfrage beendet werden. Die API unterstützt dafür `POST /ai/reviews` mit `{"start": true, "document_id": 123}`. Ungültige, gelöschte oder nicht zugängliche IDs starten niemals ersatzweise eine Gesamtprüfung.

OCR scannt Haupt-PDF und PDF-Anlagen nacheinander in Paketen von bis zu vier Seiten (`MISTRAL_REVIEW_SECTION_PAGES=4`, zulässig 1–10). Nach jedem Scan wird der erkannte Text mit Originalseitenzahlen gespeichert. Erst wenn **alle Seiten gescannt** sind, folgt **eine gemeinsame GLM-Auswertung** des gesamten Texts. Es gibt keine Hierarchie aus Unterverträgen, KI-Auswertung einzelner Seitenpakete, automatische Formatkorrekturschleifen oder Aufteilung nach einem Timeout. Die Prüfung verwendet standardmäßig **HIGH** (`MISTRAL_REVIEW_REASONING_EFFORT=high`); die allgemeine Chat-/Upload-Einstellung bleibt unabhängig davon.

**Betrag / Gesamtwert ist immer der Gesamtbetrag brutto**, einschließlich Service, Wartung und Zusatzpaketen. Ein Gesamtbetrag inklusive MwSt./USt. wird unverändert übernommen. Netto oder einzelne Produktpositionen dürfen ihn nicht ersetzen. Brutto darf aus eindeutig zusammengehörigem Gesamtnetto und ausdrücklich belegtem Steuersatz berechnet werden. Es gilt ausschließlich der Steuersatz im Dokument, niemals ein aktueller oder angenommener Satz. Mehrere Steuersätze, widersprüchliche Gesamtsummen und fehlende Belege führen zu keiner Betragskorrektur. Fehlende Angaben löschen keine gespeicherten Werte.

Die KI erhält keine früher gespeicherten Werte als Vorgabe. Der Bericht unterscheidet `CONFIRMED`, `EXPLICIT_CONFLICT`, `NOT_EVIDENCED`, `NEW_INFORMATION`, `AMBIGUOUS`, `DERIVED` und `WRONG_SCOPE`. Quellen enthalten Dokumentnummer, Originalseite und Zitat; der Server kontrolliert Schema, wörtlichen Beleg, Betragszuordnung, Datumsangaben und Kündigungsfristen. OCR-Tabellen werden einschließlich ihrer separat gelieferten Inhalte ausgewertet. Änderungen werden erst bei gezielter Übernahme gespeichert, versioniert und protokolliert. Schreibrechte und unveränderte Dokumentversion sind dafür erforderlich.

Jeder abgeschlossene aktuelle Bericht zeigt vorhandene **Änderungsvorschläge direkt mit Checkbox, bisherigem Wert, vorgeschlagenem Wert und Begründung**. Gewünschte Änderungen anhaken und **Ausgewählte Änderungen übernehmen** anklicken. Nur diese Felder werden gespeichert; weitere Vorschläge bleiben auswählbar. Belege lassen sich zusätzlich aufklappen. Unveränderte Felder stehen eingeklappt unter **Prüfdetails**. Das Statuslabel unterscheidet tatsächliche Änderungsvorschläge, Aufteilungsvorschläge und **Keine Änderungsvorschläge**; reine Prüfhinweise gelten nicht als Änderungsvorschläge. Eine fehlende belegte KI-Angabe bestätigt weder die gespeicherten Werte noch das Fehlen einer Aussage im Originaldokument.

Rechnungsdatum und Vertragsbeginn werden entsprechend dem Dokumenttyp verglichen; ein vorhandenes Datum sperrt einen belegten Änderungsvorschlag nicht mehr pauschal. Eine niedrige KI-Selbsteinschätzung allein verhindert keine durch die Quellenprüfung belegte Angabe. Widersprüche, unpassende Feldzuordnung und fehlende Belege bleiben Gründe gegen eine Übernahme. Gespeicherte, noch nicht abschließend entschiedene Berichte des aktuellen Prüfverfahrens erhalten die neuen Empfehlungen aus ihren vorhandenen Beobachtungen, ohne erneuten OCR-/KI-Aufruf. Ältere Prüfverfahren und bereits bestätigte oder abgelehnte Gesamtentscheidungen werden dabei nicht umgeschrieben.

Enthält die Sammlung eigenständige Verträge oder Rechnungen, kann dieselbe GLM-Antwort eine **optionale Aufteilung** vorschlagen. Die Vorschau zeigt Titel, Typ, Seiten und belegten Gesamtbruttobetrag. Erst nach **Ja, Einträge mit eigenen PDFs erstellen** werden ausgewählte Seiten in unabhängige PDFs kopiert und neue Einträge angelegt. Originaldatei und Originaleintrag bleiben unverändert; neue Beträge zählen zusätzlich in ihren jeweiligen Summen. Arbeitsbereiche, direkte Zugriffsrechte und Löschschutz werden übernommen. Ohne belegten Betrag bleibt das neue Betragsfeld leer. Verschiedene Produkte auf einer Rechnung sind kein Aufteilungsgrund. Überlappende Seiten und nicht nachweisbare Identitätsbelege verhindern einen Aufteilungsvorschlag. Bereits erstellte Aufteilungen werden auch bei einem späteren Prüflauf nicht erneut angelegt. Alte Berichte erhalten keine Vorschläge nachträglich; hierfür erneut prüfen.

Das GLM-Ausgabeschema unterscheidet Zahlen, Datumswerte, Text und Kategorien bereits nach dem jeweiligen Feld. Lokale Zusatzprüfungen bleiben aktiv; bei einem Formatfehler wird die konkrete Regel ohne Dokumentinhalte ausgegeben. Ungültige Angaben werden nicht stillschweigend in Korrekturen umgewandelt.

`POST /ai/reviews` mit `{"start": true}` speichert die Startabsicht; `/ai/reviews/{id}/start` setzt einen Lauf fort. **Prüfung pausieren** beendet die bereits laufende OCR- oder KI-Anfrage und startet danach keine weitere. Bis dahin zeigt die Oberfläche **Pause wird abgeschlossen …**. Ein weiterer aktiver Lauf desselben Benutzers wird verhindert; der Dispatcher bearbeitet jeweils einen Schritt. Der Ablauf läuft auf dem Server weiter, auch bei Navigation oder geschlossenem Browser. Nach einem Backend-Neustart wird die gespeicherte Startabsicht wieder aufgenommen; unterbrochene Anfragen können als Fehler erneut versucht werden.

Bei HTTP 429 **vom KI-Anbieter** erfolgt eine begrenzte Wiederholung: höchstens fünf Versuche je Anfrage, mit steigender Wartezeit und Berücksichtigung von `Retry-After`, innerhalb des Anfragezeitlimits. Der Countdown ist sichtbar. Das lokale Anlegen neuer Prüfläufe ist unabhängig davon auf **12 Anfragen pro Stunde und Client-IP** begrenzt. Fortsetzen und **Fehler erneut versuchen** legen keinen neuen Lauf an. Andere Anbieterfehler, einschließlich Timeout/HTTP 504 und ungültiger KI-Antwort, markieren das Dokument als fehlgeschlagen und lassen die übrige Prüfung weiterlaufen. **Fehler erneut versuchen** verwendet bereits gespeicherte OCR-Seiten; nach einem GLM-Fehler wird nur die Gesamtauswertung erneut angefordert. Erst nach Erfolg wird der interne OCR-Zwischenstand entfernt. Wiederholte API-Anfragen können Kosten verursachen.

Die Oberfläche unterscheidet gescannte Seiten von der abgeschlossenen Prüfung und zeigt Wartezeit, Modelle, Fehlercode und HTTP-Status. Das regelmäßige Server-Lebenszeichen bestätigt keinen Fortschritt beim Anbieter. Ein KI-Prüfergebnis kann trotz Quellenprüfung Fehler enthalten.

Für die Prüfung ist `MISTRAL_USE_OCR=true` erforderlich. Pro Dokument mit Anlagen gelten 32 MiB, pro PDF standardmäßig `MISTRAL_MAX_PDF_PAGES=100`. Das vollständige OCR-Bündel darf standardmäßig 400.000 Zeichen enthalten (`MISTRAL_REVIEW_MAX_CHARACTERS`); darüber erfolgt ein ausdrücklicher Fehler, keine stille Kürzung und keine Teilanalyse. Das Acht-Seiten-Limit `MISTRAL_MAX_IMAGE_PDF_PAGES=8` betrifft nur den separaten Bildmodus. Modell-, OCR-Modell-, Paketgrößen- oder Dateiänderungen erfordern einen neuen Lauf. Ältere Prüfberichte bleiben lesbar, sind aber nicht mehr zur Übernahme freigegeben; hierfür einen neuen Prüflauf starten.

### KI-Anfragen in Docker-Logs verfolgen

`docker compose logs -f --since 2m backend` zeigt Meldungen von `atlas.review` und `atlas.ai`. `200 OK` bei Statusabfragen bestätigt lediglich die Browserabfrage. `Review OCR saved` bestätigt gespeicherte Scans; `Review document saved` bestätigt das fertige Prüfergebnis. Für OCR und GLM erscheinen `Mistral request started`, alle 30 Sekunden `Mistral waiting for response` und abschließend `Mistral response received` oder `Mistral request failed`. Diese Meldungen enthalten Modell, Anfragekennung, Lauf-/Eintragskennung, Wartezeit und Fehlerstatus, keine Dokumenttexte oder API-Schlüssel.

Bei Chat-Antworten werden `finish_reason`, `prompt_tokens`, `completion_tokens` und `total_tokens` protokolliert, sofern vom Anbieter geliefert. `Review response rejected` kennzeichnet unvollständige Antworten, ungültiges JSON oder Schemafehler. `retry=False` bedeutet, dass keine automatische Formatkorrekturanfrage folgt. `finish_reason=length` weist auf eine Ausgabelängenbegrenzung hin; die Tokenzahlen allein trennen Reasoning- und Antworttokens nicht.

Nach Übernahme des Updates Backend und Frontend mit `docker compose up -d --build` neu erstellen. Neue Konfigurationswerte sind in `.env.example` und `docker-compose.yml` dokumentiert.

### Kündigungsfrist und getrennte Webrecherche

Eine unbekannte Frist bleibt `null` – beim Upload, Speichern, Bearbeiten und in Kalender-/Dashboard-Berechnungen. Es gibt keinen Ersatzwert von 30 Tagen. Die KI muss eine wörtliche, im OCR-Text vorhandene Kündigungsklausel angeben. Eindeutige Tage/Wochen können übernommen werden; Kalendermonate werden nicht pauschal in Tage umgerechnet. Bei unklarer Beleglage bleibt das Feld leer. Bildmodus ohne prüfbaren OCR-Text liefert keine automatisch belegte Frist. Bereits gespeicherte 30-Tage-Werte bleiben bei fehlender Erwähnung erhalten: Der Prüflauf zeigt `NOT_EVIDENCED` ohne Konflikt und ohne Löschvorschlag.

Der Button **Websuche zur Kündigungsfrist** ist in den Vertragsdetails und im Upload-/Bearbeitungsformular unabhängig vom vorhandenen Fristwert sichtbar. Das Suchfeld enthält bereits einen lokal aus Titel und Beschreibung gebildeten, bearbeitbaren Vorschlag. **Vorschlag übernehmen** stellt ihn nach eigenen Änderungen wieder her. Fehlen Titel und Beschreibung, kann **Beispiel übernehmen** den grauen Beispieltext einfügen. Erst die bestätigte Suche sendet die sichtbare Suchanfrage ab. Das Kündigungsfrist-Feld lässt sich leeren und verändert seinen Wert nicht beim Scrollen. Beispielkonfiguration für Mistral:

```dotenv
MISTRAL_CHAT_MODEL=zai-glm-latest
MISTRAL_REASONING_EFFORT=auto
MISTRAL_USE_OCR=true
NOTICE_RESEARCH_PROVIDER=mistral
NOTICE_RESEARCH_MODEL=mistral-medium-latest
```

GLM übernimmt die Dokumentanalyse, das getrennte Suchmodell verwendet Mistrals [Conversations API mit Websuche](https://docs.mistral.ai/studio/agents/agent-tools/websearch). Alternativ `NOTICE_RESEARCH_PROVIDER=openai`, `NOTICE_RESEARCH_MODEL=gpt-5.5` und `OPENAI_API_KEY` für die [Responses API mit Websuche](https://developers.openai.com/api/docs/guides/tools-web-search). `NOTICE_RESEARCH_API_KEY` kann einen separaten Suchschlüssel festlegen. Die Suchfunktion ist standardmäßig deaktiviert und unabhängig von `MISTRAL_CHAT_MODEL`, dessen Reasoning-Einstellung und dem Schalter für Dokumentverarbeitung.

Übermittelt werden ausschließlich der im Suchfeld sichtbare, bestätigte öffentliche Suchtext und feste Rechercheanweisungen. Der Vorschlag entsteht ohne API-Aufruf im Browser aus Titel/Beschreibung und ist auf 300 Zeichen begrenzt. Der Recherche-Endpunkt akzeptiert keine zusätzlichen Dokument-, OCR- oder Chatfelder und greift nicht auf Dokumentdaten zu. Auffällige E-Mail-Adressen, Kontaktdaten und Kennnummern werden zurückgewiesen; Freitext kann technisch nicht zuverlässig auf sämtliche Personennamen geprüft werden und muss deshalb vor dem Absenden geprüft werden. Die Vorschau nennt Suchanbieter und Modell. Jede Recherche startet ohne bisherigen Gesprächskontext mit `store=false` (keine Zusage über die sonstige Datenhaltung des Providers).

Nur tatsächlich zurückgegebene Webquellen werden als Quellen angezeigt. Die Recherche übernimmt keine Frist automatisch: Tarif, Land, Abschlussdatum, damalige AGB und individuelle Vereinbarungen müssen zum Vertrag passen. Fehler unterscheiden abgelehnte API-Schlüssel, Berechtigungen, Kontingente, ungültige Antworten, fehlende Quellen und das Recherche-Zeitlimit von 120 Sekunden. Anbieter-Antworttexte und Schlüssel werden dabei nicht als Fehlermeldung ausgegeben.

Ausführliches Reasoning benötigt zusätzliche Tokens und kann länger dauern. Das Zeitlimit pro Mistral-Aufruf beträgt standardmäßig **900 Sekunden (15 Minuten)**, damit GLM 5.3 mit `max` Thinking mehr Zeit erhält. Modell und Reasoning-Stufe werden bei langsamen Antworten nicht herabgesetzt. Wenn eine vorhandene `.env` noch `MISTRAL_REQUEST_TIMEOUT_SECONDS=120` oder `300` enthält, setzen Sie den Wert auf `900`: Ein expliziter Wert überschreibt den neuen Docker-Standard. Erstellen Sie anschließend das Backend mit `docker compose up -d --build backend` neu und laden Sie den internen Proxy mit `docker compose restart frontend` neu. Die mitgelieferten Nginx-Konfigurationen erlauben mit `proxy_read_timeout 1860s;` insgesamt 31 Minuten ohne Antwortdaten für OCR und anschließende Analyse. Übernehmen Sie diesen Wert auch in bereits eingerichteten externen Reverse-Proxys und laden Sie Nginx nach erfolgreichem Konfigurationstest neu. Bei höheren API-Zeitlimits muss auch das Proxy-Zeitlimit entsprechend erhöht werden. Bei der serverseitigen KI-Prüfung erhalten einzelne Anfragen jeweils die vollen 900 Sekunden; die Oberfläche zeigt den tatsächlich konfigurierten Wert.

Setzen Sie `MISTRAL_DOCUMENT_PROCESSING_ENABLED=false`, um die externe KI Dokumentverarbeitung vollständig zu deaktivieren.

Bei Mistral Medium 3.5 können mit `MISTRAL_USE_OCR=false` PDFs als Bilder verarbeitet werden. Sie werden dann
bereits bei der Validierung auf `MISTRAL_MAX_IMAGE_PDF_PAGES` begrenzt.

Starten Sie die Anwendung mit folgendem Befehl im Hauptverzeichnis:

docker-compose up -d

Vor dem ersten Start müssen Sie eine `.env` aus `.env.example` erstellen und
mindestens `SECRET_KEY` sowie ein `ADMIN_PASSWORD` mit mindestens 12 Zeichen
setzen. Das initiale Passwort wird nicht erzeugt oder ausgegeben.

Docker veröffentlicht Atlas ausschließlich auf `127.0.0.1:8080`. Für den
Produktivbetrieb konfigurieren Sie einen TLS-Reverse-Proxy davor; eine sichere
Vorlage mit HTTP-zu-HTTPS-Weiterleitung liegt in `nginx-external-sample.conf`.
Für lokale HTTP-Entwicklung müssen `PRODUCTION=false` und
`SECURE_COOKIES=false` bewusst in der lokalen `.env` gesetzt werden.

Nach dem Start ist Atlas über den konfigurierten Nginx Proxy erreichbar. Die Datenbank wird beim ersten Start automatisch initialisiert.
