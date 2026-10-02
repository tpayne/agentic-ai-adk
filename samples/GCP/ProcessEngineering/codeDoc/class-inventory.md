# Python class inventory

Scope: all class statements under `process_agents/` and `tests/`, including
nested test doubles. Inheritance names below are the bases written in source;
external bases are identified by package. Class IDs are reused in the
[hierarchy diagram](class-hierarchy.md).

## Application classes (13)

| ID | Class | Source | Declared base |
|---|---|---|---|
| R01 | `_Box` | `process_agents/cloudarch/cloudarch_layout_agent.py:149` | none |
| R02 | `DefaultLlmAgent` | `process_agents/common/agent_wrappers.py:434` | `google.adk.agents.LlmAgent` |
| R03 | `DefaultAgent` | `process_agents/common/agent_wrappers.py:531` | `google.adk.agents.Agent` |
| R04 | `DocCreationAgent` | `process_agents/common/doc_creation_agent.py:48` | `google.adk.agents.BaseAgent` |
| R05 | `JitterAdapter` | `process_agents/common/grounding_agent.py:126` | `requests.adapters.HTTPAdapter` |
| R06 | `CleanedStdout` | `process_agents/common/utils.py:3395` | none |
| R07 | `SubprocessDriverAgent` | `process_agents/process/subprocess_driver_agent.py:30` | `google.adk.agents.BaseAgent` |
| R08 | `StepRiskControl` | `process_agents/process/subprocess_generator_agent.py:19` | `pydantic.BaseModel` |
| R09 | `ChangeManagement` | `process_agents/process/subprocess_generator_agent.py:23` | `pydantic.BaseModel` |
| R10 | `ContinuousImprovement` | `process_agents/process/subprocess_generator_agent.py:27` | `pydantic.BaseModel` |
| R11 | `SubprocessStep` | `process_agents/process/subprocess_generator_agent.py:31` | `pydantic.BaseModel` |
| R12 | `SubprocessFlow` | `process_agents/process/subprocess_generator_agent.py:67` | `pydantic.BaseModel` |
| R13 | `SubprocessWriterAgent` | `process_agents/process/subprocess_writer_agent.py:24` | `google.adk.agents.BaseAgent` |

## Test classes and doubles (48)

| ID | Class | Source | Declared base |
|---|---|---|---|
| T01 | `CloneOverrideTests` | `tests/test_agent_wrappers.py:11` | `unittest.TestCase` |
| T02 | `RetryHelperTests` | `tests/test_agent_wrappers.py:25` | `unittest.TestCase` |
| T03 | `QuotaError` | `tests/test_agent_wrappers.py:50` | `Exception` |
| T04 | `FakeCacheMetadata` | `tests/test_agent_wrappers.py:84` | none |
| T05 | `FakeRequest` | `tests/test_agent_wrappers.py:91` | none |
| T06 | `FakeModel` | `tests/test_agent_wrappers.py:106` | none |
| T07 | `Model` | `tests/test_agent_wrappers.py:160` | none |
| T08 | `AsyncModel` | `tests/test_agent_wrappers.py:173` | local `Model` at line 160 |
| T09 | `Model` | `tests/test_agent_wrappers.py:189` | none |
| T10 | `AsyncModel` | `tests/test_agent_wrappers.py:193` | local `Model` at line 189 |
| T11 | `WrapperConfigurationTests` | `tests/test_agent_wrappers.py:208` | `unittest.TestCase` |
| T12 | `CloudArchDrawioMcpToolTest` | `tests/test_cloudarch_drawio_mcp.py:60` | `unittest.TestCase` |
| T13 | `ComponentHeightTests` | `tests/test_cloudarch_layout_agent.py:12` | `unittest.TestCase` |
| T14 | `LayoutOverlapTests` | `tests/test_cloudarch_layout_agent.py:34` | `unittest.TestCase` |
| T15 | `EdgeRoutingTests` | `tests/test_cloudarch_layout_agent.py:101` | `unittest.TestCase` |
| T16 | `BuildXmlTests` | `tests/test_cloudarch_layout_agent.py:287` | `unittest.TestCase` |
| T17 | `ParseDrawioGraphTests` | `tests/test_cloudarch_simulation_agent.py:46` | `unittest.TestCase` |
| T18 | `CloudArchSimulationTests` | `tests/test_cloudarch_simulation_agent.py:73` | `unittest.TestCase` |
| T19 | `DesignSimulationTests` | `tests/test_design_simulation_agent.py:35` | `unittest.TestCase` |
| T20 | `HTTPAdapter` | `tests/test_grounding_agent.py:23` | none (test stub) |
| T21 | `SSLError` | `tests/test_grounding_agent.py:30` | `Exception` |
| T22 | `Retry` | `tests/test_grounding_agent.py:45` | none (test stub) |
| T23 | `LlmAgent` | `tests/test_grounding_agent.py:80` | none (test stub) |
| T24 | `Agent` | `tests/test_grounding_agent.py:84` | local `LlmAgent` at line 80 |
| T25 | `LiteLlm` | `tests/test_grounding_agent.py:87` | none (test stub) |
| T26 | `ToolContext` | `tests/test_grounding_agent.py:91` | none (test stub) |
| T27 | `HttpOptions` | `tests/test_grounding_agent.py:94` | none (test stub) |
| T28 | `GenerateContentConfig` | `tests/test_grounding_agent.py:98` | none (test stub) |
| T29 | `Gemini` | `tests/test_grounding_agent.py:105` | none (test stub) |
| T30 | `GroundingValidationTests` | `tests/test_grounding_agent.py:132` | `unittest.TestCase` |
| T31 | `DiGraph` | `tests/test_process_graph_helpers.py:14` | none (test stub) |
| T32 | `EdgeInferenceHelperTests` | `tests/test_process_graph_helpers.py:40` | `unittest.TestCase` |
| T33 | `StepDiagramHelperTests` | `tests/test_process_graph_helpers.py:78` | `unittest.TestCase` |
| T34 | `HttpOptions` | `tests/test_simulation_agent.py:40` | none (test stub) |
| T35 | `GenerateContentConfig` | `tests/test_simulation_agent.py:44` | none (test stub) |
| T36 | `SimulationParsingTests` | `tests/test_simulation_agent.py:62` | `unittest.TestCase` |
| T37 | `SimulationCoreTests` | `tests/test_simulation_agent.py:98` | `unittest.TestCase` |
| T38 | `LlmRequest` | `tests/test_utils.py:24` | none (test stub) |
| T39 | `LlmResponse` | `tests/test_utils.py:27` | none (test stub) |
| T40 | `CallbackContext` | `tests/test_utils.py:30` | none (test stub) |
| T41 | `ToolContext` | `tests/test_utils.py:33` | none (test stub) |
| T42 | `UtilsValidationTests` | `tests/test_utils.py:125` | `unittest.TestCase` |
| T43 | `UtilsPersistenceTests` | `tests/test_utils.py:211` | `unittest.TestCase` |
| T44 | `SaveDrawioShapeMappingTests` | `tests/test_utils.py:299` | `unittest.TestCase` |
| T45 | `UtilsAgentTests` | `tests/test_utils_agent_and_design_helpers.py:29` | `unittest.TestCase` |
| T46 | `DesignHelperTests` | `tests/test_utils_agent_and_design_helpers.py:83` | `unittest.TestCase` |
| T47 | `FakeDoc` | `tests/test_utils_agent_and_design_helpers.py:95` | none (test stub) |
| T48 | `WebServiceSessionDeleteTest` | `tests/test_web_service.py:7` | `unittest.TestCase` |
