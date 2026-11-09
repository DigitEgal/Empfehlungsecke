<p align="center">
  <img src="assets/digitegal_wordmark.png" alt="DigitEgal" width="420">
</p>

# DigitEgal Empfehlungsecke

Eine lokale Windows-App für eine umfangreiche, Ordner-basierte Sammlung von Web-Empfehlungen. Sie liest Windows-Internetverknüpfungen (`.url` / `.URL`), stellt die vertraute Ordnerstruktur übersichtlich dar und macht die Sammlung schnell durchsuchbar.

## Warum dieses Tool?

Eine Link-Sammlung bleibt nur dann nützlich, wenn sie sich wie ein Explorer durchsehen und gleichzeitig wie eine Suchmaschine durchsuchen lässt. Die DigitEgal Empfehlungsecke verbindet beides – ohne Cloud, Konto oder Datenbank.

| Funktion | Nutzen |
| --- | --- |
| Ordnerbaum | Navigiere durch die vorhandene Struktur, inklusive Unterordnern. |
| Explorer-Ansicht | Zeigt ohne Suche die direkten Unterordner und Links des geöffneten Pfads. |
| Pfad-begrenzte Suche | Sucht nur im aktuell geöffneten Ordner und seinen Unterordnern. |
| Doppelfreie Treffer | Gleiche Ziel-URLs erscheinen nur einmal – alle Fundorte bleiben sichtbar. |
| Browser-Start | Öffnet ausgewählte Empfehlungen direkt im Standardbrowser. |
| Aktualisierbar | Verlinkt im Kopfbereich auf die aktuelle Sammlung bei DigitEgal. |

## Oberfläche

### Ordner erkunden

<img src="docs/oberflaeche.svg" alt="Vorschau der Ordnernavigation mit Ordnerbaum und Inhalt" width="100%">

1. Wähle links einen Ordner im Baum.
2. Rechts erscheinen seine direkten Unterordner und Links.
3. Ein Klick auf einen Unterordner öffnet ihn; ein Doppelklick auf einen Link öffnet dessen Webseite.
4. Bei ausgewähltem Link zeigt der Detailbereich alle Fundorte dieses Links.

### Im geöffneten Pfad suchen

<img src="docs/suche.svg" alt="Vorschau einer Suche mit Unterordnern und eindeutigen Links" width="100%">

Die Suche berücksichtigt Titel, URL, Ordnerpfad und Dateinamen. Sie durchsucht den gerade geöffneten Pfad inklusive aller Unterordner. Passende Unterordner werden oberhalb der Link-Treffer eingeblendet und können direkt geöffnet werden.

## Installation unter Windows

### Schnellstart

1. Das Paket vollständig entpacken.
2. `INSTALLIEREN.bat` im Ordner `empfehlungsecke_gui` doppelklicken.
3. Nach erfolgreicher Einrichtung `starten.bat` doppelklicken.

Das Installationsskript prüft Python inklusive `tkinter`. Falls Python fehlt, installiert es Python 3.11 mit dem Windows Package Manager `winget` für den aktuellen Benutzer und erstellt anschließend eine lokale virtuelle Umgebung (`.venv`). Dafür sind keine Administratorrechte erforderlich.

> Die App nutzt nur die Python-Standardbibliothek. Es werden keine zusätzlichen Pip-Pakete installiert; `requirements.txt` dokumentiert dies ausdrücklich.

### Manuell in PowerShell starten

```powershell
cd .\empfehlungsecke_gui
.\install.ps1
.\starten.bat
```

Wenn auf dem System kein `winget` verfügbar ist, installiere Python 3.9 oder neuer über [python.org](https://www.python.org/downloads/windows/) und starte anschließend das Installationsskript erneut.

## Link-Sammlung verwenden

Beim ersten Start wird der benachbarte Ordner `../000_Empfehlungsecke` automatisch eingelesen. Über **Ordner wählen** kann jede andere Sammlung mit `.url`-Verknüpfungen geöffnet werden.

Über **Aktuelle Sammlung herunterladen ↗** im Kopfbereich gelangst du zu [digitegal.de/empfehlungsecke](https://digitegal.de/empfehlungsecke/), um neue Empfehlungen herunterzuladen und als Ordner auszuwählen.

### Wie werden Duplikate erkannt?

Die App vergleicht die Ziel-URLs der Verknüpfungen. Bei diesem Vergleich werden Groß-/Kleinschreibung im Hostnamen, abschließende Slashes, Fragmente und übliche Tracking-Parameter wie `utm_*`, `fbclid` und `gclid` ignoriert. Fachliche Parameter bleiben bewusst erhalten, damit unterschiedliche Suchanfragen oder Seiten nicht versehentlich zusammengeführt werden.

## Datenschutz

Die Sammlung wird vollständig lokal eingelesen. Die App überträgt keine Link-Daten. Erst beim bewussten Öffnen einer Empfehlung wird die entsprechende Webseite im Standardbrowser aufgerufen.

## Projektstruktur

```text
empfehlungsecke_gui/
├── app.py                 # GUI und Link-Scanner
├── INSTALLIEREN.bat       # Einfacher Windows-Einstieg
├── install.ps1            # Python-Prüfung und lokale Einrichtung
├── starten.bat            # App-Start
├── requirements.txt       # Keine externen Abhängigkeiten
├── assets/                # DigitEgal-Wortmarke und Tool-Logo
└── docs/                  # GitHub-Grafiken zur Bedienung
```

## Voraussetzungen

- Windows 10 oder neuer
- Python 3.9 oder neuer (wird durch das Installationsskript eingerichtet)
- Eine Ordnerstruktur mit Windows-Internetverknüpfungen (`.url` / `.URL`)

---

DigitEgal – Empfehlungen finden, statt sie zu suchen.
