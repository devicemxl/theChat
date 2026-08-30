import streamlit as st


def get_secret(key: str) -> str:
    """Intenta obtener un secreto de forma segura desde los secrets de Streamlit.

    Devuelve cadena vacía si la key no existe o si el fichero secrets.toml
    no está configurado (en vez de reventar la aplicación).
    """
    try:
        return st.secrets[key] if key in st.secrets else ""
    except Exception:
        return ""
