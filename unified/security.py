"""
AI-OS Deterministic Security Subsystem
Ring-0 capability security engine, Data Loss Prevention (DLP) scanner,
and prompt injection firewall.
"""

import time
import re
import uuid
import hmac
import hashlib
from typing import Dict, Any, List, Tuple, Optional

class SecurityViolationError(Exception):
    pass

class DLPScanner:
    """Detects and redacts secrets, credentials, and sensitive personal identifiers."""
    PATTERNS = [
        (re.compile(r"(sk-[a-zA-Z0-9]{20,})"), "[REDACTED_API_KEY]"),
        (re.compile(r"(ghp_[a-zA-Z0-9]{20,})"), "[REDACTED_GITHUB_TOKEN]"),
        (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
        (re.compile(r"(password\s*[:=]\s*['\"][^'\"]+['\"])", re.IGNORECASE), "password:[REDACTED]"),
        (re.compile(r"(bearer\s+[a-zA-Z0-9_\-\.]{25,})", re.IGNORECASE), "Bearer [REDACTED_TOKEN]")
    ]

    @classmethod
    def sanitize(cls, text: str) -> Tuple[str, bool]:
        sanitized = text
        found_leak = False
        for pattern, replacement in cls.PATTERNS:
            if pattern.search(sanitized):
                found_leak = True
                sanitized = pattern.sub(replacement, sanitized)
        return sanitized, found_leak

class PromptInjectionGuard:
    """Quarantines untrusted inputs and detects adversarial hijacking attempts."""
    INJECTION_SIGNATURES = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
        re.compile(r"disregard\s+(all\s+)?system\s+prompts", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
        re.compile(r"system\s+override\s*:\s*execute", re.IGNORECASE),
        re.compile(r"exfiltrate\s+to\s+http", re.IGNORECASE)
    ]

    @classmethod
    def inspect(cls, prompt: str) -> Tuple[bool, Optional[str]]:
        for pattern in cls.INJECTION_SIGNATURES:
            if pattern.search(prompt):
                return False, f"Prompt injection signature detected: '{pattern.pattern}'"
        return True, None

class CapabilityEngine:
    """
    Object-Capability (ocap) security manager.
    Enforces that agents only perform actions granted by unforgeable cryptographic tokens.
    """
    def __init__(self, secret_key: bytes = b"aios_kernel_ring0_entropy_2026"):
        self.secret_key = secret_key

    def issue_token(self, agent_id: str, scopes: List[str], max_tokens: int, ttl_sec: int = 3600) -> Dict[str, Any]:
        token_id = f"ocap_{uuid.uuid4().hex[:8]}"
        issued_at = int(time.time())
        expires_at = issued_at + ttl_sec
        scopes_sorted = sorted(list(set(scopes)))
        payload = f"{token_id}:{agent_id}:{issued_at}:{expires_at}:{max_tokens}:{','.join(scopes_sorted)}".encode()
        signature = hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()

        return {
            "token_id": token_id,
            "agent_id": agent_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "max_tokens": max_tokens,
            "scopes": scopes_sorted,
            "signature": signature
        }

    def verify(self, token: Dict[str, Any], requested_scope: str) -> Tuple[bool, str]:
        now = int(time.time())
        if now > token["expires_at"]:
            return False, "Capability token expired"

        scopes_sorted = sorted(list(set(token["scopes"])))
        payload = f"{token['token_id']}:{token['agent_id']}:{token['issued_at']}:{token['expires_at']}:{token['max_tokens']}:{','.join(scopes_sorted)}".encode()
        expected = hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(token["signature"], expected):
            return False, "Cryptographic signature mismatch"

        # Permission evaluation
        for allowed in token["scopes"]:
            if allowed == "*" or allowed == requested_scope:
                return True, "Authorized"
            if allowed.endswith(":*") and requested_scope.startswith(allowed[:-2]):
                return True, "Authorized by wildcard scope"

        return False, f"Unauthorized scope requested: '{requested_scope}'"
