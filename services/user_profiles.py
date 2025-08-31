import httpx
from core.settings import OPENAI_API_KEY, OPENAI_MODEL

async def extract_name_with_llm(user_message: str) -> str:
    """
    Usa un modelo LLM para intentar extraer un nombre propio desde un mensaje libre.
    Retorna el nombre o None si no se puede extraer.
    """
    prompt = (
        "Dado el siguiente mensaje de un usuario, si puedes identificar el nombre del remitente, "
        "devuelve solamente ese nombre en una sola línea. Ten en cuenta si la persona pide hablar con alguien, no es su nombre. "
        "Intenta corregir errores de ortografía. "
        "Si no hay nombre, o la persona no quiere dar su nombre, responde 'NO'.\n\n"
        f"Mensaje: {user_message}\n\n"
        "Respuesta:"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                    "max_tokens": 20,
                }
            )
            response.raise_for_status()
            result = response.json()
            name = result["choices"][0]["message"]["content"].strip()

            if name.lower() in ["no", "ninguno"]:
                return None
            return name.title()
    except Exception as e:
        print(f"⚠️ Error extrayendo nombre con LLM: {e}")
        return None
