"""Generic model adapter over an injected transport (K04NEXT3 C2).

Adapters-side seam for M-P1-23 (generic adapters; the per-provider leg
mapping lives in legs.py) and R-356 (no built-in vendor or model
default: every constructor takes an explicit provider_id and model, and
require_explicit_selection refuses empty ids instead of filling one in).

The transport callable is the only network boundary: invoke() hands it
one request mapping and wraps the wire-shaped reply in an
AdapterResponse. The secret ref travels as an opaque mapping: it is
accepted, never read, and never copied into requests or records.
"""
from __future__ import annotations

from collections.abc import Mapping


class AdapterSetupError(ValueError):
    """Refused adapter setup: missing ids, missing transport, bad reply."""

    def __init__(self, message, code="ADAPTER_SETUP"):
        super().__init__(message)
        self.code = code


SELECTION_REQUIRED = "ADAPTER_SELECTION_REQUIRED"
TRANSPORT_REQUIRED = "ADAPTER_TRANSPORT_REQUIRED"
BACKEND_CALL_REQUIRED = "ADAPTER_BACKEND_CALL_REQUIRED"
SECRET_REQUIRED = "ADAPTER_SECRET_REQUIRED"
MESSAGES_REQUIRED = "ADAPTER_MESSAGES_REQUIRED"
REPLY_REQUIRED = "ADAPTER_REPLY_REQUIRED"


def require_explicit_selection(provider_id, model_id):
    """Return the (provider_id, model_id) pair, refusing blanks.

    No built-in vendor or model default exists on this path (R-356):
    a missing or blank id raises instead of resolving to anything.
    """
    if not (isinstance(provider_id, str) and provider_id.strip()):
        raise AdapterSetupError(
            "explicit provider_id required; no built-in vendor default",
            SELECTION_REQUIRED)
    if not (isinstance(model_id, str) and model_id.strip()):
        raise AdapterSetupError(
            "explicit model required; no built-in model default",
            SELECTION_REQUIRED)
    return provider_id, model_id


def _checked_messages(messages):
    if not isinstance(messages, (list, tuple)) or not messages:
        raise AdapterSetupError(
            "invoke needs a non-empty list of role/content messages",
            MESSAGES_REQUIRED)
    checked = []
    for item in messages:
        if not isinstance(item, Mapping):
            raise AdapterSetupError(
                "invoke messages must be role/content mappings",
                MESSAGES_REQUIRED)
        role = item.get("role")
        content = item.get("content")
        if not (isinstance(role, str) and role.strip()) or \
                not (isinstance(content, str) and content):
            raise AdapterSetupError(
                "invoke messages need a text role and text content",
                MESSAGES_REQUIRED)
        checked.append({"role": role, "content": content})
    return checked


def _checked_reply(reply):
    if not isinstance(reply, Mapping):
        raise AdapterSetupError(
            "transport must return a wire-shaped reply mapping",
            REPLY_REQUIRED)
    output = reply.get("output_text")
    if not (isinstance(output, str) and output):
        raise AdapterSetupError(
            "transport reply needs a text output_text",
            REPLY_REQUIRED)
    usage = reply.get("usage")
    return output, dict(usage) if isinstance(usage, Mapping) else {}


class AdapterResponse:
    """One served invocation result with its record form."""

    def __init__(self, provider_id, model, instance_id, output_text,
                 finish="stop", usage=None, error_ref=None):
        self.provider_id = provider_id
        self.model = model
        self.instance_id = instance_id
        self.output_text = output_text
        self.finish = finish
        self.usage = dict(usage) if isinstance(usage, Mapping) else {}
        self.error_ref = error_ref

    def to_record(self):
        return {"provider_id": self.provider_id,
                "model": self.model,
                "instance_id": self.instance_id,
                "output_text": self.output_text,
                "finish": self.finish,
                "usage": dict(self.usage),
                "error_ref": self.error_ref,
                "mock": False}


class GenericAdapter:
    """OpenAI-compatible adapter: explicit ids plus injected transport."""

    openai_compat = True

    def __init__(self, provider_id, model, secret_ref, transport, *,
                 instance_id="default",
                 chat_path="/chat/completions", base_url="",
                 route_params=None):
        require_explicit_selection(provider_id, model)
        if not callable(transport):
            raise AdapterSetupError(
                "GenericAdapter needs a callable transport "
                "(the network boundary)", TRANSPORT_REQUIRED)
        if not isinstance(secret_ref, Mapping):
            raise AdapterSetupError(
                "GenericAdapter needs the secret ref as a mapping",
                SECRET_REQUIRED)
        self.provider_id = provider_id
        self.model = model
        self.secret_ref = secret_ref
        self.transport = transport
        self.instance_id = instance_id
        self.chat_path = chat_path
        self.base_url = base_url
        self.route_params = dict(route_params or {})

    def invoke(self, messages):
        checked = _checked_messages(messages)
        request = {"provider_id": self.provider_id,
                   "instance_id": self.instance_id,
                   "model": self.model,
                   "messages": checked}
        reply = self.transport(request)
        output_text, usage = _checked_reply(reply)
        finish = reply.get("finish", "stop")
        return AdapterResponse(
            self.provider_id, self.model, self.instance_id,
            output_text, finish=finish, usage=usage)

    def transport_descriptor(self):
        return {"provider_id": self.provider_id,
                "model": self.model,
                "instance_id": self.instance_id,
                "openai_compat": True,
                "chat_path": self.chat_path,
                "base_url": self.base_url,
                "route_params": dict(self.route_params)}


class FunctionBackedAdapter:
    """Non-compatible adapter: explicit ids plus an injected backend call."""

    openai_compat = False

    def __init__(self, provider_id, model, secret_ref, backend_call, *,
                 instance_id="default", route_params=None):
        require_explicit_selection(provider_id, model)
        if not callable(backend_call):
            raise AdapterSetupError(
                "FunctionBackedAdapter needs a callable backend_call "
                "(the network boundary)", BACKEND_CALL_REQUIRED)
        if not isinstance(secret_ref, Mapping):
            raise AdapterSetupError(
                "FunctionBackedAdapter needs the secret ref as a mapping",
                SECRET_REQUIRED)
        self.provider_id = provider_id
        self.model = model
        self.secret_ref = secret_ref
        self.backend_call = backend_call
        self.instance_id = instance_id
        self.route_params = dict(route_params or {})

    def invoke(self, messages):
        checked = _checked_messages(messages)
        request = {"provider_id": self.provider_id,
                   "instance_id": self.instance_id,
                   "model": self.model,
                   "messages": checked,
                   "route_params": dict(self.route_params)}
        reply = self.backend_call(request)
        output_text, usage = _checked_reply(reply)
        finish = reply.get("finish", "stop")
        return AdapterResponse(
            self.provider_id, self.model, self.instance_id,
            output_text, finish=finish, usage=usage)

    def transport_descriptor(self):
        return {"provider_id": self.provider_id,
                "model": self.model,
                "instance_id": self.instance_id,
                "openai_compat": False,
                "chat_path": "",
                "base_url": "",
                "route_params": dict(self.route_params)}
