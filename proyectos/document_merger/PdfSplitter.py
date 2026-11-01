"""PDF Splitter - splits a large PDF into parts no bigger than a chosen size.

Useful when an email or an online form (court filing, job application...)
only accepts files up to a limit, for example 25 MB.

Designed by Oscar Alvarez Villarreal and coded with AI.
Part of Document Merger: same folder, same libraries (requirements.txt).

Structure
    Theme           colors and fonts, defined once and used by every widget
    SplitResult     what a split produced (files, sizes, warnings)
    PdfSizeSplitter the splitting logic, no GUI (can be used from code or tests)
    SplitterWindow  the Tkinter window
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, field
from io import BytesIO
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from PyPDF2 import PdfReader, PdfWriter

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.ico")
MB = 1024 * 1024


# ---------------------------------------------------------------------------
# Design: defined once, every label, entry and button inherits it
# ---------------------------------------------------------------------------
class Theme:
    """Colors and fonts shared by the whole window (same look as Document Merger)."""

    BACKGROUND = "#f3f3f3"
    CARD = "#ffffff"
    BORDER = "#d9d9d9"
    TEXT = "#222222"
    MUTED = "#666666"
    ACCENT = "#0f6cbd"
    OK = "#107c10"
    WARNING = "#9d5d00"

    FONT = ("Segoe UI Variable", 11)
    FONT_SMALL = ("Segoe UI Variable", 10)
    FONT_TITLE = ("Segoe UI Variable", 16, "bold")

    @classmethod
    def apply(cls, root: tk.Tk) -> None:
        """Configure ttk styles once for the whole application."""
        root.configure(bg=cls.BACKGROUND)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=cls.FONT, background=cls.CARD, foreground=cls.TEXT)
        style.configure("TFrame", background=cls.CARD)
        style.configure("TLabel", background=cls.CARD, foreground=cls.TEXT)
        style.configure("Muted.TLabel", foreground=cls.MUTED, font=cls.FONT_SMALL)
        style.configure("Title.TLabel", font=cls.FONT_TITLE)
        style.configure("TButton", padding=8)
        style.configure("Accent.TButton", padding=8, foreground="#ffffff", background=cls.ACCENT)
        style.map("Accent.TButton", background=[("active", "#115ea3"), ("disabled", "#9bbbe0")])
        style.configure("Horizontal.TProgressbar", background=cls.ACCENT)


def center_window(window: tk.Misc, min_width: int = 0) -> None:
    """Center a window on the user's screen.

    Only the position is fixed: the window keeps the size its content asks for,
    so it can grow (for example when a longer message appears) without cutting
    anything off.
    """
    window.update_idletasks()
    if min_width:
        window.minsize(min_width, 1)
        window.update_idletasks()
    width = max(window.winfo_reqwidth(), min_width)
    height = window.winfo_reqheight()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


# ---------------------------------------------------------------------------
# Logic (no GUI)
# ---------------------------------------------------------------------------
@dataclass
class SplitResult:
    """Outcome of a split: the files written and anything the user should know."""

    files: list[str] = field(default_factory=list)
    sizes: list[int] = field(default_factory=list)
    oversized_pages: list[int] = field(default_factory=list)  # 1-based page numbers

    @property
    def parts(self) -> int:
        return len(self.files)


class PdfSizeSplitter:
    """Splits a PDF into consecutive parts, each one no bigger than ``max_bytes``.

    How it stays fast: it first measures every page on its own, then fills each
    part using those estimates and only writes the part for real when it gets
    close to the limit. (Writing the whole part after every page, as the first
    version did, gets very slow on PDFs with hundreds of pages.)

    A single page bigger than the limit cannot be split; it goes alone in its
    own part and is reported in ``SplitResult.oversized_pages``.
    """

    SAFETY = 0.97  # leave a small margin for the PDF's own overhead

    def __init__(self, max_mb: float = 25):
        if max_mb <= 0:
            raise ValueError("The maximum size must be greater than 0 MB.")
        self.max_bytes = int(max_mb * MB * self.SAFETY)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _open(path: str) -> PdfReader:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                reader.decrypt("")  # many "protected" PDFs open with an empty password
            except Exception as exc:  # noqa: BLE001
                raise ValueError("This PDF is password protected. Remove the password first.") from exc
        return reader

    @staticmethod
    def _size(reader: PdfReader, pages: list[int]) -> int:
        """Real size in bytes of a PDF made of these pages."""
        writer = PdfWriter()
        for i in pages:
            writer.add_page(reader.pages[i])
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.tell()

    @staticmethod
    def _save(reader: PdfReader, pages: list[int], path: str) -> int:
        writer = PdfWriter()
        for i in pages:
            writer.add_page(reader.pages[i])
        with open(path, "wb") as f:
            writer.write(f)
        return os.path.getsize(path)

    # -- main entry point --------------------------------------------------
    def plan(self, reader: PdfReader, progress: Callable[[int, int], None] | None = None) -> list[list[int]]:
        """Decide which pages go in each part (0-based page indexes)."""
        total = len(reader.pages)
        estimates = []
        for i in range(total):
            estimates.append(self._size(reader, [i]))
            if progress:
                progress(i + 1, total * 2)

        parts: list[list[int]] = []
        current: list[int] = []
        estimate = 0
        for i in range(total):
            candidate = current + [i]
            fits = estimate + estimates[i] <= self.max_bytes
            if not fits and current:
                # The estimate counts shared fonts/images once per page, so it is
                # pessimistic: confirm with the real size before closing the part.
                fits = self._size(reader, candidate) <= self.max_bytes
            if fits or not current:
                current, estimate = candidate, estimate + estimates[i]
            else:
                parts.append(current)
                current, estimate = [i], estimates[i]
            if progress:
                progress(total + i + 1, total * 2)
        if current:
            parts.append(current)
        return parts

    def split(
        self,
        input_pdf: str,
        output_dir: str | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> SplitResult:
        """Split ``input_pdf`` and write ``<name>_part_1.pdf``, ``_part_2``... in ``output_dir``."""
        reader = self._open(input_pdf)
        if not reader.pages:
            raise ValueError("The PDF has no pages.")
        output_dir = output_dir or os.path.dirname(os.path.abspath(input_pdf))
        stem = os.path.splitext(os.path.basename(input_pdf))[0]

        result = SplitResult()
        for number, pages in enumerate(self.plan(reader, progress), start=1):
            path = os.path.join(output_dir, f"{stem}_part_{number}.pdf")
            size = self._save(reader, pages, path)
            result.files.append(path)
            result.sizes.append(size)
            if len(pages) == 1 and size > self.max_bytes:
                result.oversized_pages.append(pages[0] + 1)
        return result


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------
class SplitterWindow:
    """Main window: pick a PDF, choose the size limit and the folder, split."""

    WIDTH = 640

    def __init__(self, root: tk.Tk):
        self.root = root
        self.result: SplitResult | None = None
        self.pdf_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.max_mb = tk.StringVar(value="25")
        self.status = tk.StringVar(value="Choose the PDF you want to split.")

        root.title("PDF Splitter")
        root.resizable(False, False)  # size follows the content
        try:
            root.iconbitmap(ICON_PATH)
        except Exception:  # noqa: BLE001 - icon is optional
            pass
        Theme.apply(root)
        self._build()
        center_window(root, self.WIDTH)

    # -- layout ------------------------------------------------------------
    def _build(self) -> None:
        card = ttk.Frame(self.root, padding=20)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(card, text="PDF Splitter", style="Title.TLabel").pack(anchor="center")
        ttk.Label(card, text="Splits a large PDF into smaller files you can attach or upload.",
                  style="Muted.TLabel").pack(anchor="center", pady=(2, 14))

        self._file_row(card, "1. PDF to split", self.pdf_path, self._choose_pdf)
        self._file_row(card, "2. Save the parts in", self.output_dir, self._choose_folder)

        size_row = ttk.Frame(card)
        size_row.pack(fill="x", pady=(4, 10))
        ttk.Label(size_row, text="3. Maximum size of each part (MB)").pack(side="left")
        ttk.Spinbox(size_row, from_=1, to=500, increment=1, width=6,
                    textvariable=self.max_mb, justify="center").pack(side="left", padx=8)
        ttk.Label(size_row, text="(email: 20–25)", style="Muted.TLabel").pack(side="left")

        self.split_btn = ttk.Button(card, text="Split PDF", style="Accent.TButton", command=self._start)
        self.split_btn.pack(fill="x", pady=(6, 10))

        self.progress = ttk.Progressbar(card, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.status_lbl = ttk.Label(card, textvariable=self.status, style="Muted.TLabel",
                                    wraplength=self.WIDTH - 80, justify="center")
        self.status_lbl.pack(anchor="center", pady=(8, 8))

        buttons = ttk.Frame(card)
        buttons.pack(anchor="center", pady=(4, 0))
        self.open_btn = ttk.Button(buttons, text="Open folder", command=self._open_folder, state="disabled")
        self.open_btn.pack(side="left", padx=6)
        ttk.Button(buttons, text="Exit", command=self.root.destroy).pack(side="left", padx=6)

    def _file_row(self, parent, label, variable, command) -> None:
        ttk.Label(parent, text=label).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(2, 10))
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=command).pack(side="left", padx=(8, 0))

    # -- actions -----------------------------------------------------------
    def _choose_pdf(self) -> None:
        start = os.path.dirname(self.pdf_path.get()) or os.path.join(os.path.expanduser("~"), "Downloads")
        path = filedialog.askopenfilename(parent=self.root, title="Select the PDF to split",
                                          initialdir=start, filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path.set(os.path.normpath(path))
            if not self.output_dir.get():
                self.output_dir.set(os.path.dirname(os.path.normpath(path)))
            size = os.path.getsize(path) / MB
            self.status.set(f"Selected: {os.path.basename(path)} ({size:.1f} MB).")

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self.root, title="Where to save the parts",
                                         initialdir=self.output_dir.get() or None)
        if folder:
            self.output_dir.set(os.path.normpath(folder))

    def _validate(self) -> tuple[str, str, float] | None:
        pdf, folder = self.pdf_path.get().strip(), self.output_dir.get().strip()
        if not pdf:
            messagebox.showerror("PDF Splitter", "Please choose a PDF first.", parent=self.root)
            return None
        if not os.path.isfile(pdf):
            messagebox.showerror("PDF Splitter", "That file does not exist.", parent=self.root)
            return None
        folder = folder or os.path.dirname(pdf)
        if not os.path.isdir(folder):
            messagebox.showerror("PDF Splitter", "The destination folder does not exist.", parent=self.root)
            return None
        try:
            max_mb = float(self.max_mb.get().replace(",", "."))
            if max_mb <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("PDF Splitter", "The maximum size must be a number greater than 0.",
                                 parent=self.root)
            return None
        if os.path.getsize(pdf) <= max_mb * MB:
            if not messagebox.askyesno("PDF Splitter",
                                       f"This PDF is already smaller than {max_mb:g} MB.\n\nSplit it anyway?",
                                       parent=self.root):
                return None
        return pdf, folder, max_mb

    def _start(self) -> None:
        values = self._validate()
        if not values:
            return
        pdf, folder, max_mb = values
        self.split_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.progress["value"] = 0
        self.status.set("Measuring the pages…")
        # Work in a background thread so the window keeps responding.
        threading.Thread(target=self._work, args=(pdf, folder, max_mb), daemon=True).start()

    def _work(self, pdf: str, folder: str, max_mb: float) -> None:
        def progress(done: int, total: int) -> None:
            self.root.after(0, self._show_progress, done, total)

        try:
            result = PdfSizeSplitter(max_mb).split(pdf, folder, progress)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self.root.after(0, self._finish_error, exc)
        else:
            self.root.after(0, self._finish_ok, result)

    def _show_progress(self, done: int, total: int) -> None:
        self.progress["value"] = 100 * done / max(total, 1)
        self.status.set("Measuring the pages…" if done * 2 <= total else "Building the parts…")

    def _finish_ok(self, result: SplitResult) -> None:
        self.result = result
        self.progress["value"] = 100
        self.split_btn.configure(state="normal")
        self.open_btn.configure(state="normal")
        sizes = ", ".join(f"{s / MB:.1f}" for s in result.sizes)
        text = f"Done: {result.parts} part(s) saved ({sizes} MB)."
        if result.oversized_pages:
            pages = ", ".join(map(str, result.oversized_pages))
            text += f"\nPage(s) {pages} alone are bigger than the limit; each went in its own part."
            self.status_lbl.configure(foreground=Theme.WARNING)
        else:
            self.status_lbl.configure(foreground=Theme.OK)
        self.status.set(text)
        self._open_folder()

    def _finish_error(self, exc: Exception) -> None:
        self.split_btn.configure(state="normal")
        self.progress["value"] = 0
        self.status_lbl.configure(foreground=Theme.MUTED)
        self.status.set("The PDF was not split.")
        messagebox.showerror("PDF Splitter", f"Could not split the PDF:\n\n{exc}", parent=self.root)

    def _open_folder(self) -> None:
        """Open Windows Explorer with the first part selected."""
        if not self.result or not self.result.files:
            return
        first = self.result.files[0]
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", first])
        else:
            messagebox.showinfo("PDF Splitter", f"Saved in:\n{os.path.dirname(first)}", parent=self.root)


def main() -> None:
    root = tk.Tk()
    SplitterWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
