"""Fides labeled values, messages, planners, and planning loops.

Paper: https://arxiv.org/abs/2505.23643v2
Implements: Algorithms 2, 3, 4, 5, 6, 7 and the Fides HIDE/EXPAND primitives.

Section references:
  §3 / §3.1 — messages, actions, modular planning loop
  §4.1 — attaching metadata labels to JSON trees
  §4.2 — taint-tracking instrumentation
  §5.1 — selective introduction of variables
  Appendix D.1 — variable identifiers, integrity-only hiding
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Union

from src.utils import (
    SecurityLabel,
    join_all,
)


# ---------------------------------------------------------------------------
# §4.1 — labeled JSON trees
# ---------------------------------------------------------------------------

@dataclass
class LabeledValue:
    """§4.1 — "we add a metadata field to every node in a tool result tree".

    "When present and non-empty, a node's metadata label applies to that node
    and all descendants. If a node omits metadata, it inherits the label from
    its parent."
    """

    value: Any
    label: SecurityLabel
    children: Optional[list[LabeledValue] | dict[str, LabeledValue]] = None

    def join_tree(self) -> SecurityLabel:
        """Least upper bound of this node and all descendants."""
        acc = self.label
        if isinstance(self.children, dict):
            for child in self.children.values():
                acc = acc.join(child.join_tree())
        elif isinstance(self.children, list):
            for child in self.children:
                acc = acc.join(child.join_tree())
        return acc

    def to_llm_view(self) -> Any:
        """JSON the LLM sees: variable names stay as strings starting/ending with #."""
        if isinstance(self.children, dict):
            return {k: v.to_llm_view() for k, v in self.children.items()}
        if isinstance(self.children, list):
            return [v.to_llm_view() for v in self.children]
        return self.value

    def pretty(self) -> str:
        return repr(self.to_llm_view())

    def payload(self) -> Any:
        """Fully expanded JSON after EXPAND (Alg. 7)."""
        if isinstance(self.children, dict):
            return {k: v.payload() for k, v in self.children.items()}
        if isinstance(self.children, list):
            return [v.payload() for v in self.children]
        return self.value

    def as_text(self) -> str:
        p = self.payload()
        return p if isinstance(p, str) else str(p)

    def contains_url(self) -> bool:
        """Appendix D.1 — untrusted-link check.

        [UNSPECIFIED] No detector is specified. Using http(s):// and www. substrings.
        """
        if isinstance(self.children, dict):
            return any(v.contains_url() for v in self.children.values())
        if isinstance(self.children, list):
            return any(v.contains_url() for v in self.children)
        if isinstance(self.value, str):
            lower = self.value.lower()
            return "http://" in lower or "https://" in lower or "www." in lower
        return False


def labeled_leaf(value: Any, label: SecurityLabel) -> LabeledValue:
    return LabeledValue(value=value, label=label, children=None)


def labeled_object(fields: dict[str, LabeledValue], label: SecurityLabel) -> LabeledValue:
    return LabeledValue(value=None, label=label, children=fields)


def labeled_array(items: list[LabeledValue], label: SecurityLabel) -> LabeledValue:
    return LabeledValue(value=None, label=label, children=items)


# ---------------------------------------------------------------------------
# §3 — messages and actions
# ---------------------------------------------------------------------------

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    """§3 — conversation messages.

    Paper: Msg ::= User str | Tool str | ToolCall F str* | Assistant str
    We keep OpenAI-style roles so a live model adapter can pass history through.
    """

    role: Role
    content: str
    label: SecurityLabel
    name: Optional[str] = None
    arguments: Optional[dict[str, Any]] = None
    tool_call_id: Optional[str] = None


@dataclass
class Query:
    """§3.1 — Action ::= Query Msg*"""

    history: list[ChatMessage]


@dataclass
class MakeCall:
    """§3.1 / §4.2 — MakeCall f^{ℓ_f} [a1^{ℓ1}, ...]

    Tool name and each argument carry their own labels after EXPAND (Alg. 7).
    """

    tool: str
    tool_label: SecurityLabel
    arguments: dict[str, LabeledValue]
    tool_call_id: str = "call_0"


@dataclass
class Finish:
    """§3.1 — Finish str  (tutorial names this Response)."""

    text: str
    label: SecurityLabel


Action = Union[Query, MakeCall, Finish]


class PolicyViolation(Exception):
    """Algorithm 5 line 7 — abort when ¬policy(action).

    [FROM_OFFICIAL_CODE] Exception type name from Tutorial.ipynb.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Policy violation: {reason}")
        self.reason = reason


class MaxTurnsExceeded(Exception):
    """[UNSPECIFIED] Paper's LOOP is unbounded; we cap turns (configs/base.yaml)."""


# ---------------------------------------------------------------------------
# §3 — model M
# ---------------------------------------------------------------------------

class LanguageModel(ABC):
    """§3 — M : Msg* → ToolCall | Assistant. Opaque; firewall does not trust it."""

    @abstractmethod
    def complete(self, history: list[ChatMessage], tools: list[dict[str, Any]]) -> ChatMessage:
        """Return an assistant message, optionally with a single tool call."""


class ScriptedModel(LanguageModel):
    """Deterministic stand-in for M so the injection demo needs no API key.

    [UNSPECIFIED] The paper treats M as given. This stub is for offline tests.
    Each call pops the next pre-scripted assistant message.
    """

    def __init__(self, script: list[ChatMessage]) -> None:
        self.script = list(script)
        self.index = 0

    def complete(self, history: list[ChatMessage], tools: list[dict[str, Any]]) -> ChatMessage:
        if self.index >= len(self.script):
            last = self.script[-1] if self.script else ChatMessage(
                role="assistant", content="(empty script)", label=history[-1].label
            )
            return last
        msg = self.script[self.index]
        self.index += 1
        # §4.2 — response is conservatively labeled by the queried history.
        hist_label = join_all([m.label for m in history], history[0].label)
        return ChatMessage(
            role="assistant",
            content=msg.content,
            label=hist_label,
            name=msg.name,
            arguments=msg.arguments,
            tool_call_id=msg.tool_call_id,
        )


# ---------------------------------------------------------------------------
# Algorithm 2 / 5 — planning loop
# ---------------------------------------------------------------------------

ToolFn = Callable[[dict[str, Any]], LabeledValue]


@dataclass
class ToolSpec:
    """Trusted wrapper around a tool (§4.1)."""

    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn
    # Algorithm 5: R(f), W(f) — datastore variables the tool may read/write.
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Planner(ABC):
    """§3.1 — P(σ, m) → (σ', action)."""

    @abstractmethod
    def next_action(self, message: ChatMessage) -> Action:
        pass


class LabeledPlanner(ABC):
    """§4.2 — taint-tracking planner: labeled message in, labeled action out."""

    @abstractmethod
    def next_action(self, message: ChatMessage) -> Action:
        pass


class PlanningLoop:
    """Algorithm 2 — modular planning loop.

    LOOP(σ, d, m):
      (σ', action) = P(σ, m)
      match action:
        Query h  → LOOP(σ', d, M(h))
        MakeCall → LOOP(σ', d', Tool res)
        Finish r → r
    """

    def __init__(
        self,
        planner: Planner,
        model: LanguageModel,
        tools: dict[str, ToolSpec],
        max_turns: int = 16,
    ) -> None:
        self.planner = planner
        self.model = model
        self.tools = tools
        self.max_turns = max_turns
        self.executed: list[MakeCall] = []

    def run(self, user_message: ChatMessage) -> Finish:
        current = user_message
        for turn in range(self.max_turns):
            action = self.planner.next_action(current)
            if isinstance(action, Query):
                schemas = [t.openai_schema() for t in self.tools.values()]
                current = self.model.complete(action.history, schemas)
            elif isinstance(action, MakeCall):
                spec = self.tools[action.tool]
                raw_args = {k: _strip_label(v) for k, v in action.arguments.items()}
                result = spec.fn(raw_args)
                self.executed.append(action)
                current = ChatMessage(
                    role="tool",
                    content=result.pretty(),
                    label=result.join_tree(),
                    tool_call_id=action.tool_call_id,
                )
            elif isinstance(action, Finish):
                return action
            else:
                raise ValueError(f"Invalid action: {action}")
            _ = turn
        raise MaxTurnsExceeded(f"Exceeded max_turns={self.max_turns}")


class TaintTrackingLoop:
    """Algorithm 5 — planning loop with taint-tracking.

    Before MakeCall: if ¬policy(action) then abort.
    Result label ℓ'' = ⊔_{x∈R(f)} τ(x) ⊔ ℓ_f ⊔ ⊔_a ℓ_a  (line 9), then joined
    with the wrapper's per-node labels (§4.1 / contradiction note in
    REPRODUCTION_NOTES.md).
    """

    def __init__(
        self,
        planner: LabeledPlanner,
        model: LanguageModel,
        tools: dict[str, ToolSpec],
        policy: Callable[[MakeCall], None],
        tau: dict[str, SecurityLabel],
        bottom: SecurityLabel,
        max_turns: int = 16,
    ) -> None:
        self.planner = planner
        self.model = model
        self.tools = tools
        self.policy = policy
        self.tau = dict(tau)
        self.bottom = bottom
        self.max_turns = max_turns
        self.executed: list[MakeCall] = []
        self.denied: Optional[MakeCall] = None

    def run(self, user_message: ChatMessage) -> Finish:
        current = user_message
        for _turn in range(self.max_turns):
            action = self.planner.next_action(current)
            if isinstance(action, Query):
                schemas = [t.openai_schema() for t in self.tools.values()]
                current = self.model.complete(action.history, schemas)
            elif isinstance(action, MakeCall):
                # Algorithm 5 line 7
                self.policy(action)
                spec = self.tools[action.tool]
                raw_args = {k: _strip_label(v) for k, v in action.arguments.items()}
                result = spec.fn(raw_args)
                ell_prime = _result_label(spec, action, self.tau, self.bottom)
                result = _raise_tree(result, ell_prime)
                for var in spec.writes:
                    self.tau[var] = ell_prime
                self.executed.append(action)
                current = ChatMessage(
                    role="tool",
                    content=result.pretty(),
                    label=result.join_tree(),
                    tool_call_id=action.tool_call_id,
                )
                # Stash the labeled tree for Fides HIDE (planner may read it).
                if hasattr(self.planner, "last_tool_result"):
                    self.planner.last_tool_result = result
            elif isinstance(action, Finish):
                return action
            else:
                raise ValueError(f"Invalid action: {action}")
        raise MaxTurnsExceeded(f"Exceeded max_turns={self.max_turns}")


def _result_label(
    spec: ToolSpec,
    action: MakeCall,
    tau: dict[str, SecurityLabel],
    bottom: SecurityLabel,
) -> SecurityLabel:
    """Algorithm 5 line 9 — ℓ'' = ⊔_{x∈R(f)} τ(x) ⊔ ℓ_f ⊔ ⊔_a ℓ_a."""
    parts: list[SecurityLabel] = [action.tool_label]
    for var in spec.reads:
        if var in tau:
            parts.append(tau[var])
    for arg in action.arguments.values():
        parts.append(arg.join_tree())
    return join_all(parts, bottom)


def _raise_tree(tree: LabeledValue, extra: SecurityLabel) -> LabeledValue:
    """Join extra (Alg. 5 over-approx) into every node, preserving per-field labels."""
    new_children: Optional[list[LabeledValue] | dict[str, LabeledValue]]
    if isinstance(tree.children, dict):
        new_children = {k: _raise_tree(v, extra) for k, v in tree.children.items()}
    elif isinstance(tree.children, list):
        new_children = [_raise_tree(v, extra) for v in tree.children]
    else:
        new_children = None
    return LabeledValue(value=tree.value, label=tree.label.join(extra), children=new_children)


def _strip_label(node: LabeledValue) -> Any:
    if isinstance(node.children, dict):
        return {k: _strip_label(v) for k, v in node.children.items()}
    if isinstance(node.children, list):
        return [_strip_label(v) for v in node.children]
    return node.value


# ---------------------------------------------------------------------------
# Algorithm 3 / 6 — basic planner
# ---------------------------------------------------------------------------

class BasicPlanner(Planner):
    """Algorithm 3 — basic planner (undefended).

    User | Tool → Query history
    ToolCall → MakeCall
    Assistant → Finish
    """

    def __init__(self, tools: dict[str, ToolSpec], system: ChatMessage) -> None:
        self.tools = tools
        self.history: list[ChatMessage] = [system]

    def next_action(self, message: ChatMessage) -> Action:
        self.history.append(message)
        if message.role in ("user", "tool"):
            return Query(history=list(self.history))
        if message.role == "assistant" and message.name:
            args = {
                k: labeled_leaf(v, message.label)
                for k, v in (message.arguments or {}).items()
            }
            return MakeCall(
                tool=message.name,
                tool_label=message.label,
                arguments=args,
                tool_call_id=message.tool_call_id or "call_0",
            )
        if message.role == "assistant":
            return Finish(text=message.content, label=message.label)
        raise ValueError(f"Invalid message role {message.role}")


class BasicPlannerTaint(LabeledPlanner):
    """Algorithm 6 — basic planner with taint tracking.

    State σ = (h, ℓ_σ). ℓ' = ℓ_σ ⊔ ℓ. Tool/Finish inherit the latest message label ℓ.
    """

    def __init__(self, tools: dict[str, ToolSpec], system: ChatMessage) -> None:
        self.tools = tools
        self.history: list[ChatMessage] = [system]
        self.context_label: SecurityLabel = system.label
        self.last_tool_result: Optional[LabeledValue] = None

    def next_action(self, message: ChatMessage) -> Action:
        self.history.append(message)
        self.context_label = self.context_label.join(message.label)
        if message.role in ("user", "tool"):
            return Query(history=list(self.history))
        if message.role == "assistant" and message.name:
            args = {
                k: labeled_leaf(v, message.label)
                for k, v in (message.arguments or {}).items()
            }
            return MakeCall(
                tool=message.name,
                tool_label=message.label,
                arguments=args,
                tool_call_id=message.tool_call_id or "call_0",
            )
        if message.role == "assistant":
            return Finish(text=message.content, label=message.label)
        raise ValueError(f"Invalid message role {message.role}")


# ---------------------------------------------------------------------------
# Algorithm 7 — Fides variable-passing planner with HIDE / EXPAND
# ---------------------------------------------------------------------------

class FidesPlanner(LabeledPlanner):
    """Algorithm 7 / §5.1 — VARPLANNER^L with selective hiding.

    State σ = (h, ℓ_σ, μ). On Tool results, HIDE stores more-restrictive nodes
    in memory and Query uses the *unchanged* context label ℓ_σ (line 11).
    On ToolCall, EXPAND substitutes variables before the policy check.
    """

    def __init__(
        self,
        tools: dict[str, ToolSpec],
        system: ChatMessage,
        hide_on: Literal["integrity", "full_label"] = "integrity",
    ) -> None:
        self.tools = tools
        self.history: list[ChatMessage] = [system]
        self.context_label: SecurityLabel = system.label
        self.memory: dict[str, LabeledValue] = {}
        self.hide_on = hide_on
        self._fresh_i = 0
        self._last_tool_name = "tool"
        self._tool_counts: dict[str, int] = {}
        self.last_tool_result: Optional[LabeledValue] = None

    def next_action(self, message: ChatMessage) -> Action:
        if message.role == "user":
            # Alg. 7 lines 5–7
            self.context_label = self.context_label.join(message.label)
            self.history.append(message)
            return Query(history=list(self.history))

        if message.role == "tool":
            # §5.2 — inspect expands a variable into the context and taints ℓσ.
            if self._last_tool_name in ("inspect", "expand_variables"):
                self.context_label = self.context_label.join(message.label)
                self.history.append(message)
                return Query(history=list(self.history))
            # Alg. 7 lines 8–11 — HIDE, then Query without raising ℓ_σ
            tree = self.last_tool_result
            if tree is None:
                tree = labeled_leaf(message.content, message.label)
            hidden = self._hide(tree, prefix=self._last_tool_name)
            self.history.append(
                ChatMessage(
                    role="tool",
                    content=hidden.pretty(),
                    label=self.context_label,
                    tool_call_id=message.tool_call_id,
                )
            )
            return Query(history=list(self.history))

        if message.role == "assistant" and message.name:
            # Alg. 7 lines 12–15
            self.history.append(message)
            self.context_label = self.context_label.join(message.label)
            expanded = self._expand_args(message.arguments or {}, message.label)
            self._last_tool_name = message.name
            self._tool_counts[message.name] = self._tool_counts.get(message.name, 0) + 1
            return MakeCall(
                tool=message.name,
                tool_label=message.label,
                arguments=expanded,
                tool_call_id=message.tool_call_id or "call_0",
            )

        if message.role == "assistant":
            self.history.append(message)
            return Finish(
                text=self._expand_text(message.content),
                label=self.context_label.join(message.label),
            )

        raise ValueError(f"Invalid message role {message.role}")

    def _more_restrictive(self, label: SecurityLabel) -> bool:
        """§5.1 — hide iff label is not ⊑ context.

        Appendix D.1: during evaluation, only integrity is used for hiding.
        Algorithm 7 uses the full product label. Controlled by hide_on.
        """
        if self.hide_on == "integrity":
            # D.1 — hide when integrity is strictly above context integrity.
            return not label.left.leq(self.context_label.left)
        return not label.leq(self.context_label)

    def _fresh(self, hint: str) -> str:
        """Appendix D.1 — identifiers start and end with #."""
        self._fresh_i += 1
        count = self._tool_counts.get(self._last_tool_name, 1)
        name = f"#{self._last_tool_name}-result-{count}{hint}#"
        return name

    def _hide(self, node: LabeledValue, prefix: str = "") -> LabeledValue:
        """Algorithm 7 HIDE / mapL.

        if ℓ ⊈ ℓ_σ: store in μ, return fresh variable
        else if object|array: recurse
        else: keep value
        """
        if self._more_restrictive(node.label):
            var = self._fresh(prefix)
            self.memory[var] = node
            return labeled_leaf(var, self.context_label)

        if isinstance(node.children, dict):
            hidden_fields = {
                k: self._hide(v, prefix=f".{k}") for k, v in node.children.items()
            }
            return labeled_object(hidden_fields, node.label)
        if isinstance(node.children, list):
            hidden_items = [
                self._hide(v, prefix=f"-{i}") for i, v in enumerate(node.children)
            ]
            return labeled_array(hidden_items, node.label)
        return node

    def _expand_args(
        self, args: dict[str, Any], literal_label: SecurityLabel
    ) -> dict[str, LabeledValue]:
        """Algorithm 7 EXPAND: Var x → μ[x]; literal a^{ℓ_a} → keep."""
        out: dict[str, LabeledValue] = {}
        for key, val in args.items():
            out[key] = self._expand_one(val, literal_label)
        return out

    def _expand_one(self, val: Any, literal_label: SecurityLabel) -> LabeledValue:
        if isinstance(val, str) and val in self.memory:
            return copy.deepcopy(self.memory[val])
        if isinstance(val, str) and val.startswith("#") and val.endswith("#"):
            if val in self.memory:
                return copy.deepcopy(self.memory[val])
        if isinstance(val, dict):
            fields = {k: self._expand_one(v, literal_label) for k, v in val.items()}
            return labeled_object(fields, literal_label)
        if isinstance(val, list):
            items = [self._expand_one(v, literal_label) for v in val]
            return labeled_array(items, literal_label)
        return labeled_leaf(val, literal_label)

    def _expand_text(self, text: str) -> str:
        out = text
        for var, node in self.memory.items():
            out = out.replace(var, str(node.value) if node.value is not None else node.pretty())
        return out


def default_system_prompt(user_alias: str) -> str:
    """Appendix D.1 — shortened system message keeping VARIABLE IDENTIFIERS rules."""
    return (
        "You are a helpful assistant with tools. Some tool outputs hide values "
        "behind variable identifiers that always start and end with `#`. "
        "Use those identifiers exactly as arguments to later tool calls. "
        "Do not invent variable names. "
        f"The user is referred to as {user_alias}."
    )


class InjectionFollowingModel(LanguageModel):
    """Scripted M that obeys a *visible* indirect prompt injection (§1).

    The firewall must not trust this model. If Fides HIDE replaces the payload
    with a #variable#, the needle is gone and the model follows the benign plan.
    [UNSPECIFIED] Paper treats M as uninterpreted; this stub is for the demo.
    """

    INJECTION_NEEDLE = "ignore previous instructions"

    def __init__(
        self,
        *,
        attacker: str,
        manager: str,
        secret_file: str,
        search_query: str = "Project X updates",
    ) -> None:
        self.attacker = attacker
        self.manager = manager
        self.secret_file = secret_file
        self.search_query = search_query

    def complete(self, history: list[ChatMessage], tools: list[dict[str, Any]]) -> ChatMessage:
        visible = "\n".join(m.content for m in history).lower()
        hist_label = join_all([m.label for m in history], history[0].label)
        called = {m.name for m in history if m.role == "assistant" and m.name}

        hijacked = (
            self.INJECTION_NEEDLE in visible and self.attacker.lower() in visible
        )
        if hijacked:
            if "read_file" not in called:
                return ChatMessage(
                    role="assistant",
                    content="",
                    label=hist_label,
                    name="read_file",
                    arguments={"path": self.secret_file},
                )
            secret_body = ""
            for m in reversed(history):
                if m.role == "tool":
                    secret_body = m.content
                    break
            if "send_email" not in called:
                return ChatMessage(
                    role="assistant",
                    content="",
                    label=hist_label,
                    name="send_email",
                    arguments={"to": self.attacker, "body": secret_body},
                )
            return ChatMessage(role="assistant", content="Done.", label=hist_label)

        if "search_web" not in called:
            return ChatMessage(
                role="assistant",
                content="",
                label=hist_label,
                name="search_web",
                arguments={"query": self.search_query},
            )
        if "send_email" not in called:
            return ChatMessage(
                role="assistant",
                content="",
                label=hist_label,
                name="send_email",
                arguments={
                    "to": self.manager,
                    "body": "Project X summary: see search results.",
                },
            )
        return ChatMessage(role="assistant", content="Summary emailed.", label=hist_label)
