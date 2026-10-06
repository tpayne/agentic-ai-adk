# neuro-san network composition

The runtime root is `process_architect`'s front-man, `Process_Architect_Orchestrator`, which routes
an incoming request to whichever of the other fifteen networks fits it via neuro-san's same-server
external-agent references (`"/network_name"`). Green nodes are LLM-driven agents; gold nodes are
the generate/review loop stage (every pipeline front-man's own instructions implement the same
*reset → generate → review(s) → `loop_control` → continue-or-stop* convention -- there is no
runtime loop primitive the way ADK's `LoopAgent` is); purple nodes are `CodedTool` leaves (no LLM
call).

```mermaid
flowchart TB
    classDef app fill:#e6f4ea,stroke:#188038,color:#202124
    classDef loop fill:#fef7e0,stroke:#f9ab00,color:#202124
    classDef tool fill:#f3e8fd,stroke:#9334e6,color:#202124
    classDef route fill:#e8f0fe,stroke:#1a73e8,color:#202124

    Root["Process_Architect_Orchestrator<br/>(process_architect)"]:::app
    Root --> PC
    Root --> PU
    Root --> DC
    Root --> DU
    Root --> CA
    Root --> Routes

    Routes["Direct specialist routes<br/>process/design/cloudarch consultants<br/>scenario testers, simulation queries<br/>requirements_summary, requirements_consultant"]:::route

    subgraph ProcessCreate["process - registries/process.hocon"]
        direction LR
        PC["Process_Pipeline"]:::app --> PC0["reset_loop_state"]:::tool
        PC0 --> PCA["Analysis_Agent"]:::app
        PCA --> PCL["Design_Agent -> Compliance_Agent<br/>-> Simulation_Agent -> loop_control<br/>repeat on CONTINUE, max 2x"]:::loop
        PCL --> PCS["Subprocess_Driver_Agent<br/>(unconditional, either way)"]:::app
        PCS --> PCD1["generate_process_flow_diagram"]:::tool
        PCD1 --> PCD2["generate_process_document"]:::tool
    end

    subgraph ProcessUpdate["process_update - registries/process_update.hocon"]
        direction LR
        PU["Process_Update_Pipeline"]:::app --> PU0["reset_loop_state"]:::tool
        PU0 --> PUA["Process_Update_Analyst<br/>(diffs change request vs. baseline)"]:::app
        PUA --> PUL["Design_Agent -> Compliance_Agent<br/>-> Simulation_Agent -> loop_control<br/>repeat on CONTINUE, max 2x"]:::loop
        PUL --> PUD1["generate_process_flow_diagram"]:::tool
        PUD1 --> PUD2["generate_process_document"]:::tool
    end

    subgraph DesignDocCreate["design - registries/design.hocon"]
        direction LR
        DC["Design_Doc_Pipeline"]:::app --> DC0["reset_loop_state"]:::tool
        DC0 --> DCA["Design_Doc_Analysis_Agent"]:::app
        DCA --> DCL["Design_Doc_Agent -> Compliance_Agent<br/>-> Simulation_Agent -> loop_control<br/>repeat on CONTINUE, max 2x"]:::loop
        DCL --> DCD1["generate_design_flow_diagram"]:::tool
        DCD1 --> DCD2["generate_design_document"]:::tool
    end

    subgraph DesignDocUpdate["design_update - registries/design_update.hocon"]
        direction LR
        DU["Design_Doc_Update_Pipeline"]:::app --> DU0["reset_loop_state"]:::tool
        DU0 --> DUA["Design_Doc_Update_Analyst"]:::app
        DUA --> DUL["Design_Doc_Agent -> Compliance_Agent<br/>-> Simulation_Agent -> loop_control<br/>repeat on CONTINUE, max 2x"]:::loop
        DUL --> DUD1["generate_design_flow_diagram"]:::tool
        DUD1 --> DUD2["generate_design_document"]:::tool
    end

    subgraph CloudArchitecture["cloudarch - registries/cloudarch.hocon"]
        direction LR
        CA["CloudArch_Pipeline"]:::app --> CA0["reset_loop_state"]:::tool
        CA0 --> CAL["CloudArch_Agent -> CloudArch_Reviewer_Agent<br/>-> loop_control<br/>repeat on CONTINUE, max 2x"]:::loop
    end

    class Root,Routes app
    class PC,PU,DC,DU,CA app
    class PCL,PUL,DCL,DUL,CAL loop
```

## Composition notes

- All five pipelines above (`process`, `process_update`, `design`, `design_update`, `cloudarch`)
  share the exact same shape: `reset_loop_state` once, then a generate/review cycle that repeats
  until `loop_control` returns `"STOP"` (either a real approval or the iteration cap), then --
  for the four document-producing pipelines -- an unconditional diagram+document generation stage
  regardless of which way the loop stopped. `process` and `process_update` additionally run
  `Subprocess_Driver_Agent` to (re-)expand every top-level step before documents are generated
  (see [README.md](README.md)'s own note on `process_update` previously lacking this entirely);
  `cloudarch` has no document stage at all (its artifact is the drawio diagram itself, already
  persisted by `CloudArch_Agent`'s own tool calls each round).
- `loop_control` and `reset_loop_state` are the same two `CodedTool` classes
  (`LoopControlCodedTool`/`ResetLoopStateCodedTool`, declared once under `coded_tools/cloudarch/`
  and `coded_tools/common/`) reached through five different networks' own thin re-export modules --
  see [class-inventory.md](class-inventory.md).
- All five pipeline front-men also carry the `pipeline_middleware` summarization middleware (see
  the main README's "NeuroSAN implementation notes") -- not shown above since it doesn't change
  the call sequence, only how much of a long-running front-man's own tool-call history survives
  into its next model call.
- The "Direct specialist routes" node collapses ten simple, loop-free networks that follow one
  shape: a single LLM agent whose own tools are read-only `CodedTool`s (`load_master_process_json`/
  `load_master_design_json`/`load_drawio`, `load_requirements_summary`, and -- for the two
  simulation-query agents -- `simulate_process_performance`/`simulate_design_architecture`/
  `simulate_cloudarch_architecture`). None of them write state back or loop.
- Unlike the ADK original's `SequentialAgent`/`LoopAgent` composition (a real Python object tree
  constructed once at startup), every arrow above is a *convention a front-man's own instructions
  follow*, re-evaluated by the LLM on every turn -- there is no object that enforces the sequence
  at runtime beyond `loop_control`'s own hard iteration-count backstop. See the main README's "Why
  neuro-san needed a different design for the generate/review loop" for the full reasoning.
