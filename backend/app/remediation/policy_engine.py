"""Security & Safety Policy Verification Engine.

Enforces hard guardrails, allowlists, parameter constraints, and denylists
to prevent unsafe, malicious, or catastrophic remediation actions.
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from backend.app.remediation.polyglot import PolyglotEngine
from backend.app.schemas.remediation import PolicyCheckResult

ALLOWED_SERVICES = {
    "gateway-service",
    "order-service",
    "payment-service",
    "inventory-service",
    "auth-service",
    "notification-service",
}

BANNED_PATTERNS = [
    r"rm\s+-rf",
    r"mkfs",
    r"chmod\s+777",
    r"curl\s+",
    r"wget\s+",
    r"os\.system",
    r"subprocess\.",
    r"eval\(",
    r"exec\(",
    r"powershell",
    r"cmd\.exe",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM",
    r"TRUNCATE\s+TABLE",
    r"/etc/passwd",
    r"/etc/shadow",
    r"\.env",
    r"id_rsa",
    r"token[s]?\s*=",
    r"api[_-]?key",
]

PARAM_BOUNDS = {
    "max_connections": (1, 100),
    "acquire_timeout_sec": (0.01, 30.0),
    "hold_duration_sec": (0.0, 10.0),
    "extra_latency_sec": (0.0, 10.0),
    "latency_sec": (0.0, 10.0),
}


class PolicyEngine:
    """Evaluates proposed remediations against deterministic safety and security rules."""

    @classmethod
    def evaluate(
        cls,
        target_service: str,
        diff_content: str,
        patch_type: str = "CONFIG",
        config_parameters: Optional[Dict[str, Any]] = None,
        rollback_diff: Optional[str] = None,
    ) -> PolicyCheckResult:
        violations: List[str] = []
        passed_rules: List[str] = []
        evaluated_rules: List[str] = []

        # Rule 1: Service allowlist
        evaluated_rules.append("RULE_SERVICE_ALLOWLIST")
        if target_service not in ALLOWED_SERVICES:
            violations.append(
                f"Target service '{target_service}' is not in the allowed services list: {sorted(list(ALLOWED_SERVICES))}"
            )
        else:
            passed_rules.append("RULE_SERVICE_ALLOWLIST")

        # Rule 2: Banned command / injection denylist
        evaluated_rules.append("RULE_NO_DANGEROUS_COMMANDS")
        content_to_check = f"{diff_content}\n{rollback_diff or ''}"
        found_banned = []
        for pattern in BANNED_PATTERNS:
            if re.search(pattern, content_to_check, re.IGNORECASE):
                found_banned.append(pattern)
        if found_banned:
            violations.append(f"Diff contains restricted dangerous patterns: {found_banned}")
        else:
            passed_rules.append("RULE_NO_DANGEROUS_COMMANDS")

        # Rule 3: Diff bounds and structure
        evaluated_rules.append("RULE_DIFF_INTEGRITY")
        if not diff_content or not diff_content.strip():
            violations.append("Diff content cannot be empty.")
        else:
            line_count = len(diff_content.splitlines())
            if line_count > 200:
                violations.append(f"Diff exceeds maximum allowed patch size of 200 lines (found {line_count}).")
            else:
                passed_rules.append("RULE_DIFF_INTEGRITY")

        # Rule 4: Config parameter boundaries
        evaluated_rules.append("RULE_PARAMETER_BOUNDARIES")
        param_violations = []
        if config_parameters:
            for key, val in config_parameters.items():
                if key in PARAM_BOUNDS:
                    min_val, max_val = PARAM_BOUNDS[key]
                    try:
                        num_val = float(val)
                        if not (min_val <= num_val <= max_val):
                            param_violations.append(
                                f"Parameter '{key}' value {val} is outside safe boundary [{min_val}, {max_val}]."
                            )
                    except (ValueError, TypeError):
                        param_violations.append(f"Parameter '{key}' must be a numeric value, got '{val}'.")
        if param_violations:
            violations.extend(param_violations)
        else:
            passed_rules.append("RULE_PARAMETER_BOUNDARIES")

        # Rule 5: Rollback availability
        evaluated_rules.append("RULE_ROLLBACK_AVAILABLE")
        if not rollback_diff or not rollback_diff.strip():
            violations.append("Remediation proposal must include an executable rollback diff.")
        else:
            passed_rules.append("RULE_ROLLBACK_AVAILABLE")

        # Rule 6: Polyglot Multi-Language Safety Guardrails
        evaluated_rules.append("RULE_POLYGLOT_SAFETY")
        polyglot_eval = PolyglotEngine.evaluate_polyglot_patch(diff_content)
        if polyglot_eval.security_violations:
            for sec_violation in polyglot_eval.security_violations:
                violations.append(f"Polyglot guardrail violation ({polyglot_eval.language.value}): {sec_violation}")
        else:
            passed_rules.append("RULE_POLYGLOT_SAFETY")

        status = "PASSED" if len(violations) == 0 else "REJECTED"
        return PolicyCheckResult(
            status=status,
            violations=violations,
            passed_rules=passed_rules,
            evaluated_rules=evaluated_rules,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
