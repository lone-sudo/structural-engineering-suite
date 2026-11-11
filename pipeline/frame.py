"""Build and analyse a regular-grid building frame (Phase 2).

The frame is generated from the same ``GridGeometry`` used by the 3D preview:
columns at selected intersections, beams along every adjacent selected pair at
each floor, fixed bases, rigid joints. Gravity slab loads are distributed by
tributary width and wind is applied as equivalent nodal floor loads.

This is a linear-elastic screening model. It does not include soil-structure
interaction, semi-rigid joints, floor diaphragm flexibility, torsional building
response, seismic action or non-linear material behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core.frame_analysis import FrameLoadCase, FrameModel, MemberUDL
from core.geometry import GridGeometry
from core.load_combinations import Combination, combinations_for
from core.wind_load import wind_pressure_kpa


@dataclass
class FrameEnvelope:
    member: int
    label: str
    kind: str  # "beam" or "column"
    N_max_kN: float
    Vy_max_kN: float
    Vz_max_kN: float
    Mz_max_kNm: float
    My_max_kNm: float
    Mz_i_min_kNm: float
    Mz_i_max_kNm: float
    Mz_j_min_kNm: float
    Mz_j_max_kNm: float


@dataclass
class FrameBuildingResult:
    model: FrameModel
    member_meta: List[Dict[str, str]]
    combinations: List[Combination]
    envelopes: List[FrameEnvelope]
    max_drift_x: float
    max_drift_y: float
    drift_limit: float
    max_translation_x_mm: float
    max_translation_y_mm: float
    base_shear_x_kN: float
    base_shear_y_kN: float
    applied_wind_x_kN: float
    applied_wind_y_kN: float
    wind: Dict[str, float]
    storeys: int
    storey_height_m: float
    warnings: List[str] = field(default_factory=list)


class FrameBuilding:
    def __init__(
        self,
        x_spacings: Sequence[float],
        y_spacings: Sequence[float],
        columns: Sequence[Sequence[int]],
        num_storeys: int = 3,
        storey_height_m: float = 3.0,
        slab_gk_kpa: float = 4.5,
        slab_qk_kpa: float = 2.0,
        beam_b_mm: float = 250.0,
        beam_h_mm: float = 500.0,
        col_b_mm: float = 300.0,
        col_h_mm: float = 300.0,
        f_ck_mpa: float = 25.0,
        code: str = "BS8110",
        wind_speed_m_s: float = 30.0,
        terrain: str = "suburban",
        wall_load_kn_m: float = 0.0,
        drift_limit: float = 1.0 / 400.0,
    ):
        if num_storeys < 1:
            raise ValueError("num_storeys must be >= 1.")
        if storey_height_m <= 0:
            raise ValueError("storey_height_m must be positive.")
        self.geometry = GridGeometry(
            tuple(float(v) for v in x_spacings),
            tuple(float(v) for v in y_spacings),
            tuple((int(c[0]), int(c[1])) for c in columns),
        )
        self.num_storeys = int(num_storeys)
        self.storey_height_m = float(storey_height_m)
        self.slab_gk, self.slab_qk = float(slab_gk_kpa), float(slab_qk_kpa)
        self.beam_b, self.beam_h = float(beam_b_mm), float(beam_h_mm)
        self.col_b, self.col_h = float(col_b_mm), float(col_h_mm)
        self.f_ck = float(f_ck_mpa)
        self.code = code
        self.wind_speed = float(wind_speed_m_s)
        self.terrain = terrain
        self.wall_load = float(wall_load_kn_m)
        self.drift_limit = float(drift_limit)
        self.warnings: List[str] = []

    # -- section properties -------------------------------------------------
    def _properties(self, b: float, h: float):
        A = b * h
        Iz = b * h ** 3 / 12.0
        Iy = h * b ** 3 / 12.0
        J = 0.141 * min(b, h) * max(b, h) ** 3
        return A, Iy, Iz, J

    def _modulus(self) -> float:
        # EN 1992-1-1 short-term modulus, with 0.5Ecm for cracked stiffness.
        f_cm = self.f_ck + 8.0
        ecm = 22.0 * (f_cm / 10.0) ** 0.3 * 1000.0  # MPa
        return 0.5 * ecm

    # -- model construction -------------------------------------------------
    def build(self) -> Tuple[FrameModel, List[Dict[str, str]], Dict[str, float]]:
        g = self.geometry
        model = FrameModel()
        nodes: Dict[Tuple[int, int, int], int] = {}
        for level in range(self.num_storeys + 1):
            z = level * self.storey_height_m
            for j in range(len(g.y_coords)):
                for i in range(len(g.x_coords)):
                    if level == 0:
                        restraints = (True,) * 6
                    else:
                        restraints = (False,) * 6
                    label = f"L{level}-{i+1}{j+1}"
                    nodes[(level, i, j)] = model.add_node(
                        g.x_coords[i], g.y_coords[j], z, restraints, label
                    )

        E = self._modulus()
        G = E / (2.0 * (1.0 + 0.2))
        colA, colIy, colIz, colJ = self._properties(self.col_b, self.col_h)
        beamA, beamIy, beamIz, beamJ = self._properties(self.beam_b, self.beam_h)

        member_meta: List[Dict[str, str]] = []
        column_members: List[int] = []
        # Columns
        for level in range(1, self.num_storeys + 1):
            for (i, j) in g.columns:
                bottom = nodes[(level - 1, i, j)]
                top = nodes[(level, i, j)]
                label = f"C{level}-{i+1}{j+1}"
                mi = model.add_member(bottom, top, E, G, colA, colIy, colIz, colJ, label)
                member_meta.append({"label": label, "kind": "column", "level": str(level)})
                column_members.append(mi)
        # Beams
        for level in range(1, self.num_storeys + 1):
            for (a, b) in g.beam_edges:
                n1 = nodes[(level, a[0], a[1])]
                n2 = nodes[(level, b[0], b[1])]
                label = f"B{level}-{a[0]+1}{a[1]+1}-{b[0]+1}{b[1]+1}"
                mi = model.add_member(n1, n2, E, G, beamA, beamIy, beamIz, beamJ, label)
                member_meta.append({"label": label, "kind": "beam", "level": str(level)})

        # -- loads ----------------------------------------------------------
        gk_case = FrameLoadCase("G")
        qk_case = FrameLoadCase("Q")
        wx_case = FrameLoadCase("WX")
        wy_case = FrameLoadCase("WY")

        # Beam UDLs from slab tributary width + self weight + wall.
        x_sp = g.x_spacings
        y_sp = g.y_spacings
        for level in range(1, self.num_storeys + 1):
            for mi, meta in enumerate(member_meta):
                if meta["kind"] != "beam":
                    continue
                m = model.members[mi]
                p1 = model.nodes[m.i]
                p2 = model.nodes[m.j]
                if abs(p1.y - p2.y) < 1e-9:  # beam along X
                    j = min(range(len(g.y_coords)), key=lambda k: abs(g.y_coords[k] - p1.y))
                    trib = 0.5 * (y_sp[j - 1] if j > 0 else 0.0) + 0.5 * (y_sp[j] if j < len(y_sp) else 0.0)
                else:  # beam along Y
                    i = min(range(len(g.x_coords)), key=lambda k: abs(g.x_coords[k] - p1.x))
                    trib = 0.5 * (x_sp[i - 1] if i > 0 else 0.0) + 0.5 * (x_sp[i] if i < len(x_sp) else 0.0)
                self_weight = (self.beam_b / 1000.0) * (self.beam_h / 1000.0) * 24.0
                gk = self.slab_gk * trib + self_weight + self.wall_load
                qk = self.slab_qk * trib
                gk_case.udls.append(MemberUDL(mi, wz=-gk))
                qk_case.udls.append(MemberUDL(mi, wz=-qk))

        # Column self-weight at the top node of each column.
        col_self = (self.col_b / 1000.0) * (self.col_h / 1000.0) * 24.0 * self.storey_height_m
        for mi in column_members:
            top = model.members[mi].j
            load = gk_case.nodal_loads.get(top, (0.0,) * 6)
            gk_case.nodal_loads[top] = (
                load[0], load[1], load[2] - col_self, load[3], load[4], load[5]
            )

        # Wind: equivalent nodal force at each floor.
        wind = wind_pressure_kpa(self.wind_speed, max(self.num_storeys * self.storey_height_m, 1.0), self.terrain)
        width_x = g.x_coords[-1] if len(g.x_coords) > 1 else 1.0
        width_y = g.y_coords[-1] if len(g.y_coords) > 1 else 1.0
        applied_x = applied_y = 0.0
        for level in range(1, self.num_storeys + 1):
            level_nodes = [nodes[(level, i, j)] for j in range(len(g.y_coords)) for i in range(len(g.x_coords))]
            if not level_nodes:
                continue
            force_x = wind["w_kpa"] * width_y * self.storey_height_m
            force_y = wind["w_kpa"] * width_x * self.storey_height_m
            applied_x += force_x
            applied_y += force_y
            fx = force_x / len(level_nodes)
            fy = force_y / len(level_nodes)
            for n in level_nodes:
                load = wx_case.nodal_loads.get(n, (0.0,) * 6)
                wx_case.nodal_loads[n] = (load[0] + fx, load[1], load[2], load[3], load[4], load[5])
                load = wy_case.nodal_loads.get(n, (0.0,) * 6)
                wy_case.nodal_loads[n] = (load[0], load[1] + fy, load[2], load[3], load[4], load[5])

        self.load_cases = {"G": gk_case, "Q": qk_case, "WX": wx_case, "WY": wy_case}
        w = dict(wind)
        w["applied_wind_x_kN"] = applied_x
        w["applied_wind_y_kN"] = applied_y
        return model, member_meta, w

    # -- analysis -----------------------------------------------------------
    def analyse(self) -> FrameBuildingResult:
        model, member_meta, wind = self.build()
        combos = combinations_for(self.code)
        envelopes: List[FrameEnvelope] = [
            FrameEnvelope(
                member=i, label=meta["label"], kind=meta["kind"],
                N_max_kN=0.0, Vy_max_kN=0.0, Vz_max_kN=0.0,
                Mz_max_kNm=0.0, My_max_kNm=0.0,
                Mz_i_min_kNm=0.0, Mz_i_max_kNm=0.0,
                Mz_j_min_kNm=0.0, Mz_j_max_kNm=0.0,
            )
            for i, meta in enumerate(member_meta)
        ]
        g = self.geometry
        node_index = {}
        for level in range(self.num_storeys + 1):
            for j in range(len(g.y_coords)):
                for i in range(len(g.x_coords)):
                    # Recover the node index from the model labels.
                    node_index[(level, i, j)] = next(
                        k for k, nd in enumerate(model.nodes) if nd.label == f"L{level}-{i+1}{j+1}"
                    )

        max_drift_x = max_drift_y = 0.0
        max_tx = max_ty = 0.0
        base_x = base_y = 0.0
        last = None
        for combo in combos:
            # Wind is a single direction per combination; analyse X and Y
            # separately and envelope the two variants.
            variants = ["WX", "WY"] if "W" in combo.factors else [None]
            for wind_key in variants:
                cases = []
                for key, factor in combo.factors.items():
                    if key == "W":
                        if wind_key is not None:
                            cases.append((self.load_cases[wind_key], factor))
                    else:
                        cases.append((self.load_cases[key], factor))
                result = model.solve(cases)
                last = result
                for mi, mf in enumerate(result.members):
                    env = envelopes[mi]
                    env.N_max_kN = max(env.N_max_kN, abs(mf.N_i_kN), abs(mf.N_j_kN))
                    env.Vy_max_kN = max(env.Vy_max_kN, abs(mf.Vy_i_kN), abs(mf.Vy_j_kN))
                    env.Vz_max_kN = max(env.Vz_max_kN, abs(mf.Vz_i_kN), abs(mf.Vz_j_kN))
                    env.Mz_max_kNm = max(env.Mz_max_kNm, abs(mf.Mz_i_kNm), abs(mf.Mz_j_kNm))
                    env.My_max_kNm = max(env.My_max_kNm, abs(mf.My_i_kNm), abs(mf.My_j_kNm))
                    env.Mz_i_min_kNm = min(env.Mz_i_min_kNm, mf.Mz_i_kNm)
                    env.Mz_i_max_kNm = max(env.Mz_i_max_kNm, mf.Mz_i_kNm)
                    env.Mz_j_min_kNm = min(env.Mz_j_min_kNm, mf.Mz_j_kNm)
                    env.Mz_j_max_kNm = max(env.Mz_j_max_kNm, mf.Mz_j_kNm)

                # Drift per column line.
                for (i, j) in g.columns:
                    for level in range(1, self.num_storeys + 1):
                        top = 6 * node_index[(level, i, j)]
                        bot = 6 * node_index[(level - 1, i, j)]
                        dx = abs(result.displacements[top] - result.displacements[bot])
                        dy = abs(result.displacements[top + 1] - result.displacements[bot + 1])
                        hs = self.storey_height_m * 1000.0
                        max_drift_x = max(max_drift_x, dx / hs)
                        max_drift_y = max(max_drift_y, dy / hs)
                max_tx = max(max_tx, max(
                    (abs(result.displacements[6 * node_index[(level, i, j)]])
                     for level in range(self.num_storeys + 1)
                     for (i, j) in g.columns), default=0.0
                ))
                max_ty = max(max_ty, max(
                    (abs(result.displacements[6 * node_index[(level, i, j)] + 1])
                     for level in range(self.num_storeys + 1)
                     for (i, j) in g.columns), default=0.0
                ))
                # Base shear is the sum of the base reactions, not the
                # largest single column reaction.
                sum_x = sum(result.reactions[6 * node_index[(0, i, j)]] for (i, j) in g.columns) / 1000.0
                sum_y = sum(result.reactions[6 * node_index[(0, i, j)] + 1] for (i, j) in g.columns) / 1000.0
                base_x = max(base_x, abs(sum_x))
                base_y = max(base_y, abs(sum_y))

        if max_drift_x > self.drift_limit:
            self.warnings.append(
                f"X-direction drift {max_drift_x:.5f} exceeds the screening limit {self.drift_limit:.5f}."
            )
        if max_drift_y > self.drift_limit:
            self.warnings.append(
                f"Y-direction drift {max_drift_y:.5f} exceeds the screening limit {self.drift_limit:.5f}."
            )
        if last is None:
            raise ValueError("No load combination could be solved.")

        return FrameBuildingResult(
            model=model, member_meta=member_meta, combinations=combos,
            envelopes=envelopes,
            max_drift_x=max_drift_x, max_drift_y=max_drift_y,
            drift_limit=self.drift_limit,
            max_translation_x_mm=max_tx, max_translation_y_mm=max_ty,
            base_shear_x_kN=base_x, base_shear_y_kN=base_y,
            applied_wind_x_kN=wind["applied_wind_x_kN"],
            applied_wind_y_kN=wind["applied_wind_y_kN"],
            wind=wind, storeys=self.num_storeys,
            storey_height_m=self.storey_height_m, warnings=self.warnings,
        )
