"""IMAP -> IMAP copy engine.

Design rules:
  * The source mailbox is opened read-only and never modified. Nothing is
    deleted anywhere - closing the old account is the user's job.
  * Messages are de-duplicated by RFC 822 Message-ID, so re-running a job
    (after a failure or to catch new mail) does not create duplicates.
  * Progress is reported per folder and per batch via callbacks, so the
    caller can checkpoint to a database and resume.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Callable

from imapclient import IMAPClient

from .client import ImapCreds, connect
from .folders import map_dest_path, should_skip

BATCH = 200
_UNSETTABLE_FLAGS = {b"\\Recent", b"\\*"}


@dataclass
class FolderPlan:
    source_path: str
    dest_path: str
    selected: bool = True


@dataclass
class Callbacks:
    on_folder_start: Callable[[str, str, int], None] = lambda *a: None
    on_progress: Callable[[str, int, int, int, int], None] = lambda *a: None
    on_folder_done: Callable[[str, int, int, int], None] = lambda *a: None
    should_cancel: Callable[[], bool] = lambda: False


def _decode(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    return str(value)


def _server_delimiter(client: IMAPClient) -> str:
    for _flags, delim, _name in client.list_folders():
        if delim:
            return _decode(delim)
    return "/"


def list_folder_plans(source: ImapCreds, dest_delim: str = "/") -> list[FolderPlan]:
    """Connect to the source and return the folders eligible for migration."""
    client = connect(source)
    try:
        src_delim = _server_delimiter(client)
        plans: list[FolderPlan] = []
        for flags, delim, name in client.list_folders():
            if should_skip(flags, name):
                continue
            d = _decode(delim) or src_delim
            plans.append(FolderPlan(name, map_dest_path(flags, name, d, dest_delim)))
        return plans
    finally:
        _safe_logout(client)


def _message_ids(client: IMAPClient, folder: str) -> set[bytes]:
    """Message-IDs already present in a destination folder (for de-dup)."""
    seen: set[bytes] = set()
    try:
        info = client.select_folder(folder, readonly=True)
    except Exception:  # noqa: BLE001 - folder may not exist yet
        return seen
    if not info.get(b"EXISTS"):
        return seen
    uids = client.search("ALL")
    for i in range(0, len(uids), BATCH):
        resp = client.fetch(uids[i : i + BATCH], ["ENVELOPE"])
        for data in resp.values():
            env = data.get(b"ENVELOPE")
            if env is not None and getattr(env, "message_id", None):
                seen.add(env.message_id)
    return seen


def _clean_flags(raw) -> tuple:
    return tuple(f for f in (raw or ()) if f not in _UNSETTABLE_FLAGS)


def _as_utc(value):
    if isinstance(value, _dt.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


def run_migration(
    source: ImapCreds,
    dest: ImapCreds,
    plans: list[FolderPlan],
    checkpoints: dict[str, int] | None = None,
    cb: Callbacks | None = None,
) -> dict:
    cb = cb or Callbacks()
    checkpoints = checkpoints or {}
    totals = {"copied": 0, "skipped": 0, "failed": 0, "folders": 0}

    src = connect(source)
    dst = connect(dest)
    try:
        dest_delim = _server_delimiter(dst)

        for plan in plans:
            if not plan.selected:
                continue
            if cb.should_cancel():
                break
            totals["folders"] += 1

            dest_path = plan.dest_path
            try:
                if not dst.folder_exists(dest_path):
                    dst.create_folder(dest_path)
            except Exception:  # noqa: BLE001 - race / already exists
                pass

            since = int(checkpoints.get(plan.source_path, 0) or 0)
            copied = skipped = failed = 0
            last_uid = since

            info = src.select_folder(plan.source_path, readonly=True)
            total = int(info.get(b"EXISTS", 0) or 0)
            cb.on_folder_start(plan.source_path, dest_path, total)

            seen = _message_ids(dst, dest_path)

            src.select_folder(plan.source_path, readonly=True)
            if since > 0:
                uids = [u for u in src.search(["UID", f"{since + 1}:*"]) if u > since]
            else:
                uids = src.search("ALL")
            uids.sort()

            for i in range(0, len(uids), BATCH):
                if cb.should_cancel():
                    break
                chunk = uids[i : i + BATCH]
                resp = src.fetch(
                    chunk, ["BODY.PEEK[]", "FLAGS", "INTERNALDATE", "ENVELOPE"]
                )
                for uid in chunk:
                    data = resp.get(uid)
                    if not data or data.get(b"BODY[]") is None:
                        failed += 1
                        last_uid = uid
                        continue
                    env = data.get(b"ENVELOPE")
                    mid = getattr(env, "message_id", None) if env is not None else None
                    if mid and mid in seen:
                        skipped += 1
                        last_uid = uid
                        continue
                    try:
                        dst.append(
                            dest_path,
                            data[b"BODY[]"],
                            flags=_clean_flags(data.get(b"FLAGS")),
                            msg_time=_as_utc(data.get(b"INTERNALDATE")),
                        )
                        copied += 1
                        if mid:
                            seen.add(mid)
                    except Exception:  # noqa: BLE001 - keep going, count it
                        failed += 1
                    last_uid = uid
                cb.on_progress(plan.source_path, last_uid, copied, skipped, failed)

            totals["copied"] += copied
            totals["skipped"] += skipped
            totals["failed"] += failed
            cb.on_folder_done(plan.source_path, copied, skipped, failed)

        return totals
    finally:
        _safe_logout(src)
        _safe_logout(dst)


def _safe_logout(client: IMAPClient) -> None:
    try:
        client.logout()
    except Exception:  # noqa: BLE001
        pass
