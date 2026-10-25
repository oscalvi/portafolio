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
