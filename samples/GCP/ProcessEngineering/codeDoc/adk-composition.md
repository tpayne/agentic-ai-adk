# ADK agent composition

The runtime root is a `ProcessLlmAgent` factory result (`DefaultLlmAgent`,
which derives from ADK `LlmAgent`). Its `sub_agents` are mostly pipeline
objects assembled in the process, design, cloud-architecture, and shared
modules. Blue nodes are external ADK orchestration types; green nodes are
application agents/pipelines; gold nodes are iterative stages.

```mermaid
flowchart TB
    classDef adk fill:#e8f0fe,stroke:#1a73e8,color:#202124
    classDef app fill:#e6f4ea,stroke:#188038,color:#202124
    classDef loop fill:#fef7e0,stroke:#f9ab00,color:#202124
    classDef route fill:#f3e8fd,stroke:#9334e6,color:#202124

    Root["Process_Architect_Orchestrator<br/>ProcessLlmAgent -> DefaultLlmAgent"]:::app
    Root --> PC
    Root --> PU
    Root --> DC
    Root --> DU
    Root --> CA
    Root --> Routes

    Routes["Direct specialist routes<br/>process/design/cloudarch consultants<br/>scenario and simulation queries<br/>document creation and subprocess driver"]:::route

    subgraph ProcessCreate["Process create - process/create_process_agent.py"]
        direction LR
        PC["Full_Design_Pipeline<br/>SequentialAgent (ADK)"]:::adk --> PC0["Mute"]:::app
        PC0 --> PCA["Analysis"]:::app
        PCA --> PCR["LoopAgent + SequentialAgent (ADK)<br/>Design / compliance / simulation<br/>optional grounding + stop"]:::loop
        PCR --> PCN["SequentialAgent + LoopAgent (ADK)<br/>JSON normalizer / review / stop"]:::loop
        PCN --> PCS["SubprocessDriverAgent"]:::app
        PCS --> PCD["DocCreationAgent<br/>edge inference -> document generation"]:::app
        PCD --> PCU["Unmute"]:::app
    end

    subgraph ProcessUpdate["Process update - process/update_process_agent.py"]
        direction LR
        PU["Update_Design_Pipeline<br/>SequentialAgent (ADK)"]:::adk --> PU0["Mute"]:::app
        PU0 --> PUA["Context-aware update analysis"]:::app
        PUA --> PUR["LoopAgent + SequentialAgent (ADK)<br/>Design / compliance / simulation<br/>optional grounding + stop"]:::loop
        PUR --> PUN["SequentialAgent + LoopAgent (ADK)<br/>JSON normalizer / review / stop"]:::loop
        PUN --> PUS["SubprocessDriverAgent instance"]:::app
        PUS --> PUD["DocCreationAgent<br/>edge inference -> document generation"]:::app
        PUD --> PUU["Unmute"]:::app
    end

    subgraph DesignDocCreate["Design-document create - design/design_doc_create_agent.py"]
        direction LR
        DC["Full_Design_Doc_Pipeline<br/>SequentialAgent (ADK)"]:::adk --> DC0["Mute"]:::app
        DC0 --> DCA["Design requirements analysis"]:::app
        DCA --> DCR["LoopAgent + SequentialAgent (ADK)<br/>HLD / LLD / compliance / simulation<br/>optional grounding + stop"]:::loop
        DCR --> DCN["SequentialAgent + LoopAgent (ADK)<br/>JSON normalizer / review / stop"]:::loop
        DCN --> DCD["DocCreationAgent<br/>edge inference -> document generation"]:::app
        DCD --> DCU["Unmute"]:::app
    end

    subgraph DesignDocUpdate["Design-document update - design/design_doc_update_agent.py"]
        direction LR
        DU["Update_Design_Doc_Pipeline<br/>SequentialAgent (ADK)"]:::adk --> DU0["Mute"]:::app
        DU0 --> DUA["Context-aware design update analysis"]:::app
        DUA --> DUR["LoopAgent + SequentialAgent (ADK)<br/>HLD / LLD / compliance / simulation<br/>optional grounding + stop"]:::loop
        DUR --> DUN["SequentialAgent + LoopAgent (ADK)<br/>JSON normalizer / review / stop"]:::loop
        DUN --> DUD["DocCreationAgent<br/>edge inference -> document generation"]:::app
        DUD --> DUU["Unmute"]:::app
    end

    subgraph CloudArchitecture["Cloud architecture - cloudarch/cloudarch_pipeline_agent.py"]
        direction LR
        CA["CloudArch_Pipeline<br/>LoopAgent (ADK)"]:::loop --> CAG["Cloud architecture generator"]:::app
        CAG --> CAR["Cloud architecture reviewer"]:::app
        CAR --> CAS["Approval stop controller"]:::app
        CAS -. "repeat until approved / iteration limit" .-> CAG
    end

    class Root,Routes app
    class PC,PU,DC,DU adk
    class PCR,PCN,PUR,PUN,DCR,DCN,DUR,DUN,CA loop
```

## Composition notes

- The process and design-document create/update pipelines are
  `SequentialAgent` instances. Each review stage nests a `LoopAgent` around a
  `SequentialAgent`; each normalization stage nests a loop around the
  normalizer, reviewer, and stop agent.
- Grounding is added to the review loops only when
  `enableGroundingAgent` is enabled.
- `DocCreationAgent` owns a `SequentialAgent` with fresh edge-inference and
  document-generation LLM instances. `SubprocessDriverAgent` builds a
  per-step `SequentialAgent` containing a fresh structured-output generator
  and a `SubprocessWriterAgent`.
- Cloud architecture uses a separate `LoopAgent` over generator, reviewer,
  and stop-controller agents.
- `ProcessLlmAgent` and `ProcessAgent` are wrapper factories, not ADK
  orchestrators: they construct `DefaultLlmAgent` and `DefaultAgent`,
  respectively. The wrappers centralize model/configuration behavior and
  accept subagent instances; `SequentialAgent` and `LoopAgent` provide the
  actual pipeline control flow.
