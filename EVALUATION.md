# Evaluationen in TextLab 0.2.0

## Ablauf in der Oberfläche

1. Unter **Gold-Datensätze → CSV hochladen** eine CSV importieren. Mindestens benötigt werden Dokument-ID, Text und Gold-Label; vorgeschlagene Spaltennamen sind `doc_id`, `text`, `gold_label`.
2. Nach dem Import **Spalten zuordnen** wählen. Abweichende Spaltennamen können frei zugeordnet werden. Dokument-IDs bleiben Strings (z. B. `001`) und müssen nach Entfernen äußerer Leerzeichen eindeutig und nichtleer sein; Texte müssen nichtleer sein.
3. Single-Label oder Multi-Label auswählen. Bei Multi-Label trennt die konfigurierte **wörtliche Zeichenfolge** die Labels innerhalb einer CSV-Zelle, standardmäßig `|`. Beispiel: `SUPPORT|SAFETY`. Äußere Leerzeichen an Labels werden entfernt; Groß-/Kleinschreibung bleibt relevant. Leere Komponenten und Duplikate sind Fehler. Leere Labelmengen sind nur mit expliziter Freigabe erlaubt.
4. Unter **Evaluationen → Neue Evaluation** Gold-Datensatz und Klassifikationstask wählen.
5. Eine LLM-Verbindung wählen, verfügbare Modelle mehrfach auswählen und Temperaturen angeben, z. B. `0, 0.5, 1`. **Kombinationen hinzufügen** erzeugt das kartesische Produkt aus Modellen und Temperaturen.
6. Weitere Modelle aus anderen Verbindungen können ergänzt werden. Jeder Konfiguration einen eindeutigen Namen geben. Pro Variante lassen sich Modell, Temperatur und Profil direkt bearbeiten; zusätzliche Query-Overrides stehen als JSON zur Verfügung, z. B. `{"top_p":0.8,"seed":42,"rationale":false,"evidence":true}`. Diese überschreiben die gemeinsamen Einstellungen. Ein Override von `extra_body` ersetzt dieses ganze Objekt.
7. **Evaluation starten** erstellt einen persistenten Job pro Konfiguration. Der vorhandene Worker verarbeitet diese nacheinander, jeweils mit der gewählten Anzahl paralleler Anfragen.
8. **Vergleichen** öffnet Status, Qualitätsmetriken, Klassenvergleich, Confusion-Matrizen und Downloads. Pause/Fortsetzen/Abbruch sind gemeinsam oder über den jeweiligen Einzellauf möglich.

`examples/gold_single.csv` passt zum Beispieltask `examples/task.json`. `examples/gold_multi.csv` passt zu `examples/task_multi.json`, mit Zuordnung `article_id → doc_id`, `content → text`, `annotations → gold_label`. Diese kleinen Beispiele demonstrieren das Format; sie sind kein unabhängiger Gütenachweis.

Vor dem Start werden Modus, Kardinalität und sämtliche Gold-Labels gegen den Task validiert. Ein Konflikt verhindert die Erstellung aller Varianten atomar. Der Modellprompt bekommt nur den Text sowie die konfigurierten Task-Instruktionen/Beispiele; Gold-Labels werden nicht automatisch beigefügt. Selbst eingetragene Few-Shot-Beispiele können sich allerdings mit dem Gold-Datensatz überschneiden. Für wissenschaftliche Evaluationen ein unabhängiges Testset verwenden.

## Was gespeichert wird

Gold-Registrierungen sind unveränderlich und enthalten die Spaltenzuordnung, Split-Konfiguration und normalisierte Labels je `doc_id`/CSV-Datensatzindex. Für eine geänderte Zuordnung eine neue Registrierung erstellen. Jede Evaluation und jeder ihrer Läufe hält Task-Revision, Modellprofil, Modell-ID, sämtliche effektiven Query-Parameter und optionale Ausgabeentscheidungen fest. Gelöschte oder bearbeitete Tasks ändern diese Snapshots nicht.

Pro Modellkonfiguration werden Vorhersagen zeilenweise gespeichert, einschließlich Status, Begründung, Textbelegen, Thinking, Rohantwort und Versuchsprotokoll. Nach Abschluss bzw. vollständig ausgeführtem Abbruch aller Varianten berechnet der Worker zwei Reports und speichert sie dauerhaft. Nach einem Worker-Neustart werden noch ausstehende Berechnungen nachgeholt.

Gold-Datensätze sind standardmäßig auf **50.000 Zeilen** begrenzt, konfigurierbar über `TEXTLAB_MAX_EVAL_ROWS`; bis zu **50 Varianten** pro Evaluation. Große normale Klassifikationsdatensätze behalten ihren bisherigen Verarbeitungsweg. Die Evaluationsmetrikberechnung hält nur die Gold-Labels und Vorhersagen einer Variante gleichzeitig im Speicher; Originaltexte und Thinking werden dafür nicht geladen. Größere Grenzwerte erhöhen dennoch den Speicher- und Zeitbedarf.

## Metriken und Auswertungsbasis

Die Oberfläche bietet zwei Auswertungsbasen:

| Auswahl | Berechnungsmenge |
|---|---|
| **Gemeinsame gültige Dokumente** (Standard) | Schnittmenge der in allen Varianten erfolgreich und schemakonform klassifizierten Dokumente; jedes Modell wird auf exakt denselben Dokumenten verglichen. |
| **Gültige Dokumente je Variante** | Alle gültigen Vorhersagen einer Variante; die Dokumentmenge und deren Schwierigkeit können zwischen Modellen abweichen. |

Unabhängig davon erscheinen **Coverage**, Zahl gültiger/fehlgeschlagener/unbearbeiteter Dokumente und **Accuracy (alle)**. Coverage = gültige Vorhersagen / alle Gold-Dokumente. Accuracy (alle) = exakte gültige Treffer / alle Gold-Dokumente; Fehler und nicht bearbeitete Dokumente zählen dabei als falsch. Fehlgeschlagene Multi-Label-Antworten werden insbesondere **nicht** als leere Labelmenge interpretiert.

| Metrik | Single-Label | Multi-Label |
|---|---|---|
| Accuracy | Anteil korrekt vorhergesagter Klassen | Subset-/Exact-Match-Accuracy: vollständige Labelmenge muss stimmen |
| Precision, Recall, F1 | Je Klasse sowie Macro, Micro, Weighted | Je Klasse sowie Macro, Micro, Weighted, Samples |
| Cohen’s Kappa | Globales nominales Multiclass-Kappa und binär je Klasse | Binär je Klasse, dazu `kappa_macro_ovr` über definierte Klassenwerte |
| Matthews Correlation Coefficient | Globaler Multiclass-MCC und binär je Klasse | Binär je Klasse, dazu `mcc_macro_ovr` |
| Hamming Loss | Anteil falsch klassifizierter Dokumente | Anteil falscher binärer Labelentscheidungen |
| Jaccard | Nicht separat ausgegeben | Samples-Mittel über Labelmengen |
| Confusion | Gold-Klasse × vorhergesagte Klasse | TN, FP, FN, TP je Klasse |

Weitere Klassenmetriken: One-vs-rest-Accuracy, Specificity, Gold-Support, Predicted Support und TP/FP/FN/TN. `label_accuracy` ist der Anteil korrekter binärer Entscheidungen über alle Dokument×Klasse-Zellen; bei Single-Label unterscheidet sich dieser Wert von der üblichen Dokument-Accuracy.

- **Macro:** ungewichtetes Mittel über alle im Task definierten Klassen, auch Klassen ohne Gold-Support.
- **Micro:** Zusammenfassung aller TP, FP und FN vor der Berechnung.
- **Weighted:** Gewichtung nach Gold-Support innerhalb der ausgewählten Auswertungsmenge.
- **Samples:** Mittel der pro Dokument berechneten Multi-Label-Metrik.
- Precision, Recall und F1 mit Nullnenner erhalten 0 (`zero_division=0`); ebenso Samples-Jaccard für zwei leere Labelmengen. Zwei leere Labelmengen zählen bei Exact-Match-Accuracy dennoch als korrekt.
- Mathematisch undefiniertes Kappa erscheint als `null`/`n/a`. Das Macro-Kappa nutzt nur definierte Klassenwerte; `kappa_defined_classes` dokumentiert deren Anzahl.
- MCC mit Nullnenner erhält 0 entsprechend der scikit-learn-Konvention.
- Ohne auswertbare Dokumente sind Qualitätsmetriken `null`/`n/a`; Coverage und Accuracy (alle) bleiben 0.
- Kappa-/MCC-Mittel über binäre Klassenentscheidungen bei Multi-Label werden ausdrücklich nicht als globales Multiclass-Kappa/MCC bezeichnet.

Die Metriken prüfen **Labels**, nicht die inhaltliche Qualität von Begründungen, Textbelegen oder Thinking. Aktivierte Zusatzfelder gehören allerdings zum validierten Antwortschema; ein erfundener Textbeleg kann deshalb die ganze Antwort ungültig machen und nach ausgeschöpften Retries die Coverage senken.

## Reports, Tabellen und Grafiken

In der Detailansicht sind Auswertungsbasis, Mittelwert und Klassenmetrik umschaltbar.

- **Metriken CSV:** eine Zeile je Modell-/Parameterkonfiguration, inklusive Samplegrößen, Coverage und Parameterangaben.
- **Klassen CSV:** eine Zeile je Konfiguration und Klasse, inklusive Support und Confusion-Zahlen.
- **Gold + Predictions CSV/JSONL:** jedes Gold-Dokument für jede Konfiguration; einschließlich `doc_id`, Text, Gold-Labels, Vorhersage, Exact Match, Fehlern, Begründung, Belegen, Thinking und Versuchsprotokoll. Unbearbeitete Dokumente erscheinen als `not_processed`, mit fehlender Vorhersage.
- **Report JSON:** vollständige Metriken der gewählten Auswertungsbasis, Regeln und Snapshots.
- **HTML-Report:** eigenständig lesbares Dokument mit Tabellen, eingebetteten Grafiken und Konfigurationen; keine externen JavaScript-/Bildabhängigkeiten.
- **SVG/PNG:** Modellvergleich, Klassen-Heatmap und Confusion-Grafiken. Zur Lesbarkeit zeigen Klassen-/Confusion-Grafiken bei mehr als 40 Klassen einen ausdrücklich beschrifteten Ausschnitt der ersten 40 Klassen; Tabellen/JSON enthalten weiterhin alle Klassen und alle Confusion-Zahlen.
- **Reportpaket ZIP:** HTML, vollständiger Report-JSON mit beiden Auswertungsbasen, Metriken-/Klassen-CSV, Gold-/Predictions-CSV, Vergleichsgrafiken als SVG/PNG und Confusion-Grafiken je Modell als SVG.

Große Vorhersageexporte werden seitenweise gelesen. CSV schützt vor unbeabsichtigter Interpretation von Text als Tabellenformel durch ein vorangestelltes Apostroph; JSONL erhält die Strings unverändert. Das Reportpaket wird temporär auf Datenträger erstellt und nach Auslieferung entfernt. Umfangreiche Thinking-Ausgaben können den Download erheblich vergrößern.

## Begründungen und Textbelege unabhängig konfigurieren

Im Task sind **Begründung anfordern** und **Wortgetreue Textbelege extrahieren** unabhängige Schalter. In normalen Jobs und Evaluationen kann für jede Option die Task-Einstellung übernommen oder explizit An/Aus gewählt werden. Query-Overrides pro Evaluationsvariante erlauben auch den direkten Vergleich dieser Optionen.

Angefordertes Modellformat, wenn beide Optionen aktiv sind:

```json
{
  "labels": ["FOR"],
  "rationale": "Der Text spricht sich ausdrücklich für die Maßnahme aus.",
  "evidence": [
    {"label": "FOR", "quote": "diese Maßnahme unterstützen"}
  ]
}
```

Der Validator prüft jeden Beleg auf ein ausgewähltes Label und einen nichtleeren, zusammenhängenden, **exakten** Teilstring des tatsächlich gesendeten Textes. Keine Normalisierung, unscharfe Suche oder nachträgliche Erfindung von Zitaten. Doppelte Label-/Zitat-Paare werden abgelehnt. Falls kein positiver Textbeleg existiert, z. B. für eine Restkategorie, darf `evidence` leer sein.

Nach erfolgreicher Prüfung ergänzt das Backend `start` und `end`: 0-basierte Python-Unicode-Zeichenpositionen, Ende exklusiv, bei mehrfach identischem Zitat die erste Fundstelle. Für JavaScript-UTF-16-Offets oder Bytepositionen sind diese Werte nicht unmittelbar austauschbar. Bei explizitem Abschneiden überlanger Texte wird der Textpräfix verwendet; die Positionen passen weiterhin zum Originalpräfix. Die Prüfung belegt die Existenz der Textstelle, nicht deren semantische Eignung als Entscheidungsgrund.

## Thinking speichern

Thinking wird automatisch mitgespeichert, **wenn der Modellserver es liefert**, unabhängig davon, ob `rationale` angefordert wird:

- Ollama: `message.thinking`.
- OpenAI-kompatible Server/vLLM: `message.reasoning`, `message.reasoning_content` oder `message.thinking`.
- Ein expliziter führender `<think>…</think>`-Block im Antworttext wird getrennt erfasst, bevor der anschließende JSON-Output validiert wird. Die unveränderte Antwort bleibt zusätzlich erhalten.

`thinking` enthält die zuletzt erhaltene entsprechende Ausgabe. `attempt_outputs` protokolliert Inhalt, Thinking und Fehler jedes Versuchs, sodass frühere Traces nach einem Retry erhalten bleiben. Thinking und finale Rohantwort werden in v0.2 nicht still gekürzt. Serverinterne Gedanken, die die API nicht ausgibt, können nicht gespeichert werden; es werden keine Ersatztexte als Thinking erfunden.

Thinking **einschalten** ist eine modell-/serverspezifische Einstellung über `extra_body`, z. B. `{"think":true}` bei unterstützten Ollama-Modellen oder `{"chat_template_kwargs":{"enable_thinking":true}}` bei entsprechend konfigurierten vLLM-Modellen. Ein geeigneter Reasoning-Parser auf dem Server kann erforderlich sein. Thinking kann das Output-Tokenbudget mitverbrauchen; bei fehlendem abschließenden JSON bleibt die Klassifikation ungültig, während der gelieferte Trace erhalten bleibt.

Offizielle Referenzen:

- https://scikit-learn.org/stable/modules/model_evaluation.html
- https://docs.ollama.com/capabilities/thinking
- https://docs.vllm.ai/en/latest/features/reasoning_outputs/

## API-Erweiterungen

| Endpoint | Zweck |
|---|---|
| `POST /api/gold-sets` | Importierte CSV mit Spaltenmapping als Gold-Standard registrieren |
| `GET /api/gold-sets` | Registrierte Gold-Standards |
| `GET /api/gold-sets/{id}/preview` | Normalisierte Gold-Daten |
| `POST /api/evaluations` | Evaluation mit Liste von Varianten starten |
| `GET /api/evaluations[/{id}]` | Übersicht / Fortschritt / Konfigurationen |
| `POST /api/evaluations/{id}/{pause,resume,cancel}` | Passende Einzelläufe gemeinsam steuern |
| `POST /api/evaluations/{id}/retry-report` | Fehlgeschlagene Reportberechnung erneut einreihen |
| `GET /api/evaluations/{id}/report` | `scope=common|valid`, `format=json|csv|class_csv|html|zip` |
| `GET /api/evaluations/{id}/chart` | Diagrammtyp, Metrik, Auswertungsbasis, Variante, SVG/PNG |
| `GET /api/evaluations/{id}/predictions` | Paginierte Vorhersagen einer Variante |
| `GET /api/evaluations/{id}/export-predictions` | CSV/JSONL über alle Varianten |

Die vollständigen Request-Schemas sind unter `/docs` abrufbar. Es gibt keine automatische Hyperparameteroptimierung, Cross-Validation oder Konfidenzintervalle. Wiederholungen mit verschiedenen Seeds können als explizite Varianten angelegt werden; deren Ergebnisse werden einzeln berichtet.

## Upgrade von 0.1

Vorhandenes Datenvolume beibehalten. Beide alten Prozesse vor dem Upgrade stoppen, damit kein 0.1-Worker in das erweiterte Datenbankschema schreibt:

```bash
docker compose down
# Quellcode im bisherigen Projektverzeichnis durch Version 0.2 ersetzen.
# Eigene .env und Datenvolume beibehalten.
docker compose up --build -d
```

Kein `down -v` verwenden. Das Compose-Projektverzeichnis bzw. der bisherige Compose-Projektname muss unverändert bleiben, damit dasselbe benannte Volume verwendet wird. Bei Bedarf den bisherigen Projektnamen mit `docker compose -p NAME ...` ausdrücklich angeben.

Beim Start werden neue Tabellen sowie `evidence`, `thinking` und `attempt_outputs` additiv angelegt. Bestehende Tasks/Jobs bleiben erhalten; fehlende neue Task-Optionen bedeuten „aus“. Vorhandene Ergebniszeilen erhalten leere Belege/Versuchslisten und `thinking=null`. Aus früheren Antworten wird Thinking nicht rückwirkend rekonstruiert. Die Migration wird unter einer SQLite-Schreibsperre ausgeführt und ist wiederholbar.
