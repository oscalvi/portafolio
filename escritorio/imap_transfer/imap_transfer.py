#!/usr/bin/env python3
"""
imap_transfer.py — Copy or move folders (and all their messages) from one
IMAP email account to another.

Runs entirely on your own machine, talking directly to your two mail
servers over IMAP. No third-party services, no external libraries —
just the Python standard library.

Usage:
    python3 imap_transfer.py --config config.json
    python3 imap_transfer.py --config config.json --dry-run
    python3 imap_transfer.py --config config.json --resume-file progress.json

See config.example.json for the configuration format, and README.md for
full instructions (including how to get an "app password" for Gmail /
Outlook, since most providers no longer allow plain account passwords
over IMAP).
"""

import argparse
import imaplib
import email
import json
import os
import sys
import time
import re
from email.utils import parsedate_to_datetime

imaplib._MAXLINE = 10_000_000  # allow large messages/attachments


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def connect(account_cfg):
    host = account_cfg["host"]
    port = account_cfg.get("port", 993)
    use_ssl = account_cfg.get("ssl", True)

    if use_ssl:
        conn = imaplib.IMAP4_SSL(host, port)
    else:
        conn = imaplib.IMAP4(host, port)
        if account_cfg.get("starttls", False):
            conn.starttls()

    conn.login(account_cfg["username"], account_cfg["password"])
    return conn


def decode_folder_name(raw):
    """IMAP folder names are modified UTF-7 encoded; decode for display."""
    try:
        return raw.encode().decode("imap4-utf-7")
    except Exception:
        return raw


def encode_folder_name(name):
    try:
        return name.encode("imap4-utf-7").decode("ascii")
    except Exception:
        return name


LIST_RE = re.compile(r'\((?P<flags>[^)]*)\) "(?P<delim>[^"]*)" (?P<name>.*)')


def list_folders(conn):
    """Return list of (flags, delimiter, decoded_name)."""
    typ, data = conn.list()
    if typ != "OK":
        raise RuntimeError(f"LIST failed: {data}")
    folders = []
    for entry in data:
        if entry is None:
            continue
        line = entry.decode(errors="replace")
        m = LIST_RE.match(line)
        if not m:
            continue
        raw_name = m.group("name").strip()
        if raw_name.startswith('"') and raw_name.endswith('"'):
            raw_name = raw_name[1:-1]
        folders.append((m.group("flags"), m.group("delim"), decode_folder_name(raw_name)))
    return folders


def ensure_folder_exists(conn, folder_name):
    """Create the folder if it doesn't exist yet. Uses STATUS rather than
    SELECT to check, so this never leaves the mailbox "open" on this
    connection - some servers behave unreliably when APPEND is issued
    against a mailbox the same connection currently has selected.
    Returns True if the folder had to be created (didn't already exist),
    False if it was already there."""
    if get_message_count(conn, folder_name) is not None:
        return False
    conn.create(imap_quote(folder_name))
    return True


def imap_quote(name):
    encoded = encode_folder_name(name)
    return f'"{encoded}"'


def get_message_count(conn, folder_name):
    """Actual IMAP message count for a folder via STATUS, which - unlike
    SELECT/EXAMINE - does not open the mailbox on this connection. Safe to
    call right before or after an APPEND to the same folder. Returns None
    if the folder doesn't exist or STATUS isn't supported for it."""
    typ, data = conn.status(imap_quote(folder_name), "(MESSAGES)")
    if typ != "OK" or not data or data[0] is None:
        return None
    match = re.search(rb"MESSAGES\s+(\d+)", data[0])
    if not match:
        return None
    return int(match.group(1))


# ---------------------------------------------------------------------------
# Resume tracking (avoid re-copying messages already transferred)
# ---------------------------------------------------------------------------

def load_progress(path):
    if path and os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_progress(path, progress):
    if not path:
        return
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(progress, f)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Core transfer logic
# ---------------------------------------------------------------------------

def transfer_folder(src_conn, dst_conn, src_folder, dst_folder, mode,
                     dry_run, progress, progress_key, progress_path):
    log(f"Folder: '{src_folder}'  ->  '{dst_folder}'  ({mode}{' [dry-run]' if dry_run else ''})")

    typ, _ = src_conn.select(imap_quote(src_folder), readonly=(mode == "copy"))
    if typ != "OK":
        log(f"  ! could not open source folder '{src_folder}', skipping")
        return

    # A folder's UIDs are only guaranteed stable as long as UIDVALIDITY
    # doesn't change (e.g. the mailbox got recreated). If it changed since
    # our last real run, the old "already sent" UIDs no longer reliably
    # refer to the same messages, so forget them rather than risk skipping
    # messages that are actually new, or - worse - matching the wrong ones.
    uidvalidity_key = progress_key + "::uidvalidity"
    current_uidvalidity = None
    typ_uv, uv_data = src_conn.response("UIDVALIDITY")
    if typ_uv == "UIDVALIDITY" and uv_data and uv_data[0]:
        raw = uv_data[0]
        current_uidvalidity = raw.decode() if isinstance(raw, bytes) else str(raw)

    stored_uidvalidity = progress.get(uidvalidity_key)
    done_uids = set(progress.get(progress_key, []))
    if current_uidvalidity and stored_uidvalidity and stored_uidvalidity != current_uidvalidity:
        log("  ! this folder's UID numbering changed since the last run (mailbox recreated?) "
            "- forgetting previous resume history for it, to stay safe")
        done_uids = set()
    if current_uidvalidity and not dry_run:
        progress[uidvalidity_key] = current_uidvalidity

    if not dry_run:
        created = ensure_folder_exists(dst_conn, dst_folder)
        log(f"  destination folder '{dst_folder}': {'created new (did not exist before)' if created else 'already existed'}")
        before_count = get_message_count(dst_conn, dst_folder)
    else:
        before_count = None

    typ, data = src_conn.uid("search", None, "ALL")
    if typ != "OK":
        log(f"  ! search failed on '{src_folder}', skipping")
        return
    uids = data[0].split()
    total = len(uids)
    log(f"  {total} message(s) found")

    to_delete_uids = []
    transferred = 0
    new_appends_this_run = 0  # only genuinely new appends, excluding already-done skips

    for i, uid in enumerate(uids, 1):
        uid_str = uid.decode()
        if uid_str in done_uids:
            transferred += 1
            if mode == "move":
                to_delete_uids.append(uid)
            continue

        typ, msg_data = src_conn.uid("fetch", uid, "(FLAGS INTERNALDATE RFC822)")
        if typ != "OK" or not msg_data or msg_data[0] is None:
            log(f"  ! failed to fetch UID {uid_str}, skipping message")
            continue

        raw_meta = msg_data[0][0].decode(errors="replace")
        flags = imaplib.ParseFlags(msg_data[0][0])
        flags = tuple(f.decode() if isinstance(f, bytes) else f for f in flags)
        raw_email = msg_data[0][1]

        date_match = re.search(r'INTERNALDATE "([^"]+)"', raw_meta)
        internal_date = None
        if date_match:
            internal_date = imaplib.Internaldate2tuple(
                f'INTERNALDATE "{date_match.group(1)}"'.encode()
            )

        if not dry_run:
            typ, resp = dst_conn.append(
                imap_quote(dst_folder), " ".join(flags), internal_date, raw_email
            )
            resp_text = resp[0].decode(errors="replace") if resp and resp[0] else ""
            if typ != "OK":
                log(f"  ! failed to append UID {uid_str} to destination: {resp_text}")
                continue
            elif i <= 3 or i == total:
                # Show the server's raw reply for a few messages, so an
                # unexpected APPENDUID or warning text is visible.
                log(f"  appended UID {uid_str}: server replied '{resp_text}'")

            # Only a REAL append should ever be remembered as "done" - a
            # preview must never mark messages as transferred, or a real
            # run afterward would wrongly skip re-appending them.
            done_uids.add(uid_str)
            new_appends_this_run += 1
            if mode == "move":
                to_delete_uids.append(uid)

        transferred += 1

        if i % 25 == 0 or i == total:
            log(f"  ...{i}/{total}")
            if not dry_run:
                progress[progress_key] = list(done_uids)
                save_progress(progress_path, progress)

    if not dry_run:
        progress[progress_key] = list(done_uids)
        save_progress(progress_path, progress)

    if mode == "move" and to_delete_uids and not dry_run:
        log(f"  deleting {len(to_delete_uids)} transferred message(s) from source...")
        src_conn.select(imap_quote(src_folder), readonly=False)
        uid_set = b",".join(to_delete_uids)
        src_conn.uid("store", uid_set, "+FLAGS", "(\\Deleted)")
        src_conn.expunge()

    log(f"  done: {transferred}/{total} transferred")

    if not dry_run:
        after_count = _get_count_with_retry(dst_conn, dst_folder, before_count, new_appends_this_run)
        if before_count is not None and after_count is not None:
            log(f"  verified: destination '{dst_folder}' had {before_count} message(s) "
                f"before, now has {after_count} (+{after_count - before_count})")
        else:
            log(f"  ! could not verify destination message count for '{dst_folder}'")


def _get_count_with_retry(dst_conn, dst_folder, before_count, new_appends, attempts=4, delay_seconds=1.5):
    """Re-check the destination message count a few times with a short
    delay and a NOOP in between, in case the server has a brief
    replication/consistency delay between an APPEND succeeding and a
    STATUS count reflecting it. Gives up and returns the last value seen
    if it never catches up."""
    expected_min = (before_count + new_appends) if (before_count is not None and new_appends) else None
    last_count = get_message_count(dst_conn, dst_folder)
    for attempt in range(attempts - 1):
        if expected_min is None or (last_count is not None and last_count >= expected_min):
            break
        time.sleep(delay_seconds)
        try:
            dst_conn.noop()
        except Exception:
            pass
        last_count = get_message_count(dst_conn, dst_folder)
    return last_count


def resolve_folder_list(cfg, src_conn):
    """
    Build the list of (src_folder, dst_folder) pairs to process.
    Supports explicit list in config, or "ALL" to mirror every folder.
    """
    folders_cfg = cfg["folders"]
    if folders_cfg == "ALL":
        all_folders = list_folders(src_conn)
        exclude = set(cfg.get("exclude_folders", []))
        pairs = []
        for flags, _delim, name in all_folders:
            if r"\Noselect" in flags:
                continue
            if name in exclude:
                continue
            pairs.append((name, name))
        return pairs
    else:
        pairs = []
        for item in folders_cfg:
            if isinstance(item, str):
                pairs.append((item, item))
            else:
                pairs.append((item["src"], item.get("dst", item["src"])))
        return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually copy/move anything, just report")
    parser.add_argument("--resume-file", default=None, help="Path to a progress file, so a rerun skips already-transferred messages")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg = json.load(f)

    mode = cfg.get("mode", "copy")
    if mode not in ("copy", "move"):
        sys.exit("config 'mode' must be 'copy' or 'move'")

    resume_path = args.resume_file or cfg.get("resume_file")
    progress = load_progress(resume_path)

    log("Connecting to source account...")
    src_conn = connect(cfg["source"])
    log("Connecting to destination account...")
    dst_conn = connect(cfg["destination"])

    try:
        pairs = resolve_folder_list(cfg, src_conn)
        log(f"{len(pairs)} folder(s) to process")
        for src_folder, dst_folder in pairs:
            key = f"{cfg['source']['username']}::{src_folder}::{cfg['destination']['username']}::{dst_folder}"
            transfer_folder(
                src_conn, dst_conn, src_folder, dst_folder, mode,
                args.dry_run, progress, key, resume_path,
            )
    finally:
        try:
            src_conn.logout()
        except Exception:
            pass
        try:
            dst_conn.logout()
        except Exception:
            pass

    log("All done.")


if __name__ == "__main__":
    main()
