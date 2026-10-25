# IMAP Folder Transfer

Copy or move folders (with all their messages) from one email account to
another over IMAP. Runs entirely on your own computer and connects
directly to your two mail servers — no third-party service ever sees
your credentials or your mail. Uses only Python's standard library plus
Tkinter (both included with a normal Python install — no extra packages
to install).

## The easy way: point-and-click setup window

If you installed this using `install.bat`, everything below is already
done for you — there's a "IMAP Transfer" shortcut on your Desktop.
Double-click it and you get a window with:

- Dropdowns for your email provider (Gmail, Outlook, Yahoo, iCloud, or
  custom) that fill in the server details for you
- Simple boxes for your email address and app password
- A "Test connections" button to check your details work before doing
  anything
- A "Load folder list from old account" button so you can tick the
  exact folders you want, instead of typing folder names
- "Preview" to see what would happen with no changes made, and "Start
  transfer" (with a confirmation popup) when you're ready
- A live status log at the bottom

No JSON editing and no command line needed. The rest of this README is
for anyone who prefers the command-line / config-file version instead.

## 1. Requirements

- Python 3.8+
- IMAP access enabled on both accounts (usually on by default; Gmail
  requires you to turn it on under Settings → Forwarding and POP/IMAP)
- An **app password** for each account if it uses 2-factor auth (almost
  always required for Gmail and Outlook/Microsoft 365 now — your normal
  login password will not work):
  - **Gmail**: Google Account → Security → 2-Step Verification → App
    passwords → generate one for "Mail"
  - **Outlook/Microsoft 365**: account security settings → App
    passwords (or, if your org enforces modern auth only, you may need
    to enable IMAP basic auth / use a mail client app password from
    admin settings)
  - **Other providers**: check their IMAP/app-password docs; the
    common IMAP hosts are listed below

  | Provider | IMAP host | Port |
  |---|---|---|
  | Gmail | imap.gmail.com | 993 |
  | Outlook / Microsoft 365 | outlook.office365.com | 993 |
  | Yahoo | imap.mail.yahoo.com | 993 |
  | iCloud | imap.mail.me.com | 993 |
  | Fastmail | imap.fastmail.com | 993 |

## 2. Configure

Copy `config.example.json` to `config.json` and fill in your details:

```bash
cp config.example.json config.json
```

Key fields:
- `mode`: `"copy"` (leave originals in place) or `"move"` (delete from
  source after a confirmed successful transfer)
- `source` / `destination`: host, port, username, password for each
  account
- `folders`: either
  - a list of folders to transfer, each as `{"src": "...", "dst": "..."}`
    (or just a plain string if the name should stay the same), or
  - the string `"ALL"` to mirror every folder, with an optional
    `exclude_folders` list (e.g. Trash/Spam) to skip

Run this first to see the exact folder names on the source account
(IMAP folder names are case- and character-sensitive):

```bash
python3 -c "
import json, imap_transfer as t
cfg = json.load(open('config.json'))
conn = t.connect(cfg['source'])
for flags, delim, name in t.list_folders(conn):
    print(name)
"
```

## 3. Do a dry run first

```bash
python3 imap_transfer.py --config config.json --dry-run
```

This connects to both accounts and reports what *would* happen —
message counts per folder — without copying or deleting anything.

## 4. Run it for real

```bash
python3 imap_transfer.py --config config.json --resume-file progress.json
```

The `--resume-file` is optional but recommended: if the connection
drops partway through (large mailboxes, spotty network), rerunning
the exact same command will skip messages already transferred instead
of duplicating them.

## Notes on safety

- **`move` mode only deletes from the source after a successful append
  to the destination**, and only for messages actually confirmed
  transferred in that run.
- Test with `mode: "copy"` first, confirm everything looks right in
  the destination account, and only switch to `"move"` once you trust
  the setup.
- Large mailboxes with big attachments can take a long time and may
  hit provider rate limits (Gmail in particular throttles IMAP after
  heavy use) — if a run gets disconnected, just rerun the same
  command; the resume file prevents duplicates.
- This does not touch labels/categories specific to a provider (e.g.
  Gmail labels beyond folder structure) — only standard IMAP folders,
  flags (read/unread, flagged, answered, draft), and dates.
