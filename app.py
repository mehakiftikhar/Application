import streamlit as st
import fitz  # PyMuPDF
import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize Groq Client
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

def extract_form_fields(pdf_bytes):
    if not pdf_bytes or len(pdf_bytes) == 0:
        raise ValueError("Uploaded file is empty or not a valid PDF.")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}")

    form_fields = {}
    for page in doc:
        for widget in page.widgets():
            key = widget.field_name
            value = widget.field_value if widget.field_value else ""
            form_fields[key] = value

    return form_fields

def get_pdf_text(pdf_bytes):
    if not pdf_bytes or len(pdf_bytes) == 0:
        raise ValueError("Uploaded file is empty or not a valid PDF.")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}")

    text = ""
    for page in doc:
        text += page.get_text()
    return text

def get_field_details(form_fields, pdf_text):
    prompt = f"""
You are an expert at analyzing and auto-filling PDF form fields. 
Here is the extracted PDF text:
{pdf_text}

Based on this, explain the meaning or expected value of each of the following fields in JSON format:

{json.dumps(list(form_fields.keys()), indent=2)}

Return your output in the following JSON format:
{{ "field_name_1": "description", "field_name_2": "description", ... }}
    """

    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        explanation = response.choices[0].message.content
        return explanation
    except Exception as e:
        return f"Failed to analyze fields: {str(e)}"

# Streamlit UI
st.set_page_config(page_title="📄 Form Field Analyzer", layout="wide")
st.title("📄 Form Field Analyzer")
st.write("Upload a tax or registration form PDF. This tool extracts form fields and explains what each one likely means or requires.")

uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded_file:
    pdf_bytes = uploaded_file.read()

    if not pdf_bytes:
        st.error("Uploaded file is empty. Please upload a valid PDF file.")
    else:
        with st.spinner("🔍 Extracting form fields..."):
            try:
                fields = extract_form_fields(pdf_bytes)
                text = get_pdf_text(pdf_bytes)
                explanation = get_field_details(fields, text)

                st.subheader("📋 Extracted Form Fields")
                st.code(json.dumps(fields, indent=2), language='json')

                st.subheader("💡 Field Descriptions")
                st.code(explanation, language='json')

            except ValueError as ve:
                st.error(f"Error processing PDF: {ve}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")
