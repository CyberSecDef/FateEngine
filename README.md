# FateEngine

A choose-your-own-adventure engine where **authoritative game state lives behind a
[Model Context Protocol](https://modelcontextprotocol.io) (MCP) server** and an LLM supplies
only the narrative prose. Adventures are plain JSON; the engine is provider-agnostic and runs
offline-degraded when no LLM is reachable.

See [`requirements_spec.md`](./requirements_spec.md) for the full specification.

## Core idea

- **The MCP server is the single source of truth.** Locations, inventory, status, quests,
  variables, and history change *only* through MCP tools.
- **The LLM never mutates state.** It receives serialized state + authored `base_prose` and
  returns narration. It may call a **read-only** tool subset (inspect / look-up / recall) to
  enrich what it writes — hybrid control.
- **Deterministic where it matters, generative where it helps.** A turn's action resolution,
  validation, and effect application are deterministic; only the prose is generated.

## Turn loop

```
                    ┌─────────────────────────────────────────────┐
                    │              Session Controller             │
                    │            (the only MCP write client)      │
                    └───────────────┬─────────────────────────────┘
   free text / choice               │ apply_action / evaluate_quests
        ▲                           ▼
 ┌──────┴───────┐          ┌────────────────────┐   read-only tools   ┌──────────────┐
 │ Presentation │          │     MCP Server     │◄────────────────────│     LLM      │
 │   (CLI/TUI)  │          │  (authoritative    │   get_state, etc.   │ Integration  │
 └──────────────┘          │      state)        │────────────────────►│ (prose only) │
                           └────────────────────┘   serialized state  └──────────────┘
```

1. Controller asks the MCP for current state + available actions.
2. LLM Integration renders location prose (falls back to `base_prose` on failure).
3. Player picks an action or types free text → resolved **local-match first, LLM fallback**.
4. MCP validates `available_when`, then the Controller applies effects **atomically**.
5. MCP evaluates quests + win/lose predicates; LLM narrates the outcome.

## Status

Early scaffold. Package skeleton + JSON Schemas are in place; component implementations are stubs.

## Layout

```
FateEngine/
├── requirements_spec.md        # the spec (source of truth for behavior)
├── schema/
│   ├── adventure.schema.json   # adventure file schema (JSON Schema 2020-12)
│   └── save.schema.json        # runtime save schema
├── src/fateengine/
│   ├── config.py               # LLM + runtime configuration
│   ├── loader/                 # Adventure Loader — I/O, parse, schema-validate
│   ├── mcp/                    # MCP Server — state authority, tools, effects, predicates
│   ├── llm/                    # LLM Integration — provider adapter, prompts, intent-parse
│   ├── controller/             # Session Controller — turn loop, persistence
│   └── presentation/           # Presentation — CLI/TUI
├── adventures/                 # adventure JSON files
├── saves/                      # runtime saves (gitignored)
└── tests/
```

## Quick start (planned)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
fateengine play adventures/example.json      # once implemented
```

## Authoring adventures

Adventure files validate against `schema/adventure.schema.json`. The two extension points
authors care about:

- **Predicates** (`available_when`, `completion_criteria`, win/lose, connection `condition`) —
  a small boolean grammar: `and` / `or` / `not`, comparisons (`==`, `!=`, `>`, `>=`, `<`, `<=`),
  plus `has` / `exists`. A bare multi-key object is sugar for an implicit AND of equality checks.
  See **Appendix A** in the spec.
- **Effects** — a closed catalog (`move_location`, `add_inventory`, `set_status`,
  `complete_quest`, `trigger_end`, …). Unknown effect types are rejected on load.
  See **Appendix B** in the spec.
