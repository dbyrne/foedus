"""Core types and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, TypeAlias

PlayerId: TypeAlias = int
NodeId: TypeAlias = int
UnitId: TypeAlias = int


class NodeType(Enum):
    PLAIN = "plain"
    SUPPLY = "supply"
    HOME = "home"
    MOUNTAIN = "mountain"   # impassable, not ownable, not occupiable
    WATER = "water"         # same semantics as MOUNTAIN; distinct render


class Archetype(Enum):
    UNIFORM = "uniform"                       # v1 backward-compat (no terrain)
    HIGHLAND_PASS = "highland_pass"           # mountain ridges with passes
    RIVERLANDS = "riverlands"                 # snaking river with two crossings
    CONTINENTAL_SWEEP = "continental_sweep"   # open plains, dense connectivity


@dataclass(frozen=True)
class Hold:
    pass


@dataclass(frozen=True)
class Move:
    dest: NodeId


@dataclass(frozen=True)
class Support:
    """Reactive support order. Adapts to target_unit's actual canon order at
    finalize.

    If `require_dest` is None (default), the support lands on whatever the
    target unit actually does this turn, subject to geometric reachability
    (supporter must be adjacent to the target's destination if it moves, or
    to the target itself if it holds). If `require_dest` is set, behaves
    like the legacy SupportMove: lands only when the target moves to exactly
    that destination, otherwise lapses to Hold.
    """
    target: UnitId
    require_dest: NodeId | None = None


Order: TypeAlias = Hold | Move | Support


class Stance(Enum):
    ALLY = "ally"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"


class Phase(Enum):
    NEGOTIATION = "negotiation"
    ORDERS = "orders"


@dataclass(frozen=True)
class Intent:
    """A pre-declaration of what order I will issue for one of my units.

    `visible_to` controls who sees this commitment:
    - `None` -> public broadcast: visible to all surviving players
    - `frozenset({p1, p2, ...})` -> visible only to the named recipients
    - `frozenset()` -> silently dropped on submit (no recipients = no commitment)
    """
    unit_id: UnitId
    declared_order: Order
    visible_to: frozenset[PlayerId] | None  # None = public broadcast


@dataclass(frozen=True)
class Press:
    """One player's structured outbound press for one round.

    `stance` is public; missing entries default to NEUTRAL.
    `intents` is a flat list; each Intent carries its own `visible_to` set.
    """
    stance: dict[PlayerId, Stance]
    intents: list[Intent]


@dataclass(frozen=True)
class ChatDraft:
    """What an agent emits when sending chat. Engine fills in turn/sequence/sender."""
    recipients: frozenset[PlayerId] | None  # None = public broadcast
    body: str


@dataclass(frozen=True)
class ChatMessage:
    """Canonical chat record stored in chat_history."""
    turn: int
    sequence: int
    sender: PlayerId
    recipients: frozenset[PlayerId] | None
    body: str


@dataclass(frozen=True)
class SupportRound:
    """Primitive B: one turn's ally-support activity, for the rolling
    reciprocation window.

    `gave` = players who issued >=1 uncut cross-player Support benefiting a
    standing ALLY (giver declared ALLY toward the beneficiary) this turn.
    `received` = players whose unit received >=1 such support. Public
    (whole-table visible, like `reputation`); the engine keeps only the last
    `GameConfig.reciprocation_window` rounds.
    """
    turn: int
    gave: frozenset[PlayerId]
    received: frozenset[PlayerId]


@dataclass(frozen=True)
class BetrayalObservation:
    """End-of-turn signal that someone broke an intent visible to me.

    The intent's `visible_to` set determined who received this observation:
    public intents broadcast a betrayal observation to all surviving players;
    private/group intents notify only the named recipients.
    """
    turn: int
    betrayer: PlayerId
    intent: Intent
    actual_order: Order


@dataclass(frozen=True)
class IntentRevised:
    """Emitted when a player submits, modifies, or retracts an intent during
    negotiation.

    Sent to each player in `visible_to`, which mirrors the revised intent's
    own `visible_to` (None = public broadcast to all surviving non-senders;
    frozenset = named recipients).

    `intent` is the new value (None if retracted); `previous` is the prior
    value (None if this is a first declaration for the unit this round).
    Exactly one of `intent` / `previous` may be None at a time; both being
    None is invalid.
    """
    turn: int
    player: PlayerId
    intent: Intent | None     # None = retraction
    previous: Intent | None   # None = first declaration this round for this unit
    visible_to: frozenset[PlayerId] | None  # mirrors intent.visible_to


@dataclass(frozen=True)
class SupportLapsed:
    """Emitted at finalize when a Support could not land.

    `reason` taxonomy:
      - "geometry_break": supporter not adjacent to target's actual result
      - "target_destroyed": target dislodged before its order resolved
      - "pin_mismatch": require_dest set, target went elsewhere
      - "self_dislodge_blocked": support would dislodge supporter's own unit
    """
    turn: int
    supporter: UnitId
    target: UnitId
    reason: Literal[
        "geometry_break",
        "target_destroyed",
        "pin_mismatch",
        "self_dislodge_blocked",
    ]


@dataclass(frozen=True)
class DoneCleared:
    """Emitted when a player's signal_done flag auto-clears.

    Triggered when an ally revises an intent that one of this player's
    committed Support plans referenced. Only direct dependents auto-clear —
    there is no transitive cascade.
    """
    turn: int
    player: PlayerId         # whose done flag cleared
    source_player: PlayerId  # whose revision triggered the clear
    source_unit: UnitId      # which unit's intent the dependency referenced


# --- Phase 0b (F5): binding joint intents ("Pacts") ---


class PactStatus(Enum):
    PROPOSED = "proposed"   # awaiting counterparty acceptance
    ACCEPTED = "accepted"   # ratified; binding for the upcoming resolution


@dataclass(frozen=True)
class PactTerm:
    """One obligated (player, unit, order) entry within a Pact.

    `player` is the obligated party (always the pact's proposer or
    counterparty); `unit_id` is one of that player's units; `declared_order`
    is the order that player commits to issue for it this resolution.
    """
    player: PlayerId
    unit_id: UnitId
    declared_order: Order


@dataclass(frozen=True)
class Pact:
    """A proposed-or-ratified joint commitment between exactly two players
    describing coordinated orders for the upcoming resolution.

    `terms` spans BOTH parties (e.g. P0's u1 -> Move(8) AND P2's u5 ->
    Support(u1)). `proposer` proposes; `counterparty` accepts. Once ACCEPTED
    the pact is binding for the next resolution and any party's divergence
    from its term is a PactBreach (a strong signal the other party observes).

    `proposed_turn` is `state.turn` at proposal time and drives expiry: a
    PROPOSED pact must be accepted the same or the next round (see
    `foedus.press.finalize_round`).
    """
    pact_id: int
    proposer: PlayerId
    counterparty: PlayerId
    terms: tuple[PactTerm, ...]
    status: PactStatus
    proposed_turn: int


@dataclass(frozen=True)
class PactProposal:
    """What an agent emits to propose a Pact. Engine fills in pact_id,
    proposer, status, and proposed_turn.

    Mirrors how `ChatDraft` carries the agent-supplied parts of a
    `ChatMessage`. `terms` should span both the proposing player and
    `counterparty` to form a genuine joint commitment.
    """
    counterparty: PlayerId
    terms: tuple[PactTerm, ...]


@dataclass(frozen=True)
class PactBreach:
    """End-of-turn signal that a party broke one of its obligations under an
    ACCEPTED pact.

    Recorded in `state.pact_breaches[observer]` where `observer` is the
    non-breaching party of the pact — the one who relied on the commitment.
    F6 attaches a mechanical penalty (`GameConfig.pact_breach_penalty`) and a
    public reputation increment (`GameState.reputation`) to this signal.
    """
    turn: int
    pact_id: int
    breacher: PlayerId
    term: PactTerm
    actual_order: Order


@dataclass(frozen=True)
class ReputationTally:
    """F6: cumulative PUBLIC breach counts for one player, by breach type.

    Unlike `betrayals`/`pact_breaches` (keyed by the observing/victim party,
    so only visible to whoever a breach targeted), this is the whole-table
    social cost: every player's fog view sees every other player's tally,
    like `scores`. Never decays.
    """
    intent_breaches: int = 0
    pact_breaches: int = 0

    @property
    def total(self) -> int:
        return self.intent_breaches + self.pact_breaches


@dataclass(frozen=True)
class Unit:
    id: UnitId
    owner: PlayerId
    location: NodeId


@dataclass(frozen=True)
class Map:
    """Static graph + node metadata. Same across an entire game."""
    coords: dict[NodeId, tuple[int, int]]   # node -> (q, r) hex axial
    edges: dict[NodeId, frozenset[NodeId]]  # adjacency
    node_types: dict[NodeId, NodeType]
    home_assignments: dict[NodeId, PlayerId]  # node -> player whose home it is
    # Bundle 5b (C3): per-supply score yield. Only entries with non-default
    # value (≠ 1) are stored; supply_value(n) returns 1 when absent. Default
    # generation picks a small fraction of non-HOME SUPPLY nodes and marks
    # them as value=2 (see config.high_value_supply_fraction). HOME nodes
    # retain value 1; high-value heterogeneity is for the contested
    # frontier supplies, not structural homes.
    supply_values: dict[NodeId, int] = field(default_factory=dict)

    @property
    def nodes(self) -> list[NodeId]:
        return sorted(self.coords.keys())

    def neighbors(self, n: NodeId) -> frozenset[NodeId]:
        return self.edges.get(n, frozenset())

    def is_adjacent(self, a: NodeId, b: NodeId) -> bool:
        return b in self.edges.get(a, frozenset())

    def is_supply(self, n: NodeId) -> bool:
        return self.node_types[n] in (NodeType.SUPPLY, NodeType.HOME)

    def is_passable(self, n: NodeId) -> bool:
        """True iff a unit can occupy/move-through this node.

        MOUNTAIN and WATER are impassable; PLAIN, SUPPLY, and HOME are passable.
        """
        return self.node_types[n] not in (NodeType.MOUNTAIN, NodeType.WATER)

    def supply_value(self, n: NodeId) -> int:
        """Bundle 5b (C3): per-turn score yield for owning this supply.
        Returns 1 by default; overridden to 2 (or higher in future) for the
        small fraction of non-home supplies marked as high-value at mapgen.
        Non-supply nodes also return 1 for safety; callers must gate via
        is_supply() before incorporating into scoring.
        """
        return self.supply_values.get(n, 1)


@dataclass
class GameConfig:
    num_players: int = 4
    max_turns: int = 25
    fog_radius: int = 1
    build_period: int = 3  # build phase every N turns
    # Consensus mutual-ALLY turns required for the détente collective-victory.
    # `None` (the default) scales the threshold with table size: `4 + num_players`,
    # giving roomier negotiation as ordered-pair count grows. `0` disables the
    # détente condition entirely; any other positive int is honored verbatim.
    detente_threshold: int | None = None
    # Score penalty per turn for players whose canon contains no Move or
    # SupportMove (i.e. all-Hold turns). 0 disables. Default disabled (0.0)
    # because under Bundle 2's hold-or-dislodge ownership rule, a single-unit
    # player who Holds to lock in a freshly-walked-into supply was paying
    # this cost to do exactly the strategically-correct thing — a perverse
    # incentive. Callers who want the v1 behavior can still pass
    # `stagnation_cost=1.0` explicitly.
    stagnation_cost: float = 0.0
    # Phase 0a (F3): raised from 500. Playtest finding: a single 500-char
    # message/round throttled negotiation (one player's whole coordination
    # message got silently dropped mid-game for exceeding it).
    chat_char_cap: int = 2000  # chat message body length cap
    round_timer_seconds: float = 60.0  # default for live play; drivers
                                       # override to 0 in training/turn-based modes
    archetype: Archetype = Archetype.UNIFORM
    map_radius: int = 3
    seed: int | None = None
    # --- combat incentives ---
    # Direct score reward per dislodgement: combat_reward to the attacker;
    # supporter_combat_reward to each uncut supporter of the dislodging attack.
    combat_reward: float = 1.0
    supporter_combat_reward: float = 1.0
    # --- Primitive B: reciprocation standing (2026-07-02 reciprocity model) ---
    # Rolling window (in turns) over which ally-Support given/received is
    # counted for reciprocation standing. recip(P) = given(P)/max(1,received(P)).
    reciprocation_window: int = 4
    # The alliance-capture bonus (resolve.py 8b) is withheld from a MOVER whose
    # reciprocation standing is below this floor while it has taken ally support
    # (received>0). A free-rider (given 0, received>0 -> recip 0) is denied; a
    # mover that never took support (received==0) is not free-riding and keeps
    # the bonus. Supporters always earn their side. Replaces the deleted
    # aid-spend gate (`alliance_requires_aid`/`_is_aided`).
    reciprocation_floor: float = 0.5
    # Détente streak resets on any BetrayalObservation observed this turn.
    # Bug fix for v1's "détente by lying" (a table of all-Sycophant declares
    # ALLY but secretly racing for supplies, closing peaceful collective
    # victory while breaking publicly declared intents).
    betrayal_resets_detente: bool = True
    # --- betrayal teeth (harm-typed, 2026-07-02 reciprocity model) ---
    # Score penalty deducted from the BREACHER at finalize for each HARM-TYPED
    # broken declared Intent / broken accepted Pact term this turn (only fires
    # when the divergence harmed a committed ally — Primitive A). Counted once
    # per harmful broken commitment, not once per observer. 0 disables the
    # penalty (reputation-only for that commitment type).
    #
    # Both default to 1.0. The design (§4) recommends the pact fine "start ≈
    # 1.0" as a small, revisitable knob; harm-typing removes the pro-social
    # confound that previously made the flat fine over-penalize cooperators, so
    # a modest, equal value on each is the natural baseline.
    intent_breach_penalty: float = 1.0
    pact_breach_penalty: float = 1.0
    # --- Bundle 5b (C3): variable supply values ---
    # Fraction of non-HOME SUPPLY nodes marked as high-value (worth +2/turn
    # instead of +1). 0.0 reverts to v1 uniform-value scoring. Default 0.20
    # — sweep evidence (see spec §7) shows the mechanic is invisible at 5%
    # but ValueGreedy breaks above GreedyHold (+1.04) at 20%, with modest
    # variance increase and a small Coop-DC differentiation bonus
    # (+2.02 → +3.06). Generation is deterministic from config.seed.
    high_value_supply_fraction: float = 0.20
    # Score yield assigned to high-value supplies. First-pass keeps it at 2
    # (one step up from the default 1). Future bundles may add a tier of
    # value=3 supplies on a smaller fraction.
    high_value_supply_yield: int = 2
    # --- retreats (2026-07-02 lethality-softening pass) ---
    # When True, a dislodged unit RETREATS to its home node instead of being
    # eliminated (v1 default). The tempo cost is losing its forward position
    # (it is teleported home, not to where it was pushed). Fallbacks when the
    # home is unavailable are resolved in resolve.py:
    #   - home captured by an enemy (no longer owned by the player) -> eliminate
    #   - home owned but occupied (by any unit) -> nearest empty owned passable
    #     node (BFS from home, tie-break lowest node id); if none -> eliminate
    # Default OFF so v1 tests/behavior are unchanged and the retreats-on/off
    # sweep can A/B cleanly. See docs for the falsifiable-bar rationale.
    retreats_enabled: bool = False
    # Deprecated alias for detente_threshold; kept for one minor version.
    peace_threshold: int | None = None

    def __post_init__(self) -> None:
        # If peace_threshold was explicitly passed (deprecated), it overrides
        # detente_threshold. Otherwise resolve the table-size-scaled default.
        if self.peace_threshold is not None:
            self.detente_threshold = self.peace_threshold
        elif self.detente_threshold is None:
            # Default: scale with table size so 4-player has more headroom
            # than 2-player. (Sonnet playtest feedback.) Phase 0a (F3):
            # clamp below max_turns so the auto-default is always reachable
            # — a short max_turns (e.g. 7) previously left the scaled
            # default (e.g. 8) unreachable, silently disabling détente.
            # Only the auto-default is clamped; an explicit
            # detente_threshold/peace_threshold is the caller's choice and
            # is never overridden here.
            self.detente_threshold = min(
                4 + self.num_players, max(1, self.max_turns - 1)
            )
        # Always reflect the resolved value back into peace_threshold for any
        # legacy reader that reads it directly from a GameConfig instance.
        self.peace_threshold = self.detente_threshold
        # Coerce string archetype (e.g. from JSON wire) to the enum value so
        # generate_map's dispatch by-equality works regardless of input type.
        if isinstance(self.archetype, str):
            self.archetype = Archetype(self.archetype)


@dataclass
class GameState:
    """Full (omniscient) game state. Use fog filtering for per-player views."""
    turn: int
    map: Map
    units: dict[UnitId, Unit]
    ownership: dict[NodeId, PlayerId | None]
    scores: dict[PlayerId, float]
    eliminated: set[PlayerId]
    next_unit_id: UnitId
    config: GameConfig
    log: list[str] = field(default_factory=list)

    # New Press v0 fields:
    mutual_ally_streak: int = 0
    press_history: list[dict[PlayerId, "Press"]] = field(default_factory=list)
    chat_history: list[list["ChatMessage"]] = field(default_factory=list)
    betrayals: dict[PlayerId, list["BetrayalObservation"]] = field(
        default_factory=dict
    )
    phase: "Phase" = field(default_factory=lambda: Phase.NEGOTIATION)
    round_chat: list["ChatMessage"] = field(default_factory=list)
    round_press_pending: dict[PlayerId, "Press"] = field(default_factory=dict)
    round_done: set[PlayerId] = field(default_factory=set)
    chat_done: set[PlayerId] = field(default_factory=set)

    # Reactive-support lapses for the *current* round, populated by
    # _resolve_orders. Cleared by finalize_round each round. UI/agent
    # consumers read this between turns to surface "your support didn't
    # land because X".
    support_lapses: list["SupportLapsed"] = field(default_factory=list)

    # Round-scoped event channels for live-press observers. Cleared by
    # finalize_round each round.
    intent_revisions: list["IntentRevised"] = field(default_factory=list)
    done_clears: list["DoneCleared"] = field(default_factory=list)

    # --- Primitive B: rolling reciprocation window ---
    # Last `config.reciprocation_window` rounds of ally-Support activity (see
    # SupportRound). Public (whole-table visible, like reputation); carried
    # forward + trimmed by finalize_round. Drives the alliance-bonus re-gate.
    support_ledger: list["SupportRound"] = field(default_factory=list)

    # Phase 0a (F1): per-player score delta from the most recently resolved
    # turn (new cumulative score - old cumulative score), covering tiered
    # supply income, alliance/combat bonuses, and stagnation cost alike.
    # Empty before any turn resolves. Lets prompt renderers show "you scored
    # +N last turn" without re-deriving scoring logic that could drift from
    # resolve.py's actual computation.
    last_turn_score_delta: dict[PlayerId, float] = field(default_factory=dict)

    # --- Phase 0b (F5): binding joint intents ("Pacts") ---
    # Live pacts (PROPOSED + ACCEPTED). NOT round scratch: they persist across
    # rounds under the lifecycle in press.finalize_round (accepted pacts are
    # checked + consumed each resolution; un-accepted proposals expire after
    # one round). Both parties see their own via fog.
    pacts: list["Pact"] = field(default_factory=list)
    # Monotonic id source for pacts (deterministic; no RNG/clock).
    next_pact_id: int = 0
    # Cumulative pact-breach ledger keyed by the OBSERVING (non-breaching)
    # party, mirroring `betrayals`. Never decays; public to the two parties.
    pact_breaches: dict[PlayerId, list["PactBreach"]] = field(
        default_factory=dict
    )

    # --- Phase 0b (F6): betrayal teeth ---
    # Cumulative PUBLIC breach tally by breacher (see ReputationTally). Unlike
    # betrayals/pact_breaches (keyed by observer), this is visible to every
    # player regardless of who a breach was directed at -- the social cost
    # that lets the whole table refuse to ally with a proven betrayer, not
    # just their direct victims. Never decays.
    reputation: dict[PlayerId, "ReputationTally"] = field(default_factory=dict)

    def units_of(self, player: PlayerId) -> list[Unit]:
        return [u for u in self.units.values() if u.owner == player]

    def unit_at(self, node: NodeId) -> Unit | None:
        for u in self.units.values():
            if u.location == node:
                return u
        return None

    def supply_count(self, player: PlayerId) -> int:
        return sum(
            1
            for n, t in self.map.node_types.items()
            if t in (NodeType.SUPPLY, NodeType.HOME)
            and self.ownership.get(n) == player
        )

    def is_active(self, player: PlayerId) -> bool:
        return player not in self.eliminated

    def is_terminal(self) -> bool:
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        if len(active) <= 1:
            return True
        if (self.config.detente_threshold > 0
                and self.mutual_ally_streak >= self.config.detente_threshold):
            return True
        if self.turn >= self.config.max_turns:
            return True
        return False

    @property
    def detente_reached(self) -> bool:
        """True iff the game ended via the peaceful collective-victory condition.

        Requires multiple surviving players AND the consensus mutual-ALLY streak
        has reached the threshold; a last-standing victory is not détente.
        """
        if self.config.detente_threshold <= 0:
            return False
        if self.mutual_ally_streak < self.config.detente_threshold:
            return False
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        return len(active) > 1

    @property
    def winner(self) -> PlayerId | None:
        """The single winner, or None if non-terminal, tied, or détente (collective).

        Resolution priority:
        1. Only one active player: last-standing wins.
        2. Détente reached: returns None (use `winners()` for the list).
        3. Otherwise: highest cumulative score; tie at top → None.
        """
        if not self.is_terminal():
            return None
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        if len(active) == 1:
            return active[0]
        if self.detente_reached:
            return None
        if not self.scores:
            return None
        max_score = max(self.scores.values())
        top = [p for p, s in self.scores.items() if s == max_score]
        return top[0] if len(top) == 1 else None

    def winners(self) -> list[PlayerId]:
        """All winning players. For solo wins, single element. For détente,
        all surviving players. Empty for non-terminal or full ties.
        """
        if not self.is_terminal():
            return []
        active = sorted(p for p in range(self.config.num_players) if p not in self.eliminated)
        if len(active) == 1:
            return active
        if self.detente_reached:
            return active
        w = self.winner
        return [w] if w is not None else []

    def final_scores(self) -> list[tuple[PlayerId, float]]:
        """Players paired with their cumulative scores, sorted descending."""
        return sorted(self.scores.items(), key=lambda kv: -kv[1])

    # --- Primitive B: reciprocation standing helpers ---

    def reciprocation_given(self, player: PlayerId) -> int:
        """# turns in the rolling window where `player` gave >=1 uncut
        cross-player Support to a standing ALLY."""
        return sum(1 for r in self.support_ledger if player in r.gave)

    def reciprocation_received(self, player: PlayerId) -> int:
        """# turns in the rolling window where an ally supported `player`."""
        return sum(1 for r in self.support_ledger if player in r.received)

    def reciprocation_standing(self, player: PlayerId) -> float:
        """given / max(1, received). A free-rider sits near 0; a genuine
        cooperator near 1."""
        given = self.reciprocation_given(player)
        received = self.reciprocation_received(player)
        return given / max(1, received)

    def freeride_debt(self, player: PlayerId) -> int:
        """max(0, received - given): a one-glance takes-without-giving score."""
        return max(
            0, self.reciprocation_received(player) - self.reciprocation_given(player)
        )
