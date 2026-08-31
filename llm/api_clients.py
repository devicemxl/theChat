import json
import requests
from typing import List, Dict, Generator, Optional

# ========== CONSTANTES DE MODELOS ==========
MAX_TOKENS_DEEPSEEK = 8192
MAX_TOKENS_MISTRAL = 2000
MAX_TOKENS_GEMINI = None  # Sin límite explícito en Gemini
MAX_TOKENS_ANTHROPIC = 4096

# Versión de la API de Anthropic (requerida por el header 'anthropic-version')
ANTHROPIC_API_VERSION = "2023-06-01"

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
    reformulation_count: int,
    project_system_prompt: Optional[str] = None,
) -> List[Dict]:
    """Construye el contexto estándar para la API inyectando un System Prompt.

    Si `project_system_prompt` viene definido (no None, no cadena vacía), REEMPLAZA
    al default por completo, incluyendo la lógica de reformulación. Racional:
    si un proyecto tiene un prompt del estilo "eres parte de un pipeline, solo
    responde, no opines", inyectar el hint de reformulación va exactamente contra
    esa intención. El proyecto tiene la palabra final.
    """
    context = []

    if project_system_prompt:
        # El proyecto tomó control: se respeta su prompt tal cual.
        system_prompt = project_system_prompt
    else:
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
    model: str = "deepseek-reasoner", # "deepseek-chat"
    reasoning_effort: Optional[str] = None,
) -> Generator[str, None, None]:
    """Streaming para la API de DeepSeek.

    `reasoning_effort` acepta valores en español ('bajo'/'medio'/'alto') que se
    mapean al estándar de la API ('low'/'medium'/'high'). Solo aplica a modelos
    con capacidad de razonamiento (deepseek-reasoner y similares); en modelos
    chat regulares la API lo ignora sin fallar.
    """
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

    if reasoning_effort:
        _effort_map = {"bajo": "low", "medio": "medium", "alto": "high"}
        payload["reasoning_effort"] = _effort_map.get(reasoning_effort, reasoning_effort)

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


def stream_anthropic_completion(
    messages: List[Dict],
    api_key: str,
    model: str = "claude-sonnet-4-5-20250929",
    temperature: float = 0.7,
) -> Generator[str, None, None]:
    """Streaming para la API de Anthropic (Claude Messages API).

    - El 'system' se envía en un campo aparte (no como mensaje con role=system).
    - El streaming SSE emite eventos 'content_block_delta' con delta.text.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }

    # Anthropic separa el system del array de mensajes; si hay varios systems los concatenamos.
    system_prompt = None
    anthropic_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"] if system_prompt is None else system_prompt + "\n\n" + msg["content"]
        else:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    payload = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": MAX_TOKENS_ANTHROPIC,
        "temperature": temperature,
        "stream": True,
    }
    if system_prompt:
        payload["system"] = system_prompt

    try:
        with requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    json_data = json.loads(data)
                except json.JSONDecodeError:
                    continue

                event_type = json_data.get("type")
                if event_type == "content_block_delta":
                    delta = json_data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text")
                        if text:
                            yield text
                elif event_type == "message_stop":
                    break
                elif event_type == "error":
                    err = json_data.get("error", {})
                    yield f"⚠️ Error de Anthropic: {err.get('message', 'desconocido')}"
                    break
    except requests.exceptions.RequestException as e:
        yield f"⚠️ Error de conexión con Anthropic: {str(e)}"