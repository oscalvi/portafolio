# Portafolio — Small everyday apps, designed by talking

**Oscar Alvarez Villarreal** · Computer engineer · 45 years in technology, from punch cards to AI

## What this portfolio shows

Small, simple applications for everyday life: the tools a person or a small business needs, but never gets because custom software looked expensive and complicated.

The idea is simple. You **describe out loud** what you need. A **virtual systems analyst** interprets your idea as well as it can, asks a few questions, and builds a small application for you that:

- **runs on your own computer**, with no certifications, permits, servers or subscriptions;
- **installs itself**: a one-click launcher (`.bat`) sets up everything the app needs, such as Python and its libraries, so you never have to deal with the technical side of the computer.

*You speak, AI does the work, and you decide.*

## How it works

1. **Describe.** Speak, type, or upload a document with your idea.
2. **Interpret.** The analyst identifies the kind of app (inventory, appointments, sales, students, jobs…) and asks five sizing questions: users, volume, where it is used, budget and current tools.
3. **Design.** It recommends where to keep the data, from a simple file to SQL Server or Oracle, and proposes the tables.
4. **Build.** It creates the database and the tables for you.
5. **Install.** A launcher (`.bat`) checks for Python, installs what is missing and opens the app. Working today in this portfolio and in IMAP Transfer, EmailMover and Document Merger; next, in the apps the designer generates.

## Using the app — a guided tour

The page is organized so a non-technical user always knows the next step. The menu at the top has **Home**, **Desktop**, **Web** and **Databases**, plus **❓ Help** and the **EN | ES** language switch.

| Where | What you do there | How it guides you |
| --- | --- | --- |
| **Home** | Pick one of four areas, or click an app on the ribbons at the bottom. | Four large buttons; ribbons show what exists and what you can create. |
| **Virtual application designer** | Describe your idea by voice, text or document; answer five questions; accept the proposal. | Numbered steps across the top (Need → Proposal → Type → Connection → Tables → Fields); the analyst speaks and listens. |
| **Database administration** | Create or connect a database, then create tables, fields and keys. | The recommended engine is marked ★; missing libraries are named with the exact install command. |
| **Web apps** | Open the Employer finder (search jobs, save them, upload your resume, tailor it, apply and practice the interview) or EmailMover. | A sub-menu (Search · Saved · My resume · Settings) and three numbered steps on each application. EmailMover starts its own server and opens in a new tab. |
| **Desktop apps** | Open the Tkinter apps: Customers, Weather, IMAP Transfer and Document Merger. | One «Open» button per app; the window comes to the front. |

### Ask the help assistant

Every page has a **❓ Help** button. Type or say what you want to do ("how do I create a table?", "how do I send my application?") and the assistant answers with the exact steps and a button that takes you to the right page. It suggests the topics that matter on the page you are on, and it can read the answer aloud.

- **Without AI**, it matches your words against the built-in user guide (`ayuda.json`), in English or Spanish.
- **With the Claude API turned on** in Settings, it understands free-form questions — but it may only answer from that same guide, so it never invents buttons or features.
- It **only explains**: it never clicks, sends or changes anything for you.

## Apps in this repository

| App | What it does | Type |
| --- | --- | --- |
| **Virtual application designer** | The analyst above: voice, text or document in; app type, sizing, database and tables out. | Web (Flask) |
| **Database administration** | Create or connect to a database and design tables, primary and foreign keys from the browser. | Web (Flask) |
| **Employer finder** | Searches trusted job boards at once (Remotive, Jobicy, Himalayas, Remote OK, We Work Remotely, The Muse and, with a free key, Adzuna) plus the career pages of the companies you follow (Greenhouse, Lever, Ashby, Workable), shows a market overview (sources, most requested skills, companies, contract types, salaries), opens Dice, Monster, Indeed and LinkedIn with your search and lets you import any posting; scores each posting and flags possible fraud; tailors your resume without inventing experience and drafts the application email. A **virtual interview** coach builds a technical and behavioral interview for each saved job (in the style of AI interviewers such as Mercor and Alignerr), asks the questions out loud, listens to your spoken answers in the browser, asks follow-ups and scores each answer (STAR structure, key points, pace, filler words). | Web (Flask) |
| **EmailMover** | Migrates email between two accounts in the browser, with live progress. A generic job manager (`BaseWorker` → `IMAPMigrationWorker`) runs long tasks in the background; passwords live only in memory, never on disk. | Web (Flask) |
| **IMAP Transfer** | Copies or moves email folders between two accounts (Gmail, Outlook, Yahoo, iCloud…): provider presets, connection test, preview before changing anything, and resume after a dropped connection without duplicates. Python standard library only. | Desktop (Tkinter) + command line |
| **Document Merger** | Joins PDF, Word and text files into one PDF, with a separator page per document, a progress bar and Explorer opening on the result. | Desktop (Tkinter) |
| **Customers · Weather** | Customer entry and a 5-day weather forecast. | Desktop (Tkinter) |

EmailMover, IMAP Transfer and Document Merger were designed by the author and coded with AI. Each ships with a `.bat` launcher that checks for Python and installs what is missing.

## Structure

```
comun/                  Shared generic classes
  basedatos.py            One data interface: SQL Server, Oracle, MySQL, SQLite, Access, JSON, CSV, Excel
  idiomas.py              English/Spanish by browser language
  ventanas.py             Tkinter window base
escritorio/             Desktop apps
  clientes/  clima/
  imap_transfer/          IMAP Transfer (Tkinter + command line)
  document_merger/        Document Merger: PDF + Word + text into one PDF
web/
  oficina_virtual/        Flask app: designer, databases, employer finder, help assistant
  emailmover/             EmailMover (Flask)
```

## Design highlights

- **One data interface, many engines.** Changing the engine means editing `bd.json`, not the code.
- **Safety rules built in.** Update and delete always require the record ID; names are validated against SQL injection; `with datos.transaccion():` saves all or nothing.
- **Catalogs, not code.** The Desktop and Web pages read their apps from `escritorio.json` and `aplicaciones_web.json`; adding an app means adding one entry.
- **Bilingual.** English by default; Spanish when the visitor's browser asks for it.
- **Private data stays private.** Credentials, resumes, email settings and local databases never leave the user's computer.

## Run it

On Windows, double-click **`Start Portafolio.bat`** once. It checks and installs everything the apps need (Python, the libraries, Node.js and Google Chrome), starts the app, opens it in Chrome and leaves a **Portafolio** icon on your Desktop. From then on, just double-click that icon: it opens the portfolio directly, without checking again. Close the server window to stop it.

By hand, on any system:

```
pip install -r requirements.txt -r escritorio/document_merger/requirements.txt
cd web/oficina_virtual
python app.py
```

Then open http://localhost:5000.

## Coming next

A one-click launcher for the apps the designer generates; a small Django app; small apps in C#, VB.NET and C++; a voice-first virtual assistant for independents (email, purchase orders, reminders); and a pandas analysis of what users complain about in popular business apps.

> Developed with AI assistance (Claude). Design, direction and review by the author.

---

*Resumen en español:* aplicaciones pequeñas y sencillas del diario vivir. Usted describe de viva voz lo que necesita; un analista de sistemas virtual interpreta su idea y le construye una aplicación que funciona en su propio computador, sin certificaciones ni permisos, y que se instala sola con un instalador de un clic (ya funciona en este portafolio y en IMAP Transfer, EmailMover y Document Merger). Cada página tiene un asistente de ayuda que explica, por texto o por voz, cómo hacer lo que usted quiere, sin que usted tenga que lidiar con la parte técnica.
