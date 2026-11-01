# EmailMover

Move or copy email folders between two IMAP accounts (Gmail, Yahoo, Outlook,
iCloud, and most others), through a simple browser interface running on your
own computer. Nothing is sent to any third-party service, and your
credentials are never saved to disk - they live only in memory for the
duration of one migration.

## Starting EmailMover

Use the "EmailMover" shortcut on your Desktop or in the Start Menu. It will:

1. Check that Python 3 is installed.
2. Install the one small package EmailMover needs (Flask) the first time
   you run it - this requires an internet connection, but only happens once.
3. Start the local server and open http://localhost:5000 in your browser.

Leave the "EmailMover Server" window open while you use the app; closing it
stops the server. Closing your browser tab does not stop the server - use
the server window (or just close it) when you're done.

## If Python isn't found

EmailMover needs Python 3 to run its local server. If the launcher tells you
Python wasn't found, install it from https://www.python.org/downloads/ -
be sure to tick "Add python.exe to PATH" during setup - then run the
EmailMover shortcut again.

## Uninstalling

Use "Uninstall EmailMover" in the Start Menu, or Windows Settings > Apps.
This removes the app files but does not uninstall Python itself.

## Privacy

- Email account passwords (app passwords) are used only in memory, for the
  single migration you run them in, and are never written to disk.
- No usage data is collected or sent anywhere. Everything runs on your own
  machine, talking directly to your two mail providers over IMAP.
