# Document Merger

A small Windows desktop app that joins several documents into **one PDF**.
Designed by Oscar Alvarez Villarreal and coded with AI.

## What it does

- Pick the files to merge: **PDF, Word (.docx) and text (.txt)**. Other types are skipped with a warning.
- See them in a list with their Windows icon, type and size; add more, remove some or clear the list.
- Each document starts with a **separator page** showing its file name, so the merged PDF is easy to navigate.
- Word and text files are converted to PDF on the fly (text and headings; tables and images in .docx are not carried over).
- Choose where to save (by default, the source folder with a date-stamped name). A progress bar shows the merge, and when it finishes Windows Explorer opens with the new file selected.

## Run it

Double-click **`Start Document Merger.bat`**. It checks that Python is installed, installs the libraries the first time (`requirements.txt`) and opens the app — no technical steps for the user.

By hand: `pip install -r requirements.txt` and then `python DocumentMerger.py`.

## Built with

Python · Tkinter (ttk) · PyPDF2 · ReportLab · python-docx · Pillow · Windows API through `ctypes` (file icons and real paths for OneDrive/Desktop folders).

Windows only.

---

# PDF Splitter (same folder)

The opposite job: splits **one large PDF** into smaller parts, each one no bigger than the size you choose (25 MB by default), so it can be attached to an email or uploaded to a form with a size limit.

- Pick the PDF, the folder for the parts and the maximum size; click **Split PDF**.
- Parts are named `<name>_part_1.pdf`, `_part_2.pdf`… and keep the original page order.
- Fast on long documents: it measures each page once and only writes a part for real when it gets close to the limit.
- A single page bigger than the limit can't be split; it goes alone in its own part and the app tells you which page it was.
- Password-protected PDFs are reported instead of failing silently.

Run it with **`Start PDF Splitter.bat`** (same libraries as Document Merger), or `python PdfSplitter.py`.

