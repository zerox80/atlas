# Atlas

Dieses Projekt ist eine KI gestützte Plattform zur Verwaltung und Analyse von Verträgen. Es kombiniert ein modernes Web Interface mit leistungsstarken KI Funktionen zur automatischen Datenextraktion und Dokumenteninteraktion.

## Hauptfunktionen

Das System bietet umfassende Werkzeuge für das Vertragsmanagement:

* Automatisierte Vertragsanalyse: Mithilfe von Mistral Medium 3.5 werden wichtige Daten wie Laufzeiten, Beträge und Kündigungsfristen automatisch aus PDF Dokumenten extrahiert.
* Rechnungsverwaltung: Rechnungen können unabhängig von Verträgen hochgeladen, mit OCR/KI ausgelesen und separat verwaltet werden.
* Mehrere Dateien pro Vertrag: Ein Hauptdokument und bis zu neun Anhänge (jeweils maximal 10 MiB) werden gemeinsam gespeichert. Im Upload-Dialog lässt sich die PDF für die KI-Analyse separat auswählen. Anhänge sind in den Details herunterladbar, beim Bearbeiten ergänzbar und in Datensicherung sowie Papierkorb enthalten.
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
MISTRAL_REQUEST_TIMEOUT_SECONDS=300
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
MISTRAL_USE_OCR=true
```

Beide Chatmodelle und OCR verwenden ausschließlich `https://api.mistral.ai` mit demselben `MISTRAL_API_KEY`. Laut [Mistrals Modellbeschreibung](https://docs.mistral.ai/models/zai-glm-5-3) ist `zai-glm-5-3` ein Textmodell. Atlas benötigt deshalb für PDFs `MISTRAL_USE_OCR=true`; bei deaktiviertem OCR wird diese Kombination vor einem API-Aufruf abgelehnt.

Atlas sendet für GLM 5.3 `reasoning_effort="max"` unverändert an Mistral. Für Medium 3.5 wird `max` abgelehnt. Mit `MISTRAL_REASONING_EFFORT=auto` oder ohne gesetzte Variable wählt Atlas modellabhängig `max` für `zai-glm-5-3` **und `zai-glm-latest`** und `high` für Medium 3.5. Der Alias aus dem Mistral-Playground wird auch bei der OCR-Pflicht und im Transport erkannt; `5.3` allein ist keine Modellkennung. Explizite Werte haben Vorrang: Beim Wechsel von Medium zu GLM müssen Sie ein vorhandenes `high` deshalb auf `max` oder `auto` ändern. Die GLM-Übertragung von `max` wird mit dem echten Mistral-SDK und simulierten HTTP-Antworten getestet; eine Live-Bestätigung durch Mistrals API steht aus.

### Alle Verträge und Rechnungen erneut prüfen

Unter **KI-Prüfung** startet ein Prüflauf für alle zugänglichen Verträge und Rechnungen, unabhängig von Listenfiltern und Seitengröße. Geschützte Dokumente und PDF-Anlagen sind eingeschlossen, Papierkorb ist ausgeschlossen. Nicht unterstützte Hauptdateien werden als nicht geprüft ausgewiesen; nicht unterstützte Anlagen erzeugen einen Hinweis. Fehlende Dateien, unvollständiger OCR-Kontext, ungültige KI-Antworten und Zeitüberschreitungen führen zu einem Fehler, nicht zu einem erfolgreichen Prüfergebnis.

Die KI extrahiert erneut aus den Originaldateien, ohne die früher erfassten Werte als Vorgabe zu erhalten. Der Bericht zeigt alte und neue Angaben, Hinweise und Textbelege. Änderungen werden erst bei der gezielten Übernahme ausgewählter Felder gespeichert, versioniert und protokolliert. Zwischenzeitlich geänderte Dokumente müssen erneut geprüft werden. Leserechte erlauben die Prüfung, Schreibrechte sind für die Übernahme erforderlich. Die Prüfung erkennt mögliche Erfassungsfehler; sie ist keine Garantie für Vollständigkeit oder eine juristische Vertragsprüfung.

Ein Lauf verarbeitet jeweils ein Dokument mit seinen Anlagen und speichert Fortschritt und Ergebnisse in der Datenbank. Die Seite während der Prüfung geöffnet lassen. Nach Navigation/Schließen endet die Verarbeitung nach dem aktuellen Request; ein gespeicherter Lauf kann fortgesetzt werden. Abgebrochene Requests werden nach Ablauf ihrer Sperre erneut prüfbar. Fehlgeschlagene Dokumente können separat wiederholt werden. Ein Wechsel des Analysemodells erfordert einen neuen Lauf. Jeder Lauf verursacht erneut Analyse-/gegebenenfalls OCR-Kosten. Pro Dokument mit Anlagen gelten 32 MiB und das konfigurierte OCR-Kontextlimit.

### Kündigungsfrist und getrennte Webrecherche

Eine unbekannte Frist bleibt `null` – beim Upload, Speichern, Bearbeiten und in Kalender-/Dashboard-Berechnungen. Es gibt keinen Ersatzwert von 30 Tagen. Die KI muss eine wörtliche, im OCR-Text vorhandene Kündigungsklausel angeben. Eindeutige Tage/Wochen können übernommen werden; Kalendermonate werden nicht pauschal in Tage umgerechnet. Bei unklarer Beleglage bleibt das Feld leer. Bildmodus ohne prüfbaren OCR-Text liefert keine automatisch belegte Frist. Bereits gespeicherte 30-Tage-Werte werden nicht pauschal gelöscht: Der Prüflauf zeigt unbelegte Werte zur Korrektur an.

Der Button **Kündigungsfrist recherchieren** öffnet eine unabhängige öffentliche Recherche. Beispielkonfiguration für Mistral:

```dotenv
MISTRAL_CHAT_MODEL=zai-glm-latest
MISTRAL_REASONING_EFFORT=auto
MISTRAL_USE_OCR=true
NOTICE_RESEARCH_PROVIDER=mistral
NOTICE_RESEARCH_MODEL=mistral-medium-latest
```

GLM übernimmt die Dokumentanalyse, das getrennte Suchmodell verwendet Mistrals [Conversations API mit Websuche](https://docs.mistral.ai/studio/agents/agent-tools/websearch). Alternativ `NOTICE_RESEARCH_PROVIDER=openai`, `NOTICE_RESEARCH_MODEL=gpt-5.5` und `OPENAI_API_KEY` für die [Responses API mit Websuche](https://developers.openai.com/api/docs/guides/tools-web-search). `NOTICE_RESEARCH_API_KEY` kann einen separaten Suchschlüssel festlegen. Die Suchfunktion ist standardmäßig deaktiviert und unabhängig von `MISTRAL_CHAT_MODEL`, dessen Reasoning-Einstellung und dem Schalter für Dokumentverarbeitung.

Übermittelt werden ausschließlich der manuell eingegebene, bestätigte öffentliche Suchtext und feste Rechercheanweisungen. Der Recherche-Endpunkt akzeptiert keine Dokument-, OCR- oder Chatfelder und greift nicht auf Dokumentdaten zu. Titel/Beschreibung werden wegen möglicher Namen nicht automatisch übernommen. Auffällige E-Mail-Adressen, Kontaktdaten und Kennnummern werden zurückgewiesen; Freitext kann technisch nicht zuverlässig auf sämtliche Personennamen geprüft werden und muss deshalb vor dem Absenden geprüft werden. Die Vorschau nennt Suchanbieter und Modell. Jede Recherche startet ohne bisherigen Gesprächskontext mit `store=false` (keine Zusage über die sonstige Datenhaltung des Providers).

Nur tatsächlich zurückgegebene Webquellen werden als Quellen angezeigt. Die Recherche übernimmt keine Frist automatisch: Tarif, Land, Abschlussdatum, damalige AGB und individuelle Vereinbarungen müssen zum Vertrag passen.

Ausführliches Reasoning benötigt zusätzliche Tokens und kann länger dauern. Das Zeitlimit pro Mistral-Aufruf beträgt standardmäßig 300 Sekunden. Wenn eine vorhandene `.env` noch `MISTRAL_REQUEST_TIMEOUT_SECONDS=120` enthält, setzen Sie den Wert auf `300`. Die mitgelieferten Nginx-Konfigurationen erlauben 660 Sekunden ohne Antwortdaten, damit OCR und anschließende Analyse ausreichend Zeit haben. Übernehmen Sie dieses `proxy_read_timeout` auch in bereits eingerichteten externen Reverse-Proxys; bei höheren API-Zeitlimits muss es entsprechend erhöht werden.

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
