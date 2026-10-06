# Python class inventory

Scope: all `class` statements under `coded_tools/` (excluding the neuro-san-studio scaffolding
directories this project did not write -- `agent_network_editor/`, `agent_network_instructions_editor/`,
`agent_network_query_generator/`, `agent_network_test_generator/`, `experimental/`), `cli.py`, and
`tests/`, including nested test doubles. Inheritance names below are the bases written in source;
external bases are identified by package. Class IDs are reused in the
[hierarchy diagram](class-hierarchy.md).

Most of this project's own logic lives in plain functions (`coded_tools/common/*.py`,
`coded_tools/common/docgen/*.py`), not classes -- a direct consequence of neuro-san's `CodedTool`
interface being a thin `invoke(args, sly_data)` entry point rather than a class hierarchy the way
ADK's `LlmAgent`/`BaseAgent`/`SequentialAgent`/`LoopAgent` composition is. Every
`coded_tools/<network>/*.py` module not listed below (the large majority) is a one-line re-export
of a class that IS listed here, declared once under `coded_tools/common/`, `coded_tools/cloudarch/`,
`coded_tools/process/`, `coded_tools/design/`, or `coded_tools/requirements_summary/` -- see
`coded_tools/<network>/`'s own files for exactly which shared class each one re-exports.

## Application classes (33)

| ID | Class | Source | Declared base |
|---|---|---|---|
| R01 | `LoopControlCodedTool` | `coded_tools/common/loop_control.py:76` | `neuro_san.interfaces.coded_tool.CodedTool` |
| R02 | `_Box` | `coded_tools/cloudarch/cloudarch_layout_engine.py:157` | none |
| R03 | `ResetLoopStateCodedTool` | `coded_tools/cloudarch/reset_loop_state_tool.py:10` | `CodedTool` |
| R04 | `LoadIterationFeedbackCodedTool` | `coded_tools/cloudarch/load_iteration_feedback_tool.py:9` | `CodedTool` |
| R05 | `SaveIterationFeedbackCodedTool` | `coded_tools/cloudarch/save_iteration_feedback_tool.py:9` | `CodedTool` |
| R06 | `LoadDrawioCodedTool` | `coded_tools/cloudarch/load_drawio_tool.py:9` | `CodedTool` |
| R07 | `SaveDrawioStructuredCodedTool` | `coded_tools/cloudarch/save_drawio_structured_tool.py:18` | `CodedTool` |
| R08 | `SimulateCloudarchArchitectureCodedTool` | `coded_tools/cloudarch/simulate_cloudarch_architecture_tool.py:9` | `CodedTool` |
| R09 | `LoadMasterProcessJsonCodedTool` (cloudarch's own copy) | `coded_tools/cloudarch/load_master_process_json_tool.py:9` | `CodedTool` |
| R10 | `LoadMasterProcessJsonCodedTool` (process's own copy) | `coded_tools/process/process_json_tool.py:14` | `CodedTool` |
| R11 | `LoadProcessTemplateCodedTool` | `coded_tools/process/process_json_tool.py:25` | `CodedTool` |
| R12 | `ValidateProcessJsonCodedTool` | `coded_tools/process/process_json_tool.py:35` | `CodedTool` |
| R13 | `PersistFinalJsonCodedTool` | `coded_tools/process/process_json_tool.py:45` | `CodedTool` |
| R14 | `GenerateProcessFlowDiagramCodedTool` | `coded_tools/process/edge_inference_tool.py:9` | `CodedTool` |
| R15 | `LoadProcessStepsCodedTool` | `coded_tools/process/subprocess_tool.py:9` | `CodedTool` |
| R16 | `SaveSubprocessFlowCodedTool` | `coded_tools/process/subprocess_tool.py:20` | `CodedTool` |
| R17 | `SimulateProcessPerformanceCodedTool` | `coded_tools/process/simulation_tool.py:9` | `CodedTool` |
| R18 | `PerformSensitivityAnalysisCodedTool` | `coded_tools/process/simulation_tool.py:21` | `CodedTool` |
| R19 | `GenerateProcessDocumentCodedTool` | `coded_tools/process/doc_generation_tool.py:9` | `CodedTool` |
| R20 | `GenerateDesignFlowDiagramCodedTool` | `coded_tools/design/edge_inference_tool.py:9` | `CodedTool` |
| R21 | `LoadMasterDesignJsonCodedTool` | `coded_tools/design/design_json_tool.py:15` | `CodedTool` |
| R22 | `LoadDesignTemplateCodedTool` | `coded_tools/design/design_json_tool.py:27` | `CodedTool` |
| R23 | `LoadFullDesignContextCodedTool` | `coded_tools/design/design_json_tool.py:37` | `CodedTool` |
| R24 | `ValidateDesignJsonCodedTool` | `coded_tools/design/design_json_tool.py:49` | `CodedTool` |
| R25 | `PersistFinalDesignJsonCodedTool` | `coded_tools/design/design_json_tool.py:61` | `CodedTool` |
| R26 | `SimulateDesignArchitectureCodedTool` | `coded_tools/design/simulation_tool.py:9` | `CodedTool` |
| R27 | `PerformDesignSensitivityAnalysisCodedTool` | `coded_tools/design/simulation_tool.py:21` | `CodedTool` |
| R28 | `GenerateDesignDocumentCodedTool` | `coded_tools/design/doc_generation_tool.py:9` | `CodedTool` |
| R29 | `LoadDirectoryContextCodedTool` | `coded_tools/requirements_summary/load_directory_context_tool.py:15` | `CodedTool` |
| R30 | `SaveRequirementsSummaryCodedTool` | `coded_tools/requirements_summary/save_requirements_summary_tool.py:24` | `CodedTool` |
| R31 | `LoadRequirementsSummaryCodedTool` | `coded_tools/requirements_summary/load_requirements_summary_tool.py:23` | `CodedTool` |
| R32 | `LiveTraceMessageProcessor` | `cli.py:164` | `neuro_san.message.processors.message_processor.MessageProcessor` |
| R33 | `ChatSession` | `cli.py:233` | none |

R09/R10 are two independently-declared classes with the identical name, in different modules --
not an import/re-export of one another. `coded_tools/cloudarch/`'s own copy reads the same
`process_data.json` baseline cloudarch needs (e.g. to ground a consultant/simulation answer against
real components), kept as its own thin declaration rather than an import across network
boundaries, the same reasoning `registries/*.hocon`'s own comments give for why some agents are
duplicated rather than cross-referenced (neuro-san's same-server external-agent references only
reach another network's front-man, not its internal tools).

## Test classes and doubles (3)

| ID | Class | Source | Declared base |
|---|---|---|---|
| T01 | `_StubSession` | `tests/test_cli.py:50` | none (test double for `cli.ChatSession`) |
| T02 | `TestLiveTraceMessageProcessor` | `tests/test_cli.py:141` | none (pytest-style grouping class, not `unittest.TestCase` -- this project's tests are plain `pytest` functions throughout; this is the one place tests are grouped into a class at all) |
| T03 | `_StubInputProcessor` | `tests/test_cli.py:198` (nested inside `test_send_logs_token_accounting_at_info`) | none (test double for `neuro_san.client.streaming_input_processor.StreamingInputProcessor`) |
