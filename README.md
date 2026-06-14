# FateEngine

[![CI](https://github.com/CyberSecDef/FateEngine/actions/workflows/ci.yml/badge.svg)](https://github.com/CyberSecDef/FateEngine/actions/workflows/ci.yml)

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

Playable. All five components are implemented and unit-tested (118 tests): adventure
loading + validation, the MCP state engine (predicates, effects, quests, win/lose,
save/resume), provider-agnostic LLM narration (Anthropic + OpenAI/compatible), the
turn-loop controller, and a terminal CLI/TUI. The game runs fully offline; an LLM is
optional and only enriches prose + free-text understanding.

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

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Play offline (authored prose, local free-text matching) — no API key needed:
fateengine play adventures/example.json
fateengine list
fateengine resume adventures/example.json quicksave
```

In-game: choose an action by number or type what you want to do; `/save`, `/load`,
`/saves`, `/look`, `/status`, `/restart`, `/help`, `/quit`.

### Optional LLM narration

Narration and ambiguous free-text are handled by an LLM when one is configured;
on any failure it falls back to the authored `base_prose` (NFR-006).

```bash
pip install -e ".[llm]"        # anthropic + openai SDKs

# Claude (default model claude-opus-4-8):
export ANTHROPIC_API_KEY=sk-...
fateengine play adventures/example.json --llm anthropic

# OpenAI:
export OPENAI_API_KEY=sk-...
fateengine play adventures/example.json --llm openai

# Local Ollama (OpenAI-compatible, no key):
fateengine play adventures/example.json --llm ollama
```

Providers are selected by name (`anthropic`, `openai`, `ollama`/`local`,
`openai-compatible`); endpoint, model, and params live in `LLMConfig`.

### Configuring the endpoint / model / API key

Configuration is layered, lowest precedence first: **dataclass defaults → a JSON
config file → `FATEENGINE_*` environment variables → CLI flags**. Keep secrets and
endpoints out of git — use env vars, or a config file that is gitignored.

CLI overrides (per run):

```bash
fateengine play adventures/example.json \
  --llm openai-compatible --endpoint http://localhost:11434/v1 --model gemma4-rev
```

Environment variables (nothing written to disk):

```bash
export FATEENGINE_LLM_PROVIDER=openai-compatible
export FATEENGINE_LLM_ENDPOINT=http://localhost:11434/v1
export FATEENGINE_LLM_MODEL=gemma4-rev
# export FATEENGINE_LLM_API_KEY=sk-...     # or FATEENGINE_LLM_API_KEY_ENV=MY_KEY_VAR
fateengine play adventures/example.json --llm    # bare --llm uses the configured provider
```

Config file (copy the committed template, then edit — the real file is gitignored):

```bash
cp fateengine.config.example.json fateengine.config.json   # gitignored
fateengine play adventures/example.json --llm
```

Searched automatically at `./fateengine.config.json` then
`~/.config/fateengine/config.json`. **Plugging into a local Gemma 4 (Ollama):** set
`provider` to `ollama` (defaults the endpoint to `http://localhost:11434/v1`) or
`openai-compatible` with an explicit `endpoint`, set `model` to your tag (e.g.
`gemma4-rev`), and leave the API key empty — local servers need none.

The API key resolves as: `llm.api_key` (direct) → the env var named by
`llm.api_key_env` → the provider's conventional default (`ANTHROPIC_API_KEY` /
`OPENAI_API_KEY`). Local/`openai-compatible` endpoints don't require one.

### Run as an MCP server

FateEngine can also run as a real Model Context Protocol server over stdio, so an
external host (e.g. an LLM agent) can connect to a live adventure:

```bash
# (the `mcp` SDK is a core dependency, installed with the package)

# Read-only tools (get_state, describe_location, look_up_npc, recall_history):
fateengine serve adventures/example.json

# Resume a save, and also expose the gameplay-driving write tools for an agentic
# host that should drive the game itself:
fateengine serve adventures/example.json --slot quicksave --write
```

By default only the read-only tools are exposed (the hybrid-control boundary);
`--write` additionally exposes `available_actions`, `apply_action`,
`evaluate_quests`, and `check_end_conditions`. Status is written to stderr so
stdout stays clean for the MCP protocol.

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
