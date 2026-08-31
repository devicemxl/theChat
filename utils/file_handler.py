import io
from pathlib import Path
from typing import List, Dict, Tuple


# Extensiones que requieren un extractor especial (binario o formato estructurado).
# Todo lo demás se intenta leer como texto UTF-8.
SPECIAL_EXTRACTION = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".csv": "csv",
}


def extract_text_from_bytes(data: bytes, filename: str) -> str:
    """Extrae texto de un archivo a partir de sus bytes.

    Es la función central de extracción de texto. Tanto los adjuntos del chat
    como la ingesta RAG pasan por aquí; nunca debe haber dos implementaciones.
    """
    ext = Path(filename).suffix.lower()

    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

        if ext == ".docx":
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs).strip()

        if ext == ".csv":
            import pandas as pd
            df = pd.read_csv(io.BytesIO(data))
            return df.to_string()

        # Texto plano: intento genérico con UTF-8.
        return data.decode("utf-8", errors="ignore").strip()
    except Exception as e:
        return f"[Error al extraer texto: {e}]"


def extract_text_from_file(uploaded_file) -> str:
    """Extrae texto de un UploadedFile de Streamlit (wrapper de bytes)."""
    return extract_text_from_bytes(uploaded_file.getvalue(), uploaded_file.name)


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