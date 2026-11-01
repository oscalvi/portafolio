# Email Hub

Move the mail out of an email account you want to abandon into a new one.

One of three versions of the same idea in this portfolio, each built with a
different Python stack to practice it:

| App | Stack |
|---|---|
| IMAP Transfer | Desktop - Python + Tkinter |
| EmailMover | Web - Python + Flask |
| **Email Hub** (this one) | Web - Python + **Django** (ORM, admin, migrations, background jobs) |

(Its first working name was *mailhop*; the background-worker cluster keeps that name internally.)

- **Copy, never move.** The old mailbox is opened read-only. Nothing is ever
  deleted anywhere - closing the old account is the user's responsibility.
- **Move everything, or pick folders.**
- **Resumable & de-duplicated.** Messages are matched by `Message-ID`, so
  re-running a job after a failure (or to catch new mail) never makes duplicates.
- **No infrastructure.** SQLite for storage, the Django ORM as the task queue.
  No Redis, no Docker.

## Stack

| Piece | Choice |
|---|---|
| Web app + UI | Django 5 + server-rendered templates + htmx (live progress) |
| IMAP engine | [IMAPClient](https://imapclient.readthedocs.io) |
| Background jobs | [django-q2](https://django-q2.readthedocs.io) (ORM broker) |
| Database | SQLite |
| Password-at-rest | Fernet (`cryptography`) |

## Run it

From the portfolio: **Web apps -> Email Hub -> Open**, or click its bubble.

By hand, one command does everything:

```powershell
cd "P:\Projects\PY Training\proyectos\emailhub"
py iniciar.py
```

`iniciar.py` creates the virtual environment and installs `requirements.txt`
the first time, creates `.env` with a new encryption key if it is missing,
updates the database, and starts the background worker and the web server
together. Open http://127.0.0.1:8000/ and click **New migration**. Closing the
window stops both.

### Manual setup (what iniciar.py does for you)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# generate the encryption key and paste it into .env as FIELD_ENCRYPTION_KEY
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser   # optional, for /admin

# terminal 1 - web app
.\.venv\Scripts\python.exe manage.py runserver
# terminal 2 - background worker
.\.venv\Scripts\python.exe manage.py qcluster
```

Prefer no worker? Set `Q_SYNC=True` in `.env` to run migrations inline in
the web process (fine for small mailboxes). Or run a job from the CLI:
`.\.venv\Scripts\python.exe manage.py run_job <job_id>`

## Provider notes

| Provider | Host / port | Auth |
|---|---|---|
| Gmail | `imap.gmail.com:993` | Enable IMAP + 2FA, then an **App Password** |
| Outlook / M365 | `outlook.office365.com:993` | App password (basic-auth IMAP may be disabled on some tenants - OAuth is the next step, see below) |
| Yahoo | `imap.mail.yahoo.com:993` | App password |
| iCloud | `imap.mail.me.com:993` | App password |
| Fastmail | `imap.fastmail.com:993` | App password |

## Not built yet (planned)

1. **User accounts / login.** Right now anyone who can reach the server can use
   it. Run it only on localhost until real auth is added. `/admin` is available
   for inspection if you create a superuser.
2. **OAuth** for Gmail (Gmail API) and Microsoft (Graph) instead of app
   passwords. Needed once Microsoft basic-auth IMAP is off, and nicer UX.
   Warning: Google requires a CASA security assessment for production Gmail
   scopes past 100 users.
3. **"We create the new mailbox for you"** - integrate one provider mailbox API
   (Migadu / Purelymail / Fastmail) for the hybrid provisioning option. Today
   the user brings a mailbox they already made.
4. **Label preservation** for Gmail (labels aren't IMAP folders 1:1).
5. Per-message retry list for the `failed` count.

## Project layout

```
iniciar.py              one-command launcher (venv, .env, migrate, worker + server)
config/                 Django project (settings, urls)
migration/
  models.py             MailAccount, MigrationJob, FolderProgress
  views.py              dashboard, new migration wizard, job detail/progress
  tasks.py              run_migration_task - the django-q2 job
  forms.py              IMAP connection form
  crypto.py             Fernet encrypt/decrypt for stored app passwords
  imap_engine/
    client.py           connect / verify_connection
    folders.py          special-use detection, source->dest path mapping
    migrate.py          the copy engine (read-only source, dedupe, resume)
  management/commands/
    run_job.py          run a job in the foreground
  templates/ static/    server-rendered UI + htmx polling
```
