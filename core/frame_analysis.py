"""3-D frame stiffness analysis for regular reinforced-concrete buildings.

Scope: linear-elastic, rigid-jointed, small-displacement 3-D frames with
Euler-Bernoulli members, nodal loads and member UDLs. It is intended for
gravity + lateral load distribution and design-action extraction, not for
non-linear, stability or dynamic analysis.

Sign conventions
----------------
Local member axes: x from node i to node j; y and z complete a right-handed
set (y is vertical for a horizontal member). Local DOFs are
``[u, v, w, rx, ry, rz]`` at each end. The member end-force vector returned by
:meth:`FrameModel.solve` is the force the nodes apply to the member, in local
coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class FrameNode:
    x: float
    y: float
    z: float
    restraints: Tuple[bool, bool, bool, bool, bool, bool] = (False,) * 6
    label: str = ""


@dataclass
class FrameMember:
    i: int
    j: int
    E: float          # MPa
    G: float          # MPa
    A: float          # mm2
    Iy: float         # mm4, bending about local y
    Iz: float         # mm4, bending about local z
    J: float          # mm4, torsion
    label: str = ""


@dataclass
class MemberUDL:
    """Uniformly distributed load on a member, in GLOBAL components (kN/m)."""
    member: int
    wx: float = 0.0
    wy: float = 0.0
    wz: float = 0.0


@dataclass
class FrameLoadCase:
    name: str
    nodal_loads: Dict[int, Tuple[float, float, float, float, float, float]] = field(default_factory=dict)
    udls: List[MemberUDL] = field(default_factory=list)


@dataclass
class MemberForces:
    member: int
    length_mm: float
    local_axes: np.ndarray
    # force the nodes apply to the member, local coordinates
    end_forces: np.ndarray  # 12 values

    @property
    def N_i_kN(self) -> float:
        return float(self.end_forces[0]) / 1000.0

    @property
    def Vy_i_kN(self) -> float:
        return float(self.end_forces[1]) / 1000.0

    @property
    def Vz_i_kN(self) -> float:
        return float(self.end_forces[2]) / 1000.0

    @property
    def Mz_i_kNm(self) -> float:
        return float(self.end_forces[5]) / 1e6

    @property
    def My_i_kNm(self) -> float:
        return float(self.end_forces[4]) / 1e6

    @property
    def N_j_kN(self) -> float:
        return float(self.end_forces[6]) / 1000.0

    @property
    def Vy_j_kN(self) -> float:
        return float(self.end_forces[7]) / 1000.0

    @property
    def Vz_j_kN(self) -> float:
        return float(self.end_forces[8]) / 1000.0

    @property
    def Mz_j_kNm(self) -> float:
        return float(self.end_forces[11]) / 1e6

    @property
    def My_j_kNm(self) -> float:
        return float(self.end_forces[10]) / 1e6

    def as_dict(self) -> Dict[str, float]:
        return {
            "N_i_kN": self.N_i_kN, "Vy_i_kN": self.Vy_i_kN, "Vz_i_kN": self.Vz_i_kN,
            "Mz_i_kNm": self.Mz_i_kNm, "My_i_kNm": self.My_i_kNm,
            "N_j_kN": self.N_j_kN, "Vy_j_kN": self.Vy_j_kN, "Vz_j_kN": self.Vz_j_kN,
            "Mz_j_kNm": self.Mz_j_kNm, "My_j_kNm": self.My_j_kNm,
        }


@dataclass
class FrameResult:
    displacements: np.ndarray  # 6N
    reactions: np.ndarray      # 6N (zero at free DOFs)
    members: List[MemberForces]
    max_translation_mm: float
    max_drift_ratio: Optional[float] = None


def _transform(ex: np.ndarray) -> np.ndarray:
    ex = ex / np.linalg.norm(ex)
    if abs(ex[2]) > 0.99:
        ref = np.array([1.0, 0.0, 0.0])
    else:
        ref = np.array([0.0, 0.0, 1.0])
    ez = np.cross(ex, ref)
    ez = ez / np.linalg.norm(ez)
    ey = np.cross(ez, ex)
    ey = ey / np.linalg.norm(ey)
    R = np.vstack([ex, ey, ez])
    T = np.zeros((12, 12))
    for k in range(4):
        T[3 * k:3 * k + 3, 3 * k:3 * k + 3] = R
    return T


def _local_stiffness(E: float, G: float, A: float, Iy: float, Iz: float, J: float, L: float) -> np.ndarray:
    k = np.zeros((12, 12))
    EA = E * A
    GJ = G * J
    EIz = E * Iz
    EIy = E * Iy
    k[0, 0] = k[6, 6] = EA / L
    k[0, 6] = k[6, 0] = -EA / L
    k[3, 3] = k[9, 9] = GJ / L
    k[3, 9] = k[9, 3] = -GJ / L

    # bending about local z (v, rz)
    k[1, 1] = k[7, 7] = 12 * EIz / L ** 3
    k[1, 7] = k[7, 1] = -12 * EIz / L ** 3
    k[1, 5] = k[5, 1] = k[1, 11] = k[11, 1] = 6 * EIz / L ** 2
    k[5, 7] = k[7, 5] = k[7, 11] = k[11, 7] = -6 * EIz / L ** 2
    k[5, 5] = k[11, 11] = 4 * EIz / L
    k[5, 11] = k[11, 5] = 2 * EIz / L

    # bending about local y (w, ry)
    k[2, 2] = k[8, 8] = 12 * EIy / L ** 3
    k[2, 8] = k[8, 2] = -12 * EIy / L ** 3
    k[2, 4] = k[4, 2] = k[2, 10] = k[10, 2] = -6 * EIy / L ** 2
    k[4, 8] = k[8, 4] = k[8, 10] = k[10, 8] = 6 * EIy / L ** 2
    k[4, 4] = k[10, 10] = 4 * EIy / L
    k[4, 10] = k[10, 4] = 2 * EIy / L
    return k


def _fixed_end_forces(qy: float, qz: float, L: float) -> np.ndarray:
    f = np.zeros(12)
    if qy:
        f[1] = -qy * L / 2.0
        f[5] = qy * L ** 2 / 12.0
        f[7] = -qy * L / 2.0
        f[11] = -qy * L ** 2 / 12.0
    if qz:
        f[2] = -qz * L / 2.0
        f[4] = qz * L ** 2 / 12.0
        f[8] = -qz * L / 2.0
        f[10] = -qz * L ** 2 / 12.0
    return f


class FrameModel:
    def __init__(self):
        self.nodes: List[FrameNode] = []
        self.members: List[FrameMember] = []

    def add_node(self, x: float, y: float, z: float,
                 restraints: Sequence[bool] = (False,) * 6, label: str = "") -> int:
        self.nodes.append(FrameNode(float(x), float(y), float(z), tuple(bool(r) for r in restraints), label))
        return len(self.nodes) - 1

    def add_member(self, i: int, j: int, E: float, G: float, A: float,
                   Iy: float, Iz: float, J: float, label: str = "") -> int:
        if i == j:
            raise ValueError("A member cannot connect a node to itself.")
        self.members.append(FrameMember(i, j, E, G, A, Iy, Iz, J, label))
        return len(self.members) - 1

    def _member_geometry(self, m: FrameMember):
        # Node coordinates are stored in metres (the UI/geometry convention);
        # section properties and E are in N/mm units, so convert to mm here.
        p1 = np.array([self.nodes[m.i].x, self.nodes[m.i].y, self.nodes[m.i].z], dtype=float) * 1000.0
        p2 = np.array([self.nodes[m.j].x, self.nodes[m.j].y, self.nodes[m.j].z], dtype=float) * 1000.0
        d = p2 - p1
        L = float(np.linalg.norm(d))
        if L <= 1e-9:
            raise ValueError("Zero-length member.")
        return p1, p2, L, d / L

    def solve(self, cases: Sequence[Tuple[FrameLoadCase, float]]) -> FrameResult:
        """Solve a linear combination of load cases.

        ``cases`` is a sequence of ``(load_case, factor)``. The combination is
        linear, so the result is the same as solving each case and summing.
        """
        n_nodes = len(self.nodes)
        ndof = 6 * n_nodes
        K = np.zeros((ndof, ndof))
        P = np.zeros(ndof)
        fixed: List[np.ndarray] = []
        member_data = []

        for mi, m in enumerate(self.members):
            p1, p2, L, ex = self._member_geometry(m)
            T = _transform(ex)
            k_local = _local_stiffness(m.E, m.G, m.A, m.Iy, m.Iz, m.J, L)
            k_global = T.T @ k_local @ T
            dofs = list(range(6 * m.i, 6 * m.i + 6)) + list(range(6 * m.j, 6 * m.j + 6))
            K[np.ix_(dofs, dofs)] += k_global

            f_local = np.zeros(12)
            for case, factor in cases:
                for udl in case.udls:
                    if udl.member != mi:
                        continue
                    w_global = np.array([udl.wx, udl.wy, udl.wz], dtype=float) * factor
                    w_local = T[:3, :3] @ w_global
                    f_local += _fixed_end_forces(float(w_local[1]), float(w_local[2]), L)
            fixed.append(f_local)
            f_global = T.T @ f_local
            P[dofs] -= f_global
            member_data.append((m, L, ex, T, k_local, dofs))

        for case, factor in cases:
            for node, load in case.nodal_loads.items():
                # Nodal loads are specified in kN/kNm; the stiffness system is
                # in N/Nmm.
                P[6 * node:6 * node + 6] += np.array(load, dtype=float) * 1000.0 * factor

        restrained = np.zeros(ndof, dtype=bool)
        for n, node in enumerate(self.nodes):
            restrained[6 * n:6 * n + 6] = node.restraints
        free = ~restrained
        u = np.zeros(ndof)
        if np.any(free):
            Kff = K[np.ix_(free, free)]
            try:
                u[free] = np.linalg.solve(Kff, P[free])
            except np.linalg.LinAlgError as exc:
                raise ValueError("Frame stiffness matrix is singular — check supports and connectivity.") from exc

        member_forces: List[MemberForces] = []
        for mi, ((m, L, ex, T, k_local, dofs), f_local) in enumerate(zip(member_data, fixed)):
            u_m = u[dofs]
            f_end = k_local @ (T @ u_m) + f_local
            member_forces.append(MemberForces(
                member=mi, length_mm=L,
                local_axes=T[:3, :3], end_forces=f_end,
            ))

        reactions = K @ u - P
        translations = u.reshape(-1, 6)[:, :3] if ndof else np.zeros((0, 3))
        max_translation = float(np.max(np.abs(translations))) if translations.size else 0.0
        return FrameResult(u, reactions, member_forces, max_translation)

    def solve_single(self, case: FrameLoadCase) -> FrameResult:
        return self.solve([(case, 1.0)])

    def member_internal_forces(self, result: FrameResult, member_index: int,
                               x_mm: float, qy: float = 0.0, qz: float = 0.0) -> Dict[str, float]:
        """Internal forces at distance x from node i (local axes).

        UDLs must be supplied in LOCAL components for the same combination;
        this is a convenience for beam design, not a general load reader.
        """
        mf = result.members[member_index]
        L = mf.length_mm
        x = max(0.0, min(float(x_mm), L))
        f = mf.end_forces
        # Sign convention calibrated against the fixed-end/simple-beam tests.
        N = -f[0] / 1000.0
        Vy = (f[1] + qy * x) / 1000.0
        Vz = (f[2] + qz * x) / 1000.0
        Mz = (f[5] + f[1] * x + qy * x ** 2 / 2.0) / 1e6
        My = (f[4] + f[2] * x + qz * x ** 2 / 2.0) / 1e6
        return {"N_kN": N, "Vy_kN": Vy, "Vz_kN": Vz, "Mz_kNm": Mz, "My_kNm": My}
