import io
from typing import List, Dict, Tuple

def extract_text_from_file(uploaded_file) -> str:
    """
    Extrae el texto de un archivo subido según su extensión.
    Soporta: .txt, .md, .pdf, .docx, .csv, .json, .py, .js, .html, .css, .xml, .sql
    """
    # Si no tiene extensión, intentamos leer como texto
    if '.' not in uploaded_file.name:
        try:
            return uploaded_file.getvalue().decode("utf-8", errors="ignore")
        except:
            return "[Contenido binario no legible]"

    file_extension = uploaded_file.name.split('.')[-1].lower()
    content = ""

    try:
        if file_extension in ["txt", "md"]:
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        elif file_extension == "pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                for page in reader.pages:
                    content += page.extract_text() + "\n"
            except ImportError:
                content = "[Error: pypdf no está instalado. Instálalo con 'pip install pypdf']"
        elif file_extension == "docx":
            try:
                from docx import Document
                doc = Document(io.BytesIO(uploaded_file.getvalue()))
                for para in doc.paragraphs:
                    content += para.text + "\n"
            except ImportError:
                content = "[Error: python-docx no está instalado. Instálalo con 'pip install python-docx']"
        elif file_extension == "csv":
            try:
                import pandas as pd
                df = pd.read_csv(io.BytesIO(uploaded_file.getvalue()))
                content = df.to_string()
            except ImportError:
                content = "[Error: pandas no está instalado. Instálalo con 'pip install pandas']"
        elif file_extension in ["json", "py", "js", "html", "css", "xml", "sql"]:
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        else:
            # Intento genérico como texto para extensiones desconocidas
            try:
                content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            except:
                content = "[Contenido binario no legible]"
    except Exception as e:
        content = f"[Error al leer el archivo: {str(e)}]"

    return content.strip()


def extract_files_from_message(content: str) -> Tuple[str, List[Dict]]:
    """
    Extrae el prompt principal y los archivos adjuntos de un mensaje de texto completo.
    Busca el patrón "--- Contenido de '...' ---"
    """
    if "--- Contenido de '" not in content:
        return content, []

    parts = content.split("--- Contenido de '")
    prompt = parts[0].strip()
    files = []

    for part in parts[1:]:
        if "' ---" in part:
            filename = part.split("' ---")[0]
            file_content = part.split("' ---")[1].strip()
            files.append({
                "name": filename,
                "content": file_content
            })

    return prompt, files