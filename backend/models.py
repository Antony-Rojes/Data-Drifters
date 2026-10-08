"""Local Open-Weight Model Integration Interface (Qwen / Gemma / Local Providers).

Provides an abstract interface for locally hosted LLM engines (via vLLM, Ollama,
LM Studio, llama.cpp, or any OpenAI-compatible local server) without external cloud APIs.
"""
from abc import ABC, abstractmethod
import json
import os
import re
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


class BaseLLMProvider(ABC):
    """Abstract interface for local legal reasoning models."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.1) -> str:
        """Generate text completion from a prompt."""
        pass

    @abstractmethod
    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate structured JSON response adhering to a schema or requested format."""
        pass


class LocalOpenAIProvider(BaseLLMProvider):
    """Interacts with local open-weight model instances (e.g., Qwen3-32B or Gemma-3-27B)
    running via local OpenAI-compatible APIs (vLLM, Ollama, LM Studio, llama.cpp).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 60,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", "qwen2.5:32b")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "local")
        self.timeout = timeout

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Failed to communicate with local model endpoint at {url} ({self.model_name}): {e}"
            ) from e

    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.1) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        res = self._post("chat/completions", payload)
        choices = res.get("choices") or []
        if not choices:
            raise RuntimeError(f"Local model {self.model_name} returned no completion choices.")
        return choices[0].get("message", {}).get("content", "").strip()

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        full_system = (
            (system_prompt or "")
            + "\nRespond ONLY with a valid, parseable JSON object. Do not enclose in markdown ticks if possible."
        )
        raw_text = self.generate(prompt, system_prompt=full_system, temperature=0.0)
        # Clean json markdown fences if present
        clean = re.sub(r"^```(?:json)?", "", raw_text.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"```$", "", clean.strip()).strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Fallback regex search for json block
            match = re.search(r"(\{.*\}|\[.*\])", clean, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError(f"Could not parse valid JSON from local model output: {raw_text[:200]}")


class MockLocalLLMProvider(BaseLLMProvider):
    """Deterministic local mock provider for unit testing, offline environments,
    and testing without a running GPU inference server.
    """

    def __init__(self, model_name: str = "mock-qwen-local"):
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.1) -> str:
        if "VERIFIED EVIDENCE PASSAGES:" in prompt:
            block = prompt.split("VERIFIED EVIDENCE PASSAGES:")[1].split("INSTRUCTIONS:")[0].strip()
            lines = [ln.strip() for ln in block.split("\n") if ln.strip() and not ln.startswith("[")]
            if lines:
                return f"According to the records, {lines[0]}"
        return (
            "Based strictly on the verified case documents, the record indicates pertinent factual "
            "and legal details concerning the matter."
        )

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        if "VERIFIED EVIDENCE PASSAGES:" in prompt:
            block = prompt.split("VERIFIED EVIDENCE PASSAGES:")[1].split("KNOWN FACTS:")[0].strip()
            match = re.search(r"\[([a-zA-Z0-9_\-]+)\][^\n]*\n([^\n]+)", block)
            if match:
                cid, ptext = match.group(1), match.group(2).strip()
                return {
                    "sentences": [
                        {
                            "text": f"The verified filing confirms that {ptext}",
                            "type": "fact",
                            "citations": [{"chunk_id": cid, "quote": ptext[:120]}],
                        }
                    ]
                }
        return {
            "sentences": [
                {
                    "text": "The record confirms the specific filings and identities attested in the documents.",
                    "type": "fact",
                    "citations": [],
                }
            ]
        }


def get_llm_provider(provider_type: Optional[str] = None) -> BaseLLMProvider:
    """Factory to retrieve configured model provider."""
    p_type = (provider_type or os.getenv("LLM_PROVIDER", "local_openai")).lower().strip()
    if p_type in ("mock", "test", "offline"):
        return MockLocalLLMProvider()
    return LocalOpenAIProvider()
