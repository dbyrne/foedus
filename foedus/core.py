"""Core types and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

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


Order: TypeAlias = Hold | Move | SupportHold | SupportMove


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


@dataclass
class GameConfig:
    num_players: int = 4
    max_turns: int = 25
    fog_radius: int = 1
    build_period: int = 3  # build phase every N turns
    detente_threshold: int = 5  # consensus mutual-ALLY turns required for
                                # the détente collective-victory; 0 disables.
    stagnation_cost: float = 1.0  # score penalty for passive turns; 0 disables
    chat_char_cap: int = 500  # chat message body length cap
    round_timer_seconds: float = 60.0  # default for live play; drivers
                                       # override to 0 in training/turn-based modes
    archetype: Archetype = Archetype.UNIFORM
    map_radius: int = 3
    seed: int | None = None
    # Deprecated alias for detente_threshold; kept for one minor version.
    peace_threshold: int | None = None

    def __post_init__(self) -> None:
        # If peace_threshold was explicitly passed (deprecated), it overrides
        # detente_threshold. Otherwise leave detente_threshold alone.
        if self.peace_threshold is not None:
            self.detente_threshold = self.peace_threshold
        # Always reflect the current value back into peace_threshold for any
        # legacy reader that reads it directly from a GameConfig instance.
        self.peace_threshold = self.detente_threshold


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
