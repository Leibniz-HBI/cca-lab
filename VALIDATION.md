# TextLab 0.3.0 validation

- 44 automated tests passed with Python 3.12. This includes the existing classification/evaluation suite and new prediction, deletion, thinking-control and runtime tests.
- Multi-task exports checked in CSV, JSON, JSONL and Parquet, including task identity, leading-zero IDs, rationale/evidence, snapshots after task edits/connection deletion, persisted file retrieval after database reinitialization, and cancelled/unprocessed rows.
- Deletion tests cover active-job blocking, gold/evaluation dependencies, dataset cascade removal, file removal, and deleting an original CSV while preserving imported records.
- Mock HTTP transport verifies actual Ollama and compatible API request fields for thinking on/off/levels; returned thinking is retained. Conflicting configurations are rejected.
- Controlled-clock test verifies active time excludes a simulated pause while elapsed time includes it; legacy timing is unknown. Evaluation runtime is verified in JSON, CSV and rendered charts.
- Playwright/Chromium browser workflow passed: English forms, two tasks with different thinking settings, gold registration, two-task prediction, persisted download links, evaluation runtime charts, all six new deletion controls, and no JavaScript/server errors. Desktop and mobile screenshots are included in `docs/` and were visually inspected.
- Real Ollama/vLLM model servers and GPUs were not available for live inference testing. Mock timings are not model-performance benchmarks. Docker was not started in this validation run.
- Three non-failing dependency warnings remain: Starlette TestClient/httpx deprecations and scikit-learn's single-class confusion-matrix warning in a metric comparison test.
- The million-row import benchmark below is historical evidence from 0.1, not a new full-scale multi-task prediction benchmark. Version 0.3 preserves the bounded import path; aggregate prediction disk space grows with tasks and output formats.

## Earlier validation records

# Validierungsprotokoll — TextLab 0.2.0

Abschlussprüfung am 11.09.2026 unter Linux und Python 3.12.

## Automatisierte Tests

`python -m pytest -q --tb=short`: **32 Tests bestanden**. Darin sind die 13 Regressionstests aus Version 0.1 enthalten.

Neu geprüft:

- Gold-Registrierung mit abweichenden Spaltennamen, Erhaltung von Dokument-IDs wie `001`, Multi-Label-Splitting und leeren Labelmengen.
- Atomare Ablehnung doppelter/fehlender IDs, leerer Texte, doppelter/leerer Labelkomponenten, unbekannter Task-Labels und widersprüchlicher Single-/Multi-Label-Modi.
- Evaluation mit zwei Modell-/Temperaturkonfigurationen, dauerhaft gespeicherten Vorhersagen und automatischer Reportberechnung.
- Accuracy, Precision, Recall, F1 (Micro/Macro/Weighted/Samples), Kappa, MCC, Hamming Loss und Jaccard gegen scikit-learn, inklusive Klassen ohne Support.
- Unterschiedliche Fehlermengen pro Variante: gemeinsame Auswertungsschnittmenge und modellbezogene Coverage/Accuracy über alle Gold-Dokumente.
- Vollständiger Ausfall und vollständig abgebrochene Evaluationen: `n/a` statt irreführender Qualitätswerte; unbearbeitete Dokumente bleiben im Prediction-Export enthalten.
- CSV-/JSONL-Vorhersageexport, Modell-/Klassen-CSV, eigenständiger HTML-Report, JSON und Reportpaket-ZIP inklusive SVG/PNG-Grafiken und Confusion-Matrizen.
- Unabhängige Ausgabeoptionen, exakte Textbelegvalidierung mit Zeichenpositionen und erneuter Versuch nach erfundenem Beleg.
- Thinking aus Ollama- und OpenAI-/vLLM-Antwortfeldern sowie führenden Think-Blöcken; Aufbewahrung auch fehlgeschlagener Versuche und fehlender finaler JSON-Antworten.
- Additive und wiederholbare Datenbankmigration; vorhandene Ergebniszeilen bleiben erhalten.

Die Tests melden zwei Deprecation-Warnungen aus Testclient-Abhängigkeiten sowie eine scikit-learn-Warnung für den absichtlich getesteten Ein-Klassen-Sonderfall. Kein Test schlägt fehl.

## Browserprüfung

Echter Chromium-/Playwright-Lauf gegen getrennte lokale FastAPI- und Worker-Prozesse:

1. Task mit Textbelegen anlegen und eine Demo-Modellverbindung speichern.
2. Gold-CSV hochladen und mit Spaltenzuordnung registrieren.
3. Zwei Temperaturvarianten konfigurieren und als Evaluation starten.
4. Report öffnen, Mittelwert und Auswertungsbasis wechseln; SVG-Diagramme laden.
5. Gold-/Prediction-CSV über die Oberfläche herunterladen und Vorhersagedetails anzeigen.
6. Desktop- und Mobilansicht prüfen.

Ergebnis: keine JavaScript-Fehler, keine HTTP-5xx-Antworten im Browserlauf, kein horizontaler Seitenüberlauf bei 390 px Viewportbreite. Screenshots wurden visuell geprüft und liegen unter `docs/evaluation-desktop.png` und `docs/evaluation-mobile.png`. Der Test verwendet ein Demo-Modell, das immer die erste Kategorie zurückgibt; er prüft den Anwendungsablauf, keine semantische Klassifikationsqualität.

## Verbleibende Grenzen

Kein echter Ollama-/vLLM-Modellserver und kein Docker-Daemon-Build standen für diese Prüfung zur Verfügung. Provider-Protokolle sind mit simulierten HTTP-Antworten getestet. Die Lasttests unten stammen aus Version 0.1; sie wurden für 0.2 nicht als Million-Zeilen-Test wiederholt. Es gibt keinen Test mit einer Million LLM-Anfragen, keinen Stromausfalltest und keine statistische Validierung auf einem real annotierten Forschungskorpus.

---

# Historische Basisprüfung — TextLab 0.1.0

Ausgeführt am 10.09.2026 in der bereitgestellten Linux-/Python-3.12-Umgebung. Die verwendeten Python-Laufzeitabhängigkeiten stehen in `requirements.lock`.

## Automatisierte Integrationstests

`python -m pytest -q`: **13 bestanden**.

Geprüft wurden:

- Task-Erstellung, Änderungen und Revisionskonflikte; unverändertes Job-Snapshot nach Task-Änderung.
- CSV-Upload, Import, Jobausführung mit Demo-Modell, leere Texte als Fehler, Ergebnisanzeige und Jobzähler.
- CSV-, JSONL- und Parquet-Export einschließlich Originaldaten.
- Pause/Fortsetzen und simulierte Crash-Grenze zwischen Ergebnis-Commit und Cursor-Fortschritt; kein doppeltes gespeichertes Ergebnis.
- Abbruch bei tatsächlich laufenden Threads; Export erst nach Auslaufen der Anfragen.
- Fehlerhafte CSV-Kopfzeilen und Upload-Größenlimit.
- Strikte Label-/JSON-Validierung für Single- und Multi-Label.
- Ollama- und OpenAI-kompatible Request-Struktur sowie Wiederholung nach ungültigem Label über HTTP-MockTransport.
- HTTP 401 wird ohne Retry als Fehler behandelt.

Zwei Deprecation-Warnungen betreffen den von Starlette verwendeten HTTPX-Testclient und einen AnyIO-Alias. Die Tests laufen erfolgreich; dies ist keine Warnung aus dem eigentlichen Job-Worker.

## Lasttest des Imports

`PYTHONPATH=. python tests/benchmark_import.py` erzeugt eine echte synthetische CSV-Datei und importiert sie in eine frische SQLite-Datenbank.

| Messgröße | Ergebnis |
|---|---:|
| Datensätze | 1.000.000 |
| CSV-Größe | 502.888.911 Byte |
| Dateierzeugung | 2,16 s |
| Importdauer | 14,30 s |
| Maximaler RSS des Prozesses | 29,09 MiB |
| Datenbank nach Import | 585.207.808 Byte |

Die Datei enthält durchschnittlich rund 500 Byte je Zeile, ohne besonders große einzelne Felder. Die Speicherzahl ist der Linux-Prozess-RSS laut `resource.getrusage`; Dateisystem-Cache des Betriebssystems ist darin nicht enthalten. Die Messung prüft keinen LLM-Durchsatz.

## Weitere Prüfungen und Grenzen

Zusätzlich lief ein echter HTTP-Upload gegen einen Uvicorn-Prozess mit getrenntem Worker: **502.888.911 Byte in 2,52 s übertragen**, nach **17,74 s einschließlich Import** alle **1.000.000 Zeilen** bereit. Der Request-Body wurde als Iterator in 1-MiB-Blöcken gesendet. Dies ist ein lokaler Loopback-Test ohne Reverse Proxy und keine Messung einer Internetverbindung. Reproduzierbares Client-Skript: `tests/benchmark_upload.py` (nur gegen eine Testinstanz ausführen; der Datensatz bleibt dort gespeichert).

- Python-Paket erfolgreich als editierbare Installation gebaut und installiert.
- `node --check textlab/static/app.js`: bestanden.
- Keine echte Ollama-/vLLM-Instanz verfügbar: Provider-Payloads wurden mit simulierten HTTP-Antworten geprüft, nicht mit einem GPU-Modellserver.
- Kein Docker-Daemon-Build durchgeführt; Dockerfile und Compose-Konfiguration sind mitgeliefert, aber hier nicht durch einen Containerstart validiert.
- Der visuelle Playwright-Test konnte nicht ausgeführt werden: Chromium war nicht vorhanden und der Browserdownload scheiterte an Netzwerk-Timeouts. Responsivität und reale Browserinteraktion sind deshalb noch nicht visuell verifiziert.
- Wiederanlauf wurde an der relevanten Persistenzgrenze simuliert; kein Stromausfalltest.
- Kein Lasttest mit einer Million tatsächlicher Modellanfragen oder einer Million Ergebnisexporten.
