import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import pathlib
import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from PyPDF2 import PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from docx import Document as DocxDocument
from PIL import Image, ImageTk
import ctypes
from ctypes import wintypes

# ---------------------------------------------------------
# Supported input types
# ---------------------------------------------------------

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
FILE_DIALOG_TYPES = [
    ("Supported files", "*.pdf *.docx *.txt"),
    ("PDF files", "*.pdf"),
    ("Word documents", "*.docx"),
    ("Text files", "*.txt"),
    ("All files", "*.*"),
]

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.ico")


def load_icon_image(size=24):
    """Load favicon.ico as a resized PhotoImage for inline use next to panel titles."""
    try:
        img = Image.open(ICON_PATH).resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def filter_supported(files):
    """Split a list of paths into (supported, unsupported)."""
    supported, unsupported = [], []
    for f in files:
        ext = pathlib.Path(f).suffix.lower()
        (supported if ext in SUPPORTED_EXTENSIONS else unsupported).append(f)
    return supported, unsupported


def warn_unsupported(unsupported):
    if unsupported:
        names = "\n".join(os.path.basename(f) for f in unsupported)
        messagebox.showwarning(
            "Unsupported files skipped",
            f"These files aren't supported (only .pdf, .docx, .txt) and were skipped:\n\n{names}",
        )


# ---------------------------------------------------------
# Convert non-PDF files to PDF for merging
# ---------------------------------------------------------

def _unique_pdf_path(out_dir):
    """Generate a collision-free temp PDF path (different source files can share a stem)."""
    fd, path = tempfile.mkstemp(suffix="_conv.pdf", dir=out_dir)
    os.close(fd)
    return path


def convert_txt_to_pdf(txt_path, out_dir):
    out_path = _unique_pdf_path(out_dir)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(out_path, pagesize=letter)
    with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    doc.build([Preformatted(text, styles["Code"])])
    return out_path


def convert_docx_to_pdf(docx_path, out_dir):
    """Render a .docx file's paragraphs/headings to PDF using python-docx + reportlab.
    Note: this preserves text and basic heading styles, but not tables, images,
    or complex formatting from the original Word document."""
    out_path = _unique_pdf_path(out_dir)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(out_path, pagesize=letter)
    source = DocxDocument(docx_path)

    story = []
    for para in source.paragraphs:
        text = para.text.strip()
        if not text:
            story.append(Spacer(1, 10))
            continue
        style_name = (para.style.name or "").lower() if para.style else ""
        if "heading 1" in style_name:
            style = styles["Heading1"]
        elif "heading 2" in style_name:
            style = styles["Heading2"]
        elif style_name.startswith("heading"):
            style = styles["Heading3"]
        else:
            style = styles["Normal"]
        # Escape reportlab-reserved characters
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe_text, style))
        story.append(Spacer(1, 6))

    if not story:
        story = [Paragraph("(empty document)", styles["Normal"])]

    doc.build(story)
    return out_path


def resolve_to_pdf(path, out_dir):
    """Return a PDF path for the given input file, converting if necessary."""
    ext = pathlib.Path(path).suffix.lower()
    if ext == ".pdf":
        return path
    elif ext == ".docx":
        return convert_docx_to_pdf(path, out_dir)
    elif ext == ".txt":
        return convert_txt_to_pdf(path, out_dir)
    else:
        raise ValueError(f"Unsupported file type: {os.path.basename(path)}")

# ---------------------------------------------------------
# Convert virtual/OneDrive/Desktop paths to REAL physical paths
# ---------------------------------------------------------

def get_real_path(path):
    FILE_READ_ATTRIBUTES = 0x80
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

    CreateFileW = ctypes.windll.kernel32.CreateFileW
    GetFinalPathNameByHandleW = ctypes.windll.kernel32.GetFinalPathNameByHandleW
    CloseHandle = ctypes.windll.kernel32.CloseHandle

    handle = CreateFileW(
        path,
        FILE_READ_ATTRIBUTES,
        0,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None
    )

    if handle == -1:
        return path

    buffer = ctypes.create_unicode_buffer(1024)
    GetFinalPathNameByHandleW(handle, buffer, 1024, 0)
    CloseHandle(handle)

    real_path = buffer.value

    if real_path.startswith("\\\\?\\"):
        real_path = real_path[4:]

    return real_path

# ---------------------------------------------------------
# Win32 icon extraction
# ---------------------------------------------------------

SHGFI_ICON = 0x100
SHGFI_LARGEICON = 0x0
SHGFI_USEFILEATTRIBUTES = 0x10
FILE_ATTRIBUTE_NORMAL = 0x80

shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", wintypes.INT),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]

def get_file_icon(path):
    shinfo = SHFILEINFO()
    res = shell32.SHGetFileInfoW(
        path,
        FILE_ATTRIBUTE_NORMAL,
        ctypes.byref(shinfo),
        ctypes.sizeof(shinfo),
        SHGFI_ICON | SHGFI_LARGEICON | SHGFI_USEFILEATTRIBUTES
    )
    if res == 0 or not shinfo.hIcon:
        return None

    hicon = shinfo.hIcon
    width, height = 32, 32

    hdc = user32.GetDC(None)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(memdc, bmp)

    gdi32.PatBlt(memdc, 0, 0, width, height, 0x00FF0062)
    user32.DrawIconEx(memdc, 0, 0, hicon, width, height, 0, None, 0x0003)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", wintypes.DWORD * 3),
        ]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    buf_len = width * height * 4
    pixel_data = ctypes.create_string_buffer(buf_len)

    gdi32.GetDIBits(memdc, bmp, 0, height, pixel_data, ctypes.byref(bmi), 0)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(None, hdc)
    user32.DestroyIcon(hicon)

    image = Image.frombuffer("RGBA", (width, height), pixel_data, "raw", "BGRA", 0, 1)
    return ImageTk.PhotoImage(image)

# ---------------------------------------------------------
# Center window
# ---------------------------------------------------------

def center_window(root, width, height):
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2
    root.geometry(f"{width}x{height}+{x}+{y}")

# ---------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------

def run_explorer_gui():

    last_path = os.path.join(os.path.expanduser("~"), "Downloads")

    # Create the root window first (hidden, but centered) so the file dialog
    # that follows opens anchored to a centered window instead of tkinter's
    # default implicit root, which appears in the top-left of the screen.
    root = tk.Tk()
    root.withdraw()
    try:
        root.iconbitmap(ICON_PATH)
    except Exception:
        pass
    WIDTH, HEIGHT = 820, 560
    center_window(root, WIDTH, HEIGHT)
    root.update()

    files = filedialog.askopenfilenames(
        parent=root,
        title="Select files to merge",
        initialdir=last_path,
        filetypes=FILE_DIALOG_TYPES
    )
    if not files:
        root.destroy()
        return

    files, unsupported = filter_supported(files)
    warn_unsupported(unsupported)
    if not files:
        root.destroy()
        return

    last_path = os.path.dirname(files[0])

    root.title("File Merger")
    root.configure(bg="#f3f3f3")
    root.resizable(False, False)
    root.deiconify()

    style = ttk.Style()
    style.theme_use("clam")

    style.configure("TButton", font=("Segoe UI Variable", 11), padding=8)
    style.configure("Treeview", rowheight=32, font=("Segoe UI Variable", 11))

    container = tk.Frame(root, bg="#f3f3f3")
    container.pack(fill="both", expand=True, padx=20, pady=20)

    card = tk.Frame(container, bg="#ffffff")
    card.pack(fill="both", expand=True)
    card.configure(highlightbackground="#d9d9d9", highlightthickness=1)

    header = tk.Frame(card, bg="#ffffff")
    header.pack(fill="x", padx=16, pady=(12, 4))

    logo_icon = load_icon_image(66)
    if logo_icon:
        logo_lbl = tk.Label(header, image=logo_icon, bg="#ffffff")
        logo_lbl.image = logo_icon
        logo_lbl.pack(side="left", padx=(0, 12))

    title_label = tk.Label(
        header,
        text="File Merger",
        font=("Segoe UI Variable", 18, "bold"),
        bg="#ffffff"
    )
    title_label.pack(side="left", pady=(6, 0))

    ttk.Separator(card).pack(fill="x", padx=16, pady=(8, 12))

    center_frame = tk.Frame(card, bg="#ffffff")
    center_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    center_frame.rowconfigure(0, weight=1)
    center_frame.columnconfigure(0, weight=1)

    header_icon_main = load_icon_image(66)
    selected_files_header = tk.Frame(center_frame, bg="#ffffff")
    selected_files_header.grid(row=0, column=0, sticky="w")
    if header_icon_main:
        icon_lbl_main = tk.Label(selected_files_header, image=header_icon_main, bg="#ffffff")
        icon_lbl_main.image = header_icon_main
        icon_lbl_main.pack(side="left", padx=(0, 8))
    tk.Label(selected_files_header, text="Selected files", font=("Segoe UI Variable", 14, "bold"), bg="#ffffff").pack(side="left")

    tree = ttk.Treeview(center_frame, columns=("Name", "Type", "Size"), show="headings")
    tree.grid(row=0, column=0, sticky="nsew", pady=(30, 10))

    tree.heading("Name", text="Filename")
    tree.heading("Type", text="Type")
    tree.heading("Size", text="Size")

    tree.column("Name", width=360, anchor="w")
    tree.column("Type", width=160, anchor="center")
    tree.column("Size", width=120, anchor="e")

    selected_files = list(files)
    merged_path = None
    icon_cache = {}

    tree.configure(selectmode="extended")

    def refresh_tree():
        for item in tree.get_children():
            tree.delete(item)
        for f in selected_files:
            name = os.path.basename(f)
            ext = pathlib.Path(f).suffix
            size = f"{os.path.getsize(f)//1024} KB"

            if ext not in icon_cache:
                icon_cache[ext] = get_file_icon(f)

            tree.insert("", "end", iid=f, image=icon_cache[ext], values=(name, ext, size))

    refresh_tree()

    button_frame = tk.Frame(center_frame, bg="#ffffff")
    button_frame.grid(row=1, column=0, pady=(10, 0))

    browse_btn = ttk.Button(button_frame, text="Add Files", width=14)
    remove_btn = ttk.Button(button_frame, text="Remove Selected", width=16)
    merge_btn = ttk.Button(button_frame, text="Merge Files", width=14)
    clear_btn = ttk.Button(button_frame, text="Clear List", width=14)
    exit_btn = ttk.Button(button_frame, text="Exit", width=14)

    browse_btn.grid(row=0, column=0, padx=6)
    remove_btn.grid(row=0, column=1, padx=6)
    merge_btn.grid(row=0, column=2, padx=6)
    clear_btn.grid(row=0, column=3, padx=6)
    exit_btn.grid(row=0, column=4, padx=6)

    def exit_app():
        root.quit()
        root.destroy()
        os._exit(0)

    root.protocol("WM_DELETE_WINDOW", exit_app)

    # ---------------------------------------------------------
    # MERGE FILES — FINAL VERSION
    # ---------------------------------------------------------

    def merge_files():
        nonlocal merged_path

        if not selected_files:
            messagebox.showerror("Error", "No files selected.")
            return

        first_file = selected_files[0]
        source_folder = os.path.dirname(first_file)

        dialog = tk.Toplevel(root)
        dialog.title("Save Merged File")
        try:
            dialog.iconbitmap(ICON_PATH)
        except Exception:
            pass
        dialog.geometry("500x400")
        dialog.resizable(False, False)
        center_window(dialog, 500, 400)

        dialog.grab_set()
        dialog.focus_force()

        header_icon_dialog = load_icon_image(66)
        dialog_header = tk.Frame(dialog, bg=dialog.cget("bg"))
        dialog_header.pack(fill="x", padx=20, pady=(15, 0))
        if header_icon_dialog:
            icon_lbl_dialog = tk.Label(dialog_header, image=header_icon_dialog, bg=dialog.cget("bg"))
            icon_lbl_dialog.image = header_icon_dialog
            icon_lbl_dialog.pack(side="left", padx=(0, 8))
        tk.Label(dialog_header, text="Save Merged File", font=("Segoe UI Variable", 14, "bold"), bg=dialog.cget("bg")).pack(side="left")

        style = ttk.Style(dialog)
        style.theme_use("clam")
        style.configure("green.Horizontal.TProgressbar",
                        troughcolor="#e6e6e6",
                        background="#00aa00")

        progress = ttk.Progressbar(dialog,
                                   style="green.Horizontal.TProgressbar",
                                   length=300)
        progress.pack(pady=(5, 5))

        percent_label = tk.Label(dialog, text="0%", font=("Segoe UI Variable", 10))
        percent_label.pack()

        tk.Label(dialog, text="Source folder:", font=("Segoe UI Variable", 11, "bold")).pack(anchor="w", padx=20, pady=(10, 0))
        src_entry = tk.Entry(dialog, width=60)
        src_entry.insert(0, source_folder)
        src_entry.configure(state="readonly")
        src_entry.pack(padx=20, pady=(0, 10))

        default_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        default_filename = f"merged_{default_timestamp}.pdf"
        save_path_var = tk.StringVar(value=os.path.join(source_folder, default_filename))

        tk.Label(dialog, text="Save merged file as:", font=("Segoe UI Variable", 11, "bold")).pack(anchor="w", padx=20)

        save_path_row = tk.Frame(dialog, bg=dialog.cget("bg"))
        save_path_row.pack(fill="x", padx=20, pady=(0, 10))

        save_path_entry = tk.Entry(save_path_row, textvariable=save_path_var)
        save_path_entry.pack(side="left", fill="x", expand=True)

        def choose_save_path():
            current = save_path_var.get().strip()
            initial_dir = os.path.dirname(current) if current and os.path.isdir(os.path.dirname(current)) else source_folder
            initial_file = os.path.basename(current) if current else default_filename

            chosen = filedialog.asksaveasfilename(
                parent=dialog,
                title="Save merged file as",
                initialdir=initial_dir,
                initialfile=initial_file,
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")]
            )
            if chosen:
                save_path_var.set(chosen)

            dialog.grab_set()
            dialog.focus_force()

        ttk.Button(save_path_row, text="Change...", command=choose_save_path, width=10).pack(side="left", padx=(8, 0))

        def confirm_merge():
            nonlocal merged_path

            chosen_path = save_path_var.get().strip()

            if not chosen_path:
                messagebox.showerror("No save location", "Please choose where to save the merged file.")
                return

            dest_folder = os.path.dirname(chosen_path)
            if not dest_folder or not os.path.isdir(dest_folder):
                messagebox.showerror("Invalid folder", "The destination folder does not exist. Use \"Change...\" to pick a valid location.")
                return

            if not chosen_path.lower().endswith(".pdf"):
                chosen_path += ".pdf"

            merged_path = chosen_path

            merge_btn.configure(state="disabled")
            browse_btn.configure(state="disabled")
            remove_btn.configure(state="disabled")
            clear_btn.configure(state="disabled")
            exit_btn.configure(state="disabled")

            progress["value"] = 0
            progress.update()

            total_files = len(selected_files)
            step = 100 / total_files

            safe_folder = r"C:\PDF_TEMP"
            os.makedirs(safe_folder, exist_ok=True)

            separator_paths = []
            converted_paths = []

            try:
                with PdfMerger() as merger:

                    for idx, f in enumerate(selected_files):

                        sep_path = os.path.join(safe_folder, f"_separator_{idx}.pdf")
                        c = canvas.Canvas(sep_path, pagesize=letter)
                        c.setFont("Helvetica-Bold", 22)
                        c.drawString(72, 720, os.path.basename(f))
                        c.setFont("Helvetica", 12)
                        c.drawString(72, 700, "--------------------------------------------")
                        c.save()
                        separator_paths.append(sep_path)

                        with open(sep_path, "rb") as sep_file:
                            merger.append(BytesIO(sep_file.read()))

                        # Convert non-PDF files (.docx, .txt) to PDF first
                        try:
                            pdf_path = resolve_to_pdf(f, safe_folder)
                        except Exception as conv_err:
                            raise RuntimeError(
                                f"Could not convert {os.path.basename(f)}: {conv_err}"
                            )
                        if pdf_path != f:
                            converted_paths.append(pdf_path)

                        with open(pdf_path, "rb") as pdf_file:
                            merger.append(BytesIO(pdf_file.read()))

                        progress["value"] = (idx + 1) * step
                        percent_label.configure(text=f"{int(progress['value'])}%")
                        progress.update()

                    merger.write(merged_path)

                for tmp_path in separator_paths + converted_paths:
                    try:
                        os.remove(tmp_path)
                    except:
                        pass

            except Exception as e:
                merge_btn.configure(state="normal")
                browse_btn.configure(state="normal")
                remove_btn.configure(state="normal")
                clear_btn.configure(state="normal")
                exit_btn.configure(state="normal")

                messagebox.showerror("Merge error", f"Error merging files:\n{e}")
                return

            dialog.grab_release()
            dialog.destroy()

            merge_btn.configure(state="normal")
            browse_btn.configure(state="normal")
            remove_btn.configure(state="normal")
            clear_btn.configure(state="normal")
            exit_btn.configure(state="normal")

            # Reload original files only
            refresh_tree()

            # ---------------------------------------------------------
            # AUTO-OPEN WINDOWS EXPLORER IN SELECTION MODE (FINAL)
            # ---------------------------------------------------------
            messagebox.showinfo("Merge complete", f"Merged file saved in:\n{merged_path}")

            def open_explorer_after_dialog():
                real_path = get_real_path(merged_path)
                subprocess.Popen([
                    "explorer",
                    f"/select,{real_path}"
                ])

            root.after(200, open_explorer_after_dialog)

        def back_to_list():
            dialog.grab_release()
            dialog.destroy()

        save_button_frame = tk.Frame(dialog, bg=dialog.cget("bg"))
        save_button_frame.pack(pady=(0, 10))

        ttk.Button(save_button_frame, text="Back to List", command=back_to_list, width=14).grid(row=0, column=0, padx=6)
        ttk.Button(save_button_frame, text="Merge Now", command=confirm_merge, width=14).grid(row=0, column=1, padx=6)

    def add_files():
        nonlocal selected_files, merged_path, last_path

        new_files = filedialog.askopenfilenames(
            parent=root,
            title="Select files to add",
            initialdir=last_path,
            filetypes=FILE_DIALOG_TYPES
        )
        if not new_files:
            return

        new_files, unsupported = filter_supported(new_files)
        warn_unsupported(unsupported)
        if not new_files:
            return

        last_path = os.path.dirname(new_files[0])

        existing = set(os.path.normcase(os.path.abspath(f)) for f in selected_files)
        skipped_dupes = []

        for f in new_files:
            key = os.path.normcase(os.path.abspath(f))
            if key in existing:
                skipped_dupes.append(os.path.basename(f))
                continue
            selected_files.append(f)
            existing.add(key)

        merged_path = None
        refresh_tree()

        if skipped_dupes:
            names = "\n".join(skipped_dupes)
            messagebox.showinfo(
                "Some files already in list",
                f"These files are already in the list and were skipped:\n\n{names}"
            )

    def remove_selected():
        nonlocal selected_files, merged_path

        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Nothing selected", "Select one or more files in the list first.")
            return

        selected_set = set(selection)
        selected_files = [f for f in selected_files if f not in selected_set]
        merged_path = None
        refresh_tree()

    tree.bind("<Delete>", lambda e: remove_selected())

    def clear_list():
        nonlocal selected_files, merged_path

        selected_files.clear()
        merged_path = None
        refresh_tree()

        add_files()

    browse_btn.configure(command=add_files)
    remove_btn.configure(command=remove_selected)
    merge_btn.configure(command=merge_files)
    clear_btn.configure(command=clear_list)
    exit_btn.configure(command=exit_app)

    root.mainloop()

if __name__ == "__main__":
    run_explorer_gui()
