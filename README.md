# Flour Bestandsoptimierung
Ein plattformunabhängiges Python-Tool mit grafischer Oberfläche zur automatisierten Bestandsanalyse, Bedarfsberechnung und interaktiven PDF-Generierung für Filialbetriebe mit dem Kassensystem "Flour".

Das Tool soll helfen, die Lagerhaltung zu optimieren und Kapitalbindung durch Überbestellungen zu vermeiden. Bestell- und Umverteilungsprozesse bei mehreren Filialen sollen dadurch weitgehend automatisiert werden.

---

## Funktionen

- Intelligente Bedarfsanalyse: Berechnet den realen Bedarf basierend auf historischen Verkäufen unter Berücksichtigung von Mindestbeständen und optionalen Zukunftspuffern.
- Hare-Niemeyer-Umlagerung: Auf Grundlage der historischen Verkaufsstatistik aller Filialen werden die Überbestände einer Filiale proportional und mathematisch fair auf die anderen verteilt.
- Interaktiver PDF-Export: Bestell- und Umbuchungsvorschläge werden als digital ausfüllbare PDF-Datei mit Checkboxen erstellt, um den Bestellfortschritt im Auge zu behalten.
- Effizient sortierte Checkliste: Bestellvorschläge werden nach Lieferanten segmentiert. Innerhalb der Segmente werden Artikel erst nach Hersteller, dann alphabetisch gelistet.
- Privacy-by-Design: Alle Berechnungen und Datenverarbeitungen laufen zu 100% offline und lokal auf dem ausführenden System. Es werden keine Daten an externe API's oder Cloud-Dienste geschickt.

## Anleitung
### Installation
Die aktuellsten Versionen für Windows und Linux sind [hier](https://github.com/issuingemu/Flour-Bestandsoptimierung/releases) oder direkt rechts neben dem Text unter "Releases" zu finden.
#### Windows
- Lade die Datei "Bestands_Tool.exe" herunter und lege sie in einem dedizierten Ordner ab.
- Da das Programm keine offizielle Signatur hat, zeigt Windows Defender beim ersten Start evtl. eine Warnung. Klicke auf "Weitere Informationen" und "Trotzdem ausführen", um das Programm zu starten.

#### Linux
- Lade die Datei "Bestands_Tool-Linux" herunter und lege sie in einem dedizierten Ordner ab.
- Klicke mit der rechten Maustaste auf eine freie Fläche im Ordner und klicke auf "Im Terminal öffnen".
- Kopiere den folgenden Befehl, füge ihn im Terminal ein und bestätige mit Enter.

```
chmod +x Bestands_Tool-Linux
```
  
### Anwendung
#### Quelldateien herunterladen
Klicke in der Flour-Oberfläche auf das Zahnrad und wähle "Export".

![Bild 1](assets/anleitung_1.png)

##### Artikelstammdaten
Klicke auf das Drop-Down Menü und wähle "Artikel".

![Anleitung 2](assets/anleitung_2.png)

Aktiviere die Option "Inklusive kalkulierte Bestände". Klicke dann auf "Export ausführen".

![Anleitung 3](assets/anleitung_3.png)

Sobald die Datei fertig erstellt wurde, kannst du sie im Menü links oder direkt unter dem "Export ausführen" Button herunterladen.

![Anleitung 3.1](assets/anleitung_3.1.png)

##### Verkaufsdaten
Gehe wieder zu Export und wähle im Drop-Down Menü "Verkaufsübersicht Artikel".

![Anleitung 4](assets/anleitung_4.png)

###### Artikelfilter
Hier gibt es einige Optionen, nach Warengruppen zu filtern. Beispielsweise können Artikeltags angegeben werden, um nur Artikel zu exportieren, die diese Tags hinterlegt haben.
**ACHTUNG:** Wenn mehrere Tags angegeben werden, landen am Ende nur Artikel in der Datei, die **alle angegebenen Tags gleichzeitig nutzen**.
###### Zeitraum & Bedarfsrechnung
Das Tool nutzt das hier gewählte Startdatum zur Berechnung deines Verkaufszeitraums. Die verkaufte Menge aus genau dieser Spanne bestimmt den zukünftigen Basisbedarf.
- **Beispiel:** Setzt du das Feld „Datum von“ auf exakt eine Woche in die Vergangenheit und Artikel A wurde in dieser Woche 8-mal verkauft, definiert das Programm den Grundbedarf für diesen Artikel auf 8 Stück.

Wenn die Artikelfilter gesetzt sind und ein Zeitraum bestimmt wurde, klickst du wieder auf "Export starten", wartest bis die Datei fertig ist und lädst sie herunter.

![Anleitung 4.1](assets/anleitung_4.1.png)

#### Anwendung des Tools
Das Tool durchsucht beim Start automatisch den Ordner in dem es liegt nach den zwei aktuellsten CSV Dateien mit "articles" und "articlessold" im Namen. Benenne die gerade heruntergeladenen Dateien also **nicht** um, sondern lege sie so wie sie sind in dem Ordner ab, in dem auch das Programm liegt.

![Anleitung 5](assets/anleitung_5.png)

Wenn du das Tool startest, solltest du ganz oben zwei grüne Zeilen sehen, die bestätigen, dass die Dateien gefunden wurden.

![Anleitung 6](assets/anleitung_6.png)

