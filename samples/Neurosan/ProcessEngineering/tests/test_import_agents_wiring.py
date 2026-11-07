"""Wiring coverage for the two document-IMPORT networks (reads a directory
of already-existing process/design source files and persists them directly
into this toolkit's own JSON schema, distinct from the directory-context
mode embedded in process.hocon/design.hocon's own analysis stage). Mirrors
the ADK port's tests/test_import_agents_wiring.py.

Structural HOCON validation (including that every "class" path referenced
below actually resolves via neuro-san's own Resolver) is covered separately
by test_hocon_validation.py -- this file instead locks in that each
per-network shim re-exports the right class, and that the router's own
instructions actually mention both new networks.
"""

from pathlib import Path

from coded_tools.process_import.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as ProcessImportLoadDirectoryContextCodedTool,
)
from coded_tools.process_import.process_json_tool import (
    LoadMasterProcessJsonCodedTool,
    PersistFinalJsonCodedTool,
    ValidateProcessJsonCodedTool,
)
from coded_tools.design_import.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as DesignImportLoadDirectoryContextCodedTool,
)
from coded_tools.design_import.design_json_tool import (
    LoadMasterDesignJsonCodedTool,
    PersistFinalDesignJsonCodedTool,
    ValidateDesignJsonCodedTool,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_process_import_shims_reexport_the_canonical_classes():
    # Same canonical implementations the process.hocon network itself uses --
    # a fresh class object per shim would mean the shim is pointing at a
    # copy/duplicate rather than re-exporting the real thing.
    from coded_tools.process.process_json_tool import (
        LoadMasterProcessJsonCodedTool as CanonicalLoad,
        PersistFinalJsonCodedTool as CanonicalPersist,
        ValidateProcessJsonCodedTool as CanonicalValidate,
    )
    from coded_tools.requirements_summary.load_directory_context_tool import (
        LoadDirectoryContextCodedTool as CanonicalLoadDirectoryContext,
    )

    assert LoadMasterProcessJsonCodedTool is CanonicalLoad
    assert PersistFinalJsonCodedTool is CanonicalPersist
    assert ValidateProcessJsonCodedTool is CanonicalValidate
    assert ProcessImportLoadDirectoryContextCodedTool is CanonicalLoadDirectoryContext


def test_design_import_shims_reexport_the_canonical_classes():
    from coded_tools.design.design_json_tool import (
        LoadMasterDesignJsonCodedTool as CanonicalLoad,
        PersistFinalDesignJsonCodedTool as CanonicalPersist,
        ValidateDesignJsonCodedTool as CanonicalValidate,
    )
    from coded_tools.requirements_summary.load_directory_context_tool import (
        LoadDirectoryContextCodedTool as CanonicalLoadDirectoryContext,
    )

    assert LoadMasterDesignJsonCodedTool is CanonicalLoad
    assert PersistFinalDesignJsonCodedTool is CanonicalPersist
    assert ValidateDesignJsonCodedTool is CanonicalValidate
    assert DesignImportLoadDirectoryContextCodedTool is CanonicalLoadDirectoryContext


def test_load_directory_context_tool_requires_directory_argument():
    # Same contract as the canonical tool (see test_requirements_summary_tools.py) --
    # exercised again here through each import network's own shim import path.
    assert ProcessImportLoadDirectoryContextCodedTool().invoke({}, {})["status"] == "ERROR"
    assert DesignImportLoadDirectoryContextCodedTool().invoke({}, {})["status"] == "ERROR"


def test_router_references_both_import_networks():
    router_text = (PROJECT_ROOT / "registries" / "process_architect.hocon").read_text(encoding="utf-8")
    assert "Process_Import_Agent" in router_text
    assert "Design_Import_Agent" in router_text
    assert '"/process_import"' in router_text
    assert '"/design_import"' in router_text


def test_manifest_registers_both_import_networks():
    manifest_text = (PROJECT_ROOT / "registries" / "manifest.hocon").read_text(encoding="utf-8")
    assert '"process_import.hocon"' in manifest_text
    assert '"design_import.hocon"' in manifest_text


def test_design_import_forbids_populating_the_other_variant_when_a_type_is_explicit():
    # Confirmed as a real bug via live testing: importing a directory with an
    # explicit "High-Level Design only -- no low-level design content, none
    # should be invented" request still ended up with enough low_level_design
    # content for an LLD Word document to render successfully, when the
    # explicit request should have made that impossible (see
    # process_toolkit.docgen.generation's own _resolve_design_variant, which
    # treats ANY truthy low_level_design as real content). STEP 4's general
    # "infer a reasonable value" guidance was silently overriding the
    # document_type-implied scope -- this HARD RULE makes the exclusion
    # explicit and gives it precedence.
    text = (PROJECT_ROOT / "registries" / "design_import.hocon").read_text(encoding="utf-8")
    assert "HARD RULE, NO EXCEPTIONS" in text
    idx = text.index("HARD RULE, NO EXCEPTIONS")
    rule_text = text[idx:idx + 800]
    assert 'document_type is "HLD"' in rule_text
    assert "low_level_design key" in rule_text
    assert "MUST be entirely absent" in rule_text
    assert 'document_type is "LLD"' in rule_text
    assert "high_level_design MUST be entirely absent" in rule_text
