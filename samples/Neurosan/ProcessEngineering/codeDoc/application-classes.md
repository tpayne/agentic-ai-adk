# Application class diagram

This is the application-only view: all 33 classes from
[class-inventory.md](class-inventory.md), test fixtures omitted. Unlike the ADK original's
equivalent diagram (13 classes with a real composition tree -- pydantic schema nesting, ADK
`SequentialAgent` construction), 29 of the 33 classes here are direct, sibling subclasses of the
same external base (`neuro_san.interfaces.coded_tool.CodedTool`) with essentially the same shape:
a `name`/`description` docstring, an `invoke(self, args, sly_data)` method that calls one function
in `coded_tools/common/*.py`, and an `async_invoke` that wraps it via `asyncio.to_thread`. Rather
than repeat that shape 29 times, this diagram shows one representative
(`SaveDrawioStructuredCodedTool`) in full and lists the rest in a single members-free cluster box
per network area; full signatures for every one are in
[class-inventory.md](class-inventory.md).

The four classes with genuinely distinct state or behavior -- `_Box`, `LoopControlCodedTool`,
`LiveTraceMessageProcessor`, and `ChatSession` -- are shown with real members.

```mermaid
classDiagram
    direction LR

    class CodedTool["CodedTool<br/>external: neuro_san.interfaces.coded_tool"]

    class SaveDrawioStructuredCodedTool["SaveDrawioStructuredCodedTool<br/>cloudarch/save_drawio_structured_tool.py"] {
        +invoke(args, sly_data) Dict
        +async_invoke(args, sly_data) Dict
    }

    class CloudarchTools["Cloudarch tools (6 more)<br/>coded_tools/cloudarch/"] {
        ResetLoopStateCodedTool
        LoadIterationFeedbackCodedTool
        SaveIterationFeedbackCodedTool
        LoadDrawioCodedTool
        SimulateCloudarchArchitectureCodedTool
        LoadMasterProcessJsonCodedTool
    }
    class ProcessTools["Process tools (9)<br/>coded_tools/process/"] {
        LoadMasterProcessJsonCodedTool
        LoadProcessTemplateCodedTool
        ValidateProcessJsonCodedTool
        PersistFinalJsonCodedTool
        GenerateProcessFlowDiagramCodedTool
        LoadProcessStepsCodedTool
        SaveSubprocessFlowCodedTool
        SimulateProcessPerformanceCodedTool
        PerformSensitivityAnalysisCodedTool
        GenerateProcessDocumentCodedTool
    }
    class DesignTools["Design tools (9)<br/>coded_tools/design/"] {
        GenerateDesignFlowDiagramCodedTool
        LoadMasterDesignJsonCodedTool
        LoadDesignTemplateCodedTool
        LoadFullDesignContextCodedTool
        ValidateDesignJsonCodedTool
        PersistFinalDesignJsonCodedTool
        SimulateDesignArchitectureCodedTool
        PerformDesignSensitivityAnalysisCodedTool
        GenerateDesignDocumentCodedTool
    }
    class RequirementsSummaryTools["Requirements-summary tools (3)<br/>coded_tools/requirements_summary/"] {
        LoadDirectoryContextCodedTool
        SaveRequirementsSummaryCodedTool
        LoadRequirementsSummaryCodedTool
    }
    class LoopControlCodedTool["LoopControlCodedTool<br/>common/loop_control.py:76"] {
        +invoke(args, sly_data) Dict
        -_load_count() int
        -_save_count(count)
        -_load_approval_state() Dict
    }

    CodedTool <|-- SaveDrawioStructuredCodedTool : declared base
    CodedTool <|-- CloudarchTools : declared base (each)
    CodedTool <|-- ProcessTools : declared base (each)
    CodedTool <|-- DesignTools : declared base (each)
    CodedTool <|-- RequirementsSummaryTools : declared base (each)
    CodedTool <|-- LoopControlCodedTool : declared base

    class _Box["_Box<br/>cloudarch/cloudarch_layout_engine.py:157"] {
        +id: str
        +x, y, w, h: float
        +zone_id: Optional~str~
        +row, order: int
        +stack: str
        +cx()
        +cy()
        +right()
        +bottom()
    }

    class MessageProcessor["MessageProcessor<br/>external: neuro_san.message.processors.message_processor"]
    class LiveTraceMessageProcessor["LiveTraceMessageProcessor<br/>cli.py:164"] {
        +process_message(chat_message_dict, message_type)
    }
    MessageProcessor <|-- LiveTraceMessageProcessor : declared base

    class AgentSessionFactory["AgentSessionFactory<br/>external: neuro_san.client.agent_session_factory"]
    class StreamingInputProcessor["StreamingInputProcessor<br/>external: neuro_san.client.streaming_input_processor"]
    class ChatSession["ChatSession<br/>cli.py:233"] {
        +agent_name: str
        +session
        +input_processor: StreamingInputProcessor
        +sly_data: Optional~Dict~
        +chat_context: Optional~Dict~
        +__init__(agent_name)
        +send(text) str
    }

    ChatSession *-- AgentSessionFactory : creates self.session via create_session()
    ChatSession *-- StreamingInputProcessor : self.input_processor
    StreamingInputProcessor *-- LiveTraceMessageProcessor : added via get_message_processor().add_processor()
```

## Source evidence

| Diagram relationship or members | Source |
|---|---|
| `SaveDrawioStructuredCodedTool`'s invoke/async_invoke shape (representative of all 29 `CodedTool` leaves) | `coded_tools/cloudarch/save_drawio_structured_tool.py:1-30` |
| `LoopControlCodedTool`'s stop-counter/approval-state reads | `coded_tools/common/loop_control.py:76-115` |
| `_Box`'s fields and geometry properties | `coded_tools/cloudarch/cloudarch_layout_engine.py:157-181` |
| `LiveTraceMessageProcessor`'s base and override | `cli.py:142,164-190` |
| `ChatSession`'s construction and composed objects | `cli.py:233-272` |

The generic `CodedTool <|-- <cluster>` relationships reflect 29 individually-declared classes, not
one collapsed class -- see [class-inventory.md](class-inventory.md) for every one's exact file and
line number.
