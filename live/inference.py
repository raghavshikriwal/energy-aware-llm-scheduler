"""Run actual LLM inference for the Live Demo.

Phase 2/3 state: no inference backend is required to exist yet. Calling
`run_inference()` before a backend is configured raises
`InferenceNotConfiguredError` with a clear message — the API layer turns
this into an honest error response, never a fabricated result.

Phase 5: set LIVE_INFERENCE_BACKEND=transformers and LIVE_MODEL_NAME to a
real Hugging Face model id (something that actually fits your GPU's VRAM,
e.g. a small instruct model) to switch this on for real.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional


class InferenceNotConfiguredError(RuntimeError):
    """Raised when inference is requested but no backend is set up yet."""


class InferenceError(RuntimeError):
    """Raised when a configured backend fails to produce a result."""


@dataclass
class InferenceResult:
    text: str
    input_tokens: int
    output_tokens: int

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


_lock = threading.Lock()
_model = None
_tokenizer = None
_loaded_model_name: Optional[str] = None


def backend_name() -> str:
    return os.environ.get("LIVE_INFERENCE_BACKEND", "none")


def is_configured() -> bool:
    return backend_name() != "none"


def _load_transformers_model(model_name: str):
    """Load a real Hugging Face model/tokenizer once, cached for the process."""
    global _model, _tokenizer, _loaded_model_name

    with _lock:
        if _model is not None and _loaded_model_name == model_name:
            return _model, _tokenizer

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise InferenceError(
                "LIVE_INFERENCE_BACKEND=transformers requires the "
                "'transformers' and 'torch' packages on the GPU worker "
                "(pip install transformers torch)."
            ) from exc

        device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name).to(device)
        model.eval()

        _model, _tokenizer, _loaded_model_name = model, tokenizer, model_name
        return model, tokenizer


def run_inference(prompt: str, max_new_tokens: int = 128) -> InferenceResult:
    """Run one real inference request and return real token counts + text.

    Raises InferenceNotConfiguredError if no backend is set up, or
    InferenceError if the configured backend fails. Never returns
    placeholder/fake text or counts.
    """
    backend = backend_name()

    if backend == "none":
        raise InferenceNotConfiguredError(
            "No inference backend is configured on this GPU worker yet. "
            "Set LIVE_INFERENCE_BACKEND and LIVE_MODEL_NAME to enable "
            "real inference (see live/inference.py)."
        )

    if backend == "transformers":
        model_name = os.environ.get("LIVE_MODEL_NAME")
        if not model_name:
            raise InferenceNotConfiguredError(
                "LIVE_INFERENCE_BACKEND=transformers but LIVE_MODEL_NAME "
                "is not set."
            )

        import torch

        model, tokenizer = _load_transformers_model(model_name)
        device = next(model.parameters()).device

        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        input_token_count = int(inputs["input_ids"].shape[1])

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )

        generated_ids = output_ids[0][input_token_count:]
        output_token_count = int(generated_ids.shape[0])
        text = tokenizer.decode(generated_ids, skip_special_tokens=True)

        return InferenceResult(
            text=text,
            input_tokens=input_token_count,
            output_tokens=output_token_count,
        )

    raise InferenceNotConfiguredError(
        f"Unknown LIVE_INFERENCE_BACKEND='{backend}'."
    )