# MensaBot – Element/Matrix Bot für Studierendenwerk Thüringen

Ein deutschsprachiger Matrix-Bot für den Mensaplan der Jenaer Mensen. Zeigt Speisepläne an und leitet Abstimmungen (Instant-Runoff-Voting) durch.

---

## Funktionen

- **Speiseplan**: Ruft Mittagessen, Zwischenversorgung und Abendessen von stw-thueringen.de ab.
- **Automatische Zeitauswahl**: Zeigt je nach Uhrzeit das passende Angebot.
- **Preise**: Zeigt Preise für Studierende und Bedienstete (keine Gästepreise).
- **Abstimmung**: Native Matrix-Umfrage mit allen Reihenfolge-Permutationen (3 Mensen → 6 Optionen).
- **Instant-Runoff-Voting**: Ausgewertetes Ergebnis mit Rundenübersicht und Gleichstandsauflösung.
- **E2EE-Unterstützung**: Funktioniert in verschlüsselten Element-Räumen.
- **Persistenz**: SQLite-Datenbank; Bot erholt sich nach Neustart.

---

## Befehle

| Befehl | Beschreibung |
|---|---|
| `!mensa` | Aktuell relevante Speisen |
| `!mensa heute` | Heutiges Mittagessen |
| `!mensa votieren` | Abstimmung starten |
| `!mensa wahl 2,1,3` | Stimme abgeben (Kommandomodus) |
| `!mensa ergebnis` | Aktuelles Abstimmungsergebnis |
| `!mensa schließen` | Abstimmung manuell beenden |
| `!mensa hilfe` | Hilfemeldung |

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
| `bot.max_poll_mensas` | – | `3` | Ab wann Kommandomodus statt Poll |
| `bot.vote_duration_minutes` | – | `20` | Abstimmungsdauer |
| `bot.cache_duration_minutes` | – | `30` | Cache-Gültigkeit |
| `bot.timezone` | – | `Europe/Berlin` | Zeitzone |
| `meal_times.*` | – | siehe Beispiel | Mahlzeiten-Zeitfenster |
| `mensas[].name` | ✓ | – | Mensaname |
| `mensas[].url` | ✓ | – | Speiseplan-URL |
| `mensas[].short_name` | – | = name | Kurzname |

\* Eines von beiden ist Pflicht.

---

## Abstimmungsdesign

### Nativer Matrix-Poll (≤ 3 Mensen)

Für drei Mensen gibt es 3! = 6 Reihenfolge-Permutationen — alle passen in einen nativen Matrix-Poll (max. 20 Optionen). Nutzer wählen ihre bevorzugte Reihenfolge. Der Bot liest die Abstimmung aus und wendet IRV an.

**Wichtig:** Bei 4 Mensen entstehen 4! = 24 Permutationen, was den Matrix-Poll-Limit (20 Optionen) überschreitet. Ab 4 Mensen wechselt der Bot daher automatisch in den **Kommandomodus** (`!mensa wahl 2,1,3`).

### Instant-Runoff-Voting (IRV)

1. Jede Stimme beginnt bei der erstgereihten Mensa.
2. Wer > 50 % der aktiven Stimmen hat, gewinnt.
3. Sonst wird die Mensa mit den wenigsten Stimmen eliminiert.
4. Deren Stimmen wandern zur nächsten aktiven Mensa auf dem jeweiligen Stimmzettel.
5. Wiederholung bis Gewinner gefunden.

**Gleichstandsauflösung:**
1. Meiste Erststimmen in Runde 1
2. Bester Gesamt-Rangwert (kleiner = besser)
3. Konfigurierte Mensa-Reihenfolge
4. Gleichstand wird immer im Ergebnis ausgewiesen.

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
- **E2EE-Geräteverifikation:** Der Bot markiert unverifizierten Geräten als vertrauenswürdig (`ignore_unverified_devices=True`). Für höchste Sicherheitsanforderungen kann dies angepasst werden.
