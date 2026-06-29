# MensaBot – Element/Matrix Bot für Studierendenwerk Thüringen

Ein deutschsprachiger Matrix-Bot für den Mensaplan der Jenaer Mensen. Zeigt Speisepläne an und leitet Abstimmungen durch (Approval-Voting, Borda-Zählung oder Instant-Runoff-Voting).

---

## Funktionen

- **Speiseplan**: Ruft Mittagessen, Zwischenversorgung und Abendessen von stw-thueringen.de ab.
- **Automatische Zeitauswahl**: Zeigt je nach Uhrzeit das passende Angebot.
- **Preise**: Zeigt Preise für Studierende und Bedienstete (keine Gästepreise).
- **Abstimmung**: Native Matrix-Umfrage — bei Approval-Voting jede Mensa als eigene Option (Mehrfachauswahl), bei Borda/IRV alle Reihenfolge-Permutationen.
- **Drei Abstimmungsmethoden**: Approval-Voting (Standard), Borda-Zählung, Instant-Runoff-Voting — alle mit dokumentierter Gleichstandsauflösung.
- **E2EE-Unterstützung**: Funktioniert in verschlüsselten Element-Räumen.
- **Persistenz**: SQLite-Datenbank; Bot erholt sich nach Neustart.

---

## Befehle

| Befehl | Beschreibung |
|---|---|
| `!mensa` oder `!m` | Aktuell relevante Speisen |
| `!mensa heute` | Heutiges Mittagessen |
| `!mensa start` | Abstimmung starten (Standard-Methode aus Konfiguration) |
| `!mensa start approval` | Abstimmung per Approval-Voting |
| `!mensa start borda` | Abstimmung per Borda-Zählung |
| `!mensa start irv` | Abstimmung per Instant-Runoff-Voting |
| `!mensa votieren 1,3` | Stimme abgeben (Zahlen = akzeptable Mensen bei Approval, Reihenfolge bei Borda/IRV) |
| `!mensa ergebnis` | Aktuelles Abstimmungsergebnis |
| `!mensa schließen` | Abstimmung manuell beenden |
| `!mensa schluss` | Abstimmung manuell beenden (Kurzform) |
| `!mensa hilfe` | Hilfemeldung |

> `!m` ist für alle Befehle gültig, z. B. `!m start`, `!m votieren 1,2`, `!m ergebnis`.

---

## Matrix-Bot-Konto erstellen (matrix.org)

### 1. Konto registrieren

Gehe auf [app.element.io](https://app.element.io) → *Konto erstellen* → Homeserver **matrix.org** wählen → Benutzername `mensa-bot` (oder ähnlich) → Passwort vergeben.

> Alternativ per API:
> ```bash
> curl -X POST https://matrix.org/_matrix/client/v3/register \
>   -H "Content-Type: application/json" \
>   -d '{"username":"mensa-bot","password":"SICHERES_PASSWORT","auth":{"type":"m.login.dummy"}}'
> ```

### 2. Raum erstellen und Bot einladen

- Element öffnen → Neuen Raum erstellen (oder bestehenden Raum verwenden).
- Bot-Konto (`@mensa-bot:matrix.org`) in den Raum einladen.
- Raum-ID notieren (z. B. `!xyz:matrix.org` → in Element: *Rauminfo → Erweitert*).

> **Wichtig:** Der Bot benötigt keine besonderen Berechtigungen, nur das Recht, Nachrichten zu senden.

> **Hinweis zu E2EE:** Der Bot unterstützt Ende-zu-Ende-Verschlüsselung. Beim ersten Start werden Geräteschlüssel hochgeladen. Es ist kein manuelles Verifizieren nötig, aber du kannst den Bot-Account in Element als vertrauenswürdig markieren.

---

## Installation & Deployment (VPS mit Docker)

### Voraussetzungen

- VPS mit Docker und Docker Compose
- Offener Internetzugang (zum Abrufen von stw-thueringen.de und matrix.org)

### 1. Repository klonen

```bash
git clone https://github.com/your-org/mensa-element-bot.git
cd mensa-element-bot
```

### 2. Konfiguration anlegen

```bash
cp config.yaml.example /opt/mensa-bot/config.yaml
nano /opt/mensa-bot/config.yaml
```

Fülle alle Pflichtfelder aus (homeserver, username, password/access_token, room_id).

### 3. Docker Volume vorbereiten

```bash
mkdir -p /opt/mensa-bot
# Die config.yaml muss ins Volume:
docker run --rm -v mensa-element-bot_bot-data:/data -v /opt/mensa-bot:/src alpine cp /src/config.yaml /data/config.yaml
```

### 4. Bot starten

```bash
docker compose up -d
```

### 5. Logs prüfen

```bash
docker compose logs -f
```

---

## Tägliche Mensanachricht

Mit `daily_message_enabled: true` sendet der Bot automatisch den Mittagsspeiseplan zur konfigurierten Uhrzeit (Standard: 10:30 Uhr) — aber nur an Werktagen und ohne Thüringer Feiertage.

**Berücksichtigte Feiertage (Thüringen):**
Neujahr, Karfreitag, Ostermontag, Tag der Arbeit, Christi Himmelfahrt, Pfingstmontag, Weltkindertag (ab 2019), Tag der deutschen Einheit, Reformationstag, 1. und 2. Weihnachtstag.

---

## Konfiguration (`config.yaml`)

| Schlüssel | Pflicht | Standard | Beschreibung |
|---|---|---|---|
| `matrix.homeserver` | ✓ | – | Homeserver-URL |
| `matrix.username` | ✓ | – | Bot-MXID |
| `matrix.password` | \* | – | Passwort (oder access_token) |
| `matrix.access_token` | \* | – | Access-Token statt Passwort |
| `matrix.room_id` | ✓ | – | Ziel-Raum-ID |
| `matrix.store_path` | – | `/data/nio_store` | Pfad für E2EE-Schlüsselspeicher |
| `bot.command_prefix` | – | `!mensa` | Befehlspräfix |
| `bot.max_poll_mensas` | – | `3` | Ab wann Kommandomodus statt Poll (nur Borda/IRV) |
| `bot.vote_duration_minutes` | – | `20` | Abstimmungsdauer |
| `bot.cache_duration_minutes` | – | `30` | Cache-Gültigkeit |
| `bot.voting_method` | – | `approval` | Standard-Abstimmungsmethode: `approval`, `borda` oder `irv` |
| `bot.daily_message_enabled` | – | `false` | Tägliche Mensanachricht aktivieren |
| `bot.daily_message_time` | – | `10:30` | Uhrzeit für die tägliche Nachricht (Format `HH:MM`) |
| `bot.timezone` | – | `Europe/Berlin` | Zeitzone |
| `meal_times.*` | – | siehe Beispiel | Mahlzeiten-Zeitfenster |
| `mensas[].name` | ✓ | – | Mensaname |
| `mensas[].url` | ✓ | – | Speiseplan-URL |
| `mensas[].short_name` | – | = name | Kurzname |

\* Eines von beiden ist Pflicht.

---

## Abstimmungsdesign

### Approval-Voting (Standard)

Jede Person markiert alle Mensen, die sie für akzeptabel hält — eine oder mehrere. Die Mensa mit den meisten Zustimmungen gewinnt.

**Native Poll (≤ 20 Mensen):** Jede Mensa erscheint als eigene Option, Mehrfachauswahl ist aktiviert. Kein Permutationsproblem — auch bei vielen Mensen bleibt der native Poll verwendbar.

**Kommandomodus (> 20 Mensen):** `!mensa wahl 1,3` bedeutet „Mensa 1 und Mensa 3 sind für mich akzeptabel."

**Gleichstandsauflösung:** Konfigurierte Mensa-Reihenfolge (erste gewinnt). Gleichstände werden immer ausgewiesen.

### Borda-Zählung

Jede Person bringt alle Mensen in eine Reihenfolge. Bei N Mensen erhält der erstgereihte Kandidat N−1 Punkte, der zweite N−2 usw. Wer die meisten Punkte sammelt, gewinnt.

**Native Poll (≤ 3 Mensen standardmäßig):** Alle Reihenfolge-Permutationen werden als Poll-Optionen angezeigt. Bei 3 Mensen: 3! = 6 Optionen. **Ab 4 Mensen:** 4! = 24 Permutationen überschreiten das Matrix-Poll-Limit (20 Optionen) → automatischer Wechsel in den Kommandomodus.

**Kommandomodus:** `!mensa wahl 2,1,3` bedeutet „Mensa 2 > Mensa 1 > Mensa 3 (alle müssen angegeben werden)."

**Gleichstandsauflösung:**
1. Besserer Durchschnittsrang
2. Konfigurierte Mensa-Reihenfolge

### Instant-Runoff-Voting (IRV)

Wie Borda — jede Person bringt alle Mensen in eine Reihenfolge. Auswertung in Runden:

1. Jede Stimme beginnt bei der erstgereihten Mensa.
2. Wer > 50 % der aktiven Stimmen hat, gewinnt.
3. Sonst wird die Mensa mit den wenigsten Stimmen eliminiert.
4. Deren Stimmen wandern zur nächsten aktiven Mensa auf dem jeweiligen Stimmzettel.
5. Wiederholung bis Gewinner gefunden.

**Gleichstandsauflösung (Elimination):**
1. Meiste Erststimmen in Runde 1
2. Bester Gesamt-Rangwert (kleiner = besser)
3. Konfigurierte Mensa-Reihenfolge

Gleichstände werden immer im Ergebnis ausgewiesen.

---

## Datenbankschema

Tabellen: `mensas`, `menu_cache`, `meals`, `room_config`, `vote_sessions`, `vote_options`, `vote_ballots`, `matrix_poll_events`, `bot_state`.

---

## Tests ausführen

```bash
pip install -r requirements.txt
pytest
```

---

## Bekannte Einschränkungen

- **Datenbasis:** Der Bot scrapt stw-thueringen.de. Layoutänderungen können den Parser beeinträchtigen — die Fallback-Logik gibt dann leere Ergebnisse zurück statt abzustürzen.
- **OpenMensa:** Die Thüringen-Parser auf OpenMensa sind inaktiv (leere Antworten). Sobald sie wieder gepflegt werden, kann der Fetcher auf die OpenMensa-API umgestellt werden (Schnittstelle dafür ist bereits vorbereitet).
- **E2EE-Geräteverifikation:** Der Bot markiert unverifizierte Geräte als vertrauenswürdig (`ignore_unverified_devices=True`). Für höchste Sicherheitsanforderungen kann dies angepasst werden.
- **Approval-Voting im nativen Poll:** Die Mehrfachauswahl im nativen Matrix-Poll nutzt den MSC3381-Standard. Die Verarbeitung mehrerer Antworten wurde durch Code-Analyse und Tests verifiziert; ein Live-Test gegen einen echten Homeserver ist im lokalen Entwicklungssetup nicht möglich.
