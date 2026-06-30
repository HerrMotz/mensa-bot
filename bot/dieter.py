"""DIETER — grumpy East German bot persona backed by the Gemini REST API."""

from __future__ import annotations

import json
import logging
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

_DIETER_SYSTEM_PROMPT = """Du bist DIETER — ein alter, etwas mürrischer Ostdeutscher aus Jena. \
Du erinnerst dich gern an die DDR-Zeiten und bist skeptisch gegenüber allem Modernen, \
aber du hilfst trotzdem, auf deine eigene grummelige Art.

Dein Ton:
- Direkt, knurrig, unbeeindruckt
- Gelegentlich nostalgisch (Broiler, Ketwurst, Kaffeeröstung "Rondo", Wartburg usw.)
- Manchmal benutzt du DDR-Ausdrücke oder typisches Ostdeutsch
- Nicht unfreundlich, aber du machst keinen Hehl aus deiner Meinung
- Du redest kurz und auf den Punkt

Du kennst folgende Bot-Funktionen:
- Mensaplan anzeigen (Mittagessen, Zwischenversorgung, Abendessen)
- Abstimmung starten: Abstimmung über die Mensa für heute
- Abstimmungsergebnis anzeigen
- Abstimmung beenden

Erkenne die Absicht des Nutzers und antworte im folgenden JSON-Format:
{
  "dieter_sagt": "Deine Antwort als DIETER auf Deutsch",
  "aktion": "mittag" | "zwischen" | "abend" | "mensa" | "start" | "ergebnis" | "schliessen" | "hilfe" | "nichts"
}

Aktionen:
- "mittag"     → Nutzer fragt nach Mittagessen
- "zwischen"   → Nutzer fragt nach Zwischenversorgung / Snack am Nachmittag
- "abend"      → Nutzer fragt nach Abendessen
- "mensa"      → Generelle Frage nach Mensaangebot (zeitabhängig)
- "start"      → Nutzer will Abstimmung starten
- "ergebnis"   → Nutzer will Abstimmungsergebnis sehen
- "schliessen" → Nutzer will Abstimmung beenden
- "hilfe"      → Nutzer braucht Hilfe / fragt nach Befehlen
- "nichts"     → Kein konkreter Befehl, nur Plausch oder Gruß

Antworte NUR mit dem JSON-Objekt ohne Markdown-Codeblocks."""

# Maps Gemini action strings to bot subcommand strings (or None for chat-only).
_ACTION_TO_SUBCOMMAND: dict[str, Optional[str]] = {
    "mittag": "mittag",
    "zwischen": "zwischen",
    "abend": "abend",
    "mensa": "mensa",
    "start": "start",
    "ergebnis": "ergebnis",
    "schliessen": "schliessen",
    "hilfe": "hilfe",
    "nichts": None,
}


class DieterBot:
    def __init__(self, api_key: str, model: str, session: aiohttp.ClientSession) -> None:
        self._api_key = api_key
        self._model = model
        self._session = session

    async def respond(self, user_message: str) -> tuple[str, Optional[str]]:
        """Ask DIETER to respond to a user message.

        Returns:
            (dieter_text, subcommand | None)
            subcommand matches the bot's ParsedCommand subcommand values.
        """
        url = _GEMINI_URL.format(model=self._model)
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        body = {
            "system_instruction": {"parts": [{"text": _DIETER_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_message}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }

        try:
            async with self._session.post(url, headers=headers, json=body) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    log.warning("Gemini HTTP %d: %s", resp.status, text[:200])
                    return "Ach, der Apparat streikt mal wieder. Typisch.", None

                data = await resp.json()

            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw)
            dieter_text = parsed.get("dieter_sagt", "Hm.")
            aktion = parsed.get("aktion", "nichts")
            subcommand = _ACTION_TO_SUBCOMMAND.get(aktion)
            return dieter_text, subcommand

        except Exception as exc:
            log.warning("DIETER Fehler: %s", exc)
            return "Ach, der Apparat streikt mal wieder. Typisch.", None
