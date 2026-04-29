#!/usr/bin/env python3
"""Thin LLM client wrapper with offline fallback for constrained generation."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

try:
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore

try:  # Optional OpenAI client (only used when API key is available)
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    OpenAI = None  # type: ignore


class LLMClientUnavailable(RuntimeError):
    """Raised when live LLM generation cannot produce usable text."""

    def __init__(self, message: str, *, error_code: str = "", retryable: bool = False):
        super().__init__(message)
        self.error_code = (error_code or "").strip()
        self.retryable = bool(retryable)


RUNTIME_LLM_CONFIG: Dict[str, Any] = {}
RUNTIME_FORCE_LIVE = False
DEEPSEEK_STABLE_MODEL = "deepseek-v4-flash"
DEEPSEEK_QUALITY_MODEL = "deepseek-v4-pro"
DEEPSEEK_R1_EXPERIMENT_MODEL = DEEPSEEK_QUALITY_MODEL
DEEPSEEK_DEFAULT_MODEL = DEEPSEEK_STABLE_MODEL
RETRYABLE_LLM_ERROR_CODES = {
    "missing_output_text",
    "missing_choices",
    "chat_fallback_missing_text",
    "empty_content",
    "empty_packet",
    "non_dict_payload",
}
NON_RETRYABLE_SAME_PROVIDER_ERROR_CODES = {
    "empty_output_array",
    "no_message_in_output",
}


def _is_timeout_error(error: str) -> bool:
    lowered = str(error or "").strip().lower()
    return bool(lowered) and (
        "timeout" in lowered
        or "timed out" in lowered
        or "read timed out" in lowered
    )


def _normalize_timeout_error(error: str) -> str:
    return "transport_hard_stop_timeout" if _is_timeout_error(error) else str(error or "")


def is_r1_experiment_model(model: Optional[str]) -> bool:
    return str(model or "").strip() in {"deepseek-reasoner", DEEPSEEK_R1_EXPERIMENT_MODEL}


def _supports_deepseek_reasoning_controls(model: Optional[str]) -> bool:
    return str(model or "").strip() in {DEEPSEEK_STABLE_MODEL, DEEPSEEK_QUALITY_MODEL}


def _disable_fallback_for_request(payload: Optional[Dict[str, Any]], override_model: Optional[str]) -> bool:
    if is_r1_experiment_model(override_model):
        return True
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("_disable_fallback"))


def _codex_sessions_accessible() -> bool:
    sessions_dir = os.path.expanduser("~/.codex/sessions")
    if not os.path.exists(sessions_dir):
        return True
    return os.access(sessions_dir, os.R_OK | os.W_OK | os.X_OK)


def _codex_exec_timeout_budget(timeout_seconds: int) -> int:
    base = max(10, int(timeout_seconds or 0))
    # Codex exec has extra startup and session overhead versus direct HTTP calls.
    return max(30, base + 45)


def _http_post_json(
    url: str,
    body: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int = 60,
    verify_ssl: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Sends a JSON POST request using `requests` when available, otherwise falls back to urllib.
    """
    if requests is not None:
        response = requests.post(url, json=body, headers=headers, timeout=timeout, verify=verify_ssl)
        response.raise_for_status()
        return response.json(), dict(response.headers)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    try:
        context = None if verify_ssl else ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            text = resp.read().decode(charset, errors="replace")
            return json.loads(text or "{}"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"URLError: {exc.reason}") from exc


def _header_lookup(headers: Optional[Dict[str, str]], *keys: str) -> str:
    if not headers:
        return ""
    normalized = {str(k).lower(): str(v) for k, v in headers.items()}
    for key in keys:
        value = normalized.get(key.lower())
        if value:
            return value
    return ""


def _coerce_text_blocks(node: Any, depth: int = 0) -> list[str]:
    """
    Best-effort extraction for OpenAI-compatible gateways that return
    non-standard `responses` payloads.
    """
    if depth > 8 or node is None:
        return []
    if isinstance(node, str):
        text = node.strip()
        return [text] if text else []
    if isinstance(node, list):
        collected: list[str] = []
        for item in node:
            collected.extend(_coerce_text_blocks(item, depth + 1))
        return collected
    if not isinstance(node, dict):
        return []

    node_type = str(node.get("type") or "").lower()
    if node_type in {"output_text", "text", "message"}:
        direct = node.get("text") or node.get("output_text") or node.get("value")
        if isinstance(direct, str) and direct.strip():
            return [direct.strip()]

    direct_keys = ("output_text", "text", "value")
    for key in direct_keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return [value.strip()]

    prioritized_keys = (
        "content",
        "contents",
        "message",
        "messages",
        "output",
        "outputs",
        "response",
        "result",
        "data",
        "choices",
    )
    for key in prioritized_keys:
        if key not in node:
            continue
        nested = _coerce_text_blocks(node.get(key), depth + 1)
        if nested:
            return nested

    return []


def _extract_openai_compatible_text(data: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns `(text, response_state)` from a responses/chat payload.
    """
    if not isinstance(data, dict):
        return "", "non_dict_payload"

    response_state = str(data.get("status") or data.get("state") or "").strip() or "completed"

    choices = data.get("choices") or []
    if choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            text = "\n".join(_coerce_text_blocks(content)).strip()
        else:
            text = (content or "").strip() if isinstance(content, str) else ""
        if text:
            return text, response_state

    candidate_roots = [
        data.get("output"),
        data.get("outputs"),
        data.get("content"),
        data.get("response"),
        data.get("result"),
        data.get("data"),
        data.get("message"),
        data.get("messages"),
        data,
    ]
    for candidate in candidate_roots:
        blocks = _coerce_text_blocks(candidate)
        if blocks:
            return "\n".join(blocks).strip(), response_state

    output = data.get("output")
    if isinstance(output, list):
        if not output:
            return "", "empty_output_array"
        has_message_item = any(
            isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "message"
            for item in output
        )
        if not has_message_item:
            return "", "no_message_in_output"

    return "", response_state or "missing_output_text"


def configure_llm_runtime(config: Optional[Dict[str, Any]] = None) -> None:
    """Set runtime LLM config and reset singleton."""
    global RUNTIME_LLM_CONFIG, RUNTIME_FORCE_LIVE, _LLM_CLIENT_SINGLETON
    RUNTIME_LLM_CONFIG = (config or {}).copy()
    RUNTIME_FORCE_LIVE = bool(RUNTIME_LLM_CONFIG.get("force_live_llm"))
    _LLM_CLIENT_SINGLETON = None


def llm_force_live_required() -> bool:
    return RUNTIME_FORCE_LIVE


class LLMClient:
    """
    Provides a single entrypoint for constrained text generation.

    Prefers OpenAI Responses API when credentials are configured, otherwise falls
    back to an offline deterministic composer so downstream code can continue to
    run inside restricted environments.
    """

    def __init__(self):
        self._config = RUNTIME_LLM_CONFIG or {}
        self._force_live = bool(self._config.get("force_live_llm"))
        self._request_timeout_seconds = int(
            self._config.get("request_timeout_seconds")
            or os.getenv("LLM_REQUEST_TIMEOUT_SECONDS")
            or 60
        )
        verify_ssl_value = self._config.get(
            "verify_ssl",
            os.getenv("LLM_VERIFY_SSL", os.getenv("OPENAI_COMPAT_VERIFY_SSL", "1")),
        )
        self._verify_ssl = str(verify_ssl_value).strip().lower() not in {"0", "false", "no"}
        self._http_fallback_provider = deepcopy(self._config.get("http_fallback_provider") or None)
        self._disable_codex_exec_fallback = str(
            self._config.get("disable_codex_exec_fallback", os.getenv("OPENAI_COMPAT_DISABLE_CODEX_FALLBACK", "0"))
        ).strip().lower() in {"1", "true", "yes"}
        self._model = (
            self._config.get("model")
            or os.getenv("LLM_MODEL")
            or os.getenv("OPENAI_MODEL")
            or os.getenv("CODEX_LLM_MODEL")
            or "gpt-4o"
        )
        self._client: Optional[Any] = None
        self._offline = True
        self._provider = "offline"
        self._provider_label = "offline"
        self._mode_label = "offline"
        self._credential_source = "none"
        self._active_model: Optional[str] = None
        self._deepseek_key = None
        self._deepseek_base = "https://api.deepseek.com"
        self._deepseek_model = DEEPSEEK_DEFAULT_MODEL
        self._deepseek_thinking: Optional[Dict[str, Any]] = None
        self._deepseek_reasoning_effort = ""
        self._openai_compatible: Optional[Dict[str, Any]] = None
        self._codex_exec_fallback: Optional[Dict[str, Any]] = None
        self._last_response_meta: Dict[str, Any] = {}
        self._last_healthcheck: Dict[str, Any] = {}
        self._active_timeout_context: Dict[str, Any] = {}

        configured = False
        if self._config:
            configured = self._init_from_config(self._config)
        if not configured:
            configured = self._init_from_env()
        if not configured:
            self._active_model = "offline"
            self._provider_label = "offline"
            self._mode_label = "offline"
            self._credential_source = "none"
            self._offline = True

        if self._force_live and self._offline:
            raise LLMClientUnavailable(
                "force_live_llm=true but no live LLM credentials are configured."
            )

    def _record_response_meta(
        self,
        *,
        endpoint: str,
        wire_api: str,
        response_data: Optional[Dict[str, Any]] = None,
        response_headers: Optional[Dict[str, str]] = None,
        latency_ms: Optional[int] = None,
        success: bool,
        error: str = "",
        configured_model: str = "",
    ) -> None:
        response_data = response_data or {}
        response_state = error or ("success" if success else "unknown_error")
        request_id = (
            response_data.get("id")
            or _header_lookup(
                response_headers,
                "x-request-id",
                "request-id",
                "openai-request-id",
            )
        )
        self._last_response_meta = self._attach_timeout_context(
            {
            "configured_model": configured_model or self.active_model,
            "returned_model": response_data.get("model") or configured_model or self.active_model,
            "provider": self.provider_label,
            "mode": self.mode_label,
            "wire_api": wire_api,
            "base_url": self.base_url,
            "endpoint": endpoint,
            "request_id": request_id or "",
            "response_id": response_data.get("id") or "",
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
            "response_state": response_state,
            }
        )

    def _attach_timeout_context(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        timeout_context = deepcopy(self._active_timeout_context or {})
        if not timeout_context:
            return meta
        merged = dict(meta)
        merged["timeout_source"] = timeout_context.get("timeout_source") or ""
        merged["business_timeout_seconds"] = timeout_context.get("business_timeout_seconds")
        merged["transport_timeout_seconds"] = timeout_context.get("transport_timeout_seconds")
        return merged

    def _resolve_request_timeout_contract(
        self,
        payload: Optional[Dict[str, Any]],
        *,
        transport_floor_seconds: int = 0,
    ) -> Dict[str, Any]:
        payload = payload or {}
        source = "default_request_timeout"
        if payload.get("_request_timeout_seconds"):
            raw_timeout = payload.get("_request_timeout_seconds")
            source = "business_stage_timeout"
        elif self._request_timeout_seconds:
            raw_timeout = self._request_timeout_seconds
            source = "runtime_request_timeout"
        else:
            raw_timeout = 60
        try:
            business_timeout = max(5, int(raw_timeout))
        except Exception:
            business_timeout = 60
            source = "default_request_timeout"
        return {
            "business_timeout_seconds": business_timeout,
            "transport_timeout_seconds": max(business_timeout, int(transport_floor_seconds or 0)),
            "timeout_source": source,
        }

    def healthcheck(self) -> Dict[str, Any]:
        if self._offline:
            result = {
                "ok": False,
                "degraded_ok": False,
                "provider": self.provider_label,
                "configured_model": self.active_model,
                "mode": self.mode_label,
                "error": "offline_runtime",
            }
            self._last_healthcheck = result
            return deepcopy(result)

        started = time.time()
        try:
            text = self._call_llm(
                "Reply with exactly READY.",
                {"probe": "healthcheck", "purpose": "verify_live_llm_runtime"},
                0.0,
            )
        except Exception as exc:  # pragma: no cover - runtime/network path
            text = None
            error = str(exc)
        else:
            error = ""

        meta = deepcopy(self._last_response_meta)
        error_code = error or meta.get("error", "")
        degraded_ok = bool(
            not text
            and meta.get("response_state") in {
                "missing_output_text",
                "missing_choices",
                "chat_fallback_missing_text",
                "empty_output_array",
                "no_message_in_output",
                "completed",
            }
            and bool(meta.get("request_id") or meta.get("response_id"))
        )
        ok = bool(text and text.strip())
        result = {
            "ok": ok,
            "degraded_ok": degraded_ok,
            "provider": self.provider_label,
            "configured_model": self.active_model,
            "returned_model": meta.get("returned_model") or self.active_model,
            "wire_api": meta.get("wire_api") or self.wire_api,
            "base_url": meta.get("base_url") or self.base_url,
            "request_id": meta.get("request_id", ""),
            "latency_ms": meta.get("latency_ms") or int((time.time() - started) * 1000),
            "error": error_code,
            "response_state": meta.get("response_state", ""),
            "response_preview": (text or "").strip()[:32],
        }
        self._last_healthcheck = result
        return deepcopy(result)

    def _init_from_config(self, cfg: Dict[str, Any]) -> bool:
        provider = (cfg.get("provider") or "").lower()
        if provider == "openai_compatible":
            return self._init_openai_compatible(cfg)
        if provider == "openai":
            return self._init_openai_standard(cfg)
        if provider == "deepseek":
            return self._init_deepseek(cfg)
        return False

    def _init_from_env(self) -> bool:
        if os.getenv("DEEPSEEK_API_KEY"):
            return self._init_deepseek({})
        if os.getenv("OPENAI_API_KEY"):
            return self._init_openai_standard({})
        return False

    def _init_openai_compatible(self, cfg: Dict[str, Any]) -> bool:
        base_url = cfg.get("base_url")
        wire_api = (cfg.get("wire_api") or os.getenv("OPENAI_WIRE_API") or "chat_completions").lower()
        if "response" in wire_api:
            wire_api = "responses"
        elif wire_api in {"chat", "chat_completions", "chat/completions"}:
            wire_api = "chat/completions"
        else:
            wire_api = wire_api.strip("/")
        env_var = cfg.get("api_key_env") or "OPENAI_API_KEY"
        api_key = os.getenv(env_var)
        if not base_url or not api_key:
            return False
        model = cfg.get("model") or self._model
        self._openai_compatible = {
            "base_url": base_url.rstrip("/"),
            "api_key": api_key,
            "model": model,
            "wire_api": wire_api,
            "verify_ssl": self._verify_ssl,
        }
        self._provider = "openai_compatible"
        self._provider_label = cfg.get("provider", "openai_compatible")
        self._credential_source = f"env:{env_var} (config)"
        self._active_model = model
        self._offline = False
        self._mode_label = "live"
        codex_bin = shutil.which("codex")
        codex_home = cfg.get("codex_home") or os.getenv("CODEX_HOME") or os.path.join(tempfile.gettempdir(), "codex-home")
        codex_sessions_ok = _codex_sessions_accessible()
        if (
            codex_bin
            and not self._disable_codex_exec_fallback
            and (codex_sessions_ok or bool(codex_home))
            and "api.gptclubapi.xyz/openai" in self._openai_compatible["base_url"]
        ):
            self._codex_exec_fallback = {
                "codex_bin": codex_bin,
                "model": cfg.get("codex_model") or os.getenv("CODEX_LLM_MODEL") or "",
                "model_provider": cfg.get("codex_model_provider") or os.getenv("CODEX_MODEL_PROVIDER") or "",
                "sandbox": cfg.get("codex_sandbox") or "workspace-write",
                "approval": cfg.get("codex_approval_policy") or "never",
                "reasoning_effort": cfg.get("codex_reasoning_effort") or os.getenv("CODEX_REASONING_EFFORT") or "",
                "workdir": cfg.get("codex_exec_workdir") or os.getcwd() or tempfile.gettempdir(),
                "codex_home": codex_home,
                "isolated_codex_home": codex_home,
            }
        return True

    def _init_deepseek(self, cfg: Dict[str, Any]) -> bool:
        env_var = cfg.get("api_key_env") or "DEEPSEEK_API_KEY"
        api_key = os.getenv(env_var)
        if not api_key:
            return False
        self._deepseek_key = api_key
        self._deepseek_base = cfg.get("base_url") or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        self._deepseek_model = cfg.get("model") or os.getenv("DEEPSEEK_MODEL") or DEEPSEEK_DEFAULT_MODEL
        thinking = cfg.get("thinking")
        self._deepseek_thinking = thinking if isinstance(thinking, dict) else None
        self._deepseek_reasoning_effort = str(
            cfg.get("reasoning_effort") or os.getenv("DEEPSEEK_REASONING_EFFORT") or ""
        ).strip()
        self._provider = "deepseek"
        self._provider_label = cfg.get("provider", "deepseek")
        self._credential_source = f"env:{env_var}"
        self._active_model = self._deepseek_model
        self._offline = False
        self._mode_label = "live"
        return True

    def _init_openai_standard(self, cfg: Dict[str, Any]) -> bool:
        if OpenAI is None:
            return False
        env_var = cfg.get("api_key_env") or "OPENAI_API_KEY"
        api_key = os.getenv(env_var)
        if not api_key:
            return False
        model = cfg.get("model") or self._model or "gpt-4o"
        base_url = cfg.get("base_url")
        try:
            if base_url:
                self._client = OpenAI(api_key=api_key, base_url=base_url)
            else:
                self._client = OpenAI(api_key=api_key)
            self._model = model
            self._provider = "openai"
            self._provider_label = cfg.get("provider", "openai")
            self._credential_source = f"env:{env_var}"
            self._active_model = model
            self._offline = False
            self._mode_label = "live"
            return True
        except Exception as exc:  # pragma: no cover - network/auth failure
            logging.warning("OpenAI client init failed: %s", exc)
            self._client = None
            return False

    def _call_llm(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float,
        override_model: Optional[str] = None,
    ) -> Optional[str]:
        timeout_seconds = self._resolve_request_timeout(payload)
        disable_fallback = _disable_fallback_for_request(payload, override_model)
        if self._provider == "openai_compatible":
            if override_model:
                text = self._call_openai_compatible(
                    system_prompt,
                    payload,
                    temperature,
                    timeout_seconds=timeout_seconds,
                    override_model=override_model,
                )
            else:
                text = self._call_openai_compatible(
                    system_prompt,
                    payload,
                    temperature,
                    timeout_seconds=timeout_seconds,
                )
            if text:
                return text
            # If the upstream method was monkeypatched or exited early before
            # tracking a response, still allow the fallback chain to recover once.
            if (
                not disable_fallback
                and (self._http_fallback_provider or self._codex_exec_fallback)
                and not (self._last_response_meta or {}).get("wire_api")
            ):
                return self._call_fallback(
                    system_prompt=system_prompt,
                    payload=payload,
                    temperature=temperature,
                    timeout_seconds=timeout_seconds,
                )
            return None
        if self._provider == "deepseek":
            if override_model:
                text = self._call_deepseek(
                    system_prompt,
                    payload,
                    temperature,
                    timeout_seconds=timeout_seconds,
                    override_model=override_model,
                )
            else:
                text = self._call_deepseek(
                    system_prompt,
                    payload,
                    temperature,
                    timeout_seconds=timeout_seconds,
                )
            if text:
                return text
            if not disable_fallback and (self._http_fallback_provider or self._codex_exec_fallback):
                return self._call_fallback(
                    system_prompt=system_prompt,
                    payload=payload,
                    temperature=temperature,
                    timeout_seconds=timeout_seconds,
                )
            return None
        if self._offline or self._client is None:
            return None
        message = json.dumps(payload, ensure_ascii=False)
        started = time.time()
        try:
            response = self._client.chat.completions.create(
                model=override_model or self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                temperature=temperature,
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content or ""
            self._record_response_meta(
                endpoint="chat.completions",
                wire_api="chat/completions",
                response_data={
                    "id": getattr(response, "id", ""),
                    "model": getattr(response, "model", override_model or self._model),
                },
                latency_ms=int((time.time() - started) * 1000),
                success=bool(content),
                error="" if content else "empty_content",
                configured_model=override_model or self._model,
            )
            return content.strip()
        except Exception as exc:  # pragma: no cover - network failure
            self._record_response_meta(
                endpoint="chat.completions",
                wire_api="chat/completions",
                response_data={"model": override_model or self._model},
                latency_ms=int((time.time() - started) * 1000),
                success=False,
                error=str(exc),
                configured_model=override_model or self._model,
            )
            logging.warning("LLM client error, using offline generator: %s", exc)
            return None

    def _resolve_request_timeout(self, payload: Optional[Dict[str, Any]]) -> int:
        return self._resolve_request_timeout_contract(payload)["business_timeout_seconds"]

    def _call_openai_compatible(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float,
        *,
        timeout_seconds: int,
        override_model: Optional[str] = None,
    ) -> Optional[str]:
        if not self._openai_compatible:
            return None
        self._active_timeout_context = self._resolve_request_timeout_contract(
            payload,
            transport_floor_seconds=timeout_seconds,
        )
        base = self._openai_compatible["base_url"].rstrip("/")
        wire_api = self._openai_compatible.get("wire_api", "chat/completions")
        endpoint = "responses" if wire_api == "responses" else "chat/completions"
        url = f"{base}/{endpoint}".rstrip("/")
        logging.debug("OpenAI-compatible POST %s", url)
        if wire_api == "responses":
            body = {
                "model": override_model or self._openai_compatible["model"],
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
                    },
                ],
                "temperature": temperature,
            }
        else:
            body = {
                "model": override_model or self._openai_compatible["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "temperature": temperature,
            }
        headers = {
            "Authorization": f"Bearer {self._openai_compatible['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        last_error = ""
        verify_ssl = bool(self._openai_compatible.get("verify_ssl", True))
        for attempt in range(1, 4):
            started = time.time()
            try:
                data, response_headers = _http_post_json(
                    url,
                    body,
                    headers,
                    timeout=timeout_seconds,
                    verify_ssl=verify_ssl,
                )
                if wire_api == "responses":
                    content, response_state = _extract_openai_compatible_text(data)
                    if not content:
                        logging.warning("OpenAI-compatible responses payload missing text: %s", data)
                        fallback_text = self._call_openai_compatible_chat_fallback(
                            base=base,
                            system_prompt=system_prompt,
                            payload=payload,
                            temperature=temperature,
                            headers=headers,
                            timeout_seconds=timeout_seconds,
                            override_model=override_model,
                        )
                        if fallback_text:
                            return fallback_text
                        self._record_response_meta(
                            endpoint=endpoint,
                            wire_api=wire_api,
                            response_data=data,
                            response_headers=response_headers,
                            latency_ms=int((time.time() - started) * 1000),
                            success=False,
                            error=response_state if response_state != "completed" else "missing_output_text",
                            configured_model=override_model or self._openai_compatible["model"],
                        )
                        fallback_text = self._call_fallback(
                            system_prompt=system_prompt,
                            payload=payload,
                            temperature=temperature,
                            timeout_seconds=timeout_seconds,
                        )
                        if fallback_text:
                            return fallback_text
                        return None
                else:
                    content, response_state = _extract_openai_compatible_text(data)
                    if not content:
                        self._record_response_meta(
                            endpoint=endpoint,
                            wire_api=wire_api,
                            response_data=data,
                            response_headers=response_headers,
                            latency_ms=int((time.time() - started) * 1000),
                            success=False,
                            error=response_state if response_state != "completed" else "missing_choices",
                            configured_model=override_model or self._openai_compatible["model"],
                        )
                        fallback_text = self._call_fallback(
                            system_prompt=system_prompt,
                            payload=payload,
                            temperature=temperature,
                            timeout_seconds=timeout_seconds,
                        )
                        if fallback_text:
                            return fallback_text
                        return None
                self._record_response_meta(
                    endpoint=endpoint,
                    wire_api=wire_api,
                    response_data=data,
                    response_headers=response_headers,
                    latency_ms=int((time.time() - started) * 1000),
                    success=bool(content),
                    error="" if content else "empty_content",
                    configured_model=override_model or self._openai_compatible["model"],
                )
                return (content or "").strip()
            except Exception as exc:  # pragma: no cover - network failure
                last_error = _normalize_timeout_error(str(exc))
                self._record_response_meta(
                    endpoint=endpoint,
                    wire_api=wire_api,
                    response_data={"model": override_model or self._openai_compatible["model"]},
                    latency_ms=int((time.time() - started) * 1000),
                    success=False,
                    error=last_error,
                    configured_model=override_model or self._openai_compatible["model"],
                )
                if attempt < 3 and ("429" in last_error or "rate" in last_error.lower()):
                    time.sleep(2 * attempt)
                    continue
                logging.warning("OpenAI-compatible client error: %s", exc)
                fallback_text = self._call_fallback(
                    system_prompt=system_prompt,
                    payload=payload,
                    temperature=temperature,
                    timeout_seconds=timeout_seconds,
                )
                if fallback_text:
                    return fallback_text
                return None
        logging.warning("OpenAI-compatible client error after retries: %s", last_error)
        fallback_text = self._call_fallback(
            system_prompt=system_prompt,
            payload=payload,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )
        if fallback_text:
            return fallback_text
        return None

    def _call_http_fallback(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float,
        *,
        timeout_seconds: Optional[int] = None,
    ) -> Optional[str]:
        cfg = self._http_fallback_provider or {}
        if not cfg:
            return None
        base_url = str(cfg.get("base_url") or "").rstrip("/")
        api_key = str(cfg.get("api_key") or os.environ.get(str(cfg.get("api_key_env") or ""), "") or "").strip()
        model = str(cfg.get("model") or "gpt-4o").strip() or "gpt-4o"
        configured_timeout = int(cfg.get("timeout_seconds") or 30)
        payload_timeout = 0
        try:
            payload_timeout = int((payload or {}).get("_request_timeout_seconds") or 0)
        except Exception:
            payload_timeout = 0
        timeout = max(configured_timeout, int(timeout_seconds or 0), payload_timeout)
        self._active_timeout_context = self._resolve_request_timeout_contract(
            payload,
            transport_floor_seconds=max(configured_timeout, int(timeout_seconds or 0)),
        )
        if not base_url or not api_key:
            logging.warning("http_fallback_provider missing base_url or api_key")
            return None

        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
        }
        started = time.time()
        try:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            if self._verify_ssl:
                context = ssl.create_default_context()
            else:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                headers_map = dict(resp.headers)
                result = json.loads(resp.read().decode(resp.headers.get_content_charset() or "utf-8"))
            text = (((result.get("choices") or [{}])[0] or {}).get("message") or {}).get("content", "")
            text = text.strip() if isinstance(text, str) else ""
            latency_ms = int((time.time() - started) * 1000)
            if not text:
                self._last_response_meta = self._attach_timeout_context({
                    "configured_model": model,
                    "returned_model": result.get("model") or model,
                    "provider": "http_fallback",
                    "mode": "live",
                    "wire_api": "chat/completions",
                    "base_url": base_url,
                    "endpoint": "chat/completions",
                    "request_id": result.get("id") or _header_lookup(headers_map, "x-request-id", "request-id", "openai-request-id"),
                    "response_id": result.get("id") or "",
                    "latency_ms": latency_ms,
                    "success": False,
                    "error": "empty_content",
                    "response_state": "empty_content",
                })
                logging.warning("http_fallback: empty content in response")
                return None
            self._last_response_meta = self._attach_timeout_context({
                "configured_model": model,
                "returned_model": result.get("model") or model,
                "provider": "http_fallback",
                "mode": "live",
                "wire_api": "chat/completions",
                "base_url": base_url,
                "endpoint": "chat/completions",
                "request_id": result.get("id") or _header_lookup(headers_map, "x-request-id", "request-id", "openai-request-id"),
                "response_id": result.get("id") or "",
                "latency_ms": latency_ms,
                "success": True,
                "error": "",
                "response_state": "success",
            })
            logging.info("http_fallback succeeded model=%s len=%s", model, len(text))
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self._last_response_meta = self._attach_timeout_context({
                "configured_model": model,
                "returned_model": model,
                "provider": "http_fallback",
                "mode": "live",
                "wire_api": "chat/completions",
                "base_url": base_url,
                "endpoint": "chat/completions",
                "request_id": "",
                "response_id": "",
                "latency_ms": int((time.time() - started) * 1000),
                "success": False,
                "error": f"HTTPError {exc.code}: {detail[:1000]}",
                "response_state": "http_fallback_error",
            })
            logging.warning("http_fallback failed: HTTPError %s: %s", exc.code, detail[:300])
            return None
        except Exception as exc:
            normalized_error = _normalize_timeout_error(str(exc))
            self._last_response_meta = self._attach_timeout_context({
                "configured_model": model,
                "returned_model": model,
                "provider": "http_fallback",
                "mode": "live",
                "wire_api": "chat/completions",
                "base_url": base_url,
                "endpoint": "chat/completions",
                "request_id": "",
                "response_id": "",
                "latency_ms": int((time.time() - started) * 1000),
                "success": False,
                "error": normalized_error,
                "response_state": normalized_error if normalized_error == "transport_hard_stop_timeout" else "http_fallback_error",
            })
            logging.warning("http_fallback failed: %s", exc)
            return None

    def _call_fallback(
        self,
        *,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float,
        timeout_seconds: int,
    ) -> Optional[str]:
        primary_meta = deepcopy(self._last_response_meta)
        text = self._call_http_fallback(
            system_prompt,
            payload,
            temperature,
            timeout_seconds=timeout_seconds,
        )
        if text:
            return text
        if self._codex_exec_fallback:
            text = self._call_codex_exec(
                system_prompt,
                payload,
                temperature,
                timeout_seconds=max(60, int(timeout_seconds or 0)),
            )
            if text:
                if (self._last_response_meta or {}).get("wire_api") != "codex_exec":
                    self._last_response_meta = {
                        "configured_model": (self._codex_exec_fallback or {}).get("model") or self.active_model,
                        "returned_model": (self._codex_exec_fallback or {}).get("model") or self.active_model,
                        "provider": "codex_exec",
                        "mode": "live",
                        "wire_api": "codex_exec",
                        "base_url": self.base_url,
                        "endpoint": "codex exec",
                        "request_id": "",
                        "response_id": "",
                        "latency_ms": None,
                        "success": True,
                        "error": "",
                        "response_state": "success",
                    }
                return text
        self._last_response_meta = primary_meta
        return None

    def _call_openai_compatible_chat_fallback(
        self,
        *,
        base: str,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float,
        headers: Dict[str, str],
        timeout_seconds: int,
        override_model: Optional[str] = None,
    ) -> Optional[str]:
        """
        Some third-party gateways advertise `responses` but only reliably return
        assistant text through a chat-completions shape. Use a guarded retry
        before declaring the packet empty.
        """
        if "gptclubapi" in (base or "").lower():
            logging.debug("Skipping chat fallback for %s: /chat/completions returns 404", base)
            return None
        fallback_url = f"{base}/chat/completions".rstrip("/")
        fallback_body = {
            "model": override_model or self._openai_compatible["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": temperature,
        }
        started = time.time()
        try:
            data, response_headers = _http_post_json(
                fallback_url,
                fallback_body,
                headers,
                timeout=timeout_seconds,
                verify_ssl=bool(self._openai_compatible.get("verify_ssl", True)),
            )
            content, response_state = _extract_openai_compatible_text(data)
            self._record_response_meta(
                endpoint="chat/completions",
                wire_api="chat/completions",
                response_data=data,
                response_headers=response_headers,
                latency_ms=int((time.time() - started) * 1000),
                success=bool(content),
                error="" if content else (response_state if response_state != "completed" else "chat_fallback_missing_text"),
                configured_model=override_model or self._openai_compatible["model"],
            )
            return (content or "").strip() or None
        except Exception as exc:  # pragma: no cover - network path
            logging.warning("OpenAI-compatible chat fallback failed: %s", exc)
            return None

    def _build_codex_exec_prompt(self, system_prompt: str, payload: Dict[str, Any]) -> str:
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return (
            "You are a text-generation backend.\n"
            "Do not inspect files, do not run commands, and do not explain your reasoning.\n"
            "Return only the requested output content.\n\n"
            "<system_prompt>\n"
            f"{system_prompt}\n"
            "</system_prompt>\n\n"
            "<payload_json>\n"
            f"{payload_json}\n"
            "</payload_json>\n"
        )

    def _call_codex_exec(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float,
        *,
        timeout_seconds: int,
    ) -> Optional[str]:
        del temperature  # codex exec uses CLI-side defaults/config
        fallback = self._codex_exec_fallback or {}
        codex_bin = fallback.get("codex_bin")
        if not codex_bin:
            return None
        timeout_budget = max(60, int(timeout_seconds or 0))
        self._active_timeout_context = self._resolve_request_timeout_contract(
            payload,
            transport_floor_seconds=timeout_budget,
        )
        prompt = self._build_codex_exec_prompt(system_prompt, payload)
        started = time.time()
        workdir = str(fallback.get("workdir") or os.getcwd() or tempfile.gettempdir())
        with tempfile.NamedTemporaryFile(prefix="codex_exec_", suffix=".txt", delete=False) as tmp:
            out_file = tmp.name
        command = [
            codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-o",
            out_file,
            "-C",
            workdir,
            "-s",
            str(fallback.get("sandbox") or "workspace-write"),
        ]
        model_name = str(fallback.get("model") or "").strip()
        if model_name:
            command.extend(["-m", model_name])
        command.append(prompt)
        env = os.environ.copy()
        codex_home = str(fallback.get("isolated_codex_home") or fallback.get("codex_home") or "").strip()
        if codex_home:
            try:
                os.makedirs(codex_home, exist_ok=True)
                env["CODEX_HOME"] = codex_home
            except OSError:
                pass
        try:
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_budget,
                cwd=workdir,
            )
            latency_ms = int((time.time() - started) * 1000)
            stderr_text = (result.stderr or "").strip()
            stdout_text = (result.stdout or "").strip()
            if result.returncode == 0:
                try:
                    with open(out_file, "r", encoding="utf-8") as fh:
                        text = fh.read().strip()
                except FileNotFoundError:
                    text = ""
                if text:
                    self._last_response_meta = self._attach_timeout_context({
                        "configured_model": fallback.get("model") or self.active_model,
                        "returned_model": fallback.get("model") or self.active_model,
                        "provider": "codex_exec",
                        "mode": "live",
                        "wire_api": "codex_exec",
                        "base_url": self.base_url,
                        "endpoint": "codex exec",
                        "request_id": "",
                        "response_id": "",
                        "latency_ms": latency_ms,
                        "success": True,
                        "error": "",
                        "response_state": "success",
                    })
                    return text
            error = stderr_text or stdout_text or f"codex_exec_exit_{result.returncode}"
            if result.returncode == 0:
                error = "empty_output_file"
            if "permission denied" in error.lower() or "operation not permitted" in error.lower():
                self._codex_exec_fallback = None
            self._last_response_meta = self._attach_timeout_context({
                "configured_model": fallback.get("model") or self.active_model,
                "returned_model": fallback.get("model") or self.active_model,
                "provider": "codex_exec",
                "mode": "live",
                "wire_api": "codex_exec",
                "base_url": self.base_url,
                "endpoint": "codex exec",
                "request_id": "",
                "response_id": "",
                "latency_ms": latency_ms,
                "success": False,
                "error": error[:1000],
                "response_state": "codex_exec_error",
            })
            logging.warning("Codex exec fallback returned no text: %s", error)
            return None
        except subprocess.TimeoutExpired:
            latency_ms = int((time.time() - started) * 1000)
            self._last_response_meta = self._attach_timeout_context({
                "configured_model": fallback.get("model") or self.active_model,
                "returned_model": fallback.get("model") or self.active_model,
                "provider": "codex_exec",
                "mode": "live",
                "wire_api": "codex_exec",
                "base_url": self.base_url,
                "endpoint": "codex exec",
                "request_id": "",
                "response_id": "",
                "latency_ms": latency_ms,
                "success": False,
                "error": "codex_exec_timeout",
                "response_state": "codex_exec_timeout",
            })
            logging.warning("Codex exec fallback timed out after %sms", latency_ms)
            return None
        except Exception as exc:  # pragma: no cover - runtime path
            if "permission denied" in str(exc).lower() or "operation not permitted" in str(exc).lower():
                self._codex_exec_fallback = None
            self._last_response_meta = self._attach_timeout_context({
                "configured_model": fallback.get("model") or self.active_model,
                "returned_model": fallback.get("model") or self.active_model,
                "provider": "codex_exec",
                "mode": "live",
                "wire_api": "codex_exec",
                "base_url": self.base_url,
                "endpoint": "codex exec",
                "request_id": "",
                "response_id": "",
                "latency_ms": int((time.time() - started) * 1000),
                "success": False,
                "error": str(exc),
                "response_state": "codex_exec_exception",
            })
            logging.warning("Codex exec fallback error: %s", exc)
            return None
        finally:
            try:
                os.remove(out_file)
            except OSError:
                pass

    def _call_deepseek(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float,
        *,
        timeout_seconds: int,
        override_model: Optional[str] = None,
    ) -> Optional[str]:
        if not self._deepseek_key:
            return None
        self._active_timeout_context = self._resolve_request_timeout_contract(
            payload,
            transport_floor_seconds=timeout_seconds,
        )
        base = self._deepseek_base.rstrip("/")
        url = f"{base}/chat/completions"
        logging.debug("DeepSeek POST %s", url)
        target_model = override_model or self._deepseek_model
        body = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": temperature,
            "stream": False,
        }
        if self._deepseek_thinking and _supports_deepseek_reasoning_controls(target_model):
            body["thinking"] = self._deepseek_thinking
        if self._deepseek_reasoning_effort and _supports_deepseek_reasoning_controls(target_model):
            body["reasoning_effort"] = self._deepseek_reasoning_effort
        headers = {
            "Authorization": f"Bearer {self._deepseek_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        started = time.time()
        try:
            data, response_headers = _http_post_json(
                url,
                body,
                headers,
                timeout=timeout_seconds,
                verify_ssl=self._verify_ssl,
            )
            logging.debug("DeepSeek raw response: %r", data)
            if not isinstance(data, dict):
                self._record_response_meta(
                    endpoint="chat.completions",
                    wire_api="chat/completions",
                    response_data={"model": override_model or self._deepseek_model},
                    response_headers=response_headers,
                    latency_ms=int((time.time() - started) * 1000),
                    success=False,
                    error="non_dict_payload",
                    configured_model=override_model or self._deepseek_model,
                )
                logging.warning("DeepSeek returned non-dict payload: %r", data)
                return None
            choices = data.get("choices") or []
            if not choices:
                self._record_response_meta(
                    endpoint="chat.completions",
                    wire_api="chat/completions",
                    response_data=data,
                    response_headers=response_headers,
                    latency_ms=int((time.time() - started) * 1000),
                    success=False,
                    error="missing_choices",
                    configured_model=override_model or self._deepseek_model,
                )
                logging.warning("DeepSeek returned no choices: %r", data)
                return None
            message = choices[0].get("message") or {}
            content = message.get("content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content") or ""
                        if text:
                            parts.append(text)
                content = "\n".join(parts)
            if not isinstance(content, str):
                self._record_response_meta(
                    endpoint="chat.completions",
                    wire_api="chat/completions",
                    response_data=data,
                    response_headers=response_headers,
                    latency_ms=int((time.time() - started) * 1000),
                    success=False,
                    error="non_string_content",
                    configured_model=override_model or self._deepseek_model,
                )
                logging.warning("DeepSeek returned non-string content: %r", content)
                return None
            self._record_response_meta(
                endpoint="chat.completions",
                wire_api="chat/completions",
                response_data=data,
                response_headers=response_headers,
                latency_ms=int((time.time() - started) * 1000),
                success=bool(content),
                error="" if content else "empty_content",
                configured_model=override_model or self._deepseek_model,
            )
            return content.strip()
        except Exception as exc:  # pragma: no cover - network failure
            normalized_error = _normalize_timeout_error(str(exc))
            self._record_response_meta(
                endpoint="chat.completions",
                wire_api="chat/completions",
                response_data={"model": override_model or self._deepseek_model},
                latency_ms=int((time.time() - started) * 1000),
                success=False,
                error=normalized_error,
                configured_model=override_model or self._deepseek_model,
            )
            logging.warning("DeepSeek client error, using offline generator: %s", exc)
            return None

    def generate_text(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float = 0.35,
        override_model: Optional[str] = None,
    ) -> str:
        """
        Generic constrained text generation. Used by all visible fields.
        """
        if override_model:
            text = self._call_llm(system_prompt, payload, temperature, override_model=override_model)
        else:
            text = self._call_llm(system_prompt, payload, temperature)
        if text:
            return text
        meta = self._last_response_meta or {}
        error_code = (meta.get("error") or meta.get("response_state") or "").strip()
        lowered = error_code.lower()
        retryable = bool(
            lowered in RETRYABLE_LLM_ERROR_CODES and lowered not in NON_RETRYABLE_SAME_PROVIDER_ERROR_CODES
            or "timeout" in lowered
            or "timed out" in lowered
            or "rate" in lowered
            or "429" in lowered
        )
        if error_code:
            raise LLMClientUnavailable(
                f"Live LLM request returned no usable text ({error_code}).",
                error_code=error_code,
                retryable=retryable,
            )
        raise LLMClientUnavailable(
            "Live LLM generation required but no API client is available.",
            error_code="no_api_client",
            retryable=False,
        )

    def generate_bullet(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float = 0.35,
        override_model: Optional[str] = None,
    ) -> str:
        return self.generate_text(system_prompt, payload, temperature, override_model=override_model)

    def generate_description(
        self,
        system_prompt: str,
        payload: Dict[str, Any],
        temperature: float = 0.4,
        override_model: Optional[str] = None,
    ) -> str:
        return self.generate_text(system_prompt, payload, temperature, override_model=override_model)

    def _offline_text(self, payload: Dict[str, Any]) -> str:
        """Deterministic fallback that still respects structure and constraints."""
        target_lang = (payload.get("target_language") or "English").lower()
        scene_label = payload.get("scene_label") or payload.get("scene_context") or "la scène"
        capability = (
            payload.get("capability")
            or payload.get("role")
            or payload.get("title_terms")
            or "performance"
        )
        keywords = payload.get("mandatory_keywords") or []
        numeric_proof = payload.get("numeric_proof")
        pain_point = payload.get("pain_point")
        localized_pain_point = payload.get("localized_pain_point")
        pain_text = (localized_pain_point or pain_point or "").strip()
        audience = payload.get("audience")
        mini_brief = (payload.get("localized_mini_brief") or payload.get("mini_brief") or "").strip()

        keyword_clause = ", ".join(keywords) if keywords else capability
        numeric_clause = ""
        if numeric_proof:
            numeric_clause = f"{numeric_proof}"
        accessory_experiences = payload.get("accessory_experiences") or []
        localized_experiences = payload.get("localized_accessory_experiences") or []
        experience_text = ""
        if localized_experiences and not target_lang.startswith("en"):
            experience_text = localized_experiences[0]
        elif accessory_experiences:
            experience_text = accessory_experiences[0]

        subheading_source = []
        if capability:
            subheading_source.extend(re.split(r"[\s\-]+", capability)[:2])
        if numeric_clause:
            subheading_source.extend(re.split(r"[\s\-]+", numeric_clause)[:2])
        if not subheading_source and scene_label:
            subheading_source.extend(re.split(r"[\s\-]+", str(scene_label))[:2])
        if not subheading_source:
            subheading_source = ["Prime", "Benefit"]
        subheading_words = subheading_source[:5]
        subheading = " ".join(word[:1].upper() + word[1:] for word in subheading_words if word).strip()
        if len(subheading.split()) < 3:
            subheading = f"{subheading} Advantage".strip()

        if target_lang.startswith("fr"):
            audience_phrase = audience or scene_label
            pain_clause = f", élimine {pain_text}" if pain_text else ""
            scene_sentence = mini_brief or f"Pensée pour {audience_phrase}, maîtrisez {scene_label}{pain_clause}."
            action_sentence = experience_text or "Utilisez le montage fourni pour filmer mains libres."
            feeling_sentence = (
                f"Ressentez la sérénité : {pain_text} n'entrave plus vos prises."
                if pain_text else
                "Ressentez la confiance d'une POV stable."
            )
            if keyword_clause:
                base = feeling_sentence.rstrip(". ")
                feeling_sentence = f"{base} – {keyword_clause}."
            elif not feeling_sentence.endswith("."):
                feeling_sentence = f"{feeling_sentence.strip()}."
        elif target_lang.startswith("de"):
            audience_phrase = audience or scene_label
            pain_clause = f" und stoppt {pain_text}" if pain_text else ""
            scene_sentence = mini_brief or f"Ideal für {audience_phrase}, {scene_label} bleibt stabil{pain_clause}."
            action_sentence = experience_text or "Nutze das beiliegende Montageset für freihändige Aufnahmen."
            feeling_sentence = (
                f"Spüre die Erleichterung: {pain_text} bremst dich nicht mehr aus."
                if pain_text else
                "Spüre Vertrauen in jede Aufnahme."
            )
            if keyword_clause:
                base = feeling_sentence.rstrip(". ")
                feeling_sentence = f"{base} – {keyword_clause}."
            elif not feeling_sentence.endswith("."):
                feeling_sentence = f"{feeling_sentence.strip()}."
        else:
            audience_phrase = audience or scene_label
            pain_clause = f" while solving {pain_point}" if pain_point else ""
            scene_sentence = mini_brief or f"Perfect for {audience_phrase} in {scene_label}, capture every moment{pain_clause}."
            action_sentence = experience_text or "Use the included mounts for hands-free coverage."
            feeling_sentence = (
                f"Feel relief as {pain_point} disappears."
                if pain_point else
                "Feel confident with stabilized POV footage."
            )
            if keyword_clause:
                base = feeling_sentence.rstrip(". ")
                feeling_sentence = f"{base} – {keyword_clause}."
            elif not feeling_sentence.endswith("."):
                feeling_sentence = f"{feeling_sentence.strip()}."

        bullet = f"{subheading} – {scene_sentence.strip()} {action_sentence.strip()} {feeling_sentence.strip()}".strip()
        return re.sub(r"\s+", " ", bullet)

    @property
    def active_model(self) -> str:
        if self._active_model:
            return self._active_model
        if not self._offline and self._model:
            return self._model
        return "offline"

    @property
    def provider_label(self) -> str:
        return self._provider_label

    @property
    def credential_source(self) -> str:
        return self._credential_source

    @property
    def base_url(self) -> str:
        if self._provider == "openai_compatible" and self._openai_compatible:
            return self._openai_compatible.get("base_url", "")
        if self._provider == "deepseek":
            return self._deepseek_base.rstrip("/")
        return (self._config.get("base_url") or "").rstrip("/")

    @property
    def wire_api(self) -> str:
        if self._provider == "openai_compatible" and self._openai_compatible:
            return self._openai_compatible.get("wire_api", "chat/completions")
        return "chat/completions"

    @property
    def mode_label(self) -> str:
        return self._mode_label

    @property
    def is_offline(self) -> bool:
        return self._offline

    @property
    def force_live_required(self) -> bool:
        return self._force_live

    @property
    def response_metadata(self) -> Dict[str, Any]:
        return deepcopy(self._last_response_meta)

    @property
    def healthcheck_status(self) -> Dict[str, Any]:
        return deepcopy(self._last_healthcheck)

    @property
    def has_codex_exec_fallback(self) -> bool:
        return bool(self._codex_exec_fallback)

    @property
    def has_http_fallback_provider(self) -> bool:
        return bool(self._http_fallback_provider)

    def probe_http_fallback(self) -> bool:
        if not self._http_fallback_provider:
            return False
        text = self._call_http_fallback(
            "You are a test assistant. Reply with exactly READY.",
            {"probe": "http_fallback_healthcheck", "test": True},
            0.0,
            timeout_seconds=15,
        )
        return bool(text and text.strip())


_LLM_CLIENT_SINGLETON: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _LLM_CLIENT_SINGLETON
    if _LLM_CLIENT_SINGLETON is None:
        _LLM_CLIENT_SINGLETON = LLMClient()
    return _LLM_CLIENT_SINGLETON
