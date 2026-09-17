# TextLab 0.8.1 validation

83 Python tests pass, including import-log correlation and payload exclusion. Browser regression opens the actual file picker, forces two background refreshes, checks invalid-file feedback persists, then imports/edits/exports a valid codebook. No browser JavaScript errors or HTTP 5xx responses.

Reproduce the browser check against an empty disposable server using Playwright: install playwright and its Chromium browser, then run node tests/cca_browser.cjs (TEXTLAB_TEST_URL defaults to http://127.0.0.1:8099). This check creates a task; use disposable data.

Previous 0.8 validation:

- 82 automated tests passed, including 11 CCA cases covering round-trip metadata, edited codebook fields, prompt inclusion of criteria/context, machine IDs versus display names, example label references, duplicate IDs/JSON keys, invalid dates and semantic versions, extra fields, multi-label and one-category codebooks, native-task export, BOM handling and the 5 MiB upload limit.
- Invalid imports leave the task library unchanged. Export uses the current task fields and validates the resulting CCA document. CCA cannot encode empty-label tasks; those exports fail explicitly.
- Playwright/Chromium passed real file import, task editing, JSON download, metadata/criteria/context preservation, prompt preview, and desktop/mobile rendering without JavaScript or HTTP 5xx errors. Screenshots are included in docs/.
- A Python wheel was built successfully and checked to include the exact user-provided CCA 0.1 schema. Native and CCA formats remain separate; no remote schema is fetched.
- Existing three non-failing dependency/metric warnings remain. No real-model/GPU quality or new large-corpus benchmark was performed for this interchange release. Database schema remains 6.

## Earlier release validation

# TextLab 0.7.0 validation

- 71 automated tests passed. Fixed-order coverage checks all 16 combinations of optional evidence, candidate comparison, rationale and confidence fields, with matching schema/required lists, instructions, few-shot examples and demo output.
- Validation tests cover exact evidence for unselected categories, unknown-category rejection, distinct candidate sets, missing-primary rejection, multi-label set equality, backend-derived alternatives, and rejection of model-supplied derived alternatives.
- Candidate lists and derived alternatives are checked through stored results and Parquet downloads. Existing evaluation, prediction, confidence, agreement and export regression tests pass.
- The targeted 11 output-order/uncertainty tests were rerun after adding candidate persistence assertions and passed.
- Playwright/Chromium passed the prompt-preview check for the fixed order, actual demo JSON order, candidate persistence and alternative derivation, plus evaluation/prediction counts, confidence plots, agreement and downloads with no JavaScript or HTTP 5xx errors. The prompt-preview screenshot is included in docs/.
- No real model/GPU accuracy comparison was performed. Fixed prompt/schema/example order requests a generation protocol; backend key-order compliance and classification improvements are not guaranteed. Raw output is retained for audit, and valid JSON is not rejected solely for key reordering.
- Schema version 6 adds candidate storage; historical outputs remain unchanged. Attempt logs and new job snapshots identify evidence-first-v1. Three existing non-failing dependency/metric warnings remain.

## Earlier release validation

# TextLab 0.6.0 validation

- 68 automated tests passed in total: the 60 existing tests plus eight new uncertainty tests. New coverage includes finite confidence validation, single-/multi-label alternative sets, exact quotes, invalid-output retries and fallback, metric reference values, confidence ties and undefined outcomes, cancelled/duplicate-seed exclusions, nonempty alternative persistence, and numeric nullable confidence in Parquet.
- Integration checks exercise evaluation query totals with per-variant seed lists and retry settings, confidence report grouping, SVG charts, HTML/report bundles, and persisted prediction agreement CSV/JSONL.
- Playwright/Chromium exercises task settings, live evaluation model/temperature/seed count preview, per-variant retry ceiling, confidence plots, per-document agreement, prediction preview and saved agreement downloads. Desktop/mobile screenshots are included in docs/.
- Tests use demo inference or simulated HTTP model responses. No real-model calibration accuracy, GPU throughput, or new million-row inference benchmark is claimed. Agreement uses bounded document pages; dataset-size benchmarks in earlier records are historical.
- Three existing non-failing dependency/metric warnings remain. Schema version 5 is an additive migration. Confidence is uncalibrated; see UNCERTAINTY.md for estimands, exclusions and aggregation rules.

## Earlier release validation

# TextLab 0.5.0 validation

- 60 automated tests passed on Python 3.12. New tests verify reuse of evaluated task and connection snapshots after editing or deleting their library entries, preservation of provenance, and rejection of invalid or unfinished source runs without partial predictions.
- Playwright/Chromium passed the five-step navigation, combined corpus/gold preparation, task and dataset shortcuts, task revision, evaluated-configuration reuse, results filtering and grouping without duplicate child runs.
- Desktop and 390 px mobile views were visually inspected. Configuration remains accessible on mobile; no horizontal page overflow, JavaScript errors or HTTP 5xx responses occurred. Screenshots: `docs/workflow-desktop.png` and `docs/workflow-mobile.png`.
- Browser inference used the demo model. No real GPU/model benchmark or new large-scale import benchmark was performed for this UI release.
- Database schema remains version 4. Existing data is compatible; restart API/worker processes and reload the browser after upgrading. Three existing non-failing dependency/metric warnings remain.

## Earlier release validation

# TextLab 0.4.0 validation

- 58 automated tests passed on Python 3.12: all previous tests plus fallback/retry preservation, invalid fallback validation, live error pagination, recovered retry filtering, streaming error export, error-index migration, multi-seed evaluation/prediction expansion, seed validation/run limits, per-run means/sample SD, null denominators and cancellation-safe common scoring.
- Seeded prediction exports verified in JSON and Parquet with 2 tasks × 3 seeds × 2 records, including seed identities and aggregate manifest groups. Job Parquet exports verify fallback flags.
- Grouped CSV values were compared with known per-run accuracy values, and plotted overview/class charts were rendered. Cancelled runs are excluded from aggregates without emptying the scoring subset of completed runs.
- Playwright/Chromium exercised task fallback settings, prediction/evaluation seed entry, flagged fallback labels, error-log viewing, mean/SD tables, error-bar charts and existing deletion/download flows. A local simulated HTTP model endpoint provided successful responses for one seed and invalid labels for another. Screenshots are in `docs/`.
- No real model/GPU inference was tested. Seed determinism, backend-specific seed support and real-world classification quality remain dependent on the configured model server.
- The same three non-failing dependency warnings remain (Starlette/httpx deprecations and a scikit-learn single-class warning). Historical import benchmarks below were not rerun as part of this release.

## Earlier release validation

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
