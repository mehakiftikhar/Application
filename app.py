import streamlit as st
import fitz  # PyMuPDF
import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize Groq Client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def extract_form_fields(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    form_fields = {}

    for page in doc:
        for widget in page.widgets():
            key = widget.field_name
            value = widget.field_value if widget.field_value else ""
            form_fields[key] = value

    return form_fields

def get_pdf_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
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
        model="mixtral-8x7b-32768",
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
    
    with st.spinner("🔍 Extracting form fields..."):
        fields = extract_form_fields(pdf_bytes)
        text = get_pdf_text(pdf_bytes)
        explanation = get_field_details(fields, text)

    st.subheader("📋 Extracted Form Fields")
    st.code(json.dumps(fields, indent=2), language='json')

    st.subheader("💡 Field Descriptions")
    st.code(explanation, language='json')
