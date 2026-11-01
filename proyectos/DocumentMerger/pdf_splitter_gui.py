import os
import tkinter as tk
from tkinter import filedialog, messagebox
# from PyPDF2 import PdfReader, PdfWriter
from pypdf import PdfReader, PdfWriter

MAX_SIZE_MB = 25
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

def split_pdf_by_size(input_pdf):
    reader = PdfReader(input_pdf)
    part = 1
    writer = PdfWriter()

    for page_number, page in enumerate(reader.pages):
        writer.add_page(page)

        # Write to temp file to check size
        temp_filename = f"temp_part_{part}.pdf"
        with open(temp_filename, "wb") as temp_file:
            writer.write(temp_file)

        current_size = os.path.getsize(temp_filename)

        if current_size > MAX_SIZE_BYTES:
            # Remove last page and save previous part
            writer.remove_page(len(writer.pages) - 1)

            output_filename = f"{os.path.splitext(input_pdf)[0]}_part_{part}.pdf"
            with open(output_filename, "wb") as output_file:
                writer.write(output_file)

            print(f"Created: {output_filename}")

            # Start new part
            part += 1
            writer = PdfWriter()
            writer.add_page(page)

        os.remove(temp_filename)

    # Save final part
    output_filename = f"{os.path.splitext(input_pdf)[0]}_part_{part}.pdf"
    with open(output_filename, "wb") as output_file:
        writer.write(output_file)

    print(f"Created: {output_filename}")
    return True


def browse_file():
    filename = filedialog.askopenfilename(
        title="Select PDF to Split",
        filetypes=[("PDF Files", "*.pdf")]
    )
    if filename:
        file_path_var.set(filename)


def start_split():
    pdf_path = file_path_var.get()
    if not pdf_path:
        messagebox.showerror("Error", "Please select a PDF file first.")
        return

    if not os.path.exists(pdf_path):
        messagebox.showerror("Error", "Selected file does not exist.")
        return

    try:
        split_pdf_by_size(pdf_path)
        messagebox.showinfo("Success", "PDF successfully split into <25 MB parts.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred:\n{e}")


# GUI Setup
root = tk.Tk()
root.title("PDF Splitter (<25 MB)")
root.geometry("500x180")
root.resizable(False, False)

file_path_var = tk.StringVar()

tk.Label(root, text="Select PDF to Split:", font=("Arial", 12)).pack(pady=10)

frame = tk.Frame(root)
frame.pack()

tk.Entry(frame, textvariable=file_path_var, width=50).pack(side=tk.LEFT, padx=5)
tk.Button(frame, text="Browse", command=browse_file).pack(side=tk.LEFT)

tk.Button(root, text="Split PDF", font=("Arial", 12), command=start_split).pack(pady=20)

root.mainloop()
