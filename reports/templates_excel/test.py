import fitz  # PyMuPDF

def pdf_to_text(file_path):
    try:
        doc = fitz.open(file_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        return full_text
    except Exception as e:
        return f"Error reading PDF: {e}"

# Replace with your actual file path
pdf_file = "FEDCL_5690588_2022vv1896-43.pdf"

text = pdf_to_text(pdf_file)
print(text)