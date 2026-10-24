"""Polyglot Multi-Language Remediation & Safety Verification Engine.

Extends TraceHeal's remediation pipeline across enterprise tech stacks:
- Python (FastAPI, Flask, Django, Asyncio)
- Go (Gin, Fiber, Standard net/http, database/sql)
- Node.js / TypeScript (Express, Fastify, NestJS, Axios, pg)

Performs AST parsing, syntax validation, language-specific security checks,
and resilience pattern verification.
"""

import ast
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel


class SupportedLanguage(str, Enum):
    PYTHON = "python"
    GO = "golang"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    UNKNOWN = "unknown"


class LanguageValidationResult(BaseModel):
    language: SupportedLanguage
    is_valid_syntax: bool
    syntax_error: Optional[str] = None
    security_violations: List[str] = []
    resilience_patterns_detected: List[str] = []
    recommended_patterns: List[str] = []
    score: float = 1.0


class PolyglotEngine:
    """Multi-language AST parsing and security gate."""

    DANGEROUS_PATTERNS = {
        SupportedLanguage.PYTHON: [
            (r"\beval\(", "Execution of arbitrary code via eval()"),
            (r"\bexec\(", "Dynamic code execution via exec()"),
            (r"os\.system\(", "Unsanitized system shell execution"),
            (r"subprocess\..*shell\s*=\s*True", "Shell command injection vulnerability"),
            (r"__import__\(", "Dangerous dynamic reflection import"),
        ],
        SupportedLanguage.GO: [
            (r"unsafe\.Pointer", "Use of unsafe pointer arithmetic in remediation patch"),
            (r"os/exec\.Command\([^\)]*sh\b", "Arbitrary shell spawning via exec.Command"),
            (r"syscall\.Syscall", "Raw OS syscall invoked directly"),
        ],
        SupportedLanguage.JAVASCRIPT: [
            (r"\beval\(", "Execution of arbitrary code via eval()"),
            (r"new\s+Function\(", "Arbitrary code execution via Function constructor"),
            (r"child_process\.exec\(", "Unsanitized shell invocation via child_process"),
            (r"vm\.runInContext\(", "Sandboxed VM execution escape risk"),
        ],
        SupportedLanguage.TYPESCRIPT: [
            (r"\beval\(", "Execution of arbitrary code via eval()"),
            (r"new\s+Function\(", "Arbitrary code execution via Function constructor"),
            (r"child_process\.exec\(", "Unsanitized shell invocation via child_process"),
        ],
    }

    RESILIENCE_PATTERNS = {
        SupportedLanguage.PYTHON: [
            (r"timeout\s*=\s*\d+", "HTTP/Socket Timeout configuration"),
            (r"max_connections|pool_size", "Connection pool sizing boundary"),
            (r"retry|retries", "Transient fault retry policy"),
            (r"circuit_breaker", "Circuit breaker pattern"),
        ],
        SupportedLanguage.GO: [
            (r"context\.WithTimeout", "Go Context with bounded deadline/timeout"),
            (r"SetMaxOpenConns", "Database connection pool hard ceiling"),
            (r"SetMaxIdleConns", "Database connection pool idle lifecycle"),
            (r"time\.Second|time\.Millisecond", "Temporal timeout duration parameter"),
        ],
        SupportedLanguage.JAVASCRIPT: [
            (r"timeout:\s*\d+", "Axios/Fetch HTTP timeout configuration"),
            (r"AbortController", "Modern AbortController timeout cancellation"),
            (r"pool\s*:\s*\{[^}]*max\s*:", "Connection pool max limits"),
        ],
        SupportedLanguage.TYPESCRIPT: [
            (r"timeout:\s*\d+", "Axios/Fetch HTTP timeout configuration"),
            (r"AbortController", "Modern AbortController timeout cancellation"),
            (r"pool\s*:\s*\{[^}]*max\s*:", "Connection pool max limits"),
        ],
    }

    @classmethod
    def detect_language(cls, filename: Optional[str] = None, content: str = "") -> SupportedLanguage:
        """Detects programming language from filename extension or code signatures."""
        if filename:
            fn = filename.lower()
            if fn.endswith(".py"):
                return SupportedLanguage.PYTHON
            if fn.endswith(".go"):
                return SupportedLanguage.GO
            if fn.endswith(".ts") or fn.endswith(".tsx"):
                return SupportedLanguage.TYPESCRIPT
            if fn.endswith(".js") or fn.endswith(".jsx") or fn.endswith(".mjs"):
                return SupportedLanguage.JAVASCRIPT

        # Fallback to signature detection
        if re.search(r"\bdef\s+\w+\(|import\s+asyncio|from\s+\w+\s+import", content):
            return SupportedLanguage.PYTHON
        if re.search(r"\bpackage\s+\w+|\bfunc\s+\w+\(|\bimport\s+\(", content):
            return SupportedLanguage.GO
        if re.search(r"\binterface\s+\w+|\btype\s+\w+\s*=|const\s+\w+:\s*\w+", content):
            return SupportedLanguage.TYPESCRIPT
        if re.search(r"\bconst\s+\w+\s*=\s*require|\bexport\s+default|\bfunction\s+\w+\(", content):
            return SupportedLanguage.JAVASCRIPT

        return SupportedLanguage.PYTHON  # Default to Python in TraceHeal

    @classmethod
    def validate_syntax(cls, language: SupportedLanguage, code: str) -> Tuple[bool, Optional[str]]:
        """Validates code syntax according to language-specific parser."""
        if not code or not code.strip():
            return False, "Code content is empty."

        if language == SupportedLanguage.PYTHON:
            try:
                ast.parse(code)
                return True, None
            except SyntaxError as err:
                return False, f"Python Syntax Error on line {err.lineno}: {err.msg}"

        if language in (SupportedLanguage.JAVASCRIPT, SupportedLanguage.TYPESCRIPT):
            # Balanced bracket & quote validation
            stack = []
            matching = {')': '(', '}': '{', ']': '['}
            in_string = None
            escaped = False

            for idx, ch in enumerate(code):
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == '\\':
                        escaped = True
                    elif ch == in_string:
                        in_string = None
                    continue

                if ch in ("'", '"', '`'):
                    in_string = ch
                    continue

                if ch in matching.values():
                    stack.append(ch)
                elif ch in matching:
                    if not stack or stack[-1] != matching[ch]:
                        return False, f"Unbalanced delimiter '{ch}' at position {idx}."
                    stack.pop()

            if stack:
                return False, f"Unclosed token '{stack[-1]}' at end of file."
            return True, None

        if language == SupportedLanguage.GO:
            # Go structural balance check
            if not re.search(r"\bfunc\b|\bpackage\b|\btype\b|\bimport\b|\bvar\b|\bconst\b", code):
                return False, "Invalid Go syntax: missing package or function declarations."
            open_braces = code.count("{")
            close_braces = code.count("}")
            if open_braces != close_braces:
                return False, f"Unbalanced curly braces in Go patch: {open_braces} open vs {close_braces} closed."
            return True, None

        return True, None

    @classmethod
    def evaluate_polyglot_patch(
        cls,
        code: str,
        filename: Optional[str] = None,
        language_override: Optional[SupportedLanguage] = None,
    ) -> LanguageValidationResult:
        """Runs complete syntactic and security evaluation on a proposed multi-language code patch."""
        lang = language_override or cls.detect_language(filename, code)
        is_valid_syntax, syntax_error = cls.validate_syntax(lang, code)

        violations: List[str] = []
        patterns_to_check = cls.DANGEROUS_PATTERNS.get(lang, [])
        for pat, desc in patterns_to_check:
            if re.search(pat, code):
                violations.append(desc)

        detected_resilience: List[str] = []
        resilience_checks = cls.RESILIENCE_PATTERNS.get(lang, [])
        for pat, desc in resilience_checks:
            if re.search(pat, code, re.IGNORECASE):
                detected_resilience.append(desc)

        recommendations: List[str] = []
        if lang == SupportedLanguage.GO:
            if "Go Context with bounded deadline/timeout" not in detected_resilience:
                recommendations.append("Consider binding long-running operations with context.WithTimeout().")
            if "Database connection pool hard ceiling" not in detected_resilience and "db" in code.lower():
                recommendations.append("Configure db.SetMaxOpenConns() to prevent connection starvation.")
        elif lang in (SupportedLanguage.JAVASCRIPT, SupportedLanguage.TYPESCRIPT):
            if not any("Timeout" in d for d in detected_resilience):
                recommendations.append("Configure explicit HTTP timeout or AbortSignal to avoid socket hangs.")
        elif lang == SupportedLanguage.PYTHON:
            if not any("Timeout" in d for d in detected_resilience):
                recommendations.append("Pass explicit timeout parameter to async client calls.")

        score = 1.0
        if not is_valid_syntax:
            score = 0.0
        elif violations:
            score = max(0.0, 1.0 - (0.4 * len(violations)))

        return LanguageValidationResult(
            language=lang,
            is_valid_syntax=is_valid_syntax,
            syntax_error=syntax_error,
            security_violations=violations,
            resilience_patterns_detected=detected_resilience,
            recommended_patterns=recommendations,
            score=round(score, 2),
        )
