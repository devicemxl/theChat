import json
import requests
from typing import List, Dict, Generator

# ========== CONSTANTES DE MODELOS ==========
MAX_TOKENS_DEEPSEEK = 8192
MAX_TOKENS_MISTRAL = 2000
MAX_TOKENS_GEMINI = None  # Sin límite explícito en Gemini

# ========== FUNCIONES DE DETECCIÓN DE REFORMULACIÓN ==========

def detect_reformulation(user_message: str) -> bool:
    """Detecta si el mensaje del usuario es una petición de reformulación"""
    reformulation_keywords = [
        "reformula", "reformular", "reformulación", "reformulacion",
        "rephrasing", "rephrase", "reformulate",
        "otra vez", "de nuevo", "again",
        "mejor", "better", "improve",
        "más claro", "clearer", "más simple", "simpler",
        "diferente", "different", "cambia", "change",
        "reescribe", "rewrite", "reescribir",
        "explica mejor", "explain better",
        "hazlo más", "make it more",
        "intenta de nuevo", "try again",
        "no me gusta", "i don't like",
        "no es lo que quería", "not what i wanted",
        "puedes mejorar", "can you improve",
        "más profesional", "more professional",
        "más formal", "more formal",
        "más informal", "more casual",
        "más corto", "shorter",
        "más largo", "longer",
        "más detallado", "more detailed",
        "más conciso", "more concise"
    ]

    message_lower = user_message.lower()
    for keyword in reformulation_keywords:
        if keyword in message_lower:
            return True
    return False


def build_context_with_reformulation_awareness(
    messages: List[Dict],
    is_reformulation: bool,
    reformulation_count: int
) -> List[Dict]:
    """Construye el contexto estándar para la API inyectando un System Prompt."""
    context = []

    system_prompt = """Eres un asistente experto y útil.
Si el usuario pide una reformulación, prioriza la nueva versión de la pregunta.
Responde de manera clara, concisa y precisa."""

    if is_reformulation:
        system_prompt += f"""

        ⚠️ El usuario está reformulando su pregunta (intento #{reformulation_count}).
        Mantén la intención original pero mejora la respuesta anterior.
        Aplica los cambios específicos que el usuario solicite.
        """

    context.append({"role": "system", "content": system_prompt})

    for msg in messages:
        context.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    return context


# ========== FUNCIONES DE STREAMING DE APIS ==========

def stream_deepseek_completion(
    messages: List[Dict],
    api_key: str,
    model: str = "deepseek-chat",
) -> Generator[str, None, None]:
    """Streaming para la API de DeepSeek."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS_DEEPSEEK,
        "stream": True
    }

    try:
        with requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, stream=True, timeout=30) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            json_data = json.loads(data)
                            if "choices" in json_data and json_data["choices"]:
                                delta = json_data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
    except requests.exceptions.RequestException as e:
        yield f"⚠️ Error de conexión con DeepSeek: {str(e)}"


def stream_mistral_completion(
    messages: List[Dict],
    api_key: str,
    model: str = "mistral-small-latest",
) -> Generator[str, None, None]:
    """Streaming para la API de Mistral AI."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS_MISTRAL,
        "stream": True
    }

    try:
        with requests.post(
            url="https://api.mistral.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            json_data = json.loads(data)
                            if "choices" in json_data and json_data["choices"]:
                                delta = json_data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
    except requests.exceptions.RequestException as e:
        yield f"⚠️ Error de conexión con Mistral: {str(e)}"


def stream_gemini_completion(
    messages: List[Dict],
    api_key: str,
    model: str = "gemini-1.5-flash"
) -> Generator[str, None, None]:
    """Streaming nativo para Google AI Studio (Gemini)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
    headers = {"Content-Type": "application/json"}

    # Gemini requiere un formato especial, aislando el "system" en "system_instruction"
    system_instruction = None
    gemini_contents = []

    for msg in messages:
        if msg["role"] == "system":
            system_instruction = {"parts": [{"text": msg["content"]}]}
        else:
            # Gemini usa "user" y "model" (en lugar de "assistant")
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

    payload = {"contents": gemini_contents}
    if system_instruction:
        payload["system_instruction"] = system_instruction

    try:
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=30) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]" or not data.strip():
                            continue
                        try:
                            json_data = json.loads(data)
                            if "candidates" in json_data and json_data["candidates"]:
                                parts = json_data["candidates"][0].get("content", {}).get("parts", [])
                                if parts and "text" in parts[0]:
                                    yield parts[0]["text"]
                        except json.JSONDecodeError:
                            continue
    except requests.exceptions.RequestException as e:
        yield f"⚠️ Error de conexión con Gemini: {str(e)}"