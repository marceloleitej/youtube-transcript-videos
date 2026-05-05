"""AI-powered transcription summarization via Gemini."""

import os
from typing import Generator

DEFAULT_MODEL = "gemini-2.0-flash"


PROMPT_SUMMARY = """Voce analisa a transcricao de um video e produz um resumo estruturado em portugues do Brasil.

Formato de saida (Markdown):

## Resumo
Dois ou tres paragrafos cobrindo o tema central e a mensagem principal.

## Pontos Principais
- Liste de 5 a 10 pontos-chave abordados, em ordem de aparicao.

## Conclusoes / Takeaways
- Liste o que fica de mais importante para o leitor.

---
TRANSCRICAO:
{transcript}
"""

PROMPT_CHAPTERS = """Voce analisa a transcricao abaixo e identifica capitulos/segmentos tematicos do video.

Para cada capitulo, forneca:
- Um titulo curto e descritivo (3-6 palavras)
- Um resumo de 1-2 frases

Formato de saida (Markdown):

## Capitulos

### 1. Titulo do capitulo
Resumo do capitulo.

### 2. Titulo do capitulo
Resumo do capitulo.

(continua...)

---
TRANSCRICAO:
{transcript}
"""

PROMPT_QA = """Voce tem acesso a transcricao abaixo e responde perguntas sobre ela.
Responda apenas com base no conteudo da transcricao. Se a informacao nao estiver presente, diga claramente.

Pergunta: {question}

---
TRANSCRICAO:
{transcript}
"""


PROMPTS = {
    "summary": ("Resumo Executivo", PROMPT_SUMMARY),
    "chapters": ("Capitulos / Topicos", PROMPT_CHAPTERS),
    "qa": ("Perguntas e Respostas", PROMPT_QA),
}


def check_gemini() -> tuple[bool, str]:
    """Check if Gemini is configured."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return False, "GEMINI_API_KEY nao configurada no .env"
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        list(client.models.list())[:1]  # quick probe
        return True, "Gemini OK"
    except Exception as e:
        return False, f"Erro Gemini: {e}"


def list_models() -> list[str]:
    """Return available Gemini text models."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return [DEFAULT_MODEL]
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        result = []
        for m in client.models.list():
            if "gemini" not in m.name:
                continue
            if "generateContent" not in (m.supported_actions or []):
                continue
            name_lower = m.name.lower()
            if any(skip in name_lower for skip in ("image", "embedding", "aqa", "tts")):
                continue
            result.append(m.name.removeprefix("models/"))
        return result or [DEFAULT_MODEL]
    except Exception:
        return [DEFAULT_MODEL, "gemini-2.5-flash", "gemini-2.5-pro"]


def summarize_stream(
    transcript: str,
    mode: str = "summary",
    question: str = "",
    model: str = DEFAULT_MODEL,
) -> Generator[str, None, None]:
    """Stream Gemini output. mode: 'summary' | 'chapters' | 'qa'."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao configurada no .env")
    if not transcript.strip():
        raise RuntimeError("Transcricao vazia.")

    _, template = PROMPTS.get(mode, PROMPTS["summary"])
    prompt = template.replace("{transcript}", transcript)
    if mode == "qa":
        if not question.strip():
            raise RuntimeError("Pergunta vazia.")
        prompt = prompt.replace("{question}", question)

    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content_stream(model=model, contents=prompt)
    for chunk in response:
        if chunk.text:
            yield chunk.text
