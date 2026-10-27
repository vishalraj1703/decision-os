"""Qualcomm Cloud AI Playground client: chat, embeddings, reranker.

Notes from the platform (verified in the python-imagine-sdk 0.5.0 source and API docs):
- Base URL https://aisuite.cirrascale.com/apis/v2, Bearer key.
- No JSON / response_format mode; structured output comes from the prompt or from
  tool calling.
- A missing or bad key is answered with HTTP 500, and the Imagine SDK retries 5xx with
  4 s / 8 s backoff. We disable SDK retries (max_retries=1 means a single attempt) so
  our own retry policy controls the time budget.
- The Imagine SDK defaults to verify=False for TLS; we pass verify=True.
- The Playground keeps chat history server-side for the account.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from .config import Settings

log = logging.getLogger("decisionos.qualcomm")


class QualcommError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class ChatResult:
    text: str
    tool_arguments: dict | None
    model: str
    latency_ms: int
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None


def _classify(exc: Exception) -> QualcommError:
    text = str(exc)
    low = text.lower()
    name = type(exc).__name__
    if "api key" in low or "authorization" in low or "unauthorized" in low or " 401" in text or " 403" in text:
        return QualcommError("AUTH", "Qualcomm rejected the API key. Check QUALCOMM_API_KEY.", False)
    if "TooManyRequests" in name or "429" in text:
        return QualcommError("RATE_LIMITED", "Qualcomm is rate limiting requests. Retry shortly.", True)
    if "timeout" in low or "timed out" in low:
        return QualcommError("TIMEOUT", "Qualcomm did not answer in time.", True)
    if "Connection" in name or "connect" in low:
        return QualcommError("UNREACHABLE", "Could not reach Qualcomm Cloud AI.", True)
    if any(c in text for c in (" 500", " 502", " 503", " 504")):
        return QualcommError("UPSTREAM", "Qualcomm returned a server error.", True)
    return QualcommError("UPSTREAM", "Qualcomm returned an unexpected error.", True)


class Qualcomm:
    def __init__(self, s: Settings):
        if not s.qualcomm_api_key:
            raise QualcommError("NO_KEY", "QUALCOMM_API_KEY is not set.", False)
        self.s = s
        self._imagine = None
        self._openai = None

    @property
    def model(self) -> str:
        return self.s.qualcomm_model

    def _imagine_client(self):
        if self._imagine is None:
            from imagine import ImagineClient

            self._imagine = ImagineClient(
                endpoint=self.s.qualcomm_endpoint, api_key=self.s.qualcomm_api_key,
                max_retries=1, timeout=int(self.s.call_timeout_s), verify=True,
            )
        return self._imagine

    def _openai_client(self):
        if self._openai is None:
            from openai import OpenAI

            self._openai = OpenAI(
                api_key=self.s.qualcomm_api_key, base_url=self.s.qualcomm_endpoint,
                timeout=self.s.call_timeout_s, max_retries=0,
            )
        return self._openai

    def chat(self, messages: list[dict], *, max_tokens: int | None = None, temperature: float = 0.1,
             tool: dict | None = None, client: str | None = None) -> ChatResult:
        """One chat completion.

        Default path is streaming ("stream"). Verified against the live Playground on
        2026-10-27: a NON-streaming reply whose text looks like JSON is converted by the
        server into an empty tool call (content "", arguments "{}"), so the answer is lost.
        Streaming returns the generated text intact.
        """
        which = client or self.s.qualcomm_client
        if which in ("stream", "imagine") and tool is None:
            return self._chat_stream(messages, max_tokens=max_tokens, temperature=temperature)
        return self._chat_once(messages, max_tokens=max_tokens, temperature=temperature, tool=tool, which=which)

    def _chat_stream(self, messages: list[dict], *, max_tokens: int | None, temperature: float) -> ChatResult:
        import httpx

        url = self.s.qualcomm_endpoint.rstrip("/") + "/chat/completions"
        body = {"model": self.s.qualcomm_model, "messages": messages, "stream": True,
                "temperature": temperature, "max_tokens": max_tokens or self.s.max_tokens}
        headers = {"Authorization": f"Bearer {self.s.qualcomm_api_key}", "Accept": "text/event-stream"}
        timeout = httpx.Timeout(self.s.call_timeout_s, connect=10.0)
        t0 = time.perf_counter()
        parts: list[str] = []
        finish = None
        usage: dict = {}
        model = self.s.qualcomm_model
        try:
            with httpx.stream("POST", url, json=body, headers=headers, timeout=timeout, verify=True) as resp:
                if resp.status_code != 200:
                    detail = resp.read().decode("utf-8", "replace")[:200]
                    if resp.status_code in (401, 403) or "api key" in detail.lower() or "authorization" in detail.lower():
                        raise QualcommError("AUTH", "Qualcomm rejected the API key. Check QUALCOMM_API_KEY.", False)
                    if resp.status_code == 429:
                        raise QualcommError("RATE_LIMITED", "Qualcomm is rate limiting requests. Retry shortly.", True)
                    raise QualcommError("UPSTREAM", f"Qualcomm returned HTTP {resp.status_code}.", resp.status_code >= 500)
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except ValueError:
                        continue
                    model = chunk.get("model") or model
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for ch in chunk.get("choices") or []:
                        delta = ch.get("delta") or {}
                        if delta.get("content"):
                            parts.append(delta["content"])
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
        except QualcommError:
            raise
        except Exception as e:  # noqa: BLE001 - httpx raises several exception types
            err = _classify(e)
            log.warning("qualcomm stream failed code=%s type=%s", err.code, type(e).__name__)
            raise err from None
        return ChatResult(
            text="".join(parts), tool_arguments=None, model=model,
            latency_ms=int((time.perf_counter() - t0) * 1000), finish_reason=finish,
            prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
        )

    def _chat_once(self, messages: list[dict], *, max_tokens: int | None, temperature: float,
                   tool: dict | None, which: str) -> ChatResult:
        t0 = time.perf_counter()
        t0 = time.perf_counter()
        try:
            if which == "openai":
                kwargs = {}
                if tool:
                    kwargs["tools"] = [tool]
                    kwargs["tool_choice"] = {"type": "function", "function": {"name": tool["function"]["name"]}}
                r = self._openai_client().chat.completions.create(
                    model=self.s.qualcomm_model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens or self.s.max_tokens, stream=False, **kwargs,
                )
                choice = r.choices[0]
                args = None
                if choice.message.tool_calls:
                    args = _parse_args(choice.message.tool_calls[0].function.arguments)
                usage = r.usage
                return ChatResult(
                    text=choice.message.content or "", tool_arguments=args, model=r.model or self.s.qualcomm_model,
                    latency_ms=int((time.perf_counter() - t0) * 1000), finish_reason=choice.finish_reason,
                    prompt_tokens=getattr(usage, "prompt_tokens", None), completion_tokens=getattr(usage, "completion_tokens", None),
                )
            from imagine import ChatMessage

            r = self._imagine_client().chat(
                messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
                model=self.s.qualcomm_model, temperature=temperature,
                max_tokens=max_tokens or self.s.max_tokens, tools=[tool] if tool else None,
            )
        except QualcommError:
            raise
        except Exception as e:  # noqa: BLE001 - SDK raises several exception types
            err = _classify(e)
            log.warning("qualcomm chat failed code=%s type=%s", err.code, type(e).__name__)
            raise err from None
        choice = r.choices[0]
        args = None
        calls = getattr(choice.message, "tool_calls", None)
        if calls:
            fn = getattr(calls[0], "function", None)
            raw = getattr(fn, "arguments", None) if fn is not None else None
            args = _parse_args(raw)
        finish = getattr(choice.finish_reason, "value", choice.finish_reason)
        usage = getattr(r, "usage", None)
        return ChatResult(
            text=r.first_content or "", tool_arguments=args, model=r.model or self.s.qualcomm_model,
            latency_ms=int((time.perf_counter() - t0) * 1000), finish_reason=finish,
            prompt_tokens=getattr(usage, "prompt_tokens", None), completion_tokens=getattr(usage, "completion_tokens", None),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            r = self._imagine_client().embeddings(texts, model=self.s.embedding_model)
        except Exception as e:  # noqa: BLE001
            raise _classify(e) from None
        return [d.embedding for d in sorted(r.data, key=lambda d: d.index)]

    def rerank(self, query: str, documents: list[str], top_n: int = 3) -> list[tuple[int, float]]:
        if not self.s.reranker_model:
            raise QualcommError("NO_RERANKER", "No reranker model configured.", False)
        try:
            r = self._imagine_client().reranker(query, documents, model=self.s.reranker_model, top_n=top_n)
        except Exception as e:  # noqa: BLE001
            raise _classify(e) from None
        return [(d.index, d.relevance_score) for d in r.data]

    def models(self) -> dict:
        try:
            by_type = self._imagine_client().get_available_models_by_type()
        except Exception as e:  # noqa: BLE001
            raise _classify(e) from None
        return {str(getattr(k, "value", k)): v for k, v in by_type.items()}


def _parse_args(raw) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except (TypeError, ValueError):
        return None
