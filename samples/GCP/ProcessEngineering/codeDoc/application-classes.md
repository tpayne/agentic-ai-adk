# Application class diagram

This is the application-only class view: it includes all 13 classes declared
under `process_agents/`, with test fixtures and doubles omitted. Members are
selected to make state and responsibilities readable rather than exhaustively
listing every field. Project classes are white; external ADK, Pydantic, and
requests types are gray and labeled with their packages.

Solid inheritance arrows show declared bases. Filled diamonds show
composition established by object construction or typed schema fields.
Dashed arrows show a configuration/runtime dependency rather than ownership.
Labels explain the evidence for each link. Edge-inference and document
generation agents are shown as `DefaultLlmAgent` instances: their source
modules expose agent objects, not Python class declarations.

```mermaid
classDiagram
    direction LR

    class DefaultLlmAgent["DefaultLlmAgent<br/>common/agent_wrappers.py"] {
        +__init__(name, model, instruction, sub_agents)
    }
    class DefaultAgent["DefaultAgent<br/>common/agent_wrappers.py"] {
        +__init__(name, model, instruction, sub_agents)
    }
    class DocCreationAgent["DocCreationAgent<br/>common/doc_creation_agent.py"] {
        +pipeline: Optional~SequentialAgent~
        +__init__(name)
        +_run_async_impl(ctx)
    }
    class SubprocessDriverAgent["SubprocessDriverAgent<br/>process/subprocess_driver_agent.py"] {
        +per_step_pipeline: SequentialAgent
        +__init__(name)
        +_load_process_steps()
        +_run_async_impl(ctx)
    }
    class SubprocessWriterAgent["SubprocessWriterAgent<br/>process/subprocess_writer_agent.py"] {
        +__init__(name)
        +_run_async_impl(ctx)
    }
    class SubprocessFlow["SubprocessFlow<br/>process/subprocess_generator_agent.py"] {
        +step_name: str
        +subprocess_flow: List~SubprocessStep~
    }
    class SubprocessStep["SubprocessStep<br/>process/subprocess_generator_agent.py"] {
        +substep_name: str
        +description: str
        +responsible_party: str
        +inputs: List~str~
        +outputs: List~str~
        +dependencies: List~str~
        +step_risks_and_controls: List~StepRiskControl~
        +change_management: List~ChangeManagement~
        +continuous_improvement: List~ContinuousImprovement~
    }
    class StepRiskControl["StepRiskControl<br/>process/subprocess_generator_agent.py"] {
        +risk: str
        +control: str
    }
    class ChangeManagement["ChangeManagement<br/>process/subprocess_generator_agent.py"] {
        +change_request_process: str
        +versioning_rules: str
    }
    class ContinuousImprovement["ContinuousImprovement<br/>process/subprocess_generator_agent.py"] {
        +review_frequency: str
        +improvement_inputs: List~str~
    }
    class _Box["_Box<br/>cloudarch/cloudarch_layout_agent.py"] {
        +id: str
        +float x
        +float y
        +float w
        +float h
        +Optional~str~ zone_id
        +int row
        +int order
        +stack: str
        +cx()
        +cy()
        +right()
        +bottom()
    }
    class JitterAdapter["JitterAdapter<br/>common/grounding_agent.py"] {
        +sleep(sleep_time)
    }
    class CleanedStdout["CleanedStdout<br/>common/utils.py"] {
        +file
        +__init__(path)
        +write(text)
        +flush()
    }

    class ADK_LlmAgent["LlmAgent<br/>external: google.adk.agents"]
    class ADK_Agent["Agent<br/>external: google.adk.agents"]
    class ADK_BaseAgent["BaseAgent<br/>external: google.adk.agents"]
    class ADK_SequentialAgent["SequentialAgent<br/>external: google.adk.agents"]
    class Pydantic_BaseModel["BaseModel<br/>external: pydantic"]
    class Requests_HTTPAdapter["HTTPAdapter<br/>external: requests.adapters"]

    DefaultLlmAgent --|> ADK_LlmAgent : declared base
    DefaultAgent --|> ADK_Agent : declared base
    DocCreationAgent --|> ADK_BaseAgent : declared base
    SubprocessDriverAgent --|> ADK_BaseAgent : declared base
    SubprocessWriterAgent --|> ADK_BaseAgent : declared base
    SubprocessFlow --|> Pydantic_BaseModel : declared base
    SubprocessStep --|> Pydantic_BaseModel : declared base
    StepRiskControl --|> Pydantic_BaseModel : declared base
    ChangeManagement --|> Pydantic_BaseModel : declared base
    ContinuousImprovement --|> Pydantic_BaseModel : declared base
    JitterAdapter --|> Requests_HTTPAdapter : declared base

    DocCreationAgent *-- ADK_SequentialAgent : builds and stores pipeline
    ADK_SequentialAgent *-- DefaultLlmAgent : edge inference and doc generation instances
    SubprocessDriverAgent *-- ADK_SequentialAgent : per_step_pipeline
    ADK_SequentialAgent *-- DefaultLlmAgent : subprocess generator
    ADK_SequentialAgent *-- SubprocessWriterAgent : subprocess writer
    DefaultLlmAgent ..> SubprocessFlow : output_schema configured by factory
    SubprocessFlow "1" *-- "0..*" SubprocessStep : subprocess_flow
    SubprocessStep "1" *-- "0..*" StepRiskControl : step_risks_and_controls
    SubprocessStep "1" *-- "0..*" ChangeManagement : change_management
    SubprocessStep "1" *-- "0..*" ContinuousImprovement : continuous_improvement
```

## Source evidence

| Diagram relationship or members | Source |
|---|---|
| Wrapper bases and constructor configuration | `process_agents/common/agent_wrappers.py:434-612` |
| `DocCreationAgent.pipeline`, sequential construction, and stage factories | `process_agents/common/doc_creation_agent.py:17-72` |
| Driver pipeline field and generator/writer construction | `process_agents/process/subprocess_driver_agent.py:30-55` |
| Writer runtime method | `process_agents/process/subprocess_writer_agent.py:24-35` |
| Schema fields and nested typed lists | `process_agents/process/subprocess_generator_agent.py:19-69` |
| Layout box state and geometry properties | `process_agents/cloudarch/cloudarch_layout_agent.py:149-181` |
| Retry adapter override | `process_agents/common/grounding_agent.py:126-144` |
| File-like output wrapper | `process_agents/common/utils.py:3395-3430` |

The generic composition through ADK `SequentialAgent.sub_agents` reflects the
constructed child instances in `doc_creation_agent.py` and
`subprocess_driver_agent.py`; the ADK orchestration class is external and is
not part of this application's class inventory.
