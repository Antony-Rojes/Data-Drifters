import json
import random
import re
import time

from google import genai
from google.genai import types

from backend import config, prompts

_client = None
_RETRYABLE = ("429", "500", "502", "503", "504",
              "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED")
EMBED_BATCH = 50


def _get_client():
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file.")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _models():
    models = [config.GEMINI_MODEL]
    if config.GEMINI_FALLBACK_MODEL and config.GEMINI_FALLBACK_MODEL not in models:
        models.append(config.GEMINI_FALLBACK_MODEL)
    return models


def _with_retry(request, models, retries_per_model=5):
    """Runs request(model). Retries busy errors with backoff, then tries the next model."""
    last_error = "unknown error"
    for model in models:
        for attempt in range(retries_per_model):
            try:
                return request(model)
            except Exception as e:
                last_error = str(e)
                if any(code in last_error for code in _RETRYABLE):
                    # wait 1s, 2s, 4s, 8s, 16s (plus a little randomness), then retry
                    time.sleep(min(2 ** attempt, 30) + random.random())
                    continue
                if "404" in last_error or "NOT_FOUND" in last_error:
                    break  # wrong model name: move to the next model, if any
                raise RuntimeError(f"Gemini call failed: {last_error}")
    raise RuntimeError(
        "Gemini is busy or the model name is wrong. Wait a minute and try again. "
        f"Last error: {last_error}"
    )


def _call(contents, json_mode):
    cfg = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    response = _with_retry(
        lambda model: _get_client().models.generate_content(model=model, contents=contents, config=cfg),
        _models(),
    )
    return response.text or ""


def generate_json(prompt):
    text = _call(prompt, json_mode=True).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def ocr_page(png_bytes):
    image = types.Part.from_bytes(data=png_bytes, mime_type="image/png")
    return _call([image, prompts.OCR_PROMPT], json_mode=False)


def embed_texts(texts, task_type):
    """Meaning vectors for a list of texts. task_type: RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY."""
    cfg = types.EmbedContentConfig(task_type=task_type, output_dimensionality=config.EMBED_DIMS)
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        response = _with_retry(
            lambda model: _get_client().models.embed_content(model=model, contents=batch, config=cfg),
            [config.GEMINI_EMBED_MODEL],
        )
        vectors.extend(list(e.values) for e in response.embeddings)
    if len(vectors) != len(texts):
        raise RuntimeError("Embedding count does not match the number of texts.")
    return vectors


def generate_text(prompt):
    """Plain text answer (used by the evaluation baseline)."""
    return _call(prompt, json_mode=False)
