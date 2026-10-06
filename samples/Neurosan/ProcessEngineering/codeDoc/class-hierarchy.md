# Python class hierarchy

This diagram has one node per Python class declaration in the package and tests. External nodes
are labeled with their owning package. Inheritance arrows follow declared bases.

Flatter than a typical ADK-style hierarchy by design: neuro-san's `CodedTool` interface is a
single-method entry point (`invoke(args, sly_data)`), not a class hierarchy, so 31 of this
project's 33 application classes are direct, sibling subclasses of the same external base with no
intermediate layers between them -- there's no equivalent of ADK's `DefaultLlmAgent`/`DefaultAgent`
wrapper tier, or its pydantic schema composition tree.

```mermaid
classDiagram
    direction LR

    class R01["LoopControlCodedTool (loop_control.py:76)"]
    class R02["_Box (cloudarch_layout_engine.py:157)"]
    class R03["ResetLoopStateCodedTool (reset_loop_state_tool.py:10)"]
    class R04["LoadIterationFeedbackCodedTool (load_iteration_feedback_tool.py:9)"]
    class R05["SaveIterationFeedbackCodedTool (save_iteration_feedback_tool.py:9)"]
    class R06["LoadDrawioCodedTool (load_drawio_tool.py:9)"]
    class R07["SaveDrawioStructuredCodedTool (save_drawio_structured_tool.py:18)"]
    class R08["SimulateCloudarchArchitectureCodedTool (simulate_cloudarch_architecture_tool.py:9)"]
    class R09["LoadMasterProcessJsonCodedTool (cloudarch/load_master_process_json_tool.py:9)"]
    class R10["LoadMasterProcessJsonCodedTool (process/process_json_tool.py:14)"]
    class R11["LoadProcessTemplateCodedTool (process_json_tool.py:25)"]
    class R12["ValidateProcessJsonCodedTool (process_json_tool.py:35)"]
    class R13["PersistFinalJsonCodedTool (process_json_tool.py:45)"]
    class R14["GenerateProcessFlowDiagramCodedTool (edge_inference_tool.py:9)"]
    class R15["LoadProcessStepsCodedTool (subprocess_tool.py:9)"]
    class R16["SaveSubprocessFlowCodedTool (subprocess_tool.py:20)"]
    class R17["SimulateProcessPerformanceCodedTool (simulation_tool.py:9)"]
    class R18["PerformSensitivityAnalysisCodedTool (simulation_tool.py:21)"]
    class R19["GenerateProcessDocumentCodedTool (doc_generation_tool.py:9)"]
    class R20["GenerateDesignFlowDiagramCodedTool (design/edge_inference_tool.py:9)"]
    class R21["LoadMasterDesignJsonCodedTool (design_json_tool.py:15)"]
    class R22["LoadDesignTemplateCodedTool (design_json_tool.py:27)"]
    class R23["LoadFullDesignContextCodedTool (design_json_tool.py:37)"]
    class R24["ValidateDesignJsonCodedTool (design_json_tool.py:49)"]
    class R25["PersistFinalDesignJsonCodedTool (design_json_tool.py:61)"]
    class R26["SimulateDesignArchitectureCodedTool (design/simulation_tool.py:9)"]
    class R27["PerformDesignSensitivityAnalysisCodedTool (design/simulation_tool.py:21)"]
    class R28["GenerateDesignDocumentCodedTool (design/doc_generation_tool.py:9)"]
    class R29["LoadDirectoryContextCodedTool (load_directory_context_tool.py:15)"]
    class R30["SaveRequirementsSummaryCodedTool (save_requirements_summary_tool.py:24)"]
    class R31["LoadRequirementsSummaryCodedTool (load_requirements_summary_tool.py:23)"]
    class R32["LiveTraceMessageProcessor (cli.py:164)"]
    class R33["ChatSession (cli.py:233)"]

    class T01["_StubSession (test_cli.py:50)"]
    class T02["TestLiveTraceMessageProcessor (test_cli.py:141)"]
    class T03["_StubInputProcessor (test_cli.py:198)"]

    class CodedTool["CodedTool (external: neuro_san.interfaces.coded_tool)"]
    class MessageProcessor["MessageProcessor (external: neuro_san.message.processors.message_processor)"]
    class AgentSessionFactory["AgentSessionFactory (external: neuro_san.client.agent_session_factory)"]
    class StreamingInputProcessor["StreamingInputProcessor (external: neuro_san.client.streaming_input_processor)"]

    R01 --|> CodedTool : declared base
    R03 --|> CodedTool : declared base
    R04 --|> CodedTool : declared base
    R05 --|> CodedTool : declared base
    R06 --|> CodedTool : declared base
    R07 --|> CodedTool : declared base
    R08 --|> CodedTool : declared base
    R09 --|> CodedTool : declared base
    R10 --|> CodedTool : declared base
    R11 --|> CodedTool : declared base
    R12 --|> CodedTool : declared base
    R13 --|> CodedTool : declared base
    R14 --|> CodedTool : declared base
    R15 --|> CodedTool : declared base
    R16 --|> CodedTool : declared base
    R17 --|> CodedTool : declared base
    R18 --|> CodedTool : declared base
    R19 --|> CodedTool : declared base
    R20 --|> CodedTool : declared base
    R21 --|> CodedTool : declared base
    R22 --|> CodedTool : declared base
    R23 --|> CodedTool : declared base
    R24 --|> CodedTool : declared base
    R25 --|> CodedTool : declared base
    R26 --|> CodedTool : declared base
    R27 --|> CodedTool : declared base
    R28 --|> CodedTool : declared base
    R29 --|> CodedTool : declared base
    R30 --|> CodedTool : declared base
    R31 --|> CodedTool : declared base
    R32 --|> MessageProcessor : declared base

    R33 *-- AgentSessionFactory : creates self.session via create_session()
    R33 *-- StreamingInputProcessor : self.input_processor
    StreamingInputProcessor *-- R32 : added via get_message_processor().add_processor()

    T01 ..> R33 : test double for
    T03 ..> StreamingInputProcessor : test double for
```

## Notes

- R02 (`_Box`) and R33 (`ChatSession`) are the only two application classes with no declared base.
  `_Box` is a plain internal value object used by `cloudarch_layout_engine.py`'s deterministic
  layout algorithm (position/size of one diagram box); it has no relationship to anything else in
  this inventory.
- R09/R10 share a name but are declared independently in different modules -- see
  [class-inventory.md](class-inventory.md)'s note on why.
- No `@dataclass` declarations or enum subclasses were found under this project's own code (unlike
  the ADK original's pydantic schema cluster, which doesn't exist here -- `CodedTool.invoke()`
  takes/returns plain `Dict[str, Any]`, validated procedurally in `coded_tools/common/process_json.py`
  and `design_json.py` rather than via typed schema classes).
