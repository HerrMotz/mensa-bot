"""MensaBot entry point."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiohttp

from .commands import parse_command
from .config import Config, MensaConfig, load_config
from .dieter import DieterBot
from .database import Database
from .fetcher import fetch_meals_html, parse_meals
from .holidays import is_workday
from .formatter import (
    build_approval_poll_content,
    build_native_poll_content,
    format_all_mensas,
    format_help,
    format_no_active_vote,
    format_vote_already_active,
    format_vote_closed,
    format_vote_start_message,
)
from .matrix_client import MatrixBot
from .meal_time import (
    CATEGORY_ABENDESSEN,
    CATEGORY_MITTAGESSEN,
    CATEGORY_ZWISCHENVERSORGUNG,
    filter_meals_by_category,
    get_relevant_category,
)
from .vote_manager import VoteManager

log = logging.getLogger(__name__)


class MensaBot:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._db = Database(config.bot.db_path)
        self._http: Optional[aiohttp.ClientSession] = None

        self._matrix = MatrixBot(
            homeserver=config.matrix.homeserver,
            username=config.matrix.username,
            store_path=config.matrix.store_path,
            device_name=config.matrix.device_name,
            password=config.matrix.password,
            access_token=config.matrix.access_token,
        )
        self._matrix.set_room_id(config.matrix.room_id)
        self._matrix.on_command(self._handle_command)
        self._matrix.on_poll_response(self._handle_poll_response)
        self._matrix.register_sync_callback()

        self._dieter: Optional[DieterBot] = None  # initialised in run() after http session

        self._mensa_names = [m.name for m in config.mensas]

        self._vote_manager = VoteManager(
            db=self._db,
            mensas=self._mensa_names,
            max_poll_mensas=config.bot.max_poll_mensas,
            vote_duration_minutes=config.bot.vote_duration_minutes,
            vote_reminder_minutes=config.bot.vote_reminder_minutes,
            room_id=config.matrix.room_id,
            send_message=self._send,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        self._db.connect()
        self._http = aiohttp.ClientSession()

        if self._config.bot.gemini_api_key:
            self._dieter = DieterBot(
                api_key=self._config.bot.gemini_api_key,
                model=self._config.bot.gemini_model,
                session=self._http,
            )
            log.info("DIETER aktiviert (Trigger: %s, Modell: %s).",
                     self._config.bot.dieter_trigger, self._config.bot.gemini_model)

        # Ensure all configured mensas exist in the DB.
        for m in self._config.mensas:
            self._db.upsert_mensa(m.name, m.url, m.short_name)

        await self._matrix.login()
        await self._matrix.join_room(self._config.matrix.room_id)
        await self._vote_manager.start()

        if self._config.bot.daily_message_enabled:
            asyncio.create_task(self._daily_message_loop())

        log.info("MensaBot läuft. Warte auf Nachrichten …")
        try:
            await self._matrix.sync_forever()
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        if self._http:
            await self._http.close()
        await self._matrix.close()
        self._db.close()

    # ── Daily meal message ────────────────────────────────────────────────────

    async def _daily_message_loop(self) -> None:
        """Background task: send the daily meal plan at the configured time on workdays."""
        import datetime as dtmod
        from zoneinfo import ZoneInfo

        cfg = self._config.bot
        tz = ZoneInfo(cfg.timezone)
        h, m = (int(x) for x in cfg.daily_message_time.split(":"))

        while True:
            try:
                now = dtmod.datetime.now(tz)
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if target <= now:
                    target += dtmod.timedelta(days=1)

                delay = (target - now).total_seconds()
                log.debug("Nächste tägliche Nachricht in %.0f Sekunden (%s).", delay, target)
                await asyncio.sleep(delay)

                fire_date = dtmod.datetime.now(tz).date()
                if is_workday(fire_date):
                    log.info("Sende tägliche Mensanachricht für %s.", fire_date)
                    await self._cmd_show_meals(
                        self._config.matrix.room_id,
                        forced_category=CATEGORY_MITTAGESSEN,
                    )
                else:
                    log.info(
                        "Kein Arbeitstag (%s) – tägliche Nachricht wird übersprungen.", fire_date
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Fehler in der täglichen Nachrichtenroutine: %s", exc)
                await asyncio.sleep(60)

    # ── Message sending ───────────────────────────────────────────────────────

    async def _send(self, room_id: str, text: str) -> Optional[str]:
        return await self._matrix.send_message(room_id, text)

    # ── Command handler ───────────────────────────────────────────────────────

    async def _handle_command(
        self,
        room_id: str,
        sender: str,
        body: str,
        display_name: Optional[str],
        formatted_body: Optional[str] = None,
    ) -> None:
        # Explicit bot command takes priority.
        cmd = parse_command(body, [self._config.bot.command_prefix, "!m"])
        if cmd is not None:
            log.info("Befehl von %s: %r", sender, body[:80])
            try:
                await self._dispatch_subcommand(room_id, sender, display_name, cmd.subcommand, cmd)
            except Exception as exc:
                log.exception("Fehler bei der Befehlsverarbeitung: %s", exc)
                await self._send(room_id, "Es ist ein interner Fehler aufgetreten. Bitte versuche es später erneut.")
            return

        # Natural language via @DIETER mention.
        # Check both plain body (for "@DIETER" text trigger) and formatted_body (for Matrix
        # mention links which render as "DIETER: …" in plain text without the "@").
        trigger = self._config.bot.dieter_trigger
        bot_user_id = self._matrix.user_id or ""
        dieter_mentioned = (
            trigger.lower() in body.lower()
            or (formatted_body is not None and (
                trigger.lower() in formatted_body.lower()
                or (bot_user_id and bot_user_id in formatted_body)
            ))
        )
        if self._dieter and dieter_mentioned:
            log.info("DIETER angesprochen von %s: %r", sender, body[:80])
            try:
                dieter_text, subcommand = await self._dieter.respond(body)
                await self._send(room_id, f"**DIETER:** {dieter_text}")
                if subcommand:
                    await self._dispatch_subcommand(room_id, sender, display_name, subcommand, None)
            except Exception as exc:
                log.exception("Fehler in DIETER-Verarbeitung: %s", exc)

    async def _dispatch_subcommand(
        self,
        room_id: str,
        sender: str,
        display_name: Optional[str],
        subcommand: str,
        cmd,  # ParsedCommand | None
    ) -> None:
        if subcommand in ("mensa", "heute", "mittag", "zwischen", "abend"):
            forced = {
                "heute": CATEGORY_MITTAGESSEN,
                "mittag": CATEGORY_MITTAGESSEN,
                "zwischen": CATEGORY_ZWISCHENVERSORGUNG,
                "abend": CATEGORY_ABENDESSEN,
            }.get(subcommand)
            await self._cmd_show_meals(room_id, forced_category=forced)

        elif subcommand == "start":
            raw_args = cmd.raw_args.strip().lower() if cmd else ""
            method = raw_args if raw_args in ("borda", "irv", "approval") else self._config.bot.voting_method
            await self._cmd_start_vote(room_id, voting_method=method)

        elif subcommand == "votieren":
            ranking = cmd.ranking_indices if cmd else None
            await self._cmd_cast_ballot(room_id, sender, display_name, ranking)

        elif subcommand == "ergebnis":
            msg = await self._vote_manager.get_current_result_message()
            await self._send(room_id, msg)

        elif subcommand == "schliessen":
            await self._cmd_close_vote(room_id)

        elif subcommand == "hilfe":
            await self._send(room_id, format_help())

    async def _cmd_show_meals(
        self, room_id: str, forced_category: Optional[str] = None
    ) -> None:
        cfg = self._config
        tz = cfg.bot.timezone
        mt = cfg.meal_times

        if forced_category is not None:
            category = forced_category
            show_next = False
        else:
            category, show_next = get_relevant_category(
                timezone=tz,
                lunch_start=mt.lunch_start,
                lunch_end=mt.lunch_end,
                zwischenversorgung_start=mt.zwischenversorgung_start,
                zwischenversorgung_end=mt.zwischenversorgung_end,
                abendessen_start=mt.abendessen_start,
                abendessen_end=mt.abendessen_end,
            )

        from zoneinfo import ZoneInfo
        import datetime as dtmod
        tz_info = ZoneInfo(tz)
        local_now = dtmod.datetime.now(tz_info)
        target = local_now + dtmod.timedelta(days=1) if show_next else local_now
        target_date = target.date()

        results = []
        for mensa_cfg in cfg.mensas:
            meals, error = await self._get_meals_for_mensa(mensa_cfg, target_date)
            if error is None:
                filtered = filter_meals_by_category(meals, category)
                results.append((mensa_cfg.name, filtered, None))
            else:
                results.append((mensa_cfg.name, [], error))

        msg = format_all_mensas(results, category, target)
        if show_next:
            msg = "_(Morgen:)_\n\n" + msg
        await self._send(room_id, msg)

    async def _get_meals_for_mensa(
        self,
        mensa_cfg: MensaConfig,
        target_date,
    ) -> tuple[list[dict], Optional[str]]:
        """Fetch and parse meals, using the cache when fresh enough."""
        mensa_id = self._db.get_mensa_id(mensa_cfg.name)
        date_str = target_date.strftime("%Y-%m-%d")

        cache = self._db.get_cache(mensa_id, date_str)
        if cache:
            cache_age = datetime.fromisoformat(cache["fetched_at"].replace("Z", "+00:00"))
            max_age = timedelta(minutes=self._config.bot.cache_duration_minutes)
            if datetime.now(timezone.utc) - cache_age < max_age:
                meals = self._db.get_meals(cache["id"])
                if meals:
                    return meals, None

        # Fetch fresh via XHR endpoint (date-specific), fall back to full page.
        html = await fetch_meals_html(mensa_cfg.url, target_date, self._http)
        if html is None:
            return [], f"Die Mensa-Website ist derzeit nicht erreichbar."

        cache_id = self._db.set_cache(mensa_id, date_str, html)
        meals = parse_meals(html)

        if not meals:
            return [], "Kein Speiseplan für heute verfügbar (möglicherweise geschlossen)."

        self._db.save_meals(cache_id, meals)
        return meals, None

    async def _cmd_start_vote(self, room_id: str, voting_method: str = "borda") -> None:
        if self._vote_manager.has_active_vote():
            active = self._vote_manager.get_active_vote()
            closes_at = datetime.fromisoformat(active["closes_at"])
            await self._send(room_id, format_vote_already_active(closes_at))
            return

        session_id, poll_mode, options, closes_at = await self._vote_manager.create_vote(
            voting_method=voting_method
        )

        # Post the announcement.
        announcement = format_vote_start_message(
            mensas=self._mensa_names,
            options=options,
            closes_at=closes_at,
            poll_mode=poll_mode,
            voting_method=voting_method,
        )
        await self._send(room_id, announcement)

        # For native mode, also send the Matrix poll.
        if poll_mode == "native":
            if voting_method == "approval":
                poll_content = build_approval_poll_content(
                    mensas=self._mensa_names,
                    duration_minutes=self._config.bot.vote_duration_minutes,
                )
            else:
                poll_content = build_native_poll_content(
                    mensas=self._mensa_names,
                    options=options,
                    duration_minutes=self._config.bot.vote_duration_minutes,
                )
            poll_event_id = await self._matrix.send_poll(room_id, poll_content)
            if poll_event_id:
                self._vote_manager.set_poll_event_id(session_id, poll_event_id)

    async def _cmd_cast_ballot(
        self,
        room_id: str,
        sender: str,
        display_name: Optional[str],
        ranking_indices: Optional[list[int]],
    ) -> None:
        active = self._vote_manager.get_active_vote()
        if not active:
            await self._send(room_id, format_no_active_vote())
            return

        if active["poll_mode"] == "native":
            await self._send(
                room_id,
                "Bitte stimme über den oben angezeigten Poll ab, nicht per Befehl.",
            )
            return

        if not ranking_indices:
            n = len(self._mensa_names)
            numbered = "\n".join(f"{i+1}. {m}" for i, m in enumerate(self._mensa_names))
            await self._send(
                room_id,
                f"Bitte gib deine Reihenfolge an. Beispiel: `!mensa wahl 2,1,3`\n\nMensen:\n{numbered}",
            )
            return

        msg = await self._vote_manager.record_command_ballot(
            session_id=active["id"],
            user_id=sender,
            display_name=display_name,
            ranking_indices=ranking_indices,
        )
        await self._send(room_id, msg)

    async def _cmd_close_vote(self, room_id: str) -> None:
        active = self._vote_manager.get_active_vote()
        if not active:
            await self._send(room_id, format_no_active_vote())
            return

        # End the native poll if applicable.
        if active.get("poll_event_id"):
            result_msg = await self._vote_manager.close_vote(active["id"])
            await self._matrix.end_poll(room_id, active["poll_event_id"], result_msg)
        else:
            result_msg = await self._vote_manager.close_vote(active["id"])

        await self._send(room_id, result_msg)

    # ── Poll response handler ──────────────────────────────────────────────────

    async def _handle_poll_response(
        self,
        room_id: str,
        event_id: str,
        sender: str,
        content: dict,
        display_name: Optional[str],
    ) -> None:
        active = self._vote_manager.get_active_vote()
        if not active or active["poll_mode"] != "native":
            return

        poll_event_id = active.get("poll_event_id")

        # Verify this response relates to our poll.
        relates = content.get("m.relates_to") or content.get("org.matrix.msc3381.v2.relates_to", {})
        if relates.get("event_id") != poll_event_id:
            return

        # Extract the selected answer ID(s).
        answers = (
            content.get("org.matrix.msc3381.poll.response", {}).get("answers", [])
            or content.get("m.selections", [])
        )
        if not answers:
            return

        voting_method = active.get("voting_method", "borda")

        if voting_method == "approval":
            try:
                approved_indices = [int(a) for a in answers]
            except (ValueError, TypeError):
                log.warning("Ungültige Approval-Poll-Antwort von %s: %r", sender, answers)
                return
            msg = await self._vote_manager.record_approval_native_ballot(
                session_id=active["id"],
                user_id=sender,
                display_name=display_name,
                approved_indices=approved_indices,
            )
        else:
            try:
                option_index = int(answers[0])
            except (ValueError, IndexError, TypeError):
                log.warning("Ungültige Poll-Antwort von %s: %r", sender, answers)
                return
            msg = await self._vote_manager.record_native_ballot(
                session_id=active["id"],
                user_id=sender,
                display_name=display_name,
                option_index=option_index,
            )
        if msg:
            await self._send(room_id, msg)

        # Save the raw poll event.
        self._db.save_poll_event(
            event_id=event_id,
            session_id=active["id"],
            event_type="poll.response",
            sender=sender,
            content_json=json.dumps(content, ensure_ascii=False),
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Suppress noisy third-party loggers.
    logging.getLogger("peewee").setLevel(logging.WARNING)
    logging.getLogger("nio.responses").setLevel(logging.WARNING)


def main() -> None:
    config_path = os.environ.get("MENSA_BOT_CONFIG", "config.yaml")
    if not Path(config_path).exists():
        print(f"Konfigurationsdatei nicht gefunden: {config_path}", file=sys.stderr)
        print("Kopiere config.yaml.example nach config.yaml und passe sie an.", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    setup_logging(config.bot.log_level)

    bot = MensaBot(config)

    loop = asyncio.get_event_loop()

    def _shutdown():
        log.info("Beende Bot …")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    try:
        loop.run_until_complete(bot.run())
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
