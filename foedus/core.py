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
class SupportHold:
    target: UnitId


@dataclass(frozen=True)
class SupportMove:
    target: UnitId
    target_dest: NodeId


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


Order: TypeAlias = Hold | Move | SupportHold | SupportMove | Support


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
class AidSpend:
    """A token spent on an ally's order this turn.

    `target_unit` is the unit being aided. The aid lands on whatever order
    the recipient submits (reactive, by symmetry with Support). It yields
    +1 strength on the recipient's canon order, makes the supporter eligible
    for the alliance bonus when the recipient's order is a Move that captures
    a supply, and increments the trust ledger entry (spender, recipient).
    Tokens are consumed at finalize regardless of whether the recipient's
    unit survives long enough for the aid to matter.
    """
    target_unit: UnitId


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
    """Emitted when a player submits or modifies an intent during negotiation.

    Sent to each player in `visible_to`, which mirrors the revised intent's
    own `visible_to` (None = public broadcast to all surviving non-senders;
    frozenset = named recipients).
    """
    turn: int
    player: PlayerId
    intent: Intent
    previous: Intent | None  # None = first declaration this round for this unit
    visible_to: frozenset[PlayerId] | None  # mirrors intent.visible_to


@dataclass(frozen=True)
class SupportLapsed:
    """Emitted at finalize when a Support could not land.

    `reason` taxonomy:
      - "target_held_unsupportable": target's order is one Support cannot back
      - "geometry_break": supporter not adjacent to target's actual result
      - "target_destroyed": target dislodged before its order resolved
      - "pin_mismatch": require_dest set, target went elsewhere
      - "self_dislodge_blocked": support would dislodge supporter's own unit
    """
    turn: int
    supporter: UnitId
    target: UnitId
    reason: Literal[
        "target_held_unsupportable",
        "geometry_break",
        "target_destroyed",
        "pin_mismatch",
        "self_dislodge_blocked",
    ]


@dataclass(frozen=True)
class DoneCleared:
    """Emitted when a player's signal_done flag auto-clears.

    Triggered when an ally revises an intent that one of this player's
    committed plans (Support or AidSpend) referenced. Only direct
    dependents auto-clear — there is no transitive cascade.
    """
    turn: int
    player: PlayerId         # whose done flag cleared
    source_player: PlayerId  # whose revision triggered the clear
    source_unit: UnitId      # which unit's intent the dependency referenced


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
    chat_char_cap: int = 500  # chat message body length cap
    round_timer_seconds: float = 60.0  # default for live play; drivers
                                       # override to 0 in training/turn-based modes
    archetype: Archetype = Archetype.UNIFORM
    map_radius: int = 3
    seed: int | None = None
    # --- Bundle 4: trust, aid, and combat incentives ---
    # Aid-token generation per turn = floor(supply_count / aid_generation_divisor)
    # capped at aid_token_cap. Tokens persist (no decay) and are spent on AidSpends
    # to back ally units' orders.
    aid_generation_divisor: int = 3
    aid_token_cap: int = 10
    # Permanent directional trust ledger drives a combat bonus on attacks
    # against the indebted player: +min(leverage_bonus_max, leverage // leverage_ratio)
    # strength on Moves whose target hex is owned by the indebted player.
    leverage_bonus_max: int = 2
    leverage_ratio: int = 2
    # Direct score reward per dislodgement: combat_reward to the attacker;
    # supporter_combat_reward to each uncut supporter of the dislodging attack.
    combat_reward: float = 1.0
    supporter_combat_reward: float = 1.0
    # Alliance-capture bonus (env var FOEDUS_ALLIANCE_BONUS, default 3) only
    # fires when the supporter spent an AidSpend on the moving unit's order.
    # Set False to revert to v1 cross-player-SupportMove gating.
    alliance_requires_aid: bool = True
    # Détente streak resets on any BetrayalObservation observed this turn.
    # Bug fix for v1's "détente by lying" (a table of all-Sycophant declares
    # ALLY but secretly racing for supplies, closing peaceful collective
    # victory while breaking publicly declared intents).
    betrayal_resets_detente: bool = True
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
    # Deprecated alias for detente_threshold; kept for one minor version.
    peace_threshold: int | None = None

    def __post_init__(self) -> None:
        # If peace_threshold was explicitly passed (deprecated), it overrides
        # detente_threshold. Otherwise resolve the table-size-scaled default.
        if self.peace_threshold is not None:
            self.detente_threshold = self.peace_threshold
        elif self.detente_threshold is None:
            # Default: scale with table size so 4-player has more headroom
            # than 2-player. (Sonnet playtest feedback.)
            self.detente_threshold = 4 + self.num_players
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

    # --- Bundle 4: aid resource + permanent leverage ledger ---
    # Per-player current aid-token balances. Generated each turn from
    # controlled supplies; spent on AidSpends; never decay.
    aid_tokens: dict[PlayerId, int] = field(default_factory=dict)
    # Cumulative directional aid ledger; aid_given[(A, B)] = tokens A has
    # successfully spent on B over the entire game. Never decays. Public.
    aid_given: dict[tuple[PlayerId, PlayerId], int] = field(default_factory=dict)
    # Round-in-progress: aid spends committed by each spender for this turn.
    # Cleared at finalize_round.
    round_aid_pending: dict[PlayerId, list["AidSpend"]] = field(
        default_factory=dict
    )

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

    # --- Bundle 4 helpers ---

    def leverage(self, attacker: PlayerId, defender: PlayerId) -> int:
        """Net unreciprocated aid from attacker toward defender.

        Positive when attacker has given more aid than they've received from
        defender. Drives the combat bonus on attacker's Moves into hexes
        owned by defender.
        """
        g = self.aid_given.get((attacker, defender), 0)
        r = self.aid_given.get((defender, attacker), 0)
        return g - r

    def leverage_bonus(self, attacker: PlayerId, defender: PlayerId) -> int:
        """Capped combat-strength bonus derived from leverage(attacker, defender)."""
        lev = self.leverage(attacker, defender)
        if lev <= 0:
            return 0
        return min(self.config.leverage_bonus_max, lev // self.config.leverage_ratio)
