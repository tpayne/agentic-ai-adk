from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRIES = PROJECT_ROOT / "registries"


def test_manifest_registers_project_plan_export_network():
    text = (REGISTRIES / "manifest.hocon").read_text(encoding="utf-8")
    assert '"project_plan_export.hocon": true' in text


def test_router_routes_and_enables_project_plan_export_network():
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_start = text.index('"tools": [', orchestrator_start)
    tools_text = text[tools_start:text.index("]", tools_start)]

    assert '"/project_plan_export"' in tools_text
    assert "# PROJECT PLAN (MS PROJECT / PROJECTLIBRE) EXPORT" in text
    assert "call `/project_plan_export`" in text


def test_router_requires_specific_wording_not_a_bare_plan():
    # CONFIRMED anti-collision discipline, same as the vsdx/"vision
    # document" substring guard: a bare "plan" must not trigger this
    # section, since that word alone is routine phrasing for the
    # backlog/proposal itself.
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    section_start = text.index("# PROJECT PLAN (MS PROJECT / PROJECTLIBRE) EXPORT")
    section_text = text[section_start:section_start + 2000]
    assert 'Do NOT trigger on a bare "plan" alone' in section_text
    assert '"project plan"' in section_text
    assert '"MS Project"' in section_text
    assert '"ProjectLibre"' in section_text


def test_project_plan_export_network_front_man_determines_schema_type():
    text = (REGISTRIES / "project_plan_export.hocon").read_text(encoding="utf-8")
    assert '"name": "Project_Plan_Export_Agent_Main"' in text
    assert "DETERMINE schema_type FIRST" in text
    assert "schema_type =" in text
    assert "export_project_plan" in text
    assert '"enum": ["portfolio_backlog", "proposal_response"]' in text


def test_project_plan_export_network_never_overwrites_the_saved_source_json():
    # Structural guarantee: the ONLY tool this network's front-man can
    # call is export_project_plan, which itself has no save/persist path
    # for portfolio_backlog.json/proposal_response.json -- this network
    # cannot mutate either source artifact even if asked to.
    text = (REGISTRIES / "project_plan_export.hocon").read_text(encoding="utf-8")
    assert '"tools": ["export_project_plan"]' in text
    assert "save_portfolio_backlog" not in text
    assert "save_proposal_response" not in text


def test_coded_tool_delegates_to_shared_project_plan_persistence():
    text = (
        PROJECT_ROOT / "coded_tools" / "project_plan_export" / "project_plan_export_tool.py"
    ).read_text(encoding="utf-8")
    assert "from process_interface.docgen.project_plan_export import" in text
    assert "build_portfolio_backlog_project_plan" in text
    assert "build_proposal_response_project_plan" in text


def test_coded_tool_passes_resources_duration_and_holiday_calendar_through():
    text = (
        PROJECT_ROOT / "coded_tools" / "project_plan_export" / "project_plan_export_tool.py"
    ).read_text(encoding="utf-8")
    assert 'args.get("resources")' in text
    assert 'args.get("target_duration_weeks")' in text
    assert 'args.get("holiday_calendar")' in text


def test_export_project_plan_tool_schema_declares_resources_duration_and_holiday_calendar():
    text = (REGISTRIES / "project_plan_export.hocon").read_text(encoding="utf-8")
    assert '"resources"' in text
    assert '"allocation_percent"' in text
    assert '"target_duration_weeks"' in text
    assert '"holiday_calendar"' in text
    assert '"enum": ["uk"]' in text


def test_front_man_instructs_extraction_not_fabrication_of_planning_assumptions():
    # CONFIRMED AS A REAL GAP otherwise: without this, a front-man would
    # have no guidance on resources/duration/holidays at all -- and no
    # instruction NOT to fabricate a role/percentage/target the user never
    # actually stated.
    text = (REGISTRIES / "project_plan_export.hocon").read_text(encoding="utf-8")
    assert "OPTIONAL PLANNING ASSUMPTIONS" in text
    assert "never fabricate any of" in text
    assert "never invent a role or guess a" in text
    assert 'Only "uk" is supported' in text
    assert 'relay it verbatim' in text or "WARNING" in text


def test_front_man_mentions_the_companion_pert_cpm_diagram():
    # The tool's own return message always includes the PERT/CPM path (see
    # process_toolkit.docgen.project_plan_export's own
    # _build_and_write_pert_cpm) -- the front-man must be told to relay it,
    # not just the primary project-plan path.
    text = (REGISTRIES / "project_plan_export.hocon").read_text(encoding="utf-8")
    assert "PERT/CPM" in text
    assert "relay that path too" in text


def test_router_acknowledges_project_plan_wording_when_nothing_is_saved_yet():
    # CONFIRMED AS A REAL PRODUCTION BUG: a live run asked for a project
    # plan (nothing saved yet) and the router silently dropped "project
    # plan" entirely, asking an unrelated "Business Process Design or
    # Portfolio Backlog?" clarifying question that never mentioned a
    # project plan at all -- even though that is exactly what was asked
    # for. This carve-out must exist so that failure mode cannot recur.
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    assert "### PROJECT PLAN REQUESTED BUT NOTHING SAVED YET" in text
    section_start = text.index("### PROJECT PLAN REQUESTED BUT NOTHING SAVED YET")
    section_text = text[section_start:section_start + 2500]
    assert "CONFIRMED AS A REAL PRODUCTION BUG" in section_text
    assert "Business Process Design" in section_text
    assert "never mentioned a project" in section_text
    assert "you MUST explicitly acknowledge \"project plan\"" in section_text


def test_router_routes_portfolio_backlog_what_if_to_consultant_not_the_mutating_pipeline():
    # CONFIRMED AS A REAL PRODUCTION BUG: a live run asked a plain
    # hypothetical question about an already-saved backlog ("what if the
    # BA and SA allocations were changed to 60% instead of 40-50%") and
    # the router treated it as a literal update instruction, routing it to
    # Portfolio_Backlog_Pipeline -- which actually rewrote
    # portfolio_backlog.json/.xlsx with the new allocations instead of
    # answering the "what if" analysis. Sections 5a-5d already establish
    # this carve-out for process/design/TOGAF/ITSM; this is 5e, extending
    # it to Portfolio Backlog.
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    assert "### 5e. ENTERPRISE AGILE PORTFOLIO BACKLOG WHAT-IF SCENARIOS" in text
    section_start = text.index("### 5e. ENTERPRISE AGILE PORTFOLIO BACKLOG WHAT-IF SCENARIOS")
    section_text = text[section_start:section_start + 2000]
    assert "CONFIRMED AS A REAL PRODUCTION BUG" in section_text
    assert "Call: Portfolio_Backlog_Consultant_Agent" in section_text
    assert "ALWAYS routes to Portfolio_Backlog_Consultant_Agent" in section_text

    # The Tier-3 (Scenario/What-if) priority entry must list Portfolio
    # Backlog too, since Tier 1 (Creation or explicit update) is checked
    # first and would otherwise win every time.
    tier_line = text[text.index("3. Scenario / What-if"):]
    tier_line = tier_line[:tier_line.index("\n")]
    assert "Portfolio_Backlog_Consultant_Agent" in tier_line

    # 1g's own trigger must now explicitly exclude hypothetical phrasing,
    # not just rely on 5e existing elsewhere -- same discipline as every
    # other anti-collision carve-out in this file.
    section_1g_start = text.index("### 1g. ENTERPRISE AGILE PORTFOLIO BACKLOG CREATION OR UPDATE")
    section_1g_text = text[section_1g_start:section_1g_start + 1200]
    assert "Does NOT apply when the request is hypothetical/conditional" in section_1g_text
    assert "Section 5e" in section_1g_text


def test_save_portfolio_backlog_notes_a_stale_project_plan():
    # Companion fix to the routing bug above: even a GENUINE update should
    # tell the user that a previously-exported project plan (and its
    # PERT/CPM diagram) are now stale, since nothing in this codebase
    # auto-regenerates either (project_plan_export is deliberately
    # export-only -- see its own module docstring).
    text = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "shared" / "process_interface" / "src" / "process_interface"
        / "portfolio_backlog" / "portfolio_backlog.py"
    ).read_text(encoding="utf-8")
    assert "portfolio_backlog_project_plan_exists" in text
    assert "neither was regenerated and both may now be" in text
    assert "PORTFOLIO_BACKLOG_PERT_CPM_FILENAME" in text


def test_portfolio_backlog_gained_an_optional_non_authoritative_directory_read_step():
    text = (REGISTRIES / "portfolio_backlog.hocon").read_text(encoding="utf-8")
    assert "OPTIONAL SUPPORTING CONTEXT: EXISTING PROJECT PLAN" in text
    assert "load_directory_context" in text
    assert "NEVER replaces the design/requirements_summary source of truth" in text
    assert "NEVER introduces an epic/feature/story/traces_to that isn't grounded" in text
    assert '"class": "load_directory_context_tool.LoadDirectoryContextCodedTool"' in text


def test_project_plan_reviewer_shims_reexport_canonical_classes():
    from coded_tools.project_plan_reviewer.inspect_project_plan_tool import (
        InspectProjectPlanCodedTool as ReviewerInspectProjectPlan,
    )
    from coded_tools.project_plan_export.inspect_project_plan_tool import (
        InspectProjectPlanCodedTool as CanonicalInspectProjectPlan,
    )
    from coded_tools.project_plan_reviewer.load_portfolio_backlog_tool import (
        LoadPortfolioBacklogCodedTool as ReviewerLoadPortfolioBacklog,
    )
    from coded_tools.portfolio_backlog.load_portfolio_backlog_tool import (
        LoadPortfolioBacklogCodedTool as CanonicalLoadPortfolioBacklog,
    )
    from coded_tools.project_plan_reviewer.load_requirements_summary_tool import (
        LoadRequirementsSummaryCodedTool as ReviewerLoadRequirementsSummary,
    )
    from coded_tools.requirements_summary.load_requirements_summary_tool import (
        LoadRequirementsSummaryCodedTool as CanonicalLoadRequirementsSummary,
    )

    assert ReviewerInspectProjectPlan is CanonicalInspectProjectPlan
    assert ReviewerLoadPortfolioBacklog is CanonicalLoadPortfolioBacklog
    assert ReviewerLoadRequirementsSummary is CanonicalLoadRequirementsSummary

