"""Always-local re-export -- pure computation, no disk I/O of its own
(the actual save/load lives in test_specification/test_specification.py, a
separate switchable module)."""

from process_toolkit.schema.test_specification_json import (
    load_test_specification_template,
    validate_test_specification,
)

__all__ = ["load_test_specification_template", "validate_test_specification"]
