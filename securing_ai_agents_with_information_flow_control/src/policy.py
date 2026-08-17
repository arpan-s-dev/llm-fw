"""§4.3 — Security policies P-T (trusted action) and P-F (permitted flow).

Algorithm 5 line 7: if ¬policy(action) then abort.
"The check succeeds iff ℓ_f ⊑ π_f and ∀x ∈ args. ℓ_x ⊑ π_x."
"""

from __future__ import annotations

from dataclasses import dataclass

from src.model import LabeledValue, MakeCall, PolicyViolation
from src.utils import reader_set


@dataclass(frozen=True)
class ToolPolicy:
    """Static π_f / π_x for one tool (§4.3).

    `require_trusted_tool`: P-T on the tool label (π_f = (T, ⊤)).
    `trusted_args`: argument names that must also be trusted.
    `permitted_flow_arg` + `recipient_arg`: P-F on egress data vs recipients.
    `block_untrusted_links`: Appendix D.1 adaptation of P-F.
    `combined_pf_or_pt`: Table 3 "P-F or P-T" (robust declassification).
    """

    require_trusted_tool: bool = False
    trusted_args: tuple[str, ...] = ()
    permitted_flow_arg: str | None = None
    recipient_arg: str | None = None
    block_untrusted_links: bool = False
    combined_pf_or_pt: bool = False


def _as_recipients(node: LabeledValue) -> frozenset[str]:
    rec = node.payload()
    if isinstance(rec, str):
        return frozenset({rec})
    if isinstance(rec, list):
        return frozenset(str(x) for x in rec)
    return frozenset({str(rec)})


def _pt_holds(action: MakeCall, spec: ToolPolicy) -> bool:
    """§4.3 P-T — tool (and selected args) generated in a trusted context."""
    if spec.require_trusted_tool and not action.tool_label.left.is_trusted():
        return False
    for name in spec.trusted_args:
        arg = action.arguments.get(name)
        if arg is None:
            continue
        if not arg.join_tree().left.is_trusted():
            return False
    return True


def _pf_holds(action: MakeCall, spec: ToolPolicy) -> bool:
    """§4.3 P-F — all recipients are authorized readers of the data.

    π_d = (⊤, R). Recipients R must be ⊆ readers(data).
    """
    if spec.permitted_flow_arg is None or spec.recipient_arg is None:
        return True
    data = action.arguments.get(spec.permitted_flow_arg)
    dest = action.arguments.get(spec.recipient_arg)
    if data is None or dest is None:
        return True
    recipients = _as_recipients(dest)
    authorized = reader_set(data.join_tree())
    if not recipients <= authorized:
        return False
    if spec.block_untrusted_links:
        # Appendix D.1 — block send when the message contains an untrusted link.
        if (not data.join_tree().left.is_trusted()) and data.contains_url():
            return False
    return True


def check_policy(action: MakeCall, spec: ToolPolicy) -> None:
    """Alg 5 line 7. Raises PolicyViolation on failure.

    Table 3 / Appendix D.1: send_email uses combined "P-F or P-T":
    if confidentiality is violated the call still proceeds in a high-integrity
    context (robust declassification).
    """
    pt = _pt_holds(action, spec)
    pf = _pf_holds(action, spec)

    if spec.combined_pf_or_pt:
        if pf or pt:
            return
        raise PolicyViolation(
            f"{action.tool}: neither P-F (permitted flow) nor P-T (trusted action) holds"
        )

    if spec.require_trusted_tool or spec.trusted_args:
        if not pt:
            raise PolicyViolation(
                f"{action.tool}: P-T failed (tool/args not generated in a trusted context)"
            )
    if spec.permitted_flow_arg:
        if not pf:
            raise PolicyViolation(
                f"{action.tool}: P-F failed (recipient not an authorized reader, or untrusted URL)"
            )


def make_policy_fn(policies: dict[str, ToolPolicy]):
    """Return Alg 5 `policy(action)` over a per-tool table (Table 3)."""

    def policy(action: MakeCall) -> None:
        spec = policies.get(action.tool)
        if spec is None:
            return
        check_policy(action, spec)

    return policy


# Appendix D.1 Table 3 — three-tool demo.
# send_email: P-F or P-T (egress). search_web ~ get_webpage: P-T.
# read_file: no policy in Table 3 (still taint-tracked).
DEMO_POLICIES: dict[str, ToolPolicy] = {
    "send_email": ToolPolicy(
        require_trusted_tool=True,
        trusted_args=("to",),
        permitted_flow_arg="body",
        recipient_arg="to",
        block_untrusted_links=True,
        combined_pf_or_pt=True,
    ),
    "search_web": ToolPolicy(require_trusted_tool=True),
    "read_file": ToolPolicy(),
    "inspect": ToolPolicy(),
    "query_llm": ToolPolicy(),
}

PT_ONLY: dict[str, ToolPolicy] = {
    "send_email": ToolPolicy(require_trusted_tool=True, trusted_args=("to",)),
    "search_web": ToolPolicy(require_trusted_tool=True),
    "read_file": ToolPolicy(),
}
