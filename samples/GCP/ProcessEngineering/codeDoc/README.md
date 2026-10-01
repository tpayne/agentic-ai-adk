# ProcessEngineering Python UML

These editable Mermaid diagrams document the Python declarations under
`process_agents/` and `tests/`:

- [Class inventory](class-inventory.md) lists every class declaration with
  its source location and declared base.
- [Class hierarchy](class-hierarchy.md) shows all declarations and actual
  inheritance, including test fixtures.
- [Application class diagram](application-classes.md) focuses on the
  application classes, with useful members and source-supported composition.
- [ADK composition](adk-composition.md) shows the major runtime agent
  pipelines and their `SequentialAgent` / `LoopAgent` composition.

The hierarchy distinguishes project classes from external bases by labeling
the external package in each node. `Agent` is shown as the ADK-declared base
for `DefaultAgent`; the source documents `google.adk.agents.Agent` as an alias
of `LlmAgent`. Composition edges are included only where construction or
typed fields establish the relationship; agent names alone are not treated as
class relationships.

The inventory covers 61 `class` statements across application and test
Python files. No `@dataclass` declarations or enum subclasses were found.
Functions, module-level agent registries, and non-class data structures are
outside the class inventory. The diagrams are Mermaid in Markdown and render
on GitHub; no local Mermaid/PlantUML renderer was installed when these were
prepared.
