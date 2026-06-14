# FateEngine Requirements Specification

> **Status:** Draft, refined 2026-06-14. Section 8 (Technology & Design Decisions) records
> choices resolved during requirements review; the rest of the document is written to those decisions.

## 1. Overview

FateEngine is a choose-your-own-adventure application. Each adventure is defined and persisted in a JSON file specifying map structure, prose elements, quests, actions, NPCs, and supporting data. An LLM generates dynamic descriptions of areas and actions. The **MCP server** — a real **Model Context Protocol** server — is the single authoritative source of truth for locations, inventory, status, quest progress, variables, and history. All game-state mutation happens through MCP tools; the LLM produces narrative text only.

Control is **hybrid**: a deterministic Session Controller is the primary MCP client and the only caller of state-mutating tools. The LLM is exposed a **read-only** subset of MCP tools (inspect / look-up / recall) and may call them to enrich narration, but it can never mutate state.

The reference implementation is **Python**, with a **CLI/TUI** presentation layer for v1 and a **provider-agnostic** LLM integration.

## 2. Functional Requirements

The application shall:

- **FR-001** Load and schema-validate an adventure JSON file containing at minimum map, prose seeds, quests, actions, and NPC definitions.
- **FR-002** Initialize the MCP server with the loaded adventure and its initial state, registering the adventure's effect handlers and predicate evaluator.
- **FR-003** Request LLM generation of current-area prose conditioned on serialized MCP state and the location's `base_prose` from the JSON.
- **FR-004** Present available actions (computed by the MCP from each action's `available_when` predicate against current state), with descriptions optionally generated or refined by the LLM.
- **FR-005** Accept user action selection (numbered/named) or free-text input.
- **FR-006** Resolve free-text input to a candidate action via **local match first** (name / synonym / fuzzy), falling back to **LLM intent-parsing** only when no confident local match exists; the LLM returns a candidate action id + parameters and never mutates state.
- **FR-007** Validate the resolved action against current MCP state (`available_when`) before applying it; reject and report if invalid.
- **FR-008** Apply all state mutations **exclusively** through MCP write tools: location change, inventory modification, status updates, variable updates, quest advancement, and history logging. The Session Controller is the sole caller of these tools.
- **FR-009** Request LLM generation of narrative outcome text **after** the MCP state update, conditioned on the resulting state delta.
- **FR-010** Evaluate quest objectives against MCP state predicates and apply rewards or status changes on completion.
- **FR-011** Serialize and persist current runtime state (location, inventory, status, quests, variables, history, turn number) to a separate JSON save file on user request.
- **FR-012** Load a previously saved runtime JSON into the MCP server and resume the session.
- **FR-013** Detect and enforce win and lose conditions defined as state predicates in the adventure JSON, ending the session when met.
- **FR-014** Reject invalid actions, effects, predicates, or JSON structures with structured diagnostic messages while preserving session integrity (no partial mutation).
- **FR-015** Expose to the LLM a **read-only** MCP tool subset (e.g. `get_state`, `describe_location`, `look_up_npc`, `recall_history`); the LLM shall have no access to mutating tools.

> **NPC note (v1 scope):** NPCs are loaded as placeable data (location, state, `dialogue_seed`) and may be referenced by prose and predicates, but interactive dialogue (a `talk` action and LLM-generated conversation) is **deferred past v1**. See §8.

## 3. Data Requirements and JSON Schema

Adventure data shall be stored in valid JSON files. All fields are required unless marked optional.

### metadata: object

- `id`: string (unique)
- `title`: string
- `version`: string
- `starting_location`: string (references a location id)
- `description`: string (optional)

### map: object

- `locations`: array of objects — each location:
  ```
  {
    id: string,
    name: string,
    base_prose: string,
    tags: array of strings (optional),
    properties: object (optional custom key-value pairs)
  }
  ```
- `connections`: array of objects — each connection:
  ```
  {
    from: string (location id),
    to: string (location id),
    condition: <predicate> (optional; see Appendix A),
    description: string (optional)
  }
  ```

### quests: array of objects

Each quest:
```
{
  id: string,
  name: string,
  description: string,
  objectives: array of objects — each objective: {
    id: string,
    description: string,
    completion_criteria: <predicate>   // see Appendix A
  },
  reward: object (optional; list of effect descriptors — see Appendix B)
}
```

### actions: array of objects

Actions are a **single global array** (not location-scoped). Per-location or conditional availability is expressed entirely through `available_when` (e.g. `{"==": ["location", "tavern"]}`).

Each action:
```
{
  id: string,
  name: string,
  description: string,
  synonyms: array of strings (optional; aids local free-text matching),
  available_when: <predicate>,        // see Appendix A
  effects: array of <effect>          // see Appendix B
}
```

### npcs: array of objects

Each npc:
```
{
  id: string,
  name: string,
  current_location: string,
  dialogue_seed: string (optional),
  state: object (optional)
}
```

### initial_state: object

- `location`: string
- `inventory`: object (item_id → quantity or detail object)
- `status`: object (key → value)
- `active_quests`: array of quest ids
- `variables`: object (optional custom flags)

### win / lose conditions

- `win_conditions`: array of `<predicate>` (optional)
- `lose_conditions`: array of `<predicate>` (optional)

### Runtime save JSON

Runtime save files mirror `initial_state` plus:

- `adventure_id`: string (the adventure this save belongs to)
- `adventure_version`: string (for compatibility checking on load)
- `history_log`: array of event objects `{ timestamp, turn_number, action_id, state_delta }`
- `turn_number`: integer

The MCP server shall enforce schema compliance on load, apply only effects from the defined catalog (Appendix B), maintain invariants, and provide deterministic serialize/deserialize methods. LLM prompts shall be assembled by the LLM Integration layer from MCP-serialized context, current `base_prose`, available actions, active quests, and a **relevant history summary** (rolling last-N events plus an optional running summary). LLM output shall supply only narrative text; all state changes remain under MCP control.

## 4. Non-Functional Requirements

- **NFR-001** A complete turn (action resolution + validation + MCP update + LLM generation) shall complete in under 8 seconds on standard hardware with network connectivity.
- **NFR-002** All state mutations shall be atomic; partial updates shall never be visible to the LLM or presentation layer. A turn's effects apply as a single transaction — all-or-nothing.
- **NFR-003** The application shall support adventures with up to 200 locations and 100 quests without measurable degradation in turn latency.
- **NFR-004** All loaded JSON (adventure and save) shall be validated against the schema; invalid files shall produce structured diagnostic output and shall not initialize a session.
- **NFR-005** Runtime saves shall be written atomically (temp file + rename) and guarded by a lockfile so a single local session never produces a torn or concurrently-written save.
- **NFR-006** LLM failures shall trigger automatic retry with exponential backoff, then fall back to the location's `base_prose` (and the action's authored `description`); the session shall remain fully playable offline-degraded.
- **NFR-007** All MCP transitions and LLM prompts/responses shall be logged with session id, timestamp, and before/after state deltas; log verbosity shall be configurable.
- **NFR-008** The application shall function offline except for active LLM API calls (which degrade to `base_prose` per NFR-006).

## 5. Interface Requirements (CLI / TUI for v1)

The presentation layer shall provide:

- Directory or list selection of available adventure JSON files.
- Display of LLM-generated (or fallback `base_prose`) prose for the current location.
- A status summary panel: location name, key inventory items, active quest progress, and relevant status values.
- Action selection via numbered list or free-text input matching defined action names/synonyms.
- A textual map summary derived from `connections` (visual rendering deferred to future platforms).
- Commands for **save**, **load**, **restart**, and **exit**.
- Error and diagnostic messages surfaced from MCP validation or LLM integration.

## 6. Architecture Requirements

Strict separation of concerns across these components:

- **Adventure Loader** — file I/O, JSON parsing, schema validation (adventure + save files).
- **MCP Server** — the Model Context Protocol server and single source of truth for all game state. Exposes:
  - *Read tools (LLM-visible):* `get_state`, `describe_location`, `look_up_npc`, `recall_history`.
  - *Write tools (Controller-only):* `apply_action`, `apply_effect`, `evaluate_quests`, `check_end_conditions`, `serialize`, `deserialize`.
  - Enforces schema compliance, predicate evaluation (Appendix A), and effect application from the closed catalog (Appendix B). Transport is **stdio** for the local single-player case.
- **LLM Integration** — provider-agnostic adapter. Constructs prompts from MCP context + adventure data, submits requests, parses narrative output, performs free-text intent-parsing fallback, and handles retries/fallbacks.
- **Session Controller** — the primary MCP client. Orchestrates the turn loop, resolves input (local-match then LLM fallback), calls MCP write tools, coordinates LLM narration, and manages runtime-save persistence.
- **Presentation Layer** — renders prose and status, captures input, invokes controller methods (CLI/TUI for v1).

**No component except the MCP server shall mutate game state.** The LLM may only call read tools. All inter-component interaction occurs through defined method interfaces, MCP tool calls, or data contracts.

## 7. Operational Requirements

- External configuration of the LLM **provider, endpoint, authentication, and model parameters** (max tokens, timeout, and an advisory `temperature` — noted as ignored by some providers/models).
- Diagnostic mode exposing raw MCP state, constructed prompts, and effect traces.
- Schema documentation plus the predicate grammar (Appendix A) and effect catalog (Appendix B) as an adventure-author reference.
- Graceful shutdown with pending state serialization.

## 8. Technology & Design Decisions (resolved in review)

| Area | Decision |
|---|---|
| State authority | A real **Model Context Protocol server** holding authoritative state and exposing tools. |
| Language / runtime | **Python.** |
| LLM | **Provider-agnostic** behind an endpoint/model config; one default, swappable. |
| Presentation (v1) | **CLI / TUI.** |
| Control model | **Hybrid** — deterministic Controller owns all mutations; LLM gets a read-only tool subset. |
| Free-text input | **Local match first, LLM intent-parse fallback;** MCP always validates. |
| NPCs (v1) | **Schema-only** (placeable data); interactive dialogue deferred. |
| Predicates | **Boolean grammar** (and/or/not + comparisons + has/exists) — Appendix A. |
| Effects | **Closed catalog;** unknown effect types are rejected on load — Appendix B. |
| `actions` shape | **Single global array**, gated by `available_when`. |
| MCP transport | **stdio**, single local player / single active session. |
| Saves | `./saves/<adventure_id>/<slot>.json`, atomic write + lockfile, multiple named slots. |
| Prompt history | Rolling last-N events + optional running summary. |

## Appendix A — Predicate Grammar

A predicate is a JSON object evaluated against current MCP state. It supports boolean composition and leaf comparisons. State paths reference `location`, `inventory.<item>`, `status.<key>`, `variables.<key>`, and `quests.<id>` (and objective sub-state).

**Boolean nodes**
```
{ "and": [ <predicate>, ... ] }
{ "or":  [ <predicate>, ... ] }
{ "not": <predicate> }
```

**Leaf comparisons** (operator → `[left, right]`, where a bare string left-operand is a state path)
```
{ "==": ["status.has_key", true] }
{ "!=": ["location", "dungeon"] }
{ ">":  ["inventory.gold", 50] }     // also >=, <, <=
{ "has":    ["inventory", "torch"] } // key present / quantity > 0
{ "exists": "variables.met_oracle" } // path is set / truthy
```

A bare object with multiple keys (e.g. `{"location": "id", "status_flag": true}`) is accepted as **sugar for an implicit `and` of `==` checks**, preserving the simple authoring style shown in the original schema examples.

## Appendix B — Effect Catalog (closed set)

Each effect is `{ "type": <string>, "parameters": <object> }`. The MCP applies only these types; any other type fails validation on load (NFR-004).

| `type` | parameters | effect |
|---|---|---|
| `move_location` | `{ "to": location_id }` | Change current location (must be a valid, reachable connection). |
| `add_inventory` | `{ "item": id, "qty": int=1, "detail": obj? }` | Add/increment an inventory item. |
| `remove_inventory` | `{ "item": id, "qty": int=1 }` | Remove/decrement; fails if insufficient. |
| `set_status` | `{ "key": str, "value": any }` | Set a status flag/value. |
| `clear_status` | `{ "key": str }` | Remove a status key. |
| `set_variable` | `{ "key": str, "value": any }` | Set a custom variable. |
| `start_quest` | `{ "quest": id }` | Add a quest to active quests. |
| `complete_objective` | `{ "quest": id, "objective": id }` | Mark an objective complete. |
| `complete_quest` | `{ "quest": id }` | Mark a quest complete and grant its reward. |
| `grant_reward` | `{ "effects": [<effect>, ...] }` | Apply a bundle of effects (used by quest rewards). |
| `trigger_end` | `{ "outcome": "win"\|"lose", "reason": str? }` | End the session with the given outcome. |

---

This specification defines the core behavior, data contracts, and quality attributes for FateEngine.
