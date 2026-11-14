"""Linear static analysis for 2D frame (beam-column) models.

Degrees of freedom per node (global): ux, uy, rz.
Element: Euler-Bernoulli beam-column with axial stiffness.
Uniform transverse loads are converted to consistent (work-equivalent) nodal loads.

Sign convention: right-handed axes, rotations counter-clockwise positive.

Result conventions:
- displacements: global (ux, uy, rz) per node.
- reactions: global (Rx, Ry, Mz) per restrained DOF, force exerted by supports on the structure.
- member_end_actions: local (N, V, M) at each end, exerted by the joints on the member.
  Axial N is positive in tension.
"""

import math
from dataclasses import dataclass

from structpin.fem.linalg import solve_dense, SingularSystemError
from structpin.model.structural_model import ModelError

DOF_PER_NODE = 3


def element_stiffness_local(E, A, I, L):
    """6x6 local stiffness for DOFs [u1, v1, th1, u2, v2, th2]."""
    ea = E * A / L
    ei = E * I
    a = 12.0 * ei / L ** 3
    b = 6.0 * ei / L ** 2
    c = 4.0 * ei / L
    d = 2.0 * ei / L
    return [
        [ea, 0.0, 0.0, -ea, 0.0, 0.0],
        [0.0, a, b, 0.0, -a, b],
        [0.0, b, c, 0.0, -b, d],
        [-ea, 0.0, 0.0, ea, 0.0, 0.0],
        [0.0, -a, -b, 0.0, a, -b],
        [0.0, b, d, 0.0, -b, c],
    ]


def transformation_matrix(c, s):
    """Maps global element DOFs to local DOFs."""
    return [
        [c, s, 0.0, 0.0, 0.0, 0.0],
        [-s, c, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, c, s, 0.0],
        [0.0, 0.0, 0.0, -s, c, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    ]


def consistent_udl_loads_local(qy, L):
    """Consistent nodal loads (local) for a uniform load qy along local y."""
    return [0.0, qy * L / 2.0, qy * L * L / 12.0, 0.0, qy * L / 2.0, -qy * L * L / 12.0]


def _matmul(A, B):
    m = len(B)
    p = len(B[0])
    return [[sum(A[i][k] * B[k][j] for k in range(m)) for j in range(p)] for i in range(len(A))]


def _transpose(A):
    return [list(row) for row in zip(*A)]


def _mat_vec(A, v):
    return [sum(a * x for a, x in zip(row, v)) for row in A]


@dataclass
class FrameResults:
    displacements: dict
    reactions: dict
    member_end_actions: dict


def solve_frame(model):
    """Solve a 2D frame model. Raises ModelError or SingularSystemError."""
    errors = model.validate()
    if errors:
        raise ModelError("; ".join(errors))

    node_ids = sorted(model.nodes)
    pos = {nid: k for k, nid in enumerate(node_ids)}
    ndof = DOF_PER_NODE * len(node_ids)

    def gdofs(nid):
        base = DOF_PER_NODE * pos[nid]
        return [base, base + 1, base + 2]

    K = [[0.0] * ndof for _ in range(ndof)]
    F = [0.0] * ndof

    for ld in model.nodal_loads:
        g = gdofs(ld.node)
        F[g[0]] += ld.fx
        F[g[1]] += ld.fy
        F[g[2]] += ld.mz

    qy_by_member = {}
    for u in model.member_udls:
        qy_by_member[u.member] = qy_by_member.get(u.member, 0.0) + u.qy

    element_cache = {}
    for mem in model.members.values():
        ni = model.nodes[mem.node_i]
        nj = model.nodes[mem.node_j]
        L = math.hypot(nj.x - ni.x, nj.y - ni.y)
        c = (nj.x - ni.x) / L
        s = (nj.y - ni.y) / L
        mat = model.materials[mem.material]
        sec = model.sections[mem.section]

        kl = element_stiffness_local(mat.E, sec.A, sec.I, L)
        T = transformation_matrix(c, s)
        kg = _matmul(_transpose(T), _matmul(kl, T))
        dofs = gdofs(mem.node_i) + gdofs(mem.node_j)

        for a, ga in enumerate(dofs):
            for b, gb in enumerate(dofs):
                K[ga][gb] += kg[a][b]

        fl = consistent_udl_loads_local(qy_by_member.get(mem.id, 0.0), L)
        fg = _mat_vec(_transpose(T), fl)
        for a, ga in enumerate(dofs):
            F[ga] += fg[a]

        element_cache[mem.id] = (dofs, kl, T, fl)

    restrained = set()
    for r in model.restraints:
        g = gdofs(r.node)
        if r.ux:
            restrained.add(g[0])
        if r.uy:
            restrained.add(g[1])
        if r.rz:
            restrained.add(g[2])

    free = [d for d in range(ndof) if d not in restrained]
    u = [0.0] * ndof
    if free:
        Kff = [[K[i][j] for j in free] for i in free]
        Ff = [F[i] for i in free]
        try:
            uf = solve_dense(Kff, Ff)
        except SingularSystemError as exc:
            raise SingularSystemError(f"model '{model.name}' is unstable: {exc}") from exc
        for idx, d in enumerate(free):
            u[d] = uf[idx]

    Ku = [sum(K[i][j] * u[j] for j in range(ndof)) for i in range(ndof)]

    displacements = {}
    reactions = {}
    for nid in node_ids:
        g = gdofs(nid)
        displacements[nid] = (u[g[0]], u[g[1]], u[g[2]])
        reactions[nid] = tuple(
            (Ku[d] - F[d]) if d in restrained else 0.0 for d in g
        )

    member_end_actions = {}
    for mem_id, (dofs, kl, T, fl) in element_cache.items():
        ue = [u[d] for d in dofs]
        ul = _mat_vec(T, ue)
        q = [a - b for a, b in zip(_mat_vec(kl, ul), fl)]
        member_end_actions[mem_id] = (tuple(q[0:3]), tuple(q[3:6]))

    return FrameResults(displacements, reactions, member_end_actions)
