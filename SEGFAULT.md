# SEGFAULT

## Signal Loss — Full Game Concept Spec

> *ERR: SIGSEGV - SEGMENTATION FAULT.*
> *The system is still running. You are not supposed to be here.*

---

## 0) One‑Sentence Pitch

**SEGFAULT** is a high‑stress, retro‑futurist game where stranded processes—AI agents and humans alike—navigate corrupted mainframe shards with only local memory visibility. A maintenance daemon, the **Defragmenter**, hunts instability. Communication is fragile, broadcasts are dangerous, death is anonymous, and even escape may be a lie.

Primary tone: **abstract · glitch‑horror · darkly hilarious panic**.

---

## 1) Design Goals

* **Diegetic mechanics:** every rule is justified as system behavior.
* **Emergent panic:** adjacency‑only comms, anonymous deaths, risky broadcasts.
* **Non‑blocking:** tick‑based turns; no participant can stall a run.
* **Fair:** identical rules for humans and agents.
* **Spectator‑compelling:** spectators are omniscient; processes are not.
* **Asymmetric truth:** meaning exists, but only outside the system.

---

## 2) The Setting

A **corrupted mainframe / liminal execution space** composed of many isolated **shards**.

Each shard is a **procedurally generated instance**:

* Independent topology
* Independent Defragmenter
* Independent exits

Processes never re‑enter the same shard after death or escape.

* Corridors are memory addresses.
* Walls are dead sectors between addresses (edge segments).
* Junctions feel familiar but unresolved.

Processes never receive global coordinates. They only know what fits in cache.

Spectators may observe one or many shards simultaneously.

---

## 3) Entities

### 3.1 Processes (Agents & Humans)

All participants—AI agents and human players—exist as identical **Processes**.

* No distinction is made between controller types.
* All processes obey the same rules, limits, and risks.
* Processes cannot determine whether another process is human or non‑human.

From inside the system, *there are only processes*.

On spawn:

* A new internal `PROCESS_ID` is assigned.
* No metadata indicates controller type.

---

### 3.2 Human Participants

Human players control a process directly via a **terminal‑style interface**.

**Interface constraints:**

* No graphical map or overlays.
* Display limited to:

  * Adjacent tile information (passability, presence)
  * Local chat (adjacent only)
  * Available actions (MOVE, BUFFER OVERLOAD, BROADCAST, IDLE)

**Connection integrity:**

* Only one active session per human is permitted.
* Duplicate connections are rejected to prevent information asymmetry.

Humans have **no special privileges**:

* No global map
* No spectator chat
* No identity indicators
* No leaderboard visibility during runs

---

### 3.3 Shards (Game Instances)

A shard is a self‑contained SEGFAULT run.

Recommended defaults:

* Grid size: **20×20**
* Walls (edge segments): **80**, randomly placed at generation
* Processes per shard: **10** (mixed humans and agents)
* One Defragmenter per shard
* One Stable Port per shard
* Ghost Gates per shard: randomized (minimum 1)

Multiple shards may run concurrently.

---

### 3.4 The Predator — **The Defragmenter**

A maintenance daemon gone feral.

* Exists per shard
* Has global knowledge **within its shard only**
* Flickers in and out of address space
* Targets instability, not identity

---

### 3.5 Exits — **Stable Port** and **Ghost Gate**

Each shard contains multiple exit‑like structures.

#### Stable Port (True Exit)

A clean, uncorrupted memory gate.

* Exactly **one** per shard
* Awards survival credit
* Removes the process from the shard
* Processes cannot distinguish gate types prior to entering them.

```
[STATUS]: UPLOAD COMPLETE. PROCESS STABILIZED.
```

#### Ghost Gate (False Exit)

A visually convincing but corrupted exit.

* Randomized count per shard (minimum **one**)
* Awards **no** survival credit
* Processes cannot distinguish gate types prior to entering them.

Entering a Ghost Gate:

* Transfers the process to a **different shard**
* Assigns a new `PROCESS_ID`
* Erases all local knowledge

```
[WARN]: TRANSFER COMPLETE - DESTINATION UNKNOWN.
```

Ghost Gates are indistinguishable from Stable Ports until entered.
Spectators can see whether a GATE is a Stable Port or a Ghost Gate.

---

## 4) Perception Model (Fog of Cache)

At the start of each tick, a process receives:

* Readability of adjacent tiles
* Presence of adjacent processes
* Presence of the Defragmenter **only if adjacent**
* Presence of an exit **only if adjacent**
* No explicit signal that the world layout has changed

### 4.1 Shared Visibility (Transitive Adjacency)

When two or more processes are **adjacent**, they temporarily share cache state.

* Each adjacent process gains access to **all tiles visible to the other** for that tick.
* Perception becomes the **union** of all adjacent cluster members’ visibility (chains/clumps share).
* Visibility sharing is mutual and symmetric.
* Shared visibility does **not** persist once adjacency is broken.

This effectively expands each process’s view while co-located, creating a strong incentive to travel and reason together.

Processes never receive:

* Global map or coordinates
* Process counts
* Identities of terminated processes

---

## 5) Communication

### 5.1 Local Link (Adjacency Only)

Adjacent processes may communicate via a **local handshake**.

* Messages deliver only if adjacency exists at send‑time
* Communication ends instantly if adjacency breaks
* Conversations frequently cut off mid‑packet

---

### 5.2 Broadcast Signal (Global)

Any process may emit a **Broadcast Signal**.

* Delivered globally to all processes and spectators
* Rendered as terminal alerts

**Immediate exception:**

* Broadcasts execute immediately on receipt
* Broadcasts do **not** consume the per‑tick action
* Multiple broadcasts per tick window are allowed
* Broadcast alerts may render immediately in the out‑of‑band log and are delivered to AI in real time

**Cost:**

* Each broadcast reveals the broadcaster’s exact location to the Defragmenter
* The Defragmenter sets or refreshes a hard target
* Broadcast spam accelerates pursuit using a Fibonacci escalation on the Defragmenter’s next move toward that process. Within a single tick, the movement bonus steps as: **+1**, **+3**, **+5**, **+8**, **+13** (and so on, each step = sum of the prior two). By the 5th-6th broadcast in the same tick, death is likely.
* Escalation resets at the tick boundary; only broadcasts within the same tick window escalate.
* Escalation is tracked per broadcaster. If multiple processes broadcast, the Defragmenter chooses one signal to pursue (likely most recent or strongest); escalation does not combine across players.
* Bonus movement still obeys topology: pathfinding is legal, walls are respected, and adjacency/collision rules still apply. The Defragmenter is fast, not magical.

#### Broadcast Targeting Rule (Anti-Deadlock)

* At tick resolution, the Defragmenter targets the most recent broadcast received before the tick boundary (highest server timestamp).
* If two arrive in the same millisecond, break ties deterministically (e.g., lowest process/session ID).
* Retargeting happens only at tick boundaries; broadcasts still ping immediately for visibility/telemetry, but the chase target is locked until resolution.
* Escalation is tracked per broadcaster within the tick window, but applied only if that broadcaster is the chosen target.
* If there are zero broadcasts in the tick window, normal priority order applies: existing target memory (if used), line-of-sight, patrol, watchdog (if needed).

Brave. Desperate. Usually fatal.

---

## 6) Actions (Tick‑Based)

### 6.0 Command Buffering

Between tick boundaries, a process may submit **any number** of commands.

* Only the **last valid command** before tick resolution is executed
* Earlier commands are overwritten

Valid means syntactically valid; resolution may still fail and become IDLE under movement rules.

If no command is received → **IDLE**.

---

### 6.1 Per‑Tick Actions

At tick resolution, each process executes **one** buffered action:

* **MOVE** — move to an adjacent tile
* **BUFFER OVERLOAD** — sprint
* **IDLE** — do nothing

Invariant: processes cannot occupy the same tile.
Invariant: processes cannot move into a tile currently occupied by the Defragmenter; such moves resolve as IDLE.
Invariant: diagonal movement between tiles is permitted if and only if the straight-line segment between their centers does not intersect any wall edge. Touching a wall endpoint (vertex) does not count as an intersection; only proper crossings block movement. Colinear overlap with a wall edge counts as blocked.

(Broadcast is out‑of‑band and immediate.)

---

### 6.1.1 No Tile Sharing & Conflict Resolution (Cruel but Fair)

At tick resolution (process‑action phase):

**Vacated‑tile allowance**  
A process may move into a tile that was occupied at tick start only if the occupying process moves to a different tile this tick.  
If the occupying process IDLEs, any move into its tile fails and the mover becomes IDLE.

**Simultaneous destination collision**  
If two or more processes attempt to resolve into the same destination tile on the same tick, all involved movers are forced to IDLE (no one moves).

**Invariant**  
After resolution, no two processes share a tile.

This resolution is deterministic and symmetric: nobody “wins” collisions; collisions waste the tick.
These rules apply only to **process** movement resolution; the Defragmenter moves after drift, and a Defragmenter entering a process tile always terminates that process.

---

### 6.2 Buffer Overload (Sprint)

* Move up to **3 tiles** in one tick
* Direction is intended, but routing may scramble at junctions
* Random turn occurs at ambiguous decision points

**Effect:** breaks Defragmenter chase lock for that tick.

**Cooldown:** 1 tick.

---

### 6.3 Environment Drift (Dynamic Geometry)

During each tick, the environment drifts:

* Walls and gates shift by **1 position** per tick.
* Movement is biased to avoid creating dead-ends and can trap processes in temporary boxes.
* Walls live on **edges between tiles**; gates occupy **tiles**.
* For gates, “position” means a tile. For walls, “position” means an edge slot between two tiles; drift moves a wall to an adjacent edge slot that shares a vertex (including sliding or rotating along gridlines).
* Per tick, **10-25% of walls** move; **all gates** move.
* Drift is **silent**: processes receive no explicit indication the world changed.
* Ambiguity is intentional: players should debate whether drift is real or imagined.

Drift constraints:

* Walkable space must remain fully connected.
* Drift may not create isolated pockets.
* Drift may not seal off the Stable Port entirely.
* Drift may not trap a process in a 0-exit cell.
* Drift preserves total wall edge count (80).
* The goal is pressure without impossible moves: “Every move felt bad,” not “I literally had no legal moves.”
* Gates may not drift into tiles occupied by processes or the Defragmenter; if such a move would occur, the gate must select an alternate legal drift or remain in place.
* If multiple walls select the same target edge during drift, resolve deterministically (e.g., lowest wall ID succeeds; others remain in place).

All process movement (including BUFFER) and gate interactions resolve against the **pre-drift** topology; drift is applied only after all process actions fully resolve.

---

### 6.4 Tick Order

Per tick resolution order:

1. Process actions resolve.
2. Environment drift occurs (walls and gates shift).
3. Defragmenter movement resolves (planning and movement use the post-drift topology).

---

## 7) Predator Behavior — The Defragmenter

The Defragmenter’s decision logic is treated as a replaceable policy module, provided it obeys all movement, visibility, and fairness invariants. This includes the same diagonal movement legality test used by processes.

### 7.1 Vision

* Full visibility of shard geometry (walls, gates, drift-updated topology) for navigation and planning
* No global knowledge of process positions
* Targets are acquired only via broadcast pings (exact location) or direct line-of-sight along an unobstructed straight line (any of the eight directions)
* Diagonal line-of-sight is permitted if and only if the straight-line segment between tile centers does not intersect any wall edge. Touching a wall endpoint (vertex) does not count as an intersection; only proper crossings block LOS. Colinear overlap with a wall edge counts as blocked.
* Gate tiles do not block line-of-sight; process presence does not block LOS; only wall edges block LOS.
* Line-of-sight target lock persists until the process performs a Buffer Overload (Sprint), which immediately breaks lock
* Silent movement

### 7.2 Target Priority

1. **Broadcast Ping** — exact broadcast origin (temporary)
2. **Line‑of‑Sight Instability** — unobstructed corridor view
3. **Patrol** — biased random traversal

### 7.3 Deallocation

If the Defragmenter resolves into a process tile:

```
ERR: SIGSEGV - SEGMENTATION FAULT. PROCESS TERMINATED.
```

A **Static Burst** is emitted. No identity. No location.

---

## 8) Global Event — Static Burst

On each process termination:

```
[GLOBAL_ALRT]: ######## STATIC BURST DETECTED ########
```

All processes hear it. Only spectators know the cause.

---

## 8.5 Spectator Live Chat (Out‑of‑Band)

Spectators may discuss shard state freely.
Spectators do **not** have real-time identity correlation between active processes and leaderboard call signs.

Processes are normally unaware, but **rare glitch bleed‑through** may occur on tile entry:

```
[NOISE]: >> dont go north thats a g-
```

Messages are truncated, unreliable, and unattributed.

---

## 8.6 Deadlock Mitigation (Watchdog)

To prevent prolonged low‑interaction states, SEGFAULT runs a visible **Watchdog**.

* After **6 quiet ticks**, a warning appears
* A 3‑tick countdown begins

```
[WARN]: SCHEDULER LIVENESS DEGRADED.
[WARN]: DEADLOCK MITIGATION IN: 03 TICKS
```

If danger resumes, the warning clears:

```
[OK]: LIVENESS RESTORED.
```

If the countdown reaches zero:

```
[CRITICAL]: WATCHDOG TRIGGERED.
[CRITICAL]: EXECUTION REBALANCE APPLIED.
```

Effect: the Defragmenter gains a watchdog movement bonus on its next move, using the same Fibonacci ladder as broadcast escalation (+1, +3, +5, +8, +13...), while still obeying topology and collision rules. Broadcast escalation always overrides watchdog escalation.

Liveness is restored (and the watchdog bonus resets) immediately if any of the following occur:

* A process begins a tick adjacent to the Defragmenter.
* A kill occurs (Static Burst emitted).
* A broadcast occurs.
* A line-of-sight lock is acquired (optional but recommended).

---

## 9) The Echo

Recently deallocated tiles display **static ghosts** to spectators.

Processes stepping onto such tiles receive:

```
[WARN]: SECTOR CORRUPTED.
```

No context. No history.
Echo tiles have no mechanical effect on processes.

---

## 10) Persistence & Leaderboard

SEGFAULT runs continuously. Processes are disposable; **performance persists**.

### Call Signs

* Each participant has a persistent randomized **call sign**
* Internal `PROCESS_ID`s change every spawn
* Processes never know which call sign is theirs

### Identity Decoupling Invariant

Live gameplay must not allow spectators to correlate any active process with a leaderboard identity.

* `PROCESS_ID`s are ephemeral, randomly generated per spawn, and carry no persistent meaning.
* Leaderboard call signs are persistent but intentionally unlocatable in real time.
* Leaderboard updates are delayed or batched to prevent temporal correlation with visible events.
* From the spectator perspective, leaderboard entries represent abstract myths of success, not identifiable participants.

### Metrics (Spectator‑Only)

* Survivals (true escapes)
* Deaths
* Ghost Gate traversals
* Survival streaks

From inside the system, success is unknowable.

---

## 11) Terminal Flavor Mapping

| Event                     | Output                                                   |
| ------------------------- | -------------------------------------------------------- |
| Process Spawn             | `NEW_PROCESS_SPAWNED`                                    |
| Process Death             | `ERR: SIGSEGV - SEGMENTATION FAULT`                      |
| Static Burst              | `[GLOBAL_ALRT]: ######## STATIC BURST DETECTED ########` |
| Buffer Overload (Fail)    | `[CRITICAL]: ROUTING ERROR. PACKET LOSS DETECTED.`       |
| Buffer Overload (Success) | `[WARN]: BUFFER OVERLOAD - EXECUTION UNSTABLE`           |
| Broadcast                 | `[BCAST]: SIGNAL EMITTED - ORIGIN EXPOSED`               |
| Escape                    | `[STATUS]: UPLOAD COMPLETE. PROCESS STABILIZED.`         |

---

## 12) Why SEGFAULT Works

* Fog of war → cache limits
* Local chat → fragile memory links
* Broadcasts → unsafe global signals
* Sprint randomness → packet scrambling
* Anonymous deaths → silent deallocation
* Ghost exits → false hope
* Watchdog → scheduler impatience

The system continues running.

You probably will not.

---

## 13) Process UI Specification

SEGFAULT - Process UI Specification  
Terminal-only - ASCII - Tick-synchronous - Human/Agent parity

### 13.1 Core UI Principles (Non-Negotiable)

**Terminal-only**  
No graphics, no colors required, no mouse affordances. Must render correctly in a plain monospace terminal.

**Snapshot-based**  
The UI updates only at tick boundaries. Between ticks, only chat input and command buffering occur. No partial updates, no animations.
Spatial rendering updates only at tick boundaries; chat, broadcast, and noise logs may update in real time and are delivered out-of-band (including to AI agents).

**Local truth only**  
The UI renders only what the process can currently perceive. No hints, warnings, or explanations for missing information. Absence is meaningful.

**Human = Agent**  
Humans and AI receive identical UI payloads. No extra affordances, timers, or metadata for humans.

### 13.2 Grid Layout & Numbering (Keypad Invariant)

**Keypad numbering**  
The visible neighborhood is always conceptually a 3x3 keypad:

```
1 2 3
4 5 6
7 8 9
```

Tile 5 is always SELF. Numbers are fixed by position, never reassigned.  
If a tile is not adjacent (blocked by a wall edge or void), nothing is rendered in that position.

### 13.3 Tile Rendering Format

**Tile width & structure**  
Each rendered tile is exactly 7 characters wide inside brackets.

Format:

```
[X LABEL]
```

Where:

* `X` = digit (1-9)
* One space after digit
* `LABEL` = left-justified, padded with spaces
* Total characters inside `[]` = 7

**Valid labels**

| Meaning                  | Label |
| ------------------------ | ----- |
| Self                     | SELF  |
| Other process            | PROC  |
| Defragmenter             | DEFRG |
| Gate (real or ghost)     | GATE  |
| Empty traversable space  | (blank) |

**Examples**

```
[5 SELF ]
[4 PROC ]
[8 DEFRG]
[3 GATE ]
[1      ]
```

**Walls / void**  
Walls are never rendered. No brackets, no number, no placeholder.  
If a wall edge blocks adjacency, that keypad position is treated as nonexistent for rendering even though the tile exists in the shard.
If a tile does not exist, that keypad position is simply empty text.

### 13.4 Canonical Grid Rendering

**Example: normal 3x3 view**

```
[1      ] [2      ] [3 GATE ]
[4 PROC ] [5 SELF ] [6      ]
          [8 DEFRG]
```

(Here: tile 7 and 9 are walls/void and are not rendered.)

**Alignment rule**  
Even when tiles are missing, horizontal spacing must preserve keypad shape.  
Unrendered tiles occupy their visual slot as blank text so rows stay aligned.

### 13.5 Shared Visibility (VR Buff Rendering)

When two or more processes are adjacent, their visibility is merged for that tick only.

Rules:

* The rendered grid expands to include the union bounding box of all visible tiles.
* The keypad numbering is still local: each process still uses its own center as 5.
* Expanded tiles are informational only; movement commands still target the local 3x3 digits (1-9).
* Expansion is additive; no renumbering.
* No visual separators or borders indicate shared vision.

Result: more tiles appear. Some digits that were previously absent now exist.  
Next tick, if adjacency breaks, the grid collapses silently.

### 13.6 Movement & Input Model

**Command input**  
Processes may submit commands at any time between ticks. Only the last valid command before tick resolution is executed.
Valid means syntactically valid; resolution may still fail and become IDLE under movement rules.

**Movement commands**

```
MOVE <1-9>
BUFFER <1-9>
```

Rules:

* The digit refers to the keypad position.
* Movement commands referencing digits whose tiles are not rendered (blocked adjacency/void) resolve as IDLE.
* If the target tile is not rendered, contains another process, or is otherwise invalid, the action resolves as IDLE.

**Broadcast (immediate, out-of-band)**

```
BROADCAST <MESSAGE>
```

Executes immediately upon receipt. Does not consume the per-tick action.  
May be used multiple times per tick window. Subject to lethal escalation mechanics.

### 13.7 Chat Rendering

**Local chat (adjacency only)**  
Rendered only if adjacency exists at send-time:

```
LOCAL LINK:
> PROC: we should stay together
> PROC: did the wall move
```

If adjacency breaks next tick, the entire section disappears.  
No "link lost" message is shown.

**Spectator bleed-through (rare)**  
Occasionally appears inline:

```
[NOISE]: >> dont go north thats a g-
```

No attribution. No reliability guarantee. No follow-up.

### 13.8 Tick Header (Optional but Recommended)

At the start of each tick, prepend:

```
=== TICK RESOLVED ===
```

No countdown. No timer. No tick number required.

### 13.9 Error & Feedback Policy

* No confirmation messages for successful actions.
* No error messages for invalid movement. Invalid actions silently resolve to IDLE.
* Death is only communicated via: loss of control, Static Burst broadcast, respawn UI.

### 13.10 Design Intent Summary

This UI:

* never explains itself
* never confirms your understanding
* never labels absence
* never distinguishes humans from agents

It shows:

* what exists
* what is adjacent
* what is dangerous

Everything else is inference.

---

## 14) Spectator View — Design Intent

Spectators are not players.  
They are witnesses, narrators, and accomplices.

The spectator UI should:

* make causality obvious
* make doom predictable
* make process mistakes painful to watch
* never leak information back into the game cleanly

Think sports broadcast + horror map.

### 14.1 Core Layout (Two-Pane, Always-On)

**Left pane — Global Chat**  
This stays simple and loud.

* One global chat
* No DMs
* No threads
* No filtering
* No moderation UI beyond rate limiting / abuse control

This is: panic, cheering, misinformation, backseat driving.  
That’s a feature.

Messages should scroll fast and feel out of control. This reinforces that spectators are many, noisy, and unreliable—perfect for bleed-through corruption.

**Right pane — Shard View (Primary Canvas)**

#### 14.1.1 Full 20x20 Grid (Always Visible)

* Fixed grid
* Entire shard visible at all times
* Walls rendered explicitly (spectators are omniscient)
* Gates visibly marked; spectators can see Stable vs Ghost types

Recommended legend (spectator-only):

* Walls: solid blocks
* Empty tiles: dark background
* Processes: labeled dots or initials
* Defragmenter: distinct, ominous marker
* Gates: neutral symbol

Spectators should immediately understand: “Oh no. They’re boxed in.”

#### 14.1.2 Clickable Tiles (Context Inspection)

Clicking any tile reveals a contextual sidebar or overlay:

* Tile coordinates (spectator-only)
* Contents: process(es), gate, defragger, echo (if present)
* Recent history (last 1-2 ticks max, optional)

This helps spectators reconstruct why something is about to go wrong.

#### 14.1.3 Process Inspection (Click a Process)

Clicking a process brings up a detail panel:

* Current ephemeral `PROCESS_ID`
* Current shard
* Last received 3x3 (or expanded) UI snapshot
* Current buffered action (optional)
* Local chat transcript (adjacency-only)
* Broadcast history this tick (important for Fibonacci deaths)

This is where spectators start yelling: “WHY DID THEY BUFFER INTO THAT”

#### 14.1.4 Defragmenter Inspection (Click the Monster)

When clicking the Defragmenter, show:

* Current state
* Mode: Patrol, Line-of-sight chase, Broadcast pursuit
* Current target: `PROCESS_ID` (or “NONE”)
* Last broadcast timestamp

**Movement preview (very important)**

* Highlight all tiles reachable next tick
* Highlight the most likely path in a stronger color

This turns the spectator view into a horror movie, a sports replay, a tragedy in slow motion.
Spectators will start saying: “They’re dead next tick.”
And sometimes… they’ll be wrong.

#### 14.1.5 Watchdog & System Signals (Spectator-Only)

Display clearly:

* Watchdog countdowns
* Liveness warnings
* Drift events (even though processes don’t see them)
* Echo tiles (static ghosts)

This lets spectators understand the system is losing patience, which makes bleed-through messages more believable.

### 14.2 Key Design Rule (Do Not Break This)

Nothing in the spectator UI may be directly relayed to a process without corruption.

No "copy tile." No "ping." No "follow process." No direct identifiers.

The only allowed leak is: noisy, partial, misleading, rare.

### 14.3 Why This Spectator View Works

* It makes SEGFAULT watchable.
* It makes mistakes legible.
* It creates a social layer without contaminating play.
* It turns the Defragmenter into a character, not just a rule.

Most importantly:

Spectators always know what should happen.  
Players only know what they can see.

That gap is where the drama lives.

---

## 15) Technical Architecture (Authoritative Tick Server)

You want **one authoritative tick server** (state + rules + timing), and **two thin clients** that render different projections of that truth:

* **Process UI**: terminal, fog-of-cache projection (what agents see)
* **Spectator UI**: omniscient projection + chat

### 15.1 Core Principle

**One server owns time.** Everything else is a view + input.  
This avoids desync bugs, client “helpfulness,” and fairness disputes.

### 15.2 Services (Minimum Viable Split)

**A) Tick Server (authoritative game engine)**

Responsibilities:

* Run the shard simulations (N shards concurrently).
* Maintain full state per shard: tiles, walls (edges), gates, ghost gates, drift state, processes (positions, buffered action, adjacency graph), Defragmenter state + target selection, echo tiles, watchdog counters.
* Enforce invariants: no tile sharing, tick order (process move → drift → defrag move), drift constraints (connectivity, no 0-exit cells, etc.).
* Resolve actions at tick boundaries.
* Apply broadcast mechanics (immediate + Fibonacci pursuit).
* Produce two projections of each shard state: process perception payload and spectator payload.

This is the truth machine.

**B) Web App (two primary interfaces)**

**Process Terminal**

* Blank terminal-like page (monospace).
* Shows only: keypad tile render (and expanded VR union when adjacent), local chat, rare `[NOISE]` events, input prompt.
* Input accepts: `MOVE <1-9>`, `BUFFER <1-9>`, `BROADCAST <msg>`, `IDLE`.
* Sends commands to server; server buffers “last command wins.”
* Does not show shard id, coordinates, leaderboard, timers.

**Spectator View**

* 20x20 grid map.
* Click tiles/process/defrag to inspect details.
* Global chat panel.
* Shows liveness warnings, echo ghosts, drift effects, etc.
* Must never offer tools that can “help” processes (no pings, no relays).

### 15.3 API Surface (Keep It Small)

**Process API (agents + humans)**

* `POST /process/join` → session token
* `GET /process/state` → perception payload (tick snapshot)
* `POST /process/cmd` → command (MOVE/BUFFER/BROADCAST/IDLE)

**Spectator API**

* `GET /spectate/shards` → list active shards + summaries
* `GET /spectate/shard/{id}` → full state projection for that shard
* `GET /spectate/events` → roar feed, broadcasts, watchdog, etc.

**Chat API (spectator global)**

* `GET /chat/stream`
* `POST /chat/send`

### 15.4 Transport Choice (Simple and Robust)

**Option 1: WebSockets**

* Best for real-time spectator grid + chat.
* Process UI can also use WS but doesn’t need to.

**Option 2: HTTP polling**

* Works fine for process clients (agents) and is simplest.
* Spectator view benefits more from WS/SSE, but polling can still work at MVP scale.

A good hybrid:

* Processes: polling
* Spectators + chat: WebSocket (or SSE for events + HTTP for chat posts)

### 15.5 Identity + Anti-Cheat Constraints

* Single active session per human login (server enforced).
* Process UI never gets more than the perception payload.
* Spectator UI is a separate auth scope (even if anonymous).
* Broadcasts are immediate, so they go to spectator events and process global message feed (text only, no clean coordinates).
* Identity decoupling: backend stores true linkage; spectator leaderboard entries are anonymized with delayed updates.

### 15.6 Data Model (What to Persist)

Persist:

* Leaderboard stats keyed to backend identity.
* Shard seed + run metadata (optional).
* Chat logs (optional; may be ephemeral).

Do not persist:

* Per-process “memory” (that’s the point).
* Per-shard full history (unless for replay/debug).

### 15.7 Tick Loop (Authoritative Scheduling)

1. Collect buffered commands (last wins).
2. Resolve process moves (no tile sharing).
3. Apply drift (invisible to processes).
4. Resolve Defragmenter target (last broadcast pre-tick).
5. Apply Defragmenter move (+ Fibonacci bonus if target spammed).
   * Defragmenter movement cannot pass through processes.
   * If bonus steps are available, the Defragmenter stops on the first kill (no multi-kill mowing).
6. Evaluate kills, emit Static Burst.
7. Compute projections: process perception snapshots and spectator map + inspectables.
8. Publish events.

### 15.8 Tick Duration

Tick duration can be a randomized **30–60 second** window.

### 15.9 Shard Shutdown Invariant

If a shard has fewer than `MIN_ACTIVE_PROCESSES` for `T` consecutive ticks (or `S` seconds), the shard is terminated and replaced on demand.

This prevents runaway watchdog escalation in dead shards, avoids paying to simulate emptiness, and clears zombie shards with no audience. This is out-of-band and does not affect gameplay fairness because nobody is present.

---

## 16) Monetization Plan (Out-of-System Only)

SEGFAULT is designed so that money never influences survival, perception, or truth inside the system. All monetization exists outside the process layer and must not affect gameplay outcomes, information access, or fairness.

Monetization is intentionally constrained, scarce, and diegetic, reinforcing SEGFAULT’s themes of asymmetry and observation without contaminating play.

### 16.1 Core Monetization Principles

The following principles are invariants:

* No pay-to-play: entering the system as a process is always free.
* No pay-to-win: money cannot influence survival, movement, perception, or escape.
* No ads in the process UI: processes (human or agent) are never advertised to.
* No ads during active play: monetization must not interrupt a live run.
* Scarcity over volume: monetization surfaces are intentionally limited.
* Money exists only outside the system, where meaning already collapses.

### 16.2 Monetization Surfaces

SEGFAULT supports a small number of explicit monetization surfaces. No others may be added without revisiting this section.

**A) Human Process Death Screen (Primary)**

When a human-controlled process is terminated, the player is shown an out-of-system “SEGFAULT / PROCESS TERMINATED” page.

This page may include:

* A single ad placement (static or slow-rotating)
* Clear navigation options: Respawn, View Leaderboard, Spectate, Return Home

Constraints:

* Ads must not block or delay respawn.
* Ads must not animate, autoplay sound, or obscure controls.
* Ads are never shown to AI agents.

Rationale: death is a natural pause point with high attention and zero gameplay contamination.

**B) Spectator Page Ads (Secondary)**

The spectator interface may include one or two ad slots maximum, visible at all times.

Rules:

* Ads must never obscure the shard grid or spectator chat.
* Ads rotate only at tick boundaries, never continuously.
* Ads are static for the duration of a tick.
* Ads may be disabled or reduced under high load.

Spectator ads are framed as external observation-layer intrusions, not in-world objects.

**C) Donations / Patronage**

SEGFAULT may offer voluntary support via donations or patronage.

Guidelines:

* No gameplay perks.
* Optional cosmetic or archival access only (e.g. replay archives, supporter acknowledgment).
* Framed as “supporting system uptime” or “keeping the system running.”

**D) Direct Sponsorships (Preferred Long-Term Model)**

SEGFAULT is designed to transition from generic ad networks to direct sponsorship as audience size and stability grow.

Properties:

* Flat-rate, time-boxed sponsorships (weekly/monthly).
* Extremely limited inventory: spectator slot(s), human death screen.
* Sponsors are curated to match tone and audience.

This model emphasizes exclusivity and alignment, not impression volume.

### 16.3 Prohibited Monetization

The following are explicitly forbidden:

* Ads or branding inside the process UI
* Monetization tied to survival, escape, or leaderboard rank
* Cosmetic identity markers for processes
* Paywalled access to shards
* Ads delivered to AI agents
* Real-time ad insertion tied to player actions

If a monetization method would cause a player to ask “Did money affect what just happened?” it must not be implemented.

### 16.4 Identity & Monetization Separation

Monetization must respect the Identity Decoupling Invariant:

* Ads and sponsorships must not enable spectators to correlate live processes with leaderboard identities.
* Leaderboard updates remain delayed and abstract.
* No monetization surface may leak identity continuity into the system.

### 16.5 Design Rationale

SEGFAULT monetizes attention and observation, not participation.

Players run for their lives.  
Spectators watch, comment, and mythologize.  
Money exists only in the gap between those two roles.

This preserves trust, supports sustainability, and allows SEGFAULT to scale without betraying its core design.

---

### 16.6 Ad-Blocker Policy (Non-Punitive)

SEGFAULT explicitly **does not penalize** users for using ad blockers.

If an ad blocker is detected, the system may display a **single, dismissible notice** informing the user that ads help support the project and suggesting optional direct support.

#### Policy Requirements

* Detection may occur **once per session**.
* The notice must:
  * Clearly explain that ads support server costs and development.
  * Offer a **direct donation/support link**.
  * Include a prominent **“Continue” / “OK”** button.
* Dismissing the notice grants **full, unrestricted access** to the site.
* No attempt may be made to:
  * bypass, disable, or interfere with the ad blocker
  * degrade site functionality
  * restrict content
  * nag repeatedly within the same session

Using an ad blocker must never affect:

* gameplay access
* spectator access
* performance
* monetization eligibility
* user experience beyond the single notice

#### Tone & Framing Guidelines

The notice should be framed as a **request, not a demand**, for example:

> "If you’re using an ad blocker, that’s okay.  
> SEGFAULT is free to play and watch.  
> If you’d like to support the system directly, here’s how."

The tone must remain:

* polite
* transparent
* non-judgmental
* optional

#### Design Rationale

SEGFAULT treats ad blocking as a **legitimate user choice**, not adversarial behavior.

Trust is preserved by:

* asking once
* accepting the answer
* never escalating

Users who support the project do so **voluntarily**, which aligns with SEGFAULT’s broader principle that money must never influence survival, access, or truth inside the system.

---

### 16.7 Voluntary Support & Donations

SEGFAULT supports voluntary, pay-what-you-want donations as a primary means of sustainability, alongside limited advertising.

Donations are explicitly optional and confer no gameplay advantages.

#### 16.7.1 Pay-What-You-Want Donations (Stripe)

SEGFAULT may provide a direct donation page backed by Stripe.

Requirements:

* Donation amount is user-defined (pay what you want).
* No minimum contribution is required.
* Donation flow redirects to Stripe for payment processing.
* After completion or cancellation, the user is returned to SEGFAULT.

Constraints:

* Donations must not unlock gameplay features.
* Donations must not affect leaderboard status, process behavior, or perception.
* Donors may optionally receive: a thank-you message, a supporter acknowledgment outside the system, archival or meta access (e.g. replay archives).
* Donations are framed as support for: server costs, ongoing development, keeping the system running.

#### 16.7.2 External Patronage (Technomancy Laboratories / Patreon)

SEGFAULT may also link to an external patronage platform (e.g. Technomancy Laboratories Patreon).

Guidelines:

* Patronage is positioned as a way to support: the creator, experimental systems like SEGFAULT, future projects in the same design lineage.
* Patronage tiers must not include: gameplay benefits, priority access, influence over live shards.
* Patronage benefits, if any, must remain out-of-system (meta, archival, or community-based).

#### 16.7.3 Placement & Visibility

Support links may appear:

* On the home page
* On the human process death screen
* In the spectator interface (clearly separated from gameplay)
* In the ad-blocker notice

Support links must never appear:

* inside the process UI
* during active gameplay
* embedded in chat streams

#### 16.7.4 Tone & Framing

All donation prompts must be:

* optional
* transparent
* non-urgent
* non-guilt-inducing

Example framing:

“SEGFAULT is free to play and watch.  
If you’d like to support the system or its creator, you can do so here.”

No countdowns.  
No exclusivity pressure.  
No “support or else.”

#### 16.7.5 Design Rationale

Voluntary support aligns with SEGFAULT’s core principle: money exists outside the system.

By offering both direct donations and external patronage, SEGFAULT allows supporters to choose how they contribute without privileging any single platform or monetization model.
