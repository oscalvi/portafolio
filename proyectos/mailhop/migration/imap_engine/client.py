from __future__ import annotations

from dataclasses import dataclass

from imapclient import IMAPClient

DEFAULT_TIMEOUT = 60


@dataclass(frozen=True)
class ImapCreds:
    host: str
    port: int
    use_ssl: bool
    username: str
    password: str


def connect(creds: ImapCreds) -> IMAPClient:
    """Open an authenticated IMAP connection. Caller is responsible for logout()."""
    client = IMAPClient(
        creds.host,
        port=creds.port,
        ssl=creds.use_ssl,
        timeout=DEFAULT_TIMEOUT,
    )
    client.login(creds.username, creds.password)
    return client


def verify_connection(creds: ImapCreds) -> tuple[bool, str]:
    """Return (ok, error_message). Never raises."""
    try:
        client = connect(creds)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
        return False, str(exc)
    try:
        client.list_folders()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    finally:
        try:
            client.logout()
        except Exception:
            pass
