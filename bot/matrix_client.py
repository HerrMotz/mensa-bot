"""Matrix client wrapper with E2EE support via matrix-nio.

Uses AsyncClient with SqliteStore for device key persistence.
Supports both password login (first run) and stored access token (subsequent runs).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Coroutine, Optional

import nio

log = logging.getLogger(__name__)

# Stable and unstable event type names for MSC3381 polls.
_POLL_START_TYPES = {"m.poll.start", "org.matrix.msc3381.poll.start"}
_POLL_RESPONSE_TYPES = {"m.poll.response", "org.matrix.msc3381.poll.response"}
_POLL_END_TYPES = {"m.poll.end", "org.matrix.msc3381.poll.end"}


class MatrixBot:
    def __init__(
        self,
        homeserver: str,
        username: str,
        store_path: str,
        device_name: str = "MensaBot",
        password: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> None:
        self._homeserver = homeserver
        self._username = username
        self._password = password
        self._access_token = access_token
        self._device_name = device_name
        self._store_path = store_path

        Path(store_path).mkdir(parents=True, exist_ok=True)

        config = nio.AsyncClientConfig(
            max_limit_exceeded=0,
            max_timeouts=0,
            store_sync_tokens=True,
            encryption_enabled=True,
        )
        self._client = nio.AsyncClient(
            homeserver=homeserver,
            user=username,
            store_path=store_path,
            config=config,
        )
        self._client.add_event_callback(self._on_message, nio.RoomMessageText)
        self._client.add_event_callback(self._on_encrypted, nio.MegolmEvent)
        self._client.add_to_device_callback(self._on_key_verification, nio.KeyVerificationEvent)

        # Callbacks registered by the application layer.
        self._on_command_cb: Optional[Callable[[str, str, str, Optional[str]], Coroutine]] = None
        self._on_poll_response_cb: Optional[Callable[[str, str, str, dict, Optional[str]], Coroutine]] = None

        self._room_id: Optional[str] = None
        self._syncing = False

    # ── Setup & lifecycle ────────────────────────────────────────────────────

    def set_room_id(self, room_id: str) -> None:
        self._room_id = room_id

    def on_command(self, cb: Callable[[str, str, str, Optional[str]], Coroutine]) -> None:
        """Register callback: (room_id, sender, message_body, display_name) → None."""
        self._on_command_cb = cb

    def on_poll_response(
        self, cb: Callable[[str, str, str, dict, Optional[str]], Coroutine]
    ) -> None:
        """Register callback: (room_id, event_id, sender, content, display_name) → None."""
        self._on_poll_response_cb = cb

    async def login(self) -> None:
        """Login with password or restore a prior session.

        restore_login() is used whenever we have (user_id, device_id, access_token)
        because it calls load_store(), which initialises the E2EE key store for
        the specific device.  Raw attribute-setting does not.
        """
        token_file = Path(self._store_path) / "access_token.txt"

        # Token file written after successful password login — most common restart path.
        if token_file.exists():
            parts = token_file.read_text().strip().split("\n")
            if len(parts) >= 3:
                # Prefer config access_token (rotated externally) over the saved one.
                access_token = self._access_token or parts[0]
                device_id = parts[1]
                user_id = parts[2]
                self._client.restore_login(user_id, device_id, access_token)
                log.info("Session wiederhergestellt für %s (device: %s)", user_id, device_id)
                return

        # Config access_token without a prior token file: fetch device_id via whoami.
        if self._access_token:
            self._client.access_token = self._access_token
            self._client.user_id = self._username
            try:
                whoami = await self._client.whoami()
                if hasattr(whoami, "device_id") and whoami.device_id:
                    self._client.device_id = whoami.device_id
            except Exception as exc:
                log.warning("whoami() fehlgeschlagen: %s — E2EE-Store wird nicht geladen.", exc)

            if self._client.device_id:
                self._client.restore_login(
                    self._username, self._client.device_id, self._access_token
                )
                token_file.write_text(
                    f"{self._access_token}\n{self._client.device_id}\n{self._username}"
                )
            else:
                await self._client.keys_upload()
            log.info("Mit gespeichertem Access-Token eingeloggt.")
            return

        if not self._password:
            raise RuntimeError("Kein Passwort und kein Access-Token verfügbar.")

        resp = await self._client.login(self._password, device_name=self._device_name)
        if isinstance(resp, nio.LoginError):
            raise RuntimeError(f"Matrix-Login fehlgeschlagen: {resp.message}")

        token_file.write_text(
            f"{self._client.access_token}\n{self._client.device_id}\n{self._client.user_id}"
        )
        log.info("Erfolgreich eingeloggt als %s (device: %s)", self._client.user_id, self._client.device_id)
        await self._client.keys_upload()

    async def join_room(self, room_id: str) -> None:
        resp = await self._client.join(room_id)
        if isinstance(resp, nio.JoinError):
            raise RuntimeError(f"Konnte Raum nicht beitreten: {resp.message}")
        log.info("Raum beigetreten: %s", room_id)

    async def sync_forever(self) -> None:
        """Run the sync loop."""
        self._syncing = True
        log.info("Starte Matrix-Sync-Schleife.")
        try:
            await self._client.sync_forever(
                timeout=30000,
                full_state=True,
                since=self._client.next_batch,
            )
        finally:
            self._syncing = False

    async def close(self) -> None:
        await self._client.close()

    # ── Sending ──────────────────────────────────────────────────────────────

    async def send_message(self, room_id: str, text: str) -> Optional[str]:
        """Send a plain text message (Markdown). Returns event ID or None."""
        # Convert simple Markdown to minimal HTML for Matrix.
        html = _md_to_html(text)
        content = {
            "msgtype": "m.text",
            "body": _strip_markdown(text),
            "format": "org.matrix.custom.html",
            "formatted_body": html,
        }
        resp = await self._client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=True,
        )
        if isinstance(resp, nio.RoomSendError):
            log.error("Fehler beim Senden der Nachricht: %s", resp.message)
            return None
        return resp.event_id

    async def send_poll(self, room_id: str, poll_content: dict) -> Optional[str]:
        """Send a native Matrix poll (MSC3381). Returns the poll event ID."""
        resp = await self._client.room_send(
            room_id=room_id,
            message_type="org.matrix.msc3381.poll.start",
            content=poll_content,
            ignore_unverified_devices=True,
        )
        if isinstance(resp, nio.RoomSendError):
            log.error("Fehler beim Senden des Polls: %s", resp.message)
            return None
        return resp.event_id

    async def end_poll(self, room_id: str, poll_event_id: str, summary: str) -> None:
        """Send a poll end event."""
        content = {
            "m.relates_to": {
                "rel_type": "m.reference",
                "event_id": poll_event_id,
            },
            "org.matrix.msc3381.poll.end": {},
            "org.matrix.msc1767.text": summary,
            "body": summary,
        }
        await self._client.room_send(
            room_id=room_id,
            message_type="org.matrix.msc3381.poll.end",
            content=content,
            ignore_unverified_devices=True,
        )

    async def get_display_name(self, user_id: str) -> Optional[str]:
        """Fetch the display name for a Matrix user ID."""
        try:
            resp = await self._client.get_displayname(user_id)
            if isinstance(resp, nio.ProfileGetDisplayNameResponse):
                return resp.displayname or None
        except Exception as exc:
            log.debug("Display-Name-Fehler für %s: %s", user_id, exc)
        return None

    # ── Event callbacks ──────────────────────────────────────────────────────

    async def _on_message(self, room: nio.MatrixRoom, event: nio.RoomMessageText) -> None:
        if self._room_id and room.room_id != self._room_id:
            return
        if event.sender == self._client.user_id:
            return  # Ignore own messages.

        display_name = room.user_name(event.sender) or event.sender
        if self._on_command_cb:
            await self._on_command_cb(room.room_id, event.sender, event.body, display_name)

    async def _on_encrypted(self, room: nio.MatrixRoom, event: nio.MegolmEvent) -> None:
        """Handle undecryptable events — request missing keys."""
        log.debug("Verschlüsselte Nachricht konnte nicht entschlüsselt werden von %s.", event.sender)
        # matrix-nio handles key requests automatically with the store.

    async def _on_key_verification(self, event: nio.KeyVerificationEvent) -> None:
        log.debug("Schlüsselverifizierungs-Ereignis: %s", type(event).__name__)

    async def handle_to_device_events(self) -> None:
        """Process any pending to-device events (key sharing, verification)."""
        pass  # matrix-nio handles this during sync automatically.

    # ── Poll response handling (called from sync callback) ────────────────────

    def register_sync_callback(self) -> None:
        """Register a raw sync callback to capture poll response events."""
        self._client.add_response_callback(self._on_sync_response, nio.SyncResponse)

    async def _on_sync_response(self, response: nio.SyncResponse) -> None:
        """Inspect raw sync response for poll response events in the target room."""
        if not self._room_id or not self._on_poll_response_cb:
            return

        room_events = response.rooms.join.get(self._room_id)
        if not room_events:
            return

        for event in room_events.timeline.events:
            if isinstance(event, nio.UnknownEvent):
                if event.type in _POLL_RESPONSE_TYPES:
                    room = self._client.rooms.get(self._room_id)
                    display_name = None
                    if room:
                        display_name = room.user_name(event.sender)
                    await self._on_poll_response_cb(
                        self._room_id,
                        event.event_id,
                        event.sender,
                        event.source.get("content", {}),
                        display_name,
                    )


# ── Markdown helpers ──────────────────────────────────────────────────────────

def _md_to_html(text: str) -> str:
    """Convert minimal Markdown to HTML for Matrix."""
    import re

    html = text
    # Bold: **text**
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    # Italic: _text_
    html = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", html)
    html = re.sub(r"_(.+?)_", r"<em>\1</em>", html)
    # Code: `text`
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    # Line breaks.
    html = html.replace("\n", "<br/>")
    return html


def _strip_markdown(text: str) -> str:
    """Remove Markdown formatting for the plain-text fallback body."""
    import re

    t = text
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"_(.+?)_", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return t
