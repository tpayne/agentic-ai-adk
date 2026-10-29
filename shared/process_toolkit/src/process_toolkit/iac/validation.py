"""Syntax validation for generated Infrastructure-as-Code files.

Dispatches each file to a REAL parser keyed off its extension -- Terraform/
tfvars HCL (python-hcl2), YAML (CloudFormation/Pulumi-YAML/SAM), JSON
(CloudFormation-JSON/ARM/Bicep-compiled-JSON/Pulumi-JSON/package.json
alongside a CDK project), and Python (Pulumi-Python/CDK-Python) via the
stdlib `ast` module. This project has no dependency on a Terraform/Bicep/
Node toolchain to shell out to (and adding one for every possible IaC
language -- Go, TypeScript, Java, C#, real .bicep -- is out of scope), so
anything outside those extensions falls back to a best-effort structural
heuristic (balanced brackets/quotes, non-empty) that is ALWAYS reported
with best_effort=True -- never silently presented as a real syntax check
the way the real parsers above are.
"""

import ast
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

import hcl2
import yaml


def _validate_hcl(content: str) -> Optional[str]:
    try:
        hcl2.loads(content)
        return None
    except Exception as e:  # python-hcl2 raises its own lark-based exception types
        return str(e)


def _validate_yaml(content: str) -> Optional[str]:
    try:
        yaml.safe_load(content)
        return None
    except yaml.YAMLError as e:
        return str(e)


def _validate_json(content: str) -> Optional[str]:
    try:
        json.loads(content)
        return None
    except json.JSONDecodeError as e:
        return str(e)


def _validate_python(content: str) -> Optional[str]:
    try:
        ast.parse(content)
        return None
    except SyntaxError as e:
        return f"{e.msg} (line {e.lineno})"


def _validate_best_effort(content: str) -> Optional[str]:
    """NOT a real syntax validator -- a generic structural sanity check
    for a language this module has no parser for. Only catches the
    crudest failures: empty content, or grossly unbalanced brackets/
    quotes. Every result produced by this function is reported with
    best_effort=True by validate_iac_files, so a caller can always tell
    the difference between "a real parser confirmed this" and "this is
    just a heuristic smell test"."""
    if not content.strip():
        return "File is empty."
    pairs = {"{": "}", "(": ")", "[": "]"}
    closers = set(pairs.values())
    stack: List[str] = []
    in_string: Optional[str] = None
    for ch in content:
        if in_string:
            if ch == in_string:
                in_string = None
            continue
        if ch in ('"', "'"):
            in_string = ch
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in closers:
            if not stack or stack.pop() != ch:
                return f"Unbalanced '{ch}' -- possible syntax error."
    if stack:
        return f"Unclosed {stack[-1]!r} -- possible syntax error."
    return None


# Longest/most-specific suffix first -- checked in order, first match wins.
_VALIDATORS_BY_SUFFIX: List[Tuple[str, str, Callable[[str], Optional[str]]]] = [
    (".tfvars", "hcl", _validate_hcl),
    (".tf", "hcl", _validate_hcl),
    (".yaml", "yaml", _validate_yaml),
    (".yml", "yaml", _validate_yaml),
    (".json", "json", _validate_json),
    (".py", "python", _validate_python),
]


def validate_iac_files(files: Dict[str, str]) -> Dict[str, Any]:
    """Validates each file's syntax. Returns:
    {"valid": bool, "files": [{"file", "valid", "best_effort", "format", "error"}]}

    "valid" at the top level is True only if EVERY file validated True --
    a single malformed file fails the whole batch, matching this project's
    existing "the whole document must be valid" convention elsewhere
    (e.g. validate_design_json/validate_process_json).
    """
    results = []
    all_valid = True
    for filename, content in files.items():
        lower = filename.lower()
        matched = next(
            ((fmt, validator) for suffix, fmt, validator in _VALIDATORS_BY_SUFFIX if lower.endswith(suffix)),
            None,
        )
        best_effort = matched is None
        fmt, validator = matched or ("unknown", _validate_best_effort)
        error = validator(content)
        valid = error is None
        if not valid:
            all_valid = False
        results.append({
            "file": filename,
            "valid": valid,
            "best_effort": best_effort,
            "format": fmt,
            "error": error,
        })
    return {"valid": all_valid, "files": results}
