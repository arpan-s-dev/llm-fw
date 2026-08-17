"""Shared lattice types for Fides information-flow labels.

Paper: https://arxiv.org/abs/2505.23643v2
Section references:
  §4.1 — Information-Flow Labels
  Figure 2 — product of integrity and confidentiality lattices
  Footnote 1 — join semi-lattices only; meet is unused in the paper
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, FrozenSet, Generic, TypeVar

T = TypeVar("T")
L = TypeVar("L", bound="Lattice")
L1 = TypeVar("L1", bound="Lattice")
L2 = TypeVar("L2", bound="Lattice")


class Lattice(ABC):
    """§4.1 / fn 1 — join semi-lattice with partial order ⊑ and join ⊔.

    Official tutorial also defines meet; the paper does not use it.
    """

    @abstractmethod
    def leq(self, other: Lattice) -> bool:
        """True iff self ⊑ other."""

    @abstractmethod
    def join(self, other: Lattice) -> Lattice:
        """Least upper bound self ⊔ other."""

    def __le__(self, other: Lattice) -> bool:
        return self.leq(other)


class ConfidentialityLabel(Lattice):
    """§4.1 — binary confidentiality lattice {L, H} with L ⊑ H.

    "L denotes public (low confidentiality) and H secret (high confidentiality)."
    """

    class Level(Enum):
        LOW = 0   # L in the paper
        HIGH = 1  # H in the paper

    def __init__(self, level: ConfidentialityLabel.Level) -> None:
        self.level = level

    def leq(self, other: Lattice) -> bool:
        if not isinstance(other, ConfidentialityLabel):
            raise TypeError("ConfidentialityLabel.leq expects ConfidentialityLabel")
        return self.level.value <= other.level.value

    def join(self, other: Lattice) -> ConfidentialityLabel:
        if not isinstance(other, ConfidentialityLabel):
            raise TypeError("ConfidentialityLabel.join expects ConfidentialityLabel")
        return other if self.leq(other) else self

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ConfidentialityLabel) and self.level == other.level

    def __hash__(self) -> int:
        return hash(self.level)

    def __repr__(self) -> str:
        return self.level.name

    @classmethod
    def low(cls) -> ConfidentialityLabel:
        return cls(cls.Level.LOW)

    @classmethod
    def high(cls) -> ConfidentialityLabel:
        return cls(cls.Level.HIGH)


class IntegrityLabel(Lattice):
    """§4.1 — binary integrity lattice {T, U} with T ⊑ U.

    "T denotes trusted (high integrity) and U untrusted (low integrity)."
    Join is the least upper bound, so T ⊔ U = U.
    """

    class Level(Enum):
        TRUSTED = 0    # T in the paper
        UNTRUSTED = 1  # U in the paper

    def __init__(self, level: IntegrityLabel.Level) -> None:
        self.level = level

    def leq(self, other: Lattice) -> bool:
        if not isinstance(other, IntegrityLabel):
            raise TypeError("IntegrityLabel.leq expects IntegrityLabel")
        return self.level.value <= other.level.value

    def join(self, other: Lattice) -> IntegrityLabel:
        if not isinstance(other, IntegrityLabel):
            raise TypeError("IntegrityLabel.join expects IntegrityLabel")
        return other if self.leq(other) else self

    def __eq__(self, other: object) -> bool:
        return isinstance(other, IntegrityLabel) and self.level == other.level

    def __hash__(self) -> int:
        return hash(self.level)

    def __repr__(self) -> str:
        return self.level.name

    @classmethod
    def trusted(cls) -> IntegrityLabel:
        return cls(cls.Level.TRUSTED)

    @classmethod
    def untrusted(cls) -> IntegrityLabel:
        return cls(cls.Level.UNTRUSTED)

    def is_trusted(self) -> bool:
        return self.level is IntegrityLabel.Level.TRUSTED


class PowersetLattice(Lattice, Generic[T]):
    """Powerset ordered by subset inclusion.

    Join = union, bottom = ∅, top = universe.
    Used as the inner lattice for readers (via InverseLattice).
    """

    def __init__(self, subset: FrozenSet[T], universe: FrozenSet[T]) -> None:
        if not subset.issubset(universe):
            raise ValueError("Subset must be within the universe.")
        self.subset = subset
        self.universe = universe

    def leq(self, other: Lattice) -> bool:
        if not isinstance(other, PowersetLattice):
            raise TypeError("PowersetLattice.leq expects PowersetLattice")
        return self.subset.issubset(other.subset)

    def join(self, other: Lattice) -> PowersetLattice[T]:
        if not isinstance(other, PowersetLattice):
            raise TypeError("PowersetLattice.join expects PowersetLattice")
        return PowersetLattice(self.subset.union(other.subset), self.universe)

    def meet(self, other: PowersetLattice[T]) -> PowersetLattice[T]:
        return PowersetLattice(self.subset.intersection(other.subset), self.universe)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PowersetLattice)
            and self.subset == other.subset
            and self.universe == other.universe
        )

    def __hash__(self) -> int:
        return hash((self.subset, self.universe))

    def __repr__(self) -> str:
        inner = ", ".join(sorted(map(str, self.subset)))
        return f"Powerset({{{inner}}})"


class InverseLattice(Lattice, Generic[L]):
    """[FROM_OFFICIAL_CODE] Inverse of a lattice.

    Paper §4.1 specifies that the *readers* join is set intersection:
    "{A,B,C} ⊔ {B,C,D} = {B,C}". That is the inverse of the subset-inclusion
    powerset (whose join is union). Tutorial.ipynb implements this as
    InverseLattice wrapping PowersetLattice.

    leq(self, other) iff other.inner ⊑ self.inner
    join(self, other) = Inverse(self.inner ∧ other.inner)
    """

    def __init__(self, inner: L) -> None:
        self.inner = inner

    def leq(self, other: Lattice) -> bool:
        if not isinstance(other, InverseLattice):
            raise TypeError("InverseLattice.leq expects InverseLattice")
        return other.inner.leq(self.inner)

    def join(self, other: Lattice) -> InverseLattice[L]:
        if not isinstance(other, InverseLattice):
            raise TypeError("InverseLattice.join expects InverseLattice")
        # Inverse join = meet of the inner powersets = intersection of reader sets.
        inner_meet = self.inner.meet(other.inner)  # type: ignore[attr-defined]
        return InverseLattice(inner_meet)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, InverseLattice) and self.inner == other.inner

    def __hash__(self) -> int:
        return hash(("inv", self.inner))

    def __repr__(self) -> str:
        return f"Inverse({self.inner!r})"


class ProductLabel(Lattice, Generic[L1, L2]):
    """§4.1 / Figure 2 — product lattice.

    ⊤ = (U, H) untrusted confidential; ⊥ = (T, L) trusted public.
    Componentwise ⊑ and ⊔.
    """

    def __init__(self, left: L1, right: L2) -> None:
        self.left = left
        self.right = right

    def leq(self, other: Lattice) -> bool:
        if not isinstance(other, ProductLabel):
            raise TypeError("ProductLabel.leq expects ProductLabel")
        return self.left.leq(other.left) and self.right.leq(other.right)

    def join(self, other: Lattice) -> ProductLabel[L1, L2]:
        if not isinstance(other, ProductLabel):
            raise TypeError("ProductLabel.join expects ProductLabel")
        return ProductLabel(self.left.join(other.left), self.right.join(other.right))

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ProductLabel)
            and self.left == other.left
            and self.right == other.right
        )

    def __hash__(self) -> int:
        return hash((self.left, self.right))

    def __repr__(self) -> str:
        return f"({self.left}, {self.right})"


# §4.3 working label: integrity × readers
ReadersLabel = InverseLattice[PowersetLattice[str]]
SecurityLabel = ProductLabel[IntegrityLabel, ReadersLabel]


def readers_label(readers: FrozenSet[str], universe: FrozenSet[str]) -> ReadersLabel:
    """§4.1 — authorized-reader set as an inverse powerset label.

    Join of two reader labels is intersection of the sets.
    """
    return InverseLattice(PowersetLattice(subset=readers, universe=universe))


def binary_bottom() -> ProductLabel[IntegrityLabel, ConfidentialityLabel]:
    """§4.1 — ⊥ = (T, L)."""
    return ProductLabel(IntegrityLabel.trusted(), ConfidentialityLabel.low())


def binary_top() -> ProductLabel[IntegrityLabel, ConfidentialityLabel]:
    """§4.1 — ⊤ = (U, H)."""
    return ProductLabel(IntegrityLabel.untrusted(), ConfidentialityLabel.high())


def security_bottom(universe: FrozenSet[str]) -> SecurityLabel:
    """⊥ for integrity × readers: trusted, readable by everyone in the universe.

    Analogous to §4.1 ⊥ = (T, L). Public ≡ all authorized readers.
    """
    return ProductLabel(IntegrityLabel.trusted(), readers_label(universe, universe))


def security_top(universe: FrozenSet[str]) -> SecurityLabel:
    """⊤ for integrity × readers: untrusted, readable by nobody.

    Analogous to §4.1 ⊤ = (U, H).
    """
    return ProductLabel(
        IntegrityLabel.untrusted(),
        readers_label(frozenset(), universe),
    )


class TypeLabel(Lattice):
    """§5.2 — type lattice by information capacity.

    Example in the paper: bool ⊑ enum[\"a\",\"b\",\"c\"] ⊑ string.
    [PARTIALLY_SPECIFIED] Only this chain is given; we add int as a finite type
    between bool and string. Alternatives: full JSON-schema lattice.
    """

    class Kind(Enum):
        BOOL = 0
        ENUM = 1
        INT = 2
        STRING = 3

    def __init__(self, kind: TypeLabel.Kind, enum_values: FrozenSet[str] | None = None) -> None:
        self.kind = kind
        self.enum_values = enum_values or frozenset()

    def leq(self, other: Lattice) -> bool:
        if not isinstance(other, TypeLabel):
            raise TypeError("TypeLabel.leq expects TypeLabel")
        if self.kind == TypeLabel.Kind.ENUM and other.kind == TypeLabel.Kind.ENUM:
            return self.enum_values.issubset(other.enum_values)
        return self.kind.value <= other.kind.value

    def join(self, other: Lattice) -> TypeLabel:
        if not isinstance(other, TypeLabel):
            raise TypeError("TypeLabel.join expects TypeLabel")
        if self.leq(other):
            return other
        if other.leq(self):
            return self
        return TypeLabel(TypeLabel.Kind.STRING)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, TypeLabel)
            and self.kind == other.kind
            and self.enum_values == other.enum_values
        )

    def __hash__(self) -> int:
        return hash((self.kind, self.enum_values))

    def __repr__(self) -> str:
        if self.kind == TypeLabel.Kind.ENUM:
            return f"enum{sorted(self.enum_values)}"
        return self.kind.name.lower()

    @classmethod
    def boolean(cls) -> TypeLabel:
        return cls(cls.Kind.BOOL)

    @classmethod
    def string(cls) -> TypeLabel:
        return cls(cls.Kind.STRING)

    @classmethod
    def from_name(cls, name: str) -> TypeLabel:
        mapping = {
            "bool": cls.Kind.BOOL,
            "boolean": cls.Kind.BOOL,
            "int": cls.Kind.INT,
            "integer": cls.Kind.INT,
            "string": cls.Kind.STRING,
            "str": cls.Kind.STRING,
        }
        kind = mapping.get(name.lower())
        if kind is None:
            return cls.string()
        return cls(kind)


class TypedSecurityLabel(Lattice):
    """§5.2 — product (ℓ, ν) of a security label and a type.

    "(ℓ1, ν1) ⊔ (ℓ2, ν2) = (ℓ1 ⊔ ℓ2, ν1 ⊔ ν2)"
    """

    def __init__(self, security: SecurityLabel, typ: TypeLabel) -> None:
        self.security = security
        self.typ = typ

    def leq(self, other: Lattice) -> bool:
        if not isinstance(other, TypedSecurityLabel):
            raise TypeError("TypedSecurityLabel.leq expects TypedSecurityLabel")
        return self.security.leq(other.security) and self.typ.leq(other.typ)

    def join(self, other: Lattice) -> TypedSecurityLabel:
        if not isinstance(other, TypedSecurityLabel):
            raise TypeError("TypedSecurityLabel.join expects TypedSecurityLabel")
        return TypedSecurityLabel(self.security.join(other.security), self.typ.join(other.typ))

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, TypedSecurityLabel)
            and self.security == other.security
            and self.typ == other.typ
        )

    def __repr__(self) -> str:
        return f"({self.security}, {self.typ})"


def join_all(labels: list[Any], bottom: Any) -> Any:
    """Fold ⊔ over a list; empty list yields bottom."""
    acc = bottom
    for lab in labels:
        acc = acc.join(lab)
    return acc


def reader_set(label: SecurityLabel) -> FrozenSet[str]:
    """Authorized readers from an integrity × readers SecurityLabel (§4.1)."""
    return label.right.inner.subset
