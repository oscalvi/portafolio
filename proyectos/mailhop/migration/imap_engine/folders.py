"""Folder classification and source -> destination path mapping."""
from __future__ import annotations

# RFC 6154 special-use attributes, in priority order.
_KNOWN_SPECIAL_USE = [
    "\\Sent",
    "\\Drafts",
    "\\Junk",
    "\\Trash",
    "\\Archive",
    "\\All",
    "\\Flagged",
    "\\Important",
]

# Special-use folders that map to a conventional plain name on the destination.
_STANDARD_NAME = {
    "\\Sent": "Sent",
    "\\Drafts": "Drafts",
    "\\Junk": "Junk",
    "\\Trash": "Trash",
    "\\Archive": "Archive",
}

# Virtual / duplicate views we never copy (Gmail "All Mail", "Starred",
# "Important" would each re-copy messages that already live in real folders).
_SKIP_SPECIAL_USE = {"\\All", "\\Flagged", "\\Important"}


def flag_strings(flags) -> set[str]:
    out: set[str] = set()
    for f in flags or ():
        out.add(f.decode() if isinstance(f, (bytes, bytearray)) else str(f))
    return out


def special_use(flags) -> str | None:
    fs = flag_strings(flags)
    for su in _KNOWN_SPECIAL_USE:
        if su in fs:
            return su
    return None


def should_skip(flags, name: str) -> bool:
    fs = flag_strings(flags)
    if "\\Noselect" in fs or "\\NonExistent" in fs:
        return True
    if special_use(flags) in _SKIP_SPECIAL_USE:
        return True
    # Gmail's container folder, not selectable and holds nothing.
    if name == "[Gmail]" or name == "[Google Mail]":
        return True
    return False


def map_dest_path(flags, name: str, src_delim: str, dest_delim: str) -> str:
    if name.upper() == "INBOX":
        return "INBOX"
    su = special_use(flags)
    if su in _STANDARD_NAME:
        return _STANDARD_NAME[su]
    src_delim = src_delim or "/"
    dest_delim = dest_delim or "/"
    parts = [p for p in name.split(src_delim) if p and p not in ("[Gmail]", "[Google Mail]")]
    if not parts:
        return name
    return dest_delim.join(parts)
