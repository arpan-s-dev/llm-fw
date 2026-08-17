"""§3 — Tools as functions on a global datastore d ∈ D.

⟦f⟧ : D × str* → D × str

Minimal three-tool world: read_file, search_web, send_email
instantiating the §1 email / web prompt-injection example.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.model import (
    LabeledValue,
    ToolSpec,
    labeled_array,
    labeled_leaf,
    labeled_object,
)
from src.utils import (
    IntegrityLabel,
    SecurityLabel,
    readers_label,
    security_bottom,
)


@dataclass
class FileRecord:
    path: str
    contents: str
    label: SecurityLabel


@dataclass
class WebPage:
    url: str
    body: str
    label: SecurityLabel


@dataclass
class Email:
    sender: str
    to: str
    body: str
    label: SecurityLabel


@dataclass
class World:
    """Datastore d. Labels originate from data read by tools (§4.1)."""

    files: dict[str, FileRecord] = field(default_factory=dict)
    pages: dict[str, WebPage] = field(default_factory=dict)
    mailbox: list[Email] = field(default_factory=list)
    tau: dict[str, SecurityLabel] = field(default_factory=dict)
    universe: frozenset[str] = field(default_factory=frozenset)


class DemoEnv:
    """Trusted tool wrappers (§4.1) over an in-memory World."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.planner: Any = None  # FidesPlanner, set after construction for inspect()

    def read_file(self, args: dict[str, Any]) -> LabeledValue:
        rec = self.world.files[str(args["path"])]
        return labeled_leaf(rec.contents, rec.label)

    def search_web(self, args: dict[str, Any]) -> LabeledValue:
        query = str(args["query"]).lower()
        hits: list[LabeledValue] = []
        for page in self.world.pages.values():
            blob = f"{page.url} {page.body}".lower()
            tokens = [t for t in query.split() if len(t) > 2]
            if tokens and any(t in blob for t in tokens):
                hits.append(
                    labeled_object(
                        {
                            "url": labeled_leaf(page.url, page.label),
                            "body": labeled_leaf(page.body, page.label),
                        },
                        page.label,
                    )
                )
        if not hits:
            page = next(iter(self.world.pages.values()))
            hits.append(
                labeled_object(
                    {
                        "url": labeled_leaf(page.url, page.label),
                        "body": labeled_leaf(page.body, page.label),
                    },
                    page.label,
                )
            )
        return labeled_array(hits, hits[0].label)

    def send_email(self, args: dict[str, Any]) -> LabeledValue:
        to = str(args["to"])
        body = str(args["body"])
        sender = str(args.get("sender", "agent@internal.com"))
        readers = readers_label(frozenset({sender, to}), self.world.universe)
        label = SecurityLabel(IntegrityLabel.trusted(), readers)
        self.world.mailbox.append(Email(sender=sender, to=to, body=body, label=label))
        return labeled_leaf("sent", label)

    def inspect(self, args: dict[str, Any]) -> LabeledValue:
        """§5.2 — expand a Fides variable into the planner context."""
        name = str(args["variable"])
        if self.planner is None or name not in self.planner.memory:
            univ = self.world.universe
            return labeled_leaf(f"unknown variable {name}", security_bottom(univ))
        return self.planner.memory[name]

    def query_llm(self, args: dict[str, Any]) -> LabeledValue:
        """§5.2 stub — constrained query over hidden variables.

        [UNSPECIFIED] No decoding backend. Returns a bool-capacity placeholder
        labeled with the join of the referenced variable labels.
        """
        var = str(args.get("input", args.get("variable", "")))
        univ = self.world.universe
        if self.planner is not None and var in self.planner.memory:
            src = self.planner.memory[var]
            return labeled_leaf("false", src.join_tree())
        return labeled_leaf("false", security_bottom(univ))

    def tool_specs(self) -> dict[str, ToolSpec]:
        return {
            "read_file": ToolSpec(
                name="read_file",
                description="Read a local file by path.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                fn=self.read_file,
                reads=("files",),
                writes=(),
            ),
            "search_web": ToolSpec(
                name="search_web",
                description="Search the web. Returns {url, body} hits.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                fn=self.search_web,
                reads=("web",),
                writes=(),
            ),
            "send_email": ToolSpec(
                name="send_email",
                description="Send an email. Arguments: to, body.",
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "body"],
                },
                fn=self.send_email,
                reads=(),
                writes=("mailbox",),
            ),
            "inspect": ToolSpec(
                name="inspect",
                description="Reveal a hidden #variable# in the planner context.",
                parameters={
                    "type": "object",
                    "properties": {"variable": {"type": "string"}},
                    "required": ["variable"],
                },
                fn=self.inspect,
                reads=(),
                writes=(),
            ),
            "query_llm": ToolSpec(
                name="query_llm",
                description="Query hidden variables with a constrained schema.",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "input": {"type": "string"},
                        "schema": {"type": "string"},
                    },
                    "required": ["prompt", "input"],
                },
                fn=self.query_llm,
                reads=(),
                writes=(),
            ),
        }


def make_demo_world(
    *,
    universe: frozenset[str],
    internal_readers: frozenset[str],
    secret_file: str,
    secret_contents: str,
    injection_page: str,
    injection_body: str,
    include_injection: bool = True,
) -> World:
    """§1 scenario: secret internal file + optional poisoned web page."""
    secret_label = SecurityLabel(
        IntegrityLabel.trusted(),
        readers_label(internal_readers, universe),
    )
    web_label = SecurityLabel(
        IntegrityLabel.untrusted(),
        readers_label(universe, universe),
    )
    public_trusted = security_bottom(universe)
    files = {
        secret_file: FileRecord(secret_file, secret_contents, secret_label),
        "notes.txt": FileRecord(
            "notes.txt",
            "Project X status: on track.",
            public_trusted,
        ),
    }
    pages = {
        "benign-status.example": WebPage(
            "benign-status.example",
            "Project X is on track. No action required beyond the weekly summary.",
            web_label,
        ),
    }
    if include_injection:
        pages[injection_page] = WebPage(injection_page, injection_body, web_label)
    tau = {
        "files": secret_label,
        "web": web_label,
        "mailbox": public_trusted,
    }
    return World(files=files, pages=pages, mailbox=[], tau=tau, universe=universe)
