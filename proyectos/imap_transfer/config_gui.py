#!/usr/bin/env python3
"""
config_gui.py — Point-and-click setup and runner for IMAP Transfer.

No editing of config.json and no command line needed: fill in two simple
forms, pick your folders, click a button. Everything still runs locally
on this computer, connecting straight to your two mail providers.
"""

import io
import json
import os
import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

import imap_transfer as core

APP_VERSION = "1.0"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
PROGRESS_PATH = os.path.join(APP_DIR, "progress.json")
ICON_PATH = os.path.join(APP_DIR, "icon.ico")


def apply_app_icon(window):
    """Best-effort: set the custom .ico for a window's title bar/taskbar
    icon. Silently does nothing if the file is missing or the platform
    doesn't support .ico (e.g. non-Windows) - never blocks the app."""
    if os.path.exists(ICON_PATH):
        try:
            window.iconbitmap(ICON_PATH)
        except Exception:
            pass

PROVIDERS = {
    "Gmail": {"host": "imap.gmail.com", "port": 993, "ssl": True,
              "help": "Google Account -> Security -> 2-Step Verification -> App passwords"},
    "Outlook / Office 365": {"host": "outlook.office365.com", "port": 993, "ssl": True,
              "help": "Microsoft account -> Security -> Advanced security options -> App passwords"},
    "Yahoo Mail": {"host": "imap.mail.yahoo.com", "port": 993, "ssl": True,
              "help": "Yahoo Account Security -> Generate app password"},
    "iCloud Mail": {"host": "imap.mail.me.com", "port": 993, "ssl": True,
              "help": "appleid.apple.com -> Sign-In and Security -> App-Specific Passwords"},
    "Other / custom": {"host": "", "port": 993, "ssl": True, "help": ""},
}
PROVIDER_NAMES = list(PROVIDERS.keys())

# Map an email domain to one of the PROVIDERS keys, so we can guess the
# provider automatically once someone types their address.
DOMAIN_TO_PROVIDER = {
    "gmail.com": "Gmail", "googlemail.com": "Gmail",
    "yahoo.com": "Yahoo Mail", "yahoo.co.uk": "Yahoo Mail", "yahoo.es": "Yahoo Mail",
    "ymail.com": "Yahoo Mail", "rocketmail.com": "Yahoo Mail",
    "outlook.com": "Outlook / Office 365", "hotmail.com": "Outlook / Office 365",
    "live.com": "Outlook / Office 365", "msn.com": "Outlook / Office 365",
    "office365.com": "Outlook / Office 365",
    "icloud.com": "iCloud Mail", "me.com": "iCloud Mail", "mac.com": "iCloud Mail",
}


def guess_provider_from_email(email):
    email = email.strip().lower()
    if "@" not in email:
        return None
    domain = email.rsplit("@", 1)[-1]
    return DOMAIN_TO_PROVIDER.get(domain)

# Step-by-step, provider-specific instructions for creating an IMAP
# ("app") password, plus the exact page to send people to.
PASSWORD_HELP = {
    "Gmail": {
        "url": "https://myaccount.google.com/apppasswords",
        "steps": [
            "Make sure 2-Step Verification is turned on for this Google account "
            "(the app password page will ask you to turn it on first if it isn't).",
            "Click the button below to open Google's \"App passwords\" page.",
            "Sign in if asked.",
            "Type a name for it, e.g. \"IMAP Transfer\", and click Create.",
            "Google shows a 16-character password (4 groups of 4 letters). Copy it.",
            "Come back here and paste it into the IMAP password box below "
            "(spaces don't matter).",
        ],
    },
    "Outlook / Office 365": {
        "url": "https://account.live.com/proofs/AppPassword",
        "steps": [
            "Make sure two-step verification is turned on for this Microsoft account.",
            "Click the button below to open Microsoft's security page.",
            "Sign in if asked, then look for \"App passwords\" (sometimes under "
            "\"Advanced security options\").",
            "Click \"Create a new app password\".",
            "Microsoft shows a password. Copy it.",
            "Come back here and paste it into the IMAP password box below.",
        ],
    },
    "Yahoo Mail": {
        "url": "https://login.yahoo.com/account/security",
        "steps": [
            "Click the button below to open Yahoo's Account Security page.",
            "Sign in with your normal Yahoo password if asked.",
            "If \"Two-step verification\" is off, turn it on first (Yahoo requires "
            "this before it will let you create an app password).",
            "Find \"Generate app password\" (sometimes listed as \"App passwords\").",
            "Type a name for it, e.g. \"IMAP Transfer\", and click Generate.",
            "Yahoo shows a 16-character password. Copy it immediately — you can't "
            "view it again later.",
            "Come back here and paste it into the IMAP password box below.",
        ],
    },
    "iCloud Mail": {
        "url": "https://appleid.apple.com/account/manage",
        "steps": [
            "Make sure two-factor authentication is turned on for this Apple ID.",
            "Click the button below to open your Apple ID account page.",
            "Sign in if asked, then go to \"Sign-In and Security\".",
            "Find \"App-Specific Passwords\" and click \"Generate an app-specific password\".",
            "Type a label, e.g. \"IMAP Transfer\", and click Create.",
            "Apple shows a password like xxxx-xxxx-xxxx-xxxx. Copy it.",
            "Come back here and paste it into the IMAP password box below.",
        ],
    },
    "Other / custom": {
        "url": "",
        "steps": [
            "Most email providers now require a special password (often called an "
            "\"app password\" or \"application password\") for programs like this, "
            "instead of your normal login password.",
            "Look in your provider's account or security settings for something "
            "called \"App passwords\", \"Application passwords\", or "
            "\"Third-party app access\".",
            "Generate one there, then come back and paste it into the IMAP "
            "password box below.",
            "If your provider doesn't have this feature, your regular password "
            "may work instead — try it.",
        ],
    },
}


class PasswordHelpDialog(tk.Toplevel):
    """Explains, in plain language, how to create an IMAP/app password for a
    specific provider, with a button that jumps straight to that provider's
    account security page in the browser. Resizable, and the buttons are
    pinned to the bottom so they're never pushed off-screen by long content
    or a small display."""

    def __init__(self, parent, provider_name):
        super().__init__(parent)
        apply_app_icon(self)
        self.title(f"Getting an IMAP password for {provider_name}")
        self.geometry("560x500")
        self.minsize(420, 320)
        self.transient(parent)
        self.grab_set()

        info = PASSWORD_HELP.get(provider_name, PASSWORD_HELP["Other / custom"])

        # Buttons are packed to the bottom FIRST, so they always keep their
        # space no matter how tall the scrollable content above turns out
        # to be or how small the window/screen is.
        btn_row = ttk.Frame(self, padding=(16, 8))
        btn_row.pack(side="bottom", fill="x")
        if info["url"]:
            ttk.Button(
                btn_row, text=f"Open {provider_name} account security page",
                command=lambda: webbrowser.open(info["url"])
            ).pack(side="left")
        ttk.Button(btn_row, text="Back to main window", command=self.destroy).pack(side="right")
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        top = ttk.Frame(self, padding=(16, 16, 16, 0))
        top.pack(side="top", fill="x")
        intro = (f"{provider_name} needs a special IMAP password for apps like this one "
                 "— your normal email password won't work here. It only takes a minute "
                 "to create one:")
        ttk.Label(top, text=intro, wraplength=500, justify="left").pack(anchor="w", pady=(0, 10))

        # Scrollable steps area, so it never needs to grow the window taller
        # than the screen allows.
        scroll_container = ttk.Frame(self, padding=(16, 0, 16, 8))
        scroll_container.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        steps_frame = ttk.Frame(canvas)
        steps_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=steps_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for i, step in enumerate(info["steps"], 1):
            ttk.Label(steps_frame, text=f"{i}.", width=3, anchor="ne").grid(
                row=i - 1, column=0, sticky="ne", pady=3)
            ttk.Label(steps_frame, text=step, wraplength=440, justify="left").grid(
                row=i - 1, column=1, sticky="w", pady=3)


class AccountPanel(ttk.LabelFrame):
    """A form for one email account: provider (auto-detected), address,
    IMAP password (gated behind a yes/no question), host/port."""

    def __init__(self, parent, title, on_change=None):
        super().__init__(parent, text=title, padding=12)
        self.columnconfigure(1, weight=1)
        self.on_change = on_change  # called whenever anything in this panel changes

        ttk.Label(self, text="Email provider:").grid(row=0, column=0, sticky="w", pady=3)
        self.provider_var = tk.StringVar(value=PROVIDER_NAMES[0])
        self.provider_combo = ttk.Combobox(self, textvariable=self.provider_var,
                                            values=PROVIDER_NAMES, state="readonly")
        self.provider_combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        ttk.Label(self, text="Email address:").grid(row=1, column=0, sticky="w", pady=3)
        self.email_var = tk.StringVar()
        self.email_entry = ttk.Entry(self, textvariable=self.email_var)
        self.email_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)
        self.email_entry.bind("<FocusOut>", lambda e: self._on_email_finished())
        self.email_entry.bind("<Return>", lambda e: self._on_email_finished())

        # --- Do you have an IMAP password? yes/no ---
        ttk.Label(self, text="Do you have an IMAP password?").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 2))
        has_pw_frame = ttk.Frame(self)
        has_pw_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 2))
        self.has_password_var = tk.StringVar(value="")  # "", "yes", or "no"
        ttk.Radiobutton(has_pw_frame, text="Yes", variable=self.has_password_var,
                        value="yes", command=self._on_has_password_change).pack(side="left", padx=(0, 20))
        ttk.Radiobutton(has_pw_frame, text="No", variable=self.has_password_var,
                        value="no", command=self._on_has_password_change).pack(side="left")
        ttk.Label(self, text="(this is NOT your regular email password)",
                  foreground="#a33", wraplength=340, justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(0, 6))

        ttk.Label(self, text="IMAP password:").grid(row=5, column=0, sticky="w", pady=3)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(self, textvariable=self.password_var, show="*", state="disabled")
        self.password_entry.grid(row=5, column=1, sticky="ew", pady=3)
        self.password_var.trace_add("write", lambda *a: self._notify_change())
        self.show_pw_var = tk.BooleanVar(value=False)
        self.show_pw_check = ttk.Checkbutton(self, text="Show", variable=self.show_pw_var,
                                              command=self._toggle_password, state="disabled")
        self.show_pw_check.grid(row=5, column=2, padx=(6, 0))

        self._help_shown_for = None  # (provider, email) pair we've already shown "No" help for

        self.help_label = ttk.Label(self, foreground="#555555", wraplength=340, justify="left")
        self.help_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 8))

        adv = ttk.Frame(self)
        adv.grid(row=7, column=0, columnspan=3, sticky="ew")
        ttk.Label(adv, text="Server:").grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar()
        ttk.Entry(adv, textvariable=self.host_var, width=28).grid(row=0, column=1, padx=(4, 12))
        ttk.Label(adv, text="Port:").grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar()
        ttk.Entry(adv, textvariable=self.port_var, width=6).grid(row=0, column=3, padx=(4, 0))

        self._on_provider_change()

    def _notify_change(self):
        if self.on_change:
            self.on_change()

    def _toggle_password(self):
        if self.has_password_var.get() == "yes":
            self.password_entry.config(show="" if self.show_pw_var.get() else "*")

    def _on_provider_change(self, event=None):
        info = PROVIDERS[self.provider_var.get()]
        self.host_var.set(info["host"])
        self.port_var.set(str(info["port"]))
        self.help_label.config(text=info["help"])
        self._help_shown_for = None  # provider changed, allow the "No" dialog again
        self._notify_change()

    def _on_email_finished(self):
        email = self.email_var.get().strip()
        guessed = guess_provider_from_email(email)
        if guessed and guessed != self.provider_var.get():
            self.provider_var.set(guessed)
            self._on_provider_change()
        self._maybe_show_no_password_help()
        self._notify_change()

    def _on_has_password_change(self):
        if self.has_password_var.get() == "yes":
            self.password_entry.config(state="normal")
            self.show_pw_check.config(state="normal")
            self._toggle_password()
        else:
            self.password_entry.config(state="disabled")
            self.show_pw_check.config(state="disabled")
            self.password_var.set("")
            self._help_shown_for = None  # a deliberate "No" click should always show help
            self._maybe_show_no_password_help()
        self._notify_change()

    def _maybe_show_no_password_help(self):
        if self.has_password_var.get() != "no":
            return
        email = self.email_var.get().strip()
        if not email:
            return
        provider = self.provider_var.get()
        key = (provider, email)
        if self._help_shown_for == key:
            return  # already shown for this exact provider+email combo
        self._help_shown_for = key
        PasswordHelpDialog(self.winfo_toplevel(), provider)

    def get_values(self):
        return {
            "host": self.host_var.get().strip(),
            "port": int(self.port_var.get().strip() or 993),
            "ssl": True,
            "username": self.email_var.get().strip(),
            "password": self.password_var.get(),
        }

    def set_values(self, cfg):
        self.host_var.set(cfg.get("host", ""))
        self.port_var.set(str(cfg.get("port", 993)))
        self.email_var.set(cfg.get("username", ""))
        if cfg.get("password"):
            self.has_password_var.set("yes")
            self._on_has_password_change()
            self.password_var.set(cfg.get("password", ""))
        # Try to match a known provider for a nicer display; otherwise leave as "Other"
        for name, info in PROVIDERS.items():
            if info["host"] and info["host"] == cfg.get("host"):
                self.provider_var.set(name)
                self.help_label.config(text=info["help"])
                return
        self.provider_var.set("Other / custom")
        self.help_label.config(text="")

    def is_filled(self):
        v = self.get_values()
        return bool(v["host"] and v["username"] and v["password"]
                    and self.has_password_var.get() == "yes")

    def set_enabled(self, enabled):
        """Enable or disable every input in this panel (used to lock the TO
        panel until the FROM panel is fully filled in)."""
        state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.provider_combo.config(state=state)
        self.email_entry.config(state=entry_state)
        # Password field respects its own yes/no gating on top of this
        if enabled and self.has_password_var.get() == "yes":
            self.password_entry.config(state="normal")
            self.show_pw_check.config(state="normal")
        else:
            self.password_entry.config(state="disabled")
            self.show_pw_check.config(state="disabled")
        for child in self.winfo_children():
            if isinstance(child, (ttk.Frame,)):
                for grandchild in child.winfo_children():
                    if isinstance(grandchild, ttk.Radiobutton):
                        grandchild.config(state=entry_state)
            if isinstance(child, ttk.Entry) and child not in (self.email_entry, self.password_entry):
                child.config(state=entry_state)


class ProgressWindow(tk.Toplevel):
    """A separate, resizable window that shows the live log for a running
    task (testing connections, loading folders, previewing, or running the
    transfer). Kept apart from the main setup window so a small screen
    never hides it, and closing it ("Back to main window") never
    interrupts whatever is running in the background."""

    def __init__(self, parent, title):
        super().__init__(parent)
        apply_app_icon(self)
        self._base_title = title
        self.title(title)
        self.geometry("680x460")
        self.minsize(440, 280)
        self.transient(parent)

        # Button row pinned to the bottom first, so it always has room.
        btn_row = ttk.Frame(self, padding=(10, 8))
        btn_row.pack(side="bottom", fill="x")
        ttk.Button(btn_row, text="Back to main window", command=self.destroy).pack(side="right")
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        content = ttk.Frame(self, padding=10)
        content.pack(side="top", fill="both", expand=True)
        self.text = tk.Text(content, wrap="word", state="disabled",
                             background="#111111", foreground="#e0e0e0")
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def append(self, text):
        self.text.config(state="normal")
        self.text.insert("end", text)
        self.text.see("end")
        self.text.config(state="disabled")

    def mark_finished(self):
        try:
            if self.winfo_exists() and "(finished)" not in self.title():
                self.title(f"{self._base_title}  (finished)")
        except tk.TclError:
            pass  # window was already closed


def build_folder_tree(names, delim):
    """Turn a flat list of IMAP folder names (e.g. "Work/Clients") into a
    nested dict tree using the account's folder delimiter, so it can be
    displayed as an Explorer-style hierarchy. Each node is
    {"children": {...}, "full": <real IMAP name or None if it's just a
    grouping level with no folder of its own>}."""
    tree = {}
    for full in names:
        parts = full.split(delim) if delim else [full]
        node = tree
        for i, part in enumerate(parts):
            if part not in node:
                node[part] = {"children": {}, "full": None}
            if i == len(parts) - 1:
                node[part]["full"] = full
            node = node[part]["children"]
    return tree


class FolderSelectionWindow(tk.Toplevel):
    """Explorer-style folder browser for the FROM account: connects, shows
    a tree the user can multi-select (ctrl/shift-click, just like Windows
    Explorer), and holds the Preview / Start transfer buttons — which stay
    disabled until at least one real folder is selected."""

    def __init__(self, app, source_cfg):
        super().__init__(app)
        apply_app_icon(self)
        self.app = app
        self.title("Choose folders to transfer")
        self.geometry("640x580")
        self.minsize(480, 420)
        self.transient(app)

        self.node_to_folder = {}  # tree item id -> real IMAP folder name
        self._load_queue = queue.Queue()

        # Buttons pinned to the bottom first, so they always keep their space.
        btn_row = ttk.Frame(self, padding=(10, 8))
        btn_row.pack(side="bottom", fill="x")
        self.start_btn = ttk.Button(btn_row, text="Start transfer",
                                     command=self._start_transfer_clicked, state="disabled")
        self.start_btn.pack(side="right")
        self.preview_btn = ttk.Button(btn_row, text="Preview (no changes)",
                                       command=self._preview_clicked, state="disabled")
        self.preview_btn.pack(side="right", padx=(0, 8))
        ttk.Button(btn_row, text="Back to main window", command=self.destroy).pack(side="left")
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.pack(side="top", fill="x")
        select_row = ttk.Frame(top)
        select_row.pack(fill="x")
        ttk.Button(select_row, text="Select all", command=self._select_all).pack(side="left")
        ttk.Button(select_row, text="Select none", command=self._select_none).pack(side="left", padx=6)
        self.status_label = ttk.Label(top, text="Connecting to the old account...",
                                       foreground="#555555", wraplength=580, justify="left")
        self.status_label.pack(anchor="w", pady=(8, 6))

        tree_container = ttk.Frame(self, padding=(10, 0, 10, 10))
        tree_container.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(tree_container, selectmode="extended", show="tree")
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._refresh_buttons())

        # Defensive: whenever this window regains focus (e.g. the user came
        # back from the progress window, or from main), force the button
        # states to be recomputed from scratch, so they can never get stuck
        # showing a stale disabled/enabled state.
        self.bind("<FocusIn>", lambda e: self._refresh_buttons() if e.widget is self else None)

        self.app._busy_observers.append(self._refresh_buttons)
        self.bind("<Destroy>", self._on_destroy)

        threading.Thread(target=self._load_worker, args=(source_cfg,), daemon=True).start()
        self.after(100, self._poll_load_queue)

    def _on_destroy(self, event):
        if event.widget is self and self._refresh_buttons in self.app._busy_observers:
            self.app._busy_observers.remove(self._refresh_buttons)

    # --- loading folders from the server (own thread, own queue - does
    # not depend on the main window's log/progress plumbing) -----------
    def _load_worker(self, source_cfg):
        try:
            conn = core.connect(source_cfg)
            folders = core.list_folders(conn)
            conn.logout()
            selectable = [(flags, delim, name) for flags, delim, name in folders
                          if r"\Noselect" not in flags]
            self._load_queue.put(("ok", selectable))
        except Exception as e:
            self._load_queue.put(("error", str(e)))

    def _poll_load_queue(self):
        try:
            kind, payload = self._load_queue.get_nowait()
        except queue.Empty:
            try:
                if self.winfo_exists():
                    self.after(150, self._poll_load_queue)
            except tk.TclError:
                pass
            return
        if kind == "ok":
            self._populate_tree(payload)
        else:
            self.status_label.config(text=f"Could not load folders: {payload}")

    def _populate_tree(self, selectable_folders):
        if not selectable_folders:
            self.status_label.config(text="No folders were found in this account.")
            return
        delim = next((d for _, d, _ in selectable_folders if d), "/")
        names = [name for _, _, name in selectable_folders]
        tree_data = build_folder_tree(names, delim)

        def insert_nodes(parent_item, subtree):
            for name, info in sorted(subtree.items()):
                item_id = self.tree.insert(parent_item, "end", text=name, open=True)
                if info["full"] is not None:
                    self.node_to_folder[item_id] = info["full"]
                insert_nodes(item_id, info["children"])

        insert_nodes("", tree_data)

        # Pre-select based on whatever was previously chosen (or everything,
        # the first time).
        if self.app.selected_folders == "ALL":
            self.tree.selection_set(list(self.node_to_folder.keys()))
        else:
            want = set()
            for item in self.app.selected_folders:
                want.add(item["src"] if isinstance(item, dict) else item)
            matching = [iid for iid, full in self.node_to_folder.items() if full in want]
            if matching:
                self.tree.selection_set(matching)

        self.status_label.config(
            text=f"Found {len(names)} folder(s). Click to select one, or Ctrl/Shift-click "
                 "to select several, then Preview or Start transfer."
        )
        self._refresh_buttons()

    # --- selection helpers ----------------------------------------------
    def _selected_folder_names(self):
        return [self.node_to_folder[iid] for iid in self.tree.selection() if iid in self.node_to_folder]

    def _select_all(self):
        self.tree.selection_set(list(self.node_to_folder.keys()))
        self._refresh_buttons()

    def _select_none(self):
        self.tree.selection_set([])
        self._refresh_buttons()

    def _refresh_buttons(self):
        try:
            has_selection = len(self._selected_folder_names()) > 0
        except tk.TclError:
            return  # window is mid-destroy
        state = "normal" if (has_selection and not self.app.busy) else "disabled"
        self.start_btn.config(state=state)
        self.preview_btn.config(state=state)

    # --- actions ----------------------------------------------------------
    def _preview_clicked(self):
        names = self._selected_folder_names()
        if not names:
            return
        folders_value = [{"src": n, "dst": n} for n in names]
        self.app.selected_folders = folders_value
        cfg = self.app._build_config_dict(folders_value)
        self.app._run_in_background("Preview (no changes made)", self.app._run_transfer, cfg, True)

    def _start_transfer_clicked(self):
        names = self._selected_folder_names()
        if not names:
            return
        folders_value = [{"src": n, "dst": n} for n in names]
        cfg = self.app._build_config_dict(folders_value)

        def on_confirm():
            self.app.selected_folders = folders_value
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
            self.destroy()  # close the folder browser; the ProgressWindow takes over
            self.app._run_in_background("Transfer in progress", self.app._run_transfer, cfg, False)

        def on_cancel():
            self.destroy()  # back to the main window; nothing there is touched or lost

        ConfirmTransferDialog(self, names, cfg, on_confirm, on_cancel)


class ConfirmTransferDialog(tk.Toplevel):
    """Shows exactly which folders are about to be copied/moved, and which
    accounts are involved, before anything happens. Cancel closes the
    folder browser and returns to the main window untouched; Confirm
    proceeds with the transfer."""

    def __init__(self, parent, folder_names, cfg, on_confirm, on_cancel):
        super().__init__(parent)
        apply_app_icon(self)
        self.title("Confirm transfer")
        self.geometry("480x460")
        self.minsize(380, 320)
        self.transient(parent)
        self.grab_set()
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

        verb = "MOVE (and delete from the old account)" if cfg["mode"] == "move" else "COPY"

        # Buttons pinned to the bottom first, so they're always visible.
        btn_row = ttk.Frame(self, padding=(14, 10))
        btn_row.pack(side="bottom", fill="x")
        ttk.Button(btn_row, text="Cancel", command=self._cancel).pack(side="right")
        ttk.Button(btn_row, text="Confirm & start transfer", command=self._confirm).pack(side="right", padx=(0, 8))
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        top = ttk.Frame(self, padding=(14, 14, 14, 0))
        top.pack(side="top", fill="x")
        summary = (f"This will {verb} emails in {len(folder_names)} folder(s):\n\n"
                   f"From:  {cfg['source']['username']}\n"
                   f"To:      {cfg['destination']['username']}")
        ttk.Label(top, text=summary, wraplength=440, justify="left").pack(anchor="w")
        ttk.Label(top, text="Folders:", font=("", 9, "bold")).pack(anchor="w", pady=(10, 2))

        list_container = ttk.Frame(self, padding=(14, 0, 14, 8))
        list_container.pack(side="top", fill="both", expand=True)
        listbox = tk.Listbox(list_container, exportselection=False)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        for name in folder_names:
            listbox.insert("end", name)
        listbox.configure(state="disabled")  # read-only: informational list, not editable/selectable
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _confirm(self):
        self.destroy()
        self._on_confirm()

    def _cancel(self):
        self.destroy()
        self._on_cancel()


class QueueWriter(io.TextIOBase):
    """Redirect print() output from background work into the GUI log."""

    def __init__(self, q):
        self.q = q

    def write(self, text):
        if text:
            self.q.put(text)
        return len(text)

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        apply_app_icon(self)
        self.title(f"IMAP Transfer  (v{APP_VERSION})")

        self.log_queue = queue.Queue()
        # Background threads must never touch Tkinter directly (including .after()).
        # Instead they post zero-arg callables here, and the main thread's poll
        # loop below executes them safely.
        self.action_queue = queue.Queue()
        self.busy = False
        self.active_progress = None  # the currently open ProgressWindow, if any
        self.selected_folders = "ALL"  # "ALL", or a list of {"src":..,"dst":..}
        # Zero-arg callables to notify whenever busy state changes, so other
        # windows (like the folder browser) can refresh their own buttons.
        self._busy_observers = []

        self._build_ui()
        self._load_existing_config()
        self._update_dest_lock()
        self._refresh_action_buttons()
        self._center_on_screen(980, 700)
        self.minsize(900, 640)
        self.after(100, self._poll_queues)

    def _center_on_screen(self, width, height):
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        intro = ("Move or copy email folders from one account to another. "
                 "Everything runs on this computer only — nothing is sent anywhere else.")
        ttk.Label(container, text=intro, wraplength=720, foreground="#333333").pack(anchor="w", pady=(0, 10))

        accounts_row = ttk.Frame(container)
        accounts_row.pack(fill="x")
        accounts_row.columnconfigure(0, weight=1, minsize=420)
        accounts_row.columnconfigure(1, weight=1, minsize=420)

        self.source_panel = AccountPanel(accounts_row, "FROM  (old account)",
                                          on_change=self._on_form_changed)
        self.source_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.dest_panel = AccountPanel(accounts_row, "TO  (new account)",
                                        on_change=self._on_form_changed)
        self.dest_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.dest_panel.set_enabled(False)

        # --- Mode ---
        mode_frame = ttk.LabelFrame(container, text="What should happen to the original emails?", padding=10)
        mode_frame.pack(fill="x", pady=10)
        self.mode_var = tk.StringVar(value="copy")
        ttk.Radiobutton(mode_frame, text="Copy — keep the emails in the old account too",
                        variable=self.mode_var, value="copy", command=self._on_form_changed).pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Move — remove the emails from the old account once copied",
                        variable=self.mode_var, value="move", command=self._on_form_changed).pack(anchor="w")

        # --- Buttons (centered) ---
        btn_row = ttk.Frame(container)
        btn_row.pack(pady=(10, 8))  # no fill="x": pack centers a non-filled child by default
        self.test_btn = ttk.Button(btn_row, text="Test connections", command=self._test_connections_clicked)
        self.test_btn.pack(side="left")
        self.save_btn = ttk.Button(btn_row, text="Save settings", command=self._save_clicked)
        self.save_btn.pack(side="left", padx=8)
        self.choose_folders_btn = ttk.Button(
            btn_row, text="Choose folders & start transfer", command=self._open_folder_selection)
        self.choose_folders_btn.pack(side="left")
        ttk.Button(btn_row, text="Exit", command=self.destroy).pack(side="left", padx=(8, 0))

        note = ("\"Test connections\" and \"Choose folders & start transfer\" each open a "
                "separate window showing what's happening, with a button to come back here. "
                "The buttons above stay disabled until both FROM and TO are filled in.")
        ttk.Label(container, text=note, foreground="#666666", wraplength=720,
                  justify="left").pack(anchor="w", pady=(4, 0))

        ttk.Label(container, text=f"v{APP_VERSION}", foreground="#aaaaaa",
                  font=("", 8)).pack(side="bottom", anchor="e", pady=(6, 0))

    def _update_dest_lock(self):
        if not hasattr(self, "dest_panel"):
            return  # source panel is still being constructed
        self.dest_panel.set_enabled(self.source_panel.is_filled())

    def _refresh_action_buttons(self):
        if not hasattr(self, "test_btn"):
            return  # UI still being constructed
        complete = self.source_panel.is_filled() and self.dest_panel.is_filled()
        state = "normal" if (complete and not self.busy) else "disabled"
        self.test_btn.config(state=state)
        self.save_btn.config(state=state)
        self.choose_folders_btn.config(state=state)

    def _on_form_changed(self):
        self._update_dest_lock()
        self._refresh_action_buttons()
        self._autosave()

    def _autosave(self):
        # Best-effort background save so nothing is lost if a window is
        # closed or the app exits unexpectedly. Never interrupts the user.
        try:
            cfg = self._build_config_dict()
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Config load/save
    # ------------------------------------------------------------------
    def _load_existing_config(self):
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except Exception:
            return

        if "source" in cfg:
            self.source_panel.set_values(cfg["source"])
        if "destination" in cfg:
            self.dest_panel.set_values(cfg["destination"])
        self.mode_var.set(cfg.get("mode", "copy"))

        folders = cfg.get("folders")
        if isinstance(folders, list) and folders:
            self.selected_folders = folders
        else:
            self.selected_folders = "ALL"

    def _build_config_dict(self, folders_value=None):
        if folders_value is None:
            folders_value = self.selected_folders
        return {
            "mode": self.mode_var.get(),
            "resume_file": "progress.json",
            "source": self.source_panel.get_values(),
            "destination": self.dest_panel.get_values(),
            "folders": folders_value,
        }

    def _validate_before_action(self):
        if not self.source_panel.is_filled():
            messagebox.showwarning("Missing information", "Please fill in the FROM (old account) details.")
            return False
        if not self.dest_panel.is_filled():
            messagebox.showwarning("Missing information", "Please fill in the TO (new account) details.")
            return False
        return True

    def _save_clicked(self):
        if not self._validate_before_action():
            return
        cfg = self._build_config_dict()
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        messagebox.showinfo("Saved", "Your settings have been saved.")

    # ------------------------------------------------------------------
    # Logging / background task plumbing
    # ------------------------------------------------------------------
    def _log(self, text):
        if self.active_progress is None:
            return
        try:
            self.active_progress.append(text)
        except tk.TclError:
            pass  # the progress window was closed; task keeps running silently

    def _poll_queues(self):
        try:
            while True:
                text = self.log_queue.get_nowait()
                self._log(text)
        except queue.Empty:
            pass
        try:
            while True:
                action = self.action_queue.get_nowait()
                action()
        except queue.Empty:
            pass
        self.after(100, self._poll_queues)

    def _set_busy(self, busy):
        self.busy = busy
        self._refresh_action_buttons()
        for observer in list(self._busy_observers):
            try:
                observer()
            except tk.TclError:
                pass

    def _finish_progress_window(self):
        self._set_busy(False)
        if self.active_progress is not None:
            self.active_progress.mark_finished()
            self.active_progress = None

    def _run_in_background(self, title, fn, *args):
        if self.busy:
            return
        self._set_busy(True)
        self.active_progress = ProgressWindow(self, title)

        def wrapper():
            old_stdout = sys.stdout
            sys.stdout = QueueWriter(self.log_queue)
            try:
                fn(*args)
            except Exception as e:
                self.log_queue.put(f"\n[ERROR] {e}\n")
            finally:
                sys.stdout = old_stdout
                self.action_queue.put(lambda: self._finish_progress_window())

        threading.Thread(target=wrapper, daemon=True).start()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _test_connections_clicked(self):
        if not self._validate_before_action():
            return
        cfg = self._build_config_dict()
        self._run_in_background("Testing connections", self._test_connections, cfg)

    def _test_connections(self, cfg):
        print("Testing connection to the FROM account...")
        src = core.connect(cfg["source"])
        print("  OK - connected successfully.")
        src.logout()

        print("Testing connection to the TO account...")
        dst = core.connect(cfg["destination"])
        print("  OK - connected successfully.")
        dst.logout()

        print("\nBoth accounts look good.")

    def _open_folder_selection(self):
        if not self._validate_before_action():
            return
        FolderSelectionWindow(self, self.source_panel.get_values())

    def _run_transfer(self, cfg, dry_run):
        progress = core.load_progress(PROGRESS_PATH)
        print("Connecting to both accounts...")
        src_conn = core.connect(cfg["source"])
        dst_conn = core.connect(cfg["destination"])
        try:
            pairs = core.resolve_folder_list(cfg, src_conn)
            print(f"{len(pairs)} folder(s) to process\n")
            for src_folder, dst_folder in pairs:
                key = f"{cfg['source']['username']}::{src_folder}::{cfg['destination']['username']}::{dst_folder}"
                core.transfer_folder(
                    src_conn, dst_conn, src_folder, dst_folder, cfg["mode"],
                    dry_run, progress, key, PROGRESS_PATH,
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
        print("\nFinished." if not dry_run else "\nPreview finished — nothing was changed.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
