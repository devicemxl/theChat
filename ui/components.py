import base64
import streamlit as st
import streamlit.components.v1 as components

def add_copy_button(text: str, key: str):
    """
    Renderiza un botón de copiar usando un Iframe HTML puro.
    Esto evita el error 'Minified React error #231' en Streamlit
    y asegura soporte completo para UTF-8 (acentos, emojis) y Markdown.
    """
    # 1. Codificamos a base64 asegurando el soporte UTF-8
    text_b64 = base64.b64encode(text.encode('utf-8')).decode('utf-8')

    # 2. Creamos un mini-documento HTML aislado
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: sans-serif;
            display: flex;
            justify-content: flex-end; /* Alinea el botón a la derecha */
            background-color: transparent;
        }}
        .copy-btn {{
            background: transparent;
            border: 1px solid #d3d4d6;
            color: #888;
            cursor: pointer;
            font-size: 13px;
            padding: 4px 10px;
            border-radius: 5px;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
        }}
        /* Efecto hover hecho con CSS puro en vez de JavaScript */
        .copy-btn:hover {{
            border-color: #FF4B4B;
            color: #FF4B4B;
        }}
        .feedback {{
            display: none;
            color: #28a745;
            font-size: 13px;
            margin-left: 8px;
            line-height: 26px;
            font-weight: bold;
        }}
    </style>
    </head>
    <body>
        <button class="copy-btn" id="btn" title="Copiar en formato Markdown">
            📋 Copiar MD
        </button>
        <span class="feedback" id="feedback">✅ ¡Copiado!</span>

        <script>
            document.getElementById('btn').addEventListener('click', function() {{
                
                // Decodificar Base64 de vuelta a texto respetando UTF-8
                const b64 = '{text_b64}';
                const bin = atob(b64);
                const bytes = new Uint8Array(bin.length);
                for(let i = 0; i < bin.length; i++) {{
                    bytes[i] = bin.charCodeAt(i);
                }}
                const decodedText = new TextDecoder('utf-8').decode(bytes);
                
                // Función segura para copiar incluso desde dentro de un Iframe
                const copyToClipboard = async () => {{
                    try {{
                        await navigator.clipboard.writeText(decodedText);
                        return true;
                    }} catch (err) {{
                        // Fallback de emergencia
                        const textarea = document.createElement('textarea');
                        textarea.value = decodedText;
                        textarea.style.position = 'fixed';
                        textarea.style.opacity = '0';
                        document.body.appendChild(textarea);
                        textarea.select();
                        try {{
                            document.execCommand('copy');
                            document.body.removeChild(textarea);
                            return true;
                        }} catch (e) {{
                            document.body.removeChild(textarea);
                            return false;
                        }}
                    }}
                }};

                copyToClipboard().then((success) => {{
                    if (success) {{
                        const f = document.getElementById('feedback');
                        f.style.display = 'inline-block';
                        setTimeout(() => f.style.display = 'none', 2000);
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    # 3. Lo inyectamos como un componente nativo de HTML
    # height=35 evita que aparezca una barra de scroll vertical
    components.html(html_code, height=35)


def load_custom_css():
    """
    Inyecta los estilos CSS personalizados para la aplicación Streamlit.
    """
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { max-width: 300px; }
        [data-testid="stMainMenu"] { display: none; }
        body{ line-height: 1; text-size-adjust: 80%; }
        .st-emotion-cache-liupih {
            width: 100%;
            padding: 2rem 0rem 1rem;
            max-width: initial;
            min-width: auto;
            z-index: 100;
        }
        @media (min-width: calc(736px + 8rem)) {
            .st-emotion-cache-liupih {
                padding-left: 2rem;
                padding-right: 2rem;
            }
        }
        .stAppToolbar, .stAppHeader { background-color: transparent; }

        /* Mejorar la visualización de archivos adjuntos */
        .stMain .stExpander {
            border-left: 3px solid #FF4B4B;
            border-radius: 5px;
        }

        /* Limitar altura de código en expanders */
        .stExpander .stCode {
            max-height: 300px;
            overflow-y: auto;
        }

        /* Mejorar el mensaje del usuario cuando tiene archivos */
        div[data-testid="stChatMessage"]:has(.stExpander) {
            background-color: #f0f2f6;
            border-radius: 10px;
            padding: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )