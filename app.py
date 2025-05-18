import os
import io
import re
import ast
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
import requests
import gradio as gr
import streamlit as st
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import NameObject, BooleanObject
from pdf2image import convert_from_bytes
from groq import Groq

# 🔐 Initialize GROQ client
client = Groq(api_key=st.secrets["GROQ_API_KEY"])
MODEL = "llama3-8b-8192"

# 📥 Helpers
def extract_text_from_pdf(file_bytes):
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def extract_text_with_ocr(file_bytes):
    images = convert_from_bytes(file_bytes)
    return "\n".join(pytesseract.image_to_string(img) for img in images)

def extract_all_fields_from_text(text):
    data = {}
    for line in text.splitlines():
        line = line.strip("• ").strip()
        if not line:
            continue

        match_colon = re.match(r"^([A-Za-z\s\/\(\)\[\]\-\.]+?)[:：]\s*(.+)$", line)
        if match_colon:
            data[match_colon.group(1).strip()] = match_colon.group(2).strip()
            continue

        match_dots = re.match(r"^([A-Za-z\s\/\(\)\[\]\-\.]+?)\s*[\.\-]{2,}\s*(.+)$", line)
        if match_dots:
            data[match_dots.group(1).strip()] = match_dots.group(2).strip()
            continue

        words = line.split()
        for i in reversed(range(1, min(5, len(words)))):
            label = " ".join(words[:i])
            value = " ".join(words[i:])
            if len(label) > 1 and len(value) > 1:
                data[label] = value
                break

    return data

def extract_labels_from_text(file_bytes):
    labels = set()
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                matches = re.findall(r"(?:\d+\.\s*)?([A-Za-z\s\/\(\)]+):", line)
                for match in matches:
                    clean = match.strip()
                    if len(clean) > 1:
                        labels.add(clean)
    return list(labels)

def extract_acroform_fields(reader):
    fields = reader.get_fields()
    return list(fields.keys()) if fields else []

def get_field_mapping_from_llm(form_fields, user_data):
    prompt = f"""
You are a form-filling assistant. Match the FORM FIELD NAMES with the closest values from USER DATA.

FORM FIELDS:
{form_fields}

USER DATA (key-value pairs):
{user_data}

Return a Python dict that maps each FORM FIELD to:
- The best matching USER DATA field name, or
- A Python expression using user fields (e.g., "First Name + ' ' + Last Name"), or
- `None` if no match is found.
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a form-matching assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    content = response.choices[0].message.content.strip()
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            return ast.literal_eval(match.group(0))
        except Exception:
            pass
    return {}

def reconstruct_user_data(field_mapping, raw_user_data):
    final_data = {}
    for form_field, user_expr in field_mapping.items():
        if user_expr is None:
            continue
        try:
            value = eval(user_expr, {}, raw_user_data)
        except Exception:
            value = raw_user_data.get(user_expr) if isinstance(user_expr, str) else None
        if value:
            final_data[form_field] = value
    return final_data

def fill_pdf_acroform(template_bytes, user_data):
    reader = PdfReader(io.BytesIO(template_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.update_page_form_field_values(writer.pages[0], user_data)
    writer._root_object.update({NameObject("/NeedAppearances"): BooleanObject(True)})
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

# 🎯 Main App Logic
def process_pdf(form_url_or_file):
    if isinstance(form_url_or_file, str) and form_url_or_file.startswith("http"):
        response = requests.get(form_url_or_file)
        pdf_bytes = response.content
    else:
        pdf_bytes = form_url_or_file.read()

    text = extract_text_from_pdf(pdf_bytes)
    if len(text.strip()) < 30:
        text = extract_text_with_ocr(pdf_bytes)

    raw_user_data = extract_all_fields_from_text(text)
    pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
    form_fields = extract_acroform_fields(pdf_reader) or extract_labels_from_text(pdf_bytes)

    if not form_fields:
        return "❌ No form fields found.", None

    field_mapping = get_field_mapping_from_llm(form_fields, raw_user_data)
    filled_data = reconstruct_user_data(field_mapping, raw_user_data)
    filled_pdf = fill_pdf_acroform(pdf_bytes, filled_data)

    return "✅ Form filled successfully!", ("filled_form.pdf", filled_pdf)

# 🌐 Gradio Interface
def gradio_interface(file_or_url):
    try:
        message, result = process_pdf(file_or_url)
        if result:
            return message, result
        return message, None
    except Exception as e:
        return f"❌ Error: {str(e)}", None

with gr.Blocks() as demo:
    gr.Markdown("## 📝 Smart Form Auto-Filler")
    gr.Markdown("Upload a filled form or provide the PDF form URL. The assistant will extract your details and auto-fill the form fields.")
    inp = gr.File(label="Upload your filled document")  # or use gr.Textbox(label="Form URL")
    out_text = gr.Textbox(label="Status")
    out_file = gr.File(label="Download Filled Form")

    btn = gr.Button("Auto-Fill Form")
    btn.click(fn=gradio_interface, inputs=inp, outputs=[out_text, out_file])

demo.launch()
