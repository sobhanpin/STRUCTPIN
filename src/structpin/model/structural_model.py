"""Shared structural data model for STRUCTPIN (2D frame subset).

Units are not enforced: the caller must use one consistent system
(for example N, m, Pa). The model itself performs no calculations.
"""

from dataclasses import dataclass
import math


class ModelError(ValueError):
    """Raised when a structural model is invalid."""


@dataclass(frozen=True)
class Material:
    name: str
    E: float  # Elastic modulus


@dataclass(frozen=True)
class Section:
    name: str
    A: float  # Cross-sectional area
    I: float  # Second moment of area about the local z-axis


@dataclass(frozen=True)
class Node:
    id: int
    x: float
    y: float


@dataclass(frozen=True)
class Member:
    id: int
    node_i: int
    node_j: int
    material: str
    section: str


@dataclass(frozen=True)
class Restraint:
    node: int
    ux: bool = False
    uy: bool = False
    rz: bool = False


@dataclass(frozen=True)
class NodalLoad:
    node: int
    fx: float = 0.0
    fy: float = 0.0
    mz: float = 0.0  # Counter-clockwise positive


@dataclass(frozen=True)
class MemberUDL:
    member: int
    qy: float  # Uniform load per unit length along the member's local y-axis


class StructuralModel:
    """Container for a 2D frame model."""

    def __init__(self, name="Untitled"):
        self.name = name
        self.materials = {}
        self.sections = {}
        self.nodes = {}
        self.members = {}
        self.restraints = []
        self.nodal_loads = []
        self.member_udls = []

    @staticmethod
    def _add_unique(store, key, obj, kind):
        if key in store:
            raise ModelError(f"duplicate {kind} id {key!r}")
        store[key] = obj

    def add_material(self, name, E):
        self._add_unique(self.materials, name, Material(name, float(E)), "material")

    def add_section(self, name, A, I):
        self._add_unique(self.sections, name, Section(name, float(A), float(I)), "section")

    def add_node(self, node_id, x, y):
        self._add_unique(self.nodes, node_id, Node(node_id, float(x), float(y)), "node")

    def add_member(self, member_id, node_i, node_j, material, section):
        self._add_unique(
            self.members,
            member_id,
            Member(member_id, node_i, node_j, material, section),
            "member",
        )

    def add_restraint(self, node, ux=False, uy=False, rz=False):
        self.restraints.append(Restraint(node, ux, uy, rz))

    def add_nodal_load(self, node, fx=0.0, fy=0.0, mz=0.0):
        self.nodal_loads.append(NodalLoad(node, float(fx), float(fy), float(mz)))

    def add_member_udl(self, member, qy):
        self.member_udls.append(MemberUDL(member, float(qy)))

    def member_length(self, member_id):
        m = self.members[member_id]
        ni = self.nodes[m.node_i]
        nj = self.nodes[m.node_j]
        return math.hypot(nj.x - ni.x, nj.y - ni.y)

    def validate(self, min_length=1e-9):
        """Return a list of human-readable error strings (empty if valid)."""
        errors = []
        if not self.nodes:
            errors.append("model has no nodes")
        if not self.members:
            errors.append("model has no members")

        for mat in self.materials.values():
            if mat.E <= 0:
                errors.append(f"material {mat.name!r}: E must be positive")
        for sec in self.sections.values():
            if sec.A <= 0 or sec.I <= 0:
                errors.append(f"section {sec.name!r}: A and I must be positive")

        used_nodes = set()
        pairs = set()
        for m in self.members.values():
            missing = [n for n in (m.node_i, m.node_j) if n not in self.nodes]
            if missing:
                errors.append(f"member {m.id}: missing node(s) {missing}")
                continue
            if m.node_i == m.node_j:
                errors.append(f"member {m.id}: both ends on node {m.node_i}")
                continue
            used_nodes.update((m.node_i, m.node_j))
            if m.material not in self.materials:
                errors.append(f"member {m.id}: unknown material {m.material!r}")
            if m.section not in self.sections:
                errors.append(f"member {m.id}: unknown section {m.section!r}")
            if self.member_length(m.id) < min_length:
                errors.append(f"member {m.id}: zero length")
            pair = frozenset((m.node_i, m.node_j))
            if pair in pairs:
                errors.append(f"member {m.id}: duplicate element between nodes {m.node_i} and {m.node_j}")
            pairs.add(pair)

        for nid in sorted(self.nodes):
            if nid not in used_nodes:
                errors.append(f"node {nid} is disconnected")

        for r in self.restraints:
            if r.node not in self.nodes:
                errors.append(f"restraint references missing node {r.node}")
        for ld in self.nodal_loads:
            if ld.node not in self.nodes:
                errors.append(f"nodal load references missing node {ld.node}")
        for u in self.member_udls:
            if u.member not in self.members:
                errors.append(f"member load references missing member {u.member}")

        return errors
