"""Genesys AudioHook HTTP Message Signature canonicalization (TASK-INFRA-012).

Pure, side-effect-free helpers that rebuild the signature base for the Genesys
AudioHook "connection authentication" scheme (IETF HTTP Message Signatures, alg
fixed to ``hmac-sha256``). The client sends:

- ``Signature-Input: sig1=("@request-target" "@authority" "audiohook-organization-id"
  "audiohook-session-id" "audiohook-correlation-id" "x-api-key");keyid="…";
  nonce="…";alg="hmac-sha256";created=…;expires=…`` — names the covered components
  (order can vary per request, so it MUST be parsed, never assumed) + the params.
- ``Signature: sig1=:<base64 HMAC>:``.

The signature base is each covered component on its own line as ``"name": value``
joined with ``\\n``, then a final ``"@signature-params": <the exact value of the
Signature-Input for that label>`` line. Byte precision matters — a stray space
breaks the HMAC. Scheme reference (deterministically known now):
https://developer.genesys.cloud/devapps/audiohook/security#client-authentication

No secret/signature/API-key/PII is handled beyond returning the raw signature
bytes to the caller (the authenticator) for a constant-time compare.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any, Mapping

REQUEST_TARGET = "@request-target"
AUTHORITY = "@authority"
SIGNATURE_PARAMS = "@signature-params"


@dataclass(frozen=True)
class SignatureInput:
    """Parsed ``Signature-Input`` + ``Signature`` for a single label."""

    label: str
    components: list[str]
    raw_params: str
    params: dict[str, str]
    signature: bytes


def parse_signature_headers(headers: Mapping[str, str]) -> SignatureInput | None:
    """Parse the AudioHook signature headers, or None when absent/malformed."""
    raw_input = headers.get("Signature-Input", "")
    raw_sig = headers.get("Signature", "")
    if not raw_input or not raw_sig:
        return None
    label, raw_params = _split_label(raw_input)
    components = _covered_components(raw_params)
    if not label or not components:
        return None
    signature = _decode_signature_value(raw_sig, label)
    if signature is None:
        return None
    return SignatureInput(label, components, raw_params, _parse_params(raw_params), signature)


def build_signature_base(
    request: Any, sig_input: SignatureInput, authority_override: str | None
) -> str | None:
    """Rebuild the canonical signature base, or None if a covered component is missing."""
    lines = []
    for name in sig_input.components:
        value = _component_value(request, name, authority_override)
        if value is None:
            return None
        lines.append(f'"{name}": {value}')
    lines.append(f'"{SIGNATURE_PARAMS}": {sig_input.raw_params}')
    return "\n".join(lines)


def _component_value(request: Any, name: str, authority_override: str | None) -> str | None:
    lowered = name.lower()
    if lowered == REQUEST_TARGET:
        return _request_target(request)
    if lowered == AUTHORITY:
        return authority_override or request.headers.get("Host", "")
    return request.headers.get(name)  # case-insensitive header lookup (CIMultiDict)


def _request_target(request: Any) -> str:
    # TODO(TASK-INFRA-012: live-measurement): behind the pilot HAProxy edge the signed
    # @request-target path may be rewritten before it reaches the bridge; confirm the
    # exact value against the live Genesys tenant (GENESYS_AUDIOHOOK_AUTHORITY covers host).
    return request.raw_path


def _split_label(raw_input: str) -> tuple[str | None, str]:
    head, sep, rest = raw_input.strip().partition("=")
    rest = rest.strip()
    if not sep or not rest.startswith("("):
        return None, ""
    return head.strip(), rest


def _covered_components(raw_params: str) -> list[str]:
    start, end = raw_params.find("("), raw_params.find(")")
    if start < 0 or end <= start:
        return []
    inside = raw_params[start + 1 : end]
    return [token.strip().strip('"') for token in inside.split() if token.strip()]


def _parse_params(raw_params: str) -> dict[str, str]:
    tail = raw_params.split(")", 1)[1] if ")" in raw_params else ""
    params: dict[str, str] = {}
    for part in tail.split(";"):
        key, sep, value = part.partition("=")
        if sep:
            params[key.strip()] = value.strip().strip('"')
    return params


def _decode_signature_value(raw_sig: str, label: str) -> bytes | None:
    for member in raw_sig.split(","):
        head, sep, value = member.strip().partition("=")
        if sep and head.strip() == label:
            return _b64_or_none(value.strip().strip(":"))
    return None


def _b64_or_none(token: str) -> bytes | None:
    padded = token + "=" * ((-len(token)) % 4)
    try:
        return base64.b64decode(padded)
    except (binascii.Error, ValueError):
        return None
