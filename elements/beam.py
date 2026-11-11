from __future__ import annotations

from typing import Dict, List, Union
import math

from core.rebar import RebarSelector
from core.results import DesignAudit, CheckStatus
from core.standards import BS8110, Eurocode2, design_flexure, load_factors
from core.beam_analysis import envelope_analysis, analyze_continuous_beam, SpanLoadInput, SpanInput

Number = Union[float, int]


def _broadcast(value, n: int, name: str) -> List[float]:
    if isinstance(value, (list, tuple)):
        if len(value) != n:
            raise ValueError(f"{name} list must have exactly {n} entries (one per span).")
        return [float(v) for v in value]
    return [float(value)] * n


class ContinuousBeam:
    """Continuous beam design over an arbitrary number of spans.

    Each span can have its OWN length, width, overall depth, and slab
    dead/live load — pass a list for any of these to vary it per span, or
    a single number to apply the same value to every span. Analysis is a
    real matrix (slope-deflection) solution with BS 8110/EC2-style pattern
    loading (the governing envelope across alternate-span load cases), not
    a lookup table restricted to equal spans.

    Both beam ends are assumed simply supported (no fixed/built-in ends,
    no cantilever overhangs) — that boundary condition is not yet
    implemented; see the "limitations" list in the result.
    """

    def __init__(
        self, spans: List[float],
        b_w=200.0, h_overall=450.0, cover: float = 25.0,
        gk_slab=12.0, qk_slab=6.0,
        wall_height: float = 2.8, wall_unit_weight: float = 18.0,
        wall_thick: float = 0.20, f_cu: float = 25.0, f_y: float = 460.0,
        f_yv: float = 250.0, code: str = "BS8110"
    ):
        if not spans or any(s <= 0 for s in spans):
            raise ValueError("spans must contain positive lengths in metres.")
        n = len(spans)
        self.spans = [float(s) for s in spans]
        self.num_spans = n
        self.b_w_list = _broadcast(b_w, n, "b_w")
        self.h_list = _broadcast(h_overall, n, "h_overall")
        self.gk_slab_list = _broadcast(gk_slab, n, "gk_slab")
        self.qk_slab_list = _broadcast(qk_slab, n, "qk_slab")
        if any(v <= 0 for v in self.b_w_list) or any(v <= 0 for v in self.h_list):
            raise ValueError("b_w and h_overall must be positive for every span.")
        if any(v < 0 for v in self.gk_slab_list) or any(v < 0 for v in self.qk_slab_list):
            raise ValueError("Loads cannot be negative.")

        self.cover = cover
        self.f_cu, self.f_y, self.f_yv, self.code = f_cu, f_y, f_yv, code
        self.wall_height, self.wall_thick, self.wall_unit_weight = wall_height, wall_thick, wall_unit_weight
        self.gk_wall = wall_height * wall_thick * wall_unit_weight

        self.main_bar_dia = 16
        self.link_dia = 8
        self.d_list = []
        for h in self.h_list:
            d = h - cover - self.link_dia - self.main_bar_dia / 2
            if d <= 0:
                raise ValueError(f"Beam effective depth is non-positive for h_overall={h}mm.")
            self.d_list.append(d)

        # Backward-compatible single-value attributes for any code path
        # that still expects a single beam-wide dimension.
        self.L = self.spans[0]
        self.b_w = self.b_w_list[0]
        self.h = self.h_list[0]
        self.d = self.d_list[0]

    def design_beam(self) -> Dict:
        n = self.num_spans
        gamma_g, gamma_q = load_factors(self.code)

        gk_total_list, qk_total_list, I_list = [], [], []
        for i in range(n):
            gk_self = (self.b_w_list[i] / 1000) * (self.h_list[i] / 1000) * 24.0
            gk_total_list.append(self.gk_slab_list[i] + gk_self + self.gk_wall)
            qk_total_list.append(self.qk_slab_list[i])
            I_list.append(self.b_w_list[i] * self.h_list[i] ** 3 / 12.0)

        span_loads = [
            SpanLoadInput(
                length_m=self.spans[i], I_relative=I_list[i],
                gk_kn_m=gk_total_list[i], qk_kn_m=qk_total_list[i],
                gamma_g=gamma_g, gamma_q=gamma_q,
            )
            for i in range(n)
        ]
        envelope = envelope_analysis(span_loads)

        gk_service = analyze_continuous_beam([SpanInput(length_m=self.spans[i], I_relative=I_list[i], w_ult_kn_m=gk_total_list[i]) for i in range(n)])
        has_qk = any(qk_total_list)
        qk_service = analyze_continuous_beam([SpanInput(length_m=self.spans[i], I_relative=I_list[i], w_ult_kn_m=qk_total_list[i]) for i in range(n)]) if has_qk else None

        def _support_reactions(results) -> List[float]:
            r = [0.0] * (n + 1)
            r[0] += results[0].V_left_kN
            r[n] += results[n - 1].V_right_kN
            for i in range(n - 1):
                r[i + 1] += results[i].V_right_kN + results[i + 1].V_left_kN
            return r

        gk_reactions = _support_reactions(gk_service)
        qk_reactions = _support_reactions(qk_service) if qk_service else [0.0] * (n + 1)

        span_results = []
        audit = DesignAudit()
        for i in range(n):
            b_w, d, h = self.b_w_list[i], self.d_list[i], self.h_list[i]
            M_span = envelope[i].M_span_max_kNm
            M_support = max(abs(envelope[i].M_left_support_kNm), abs(envelope[i].M_right_support_kNm))
            V_design = max(abs(envelope[i].V_left_kN), abs(envelope[i].V_right_kN))

            # Compression-steel centroid. Using 25 mm (the largest bar the
            # module selects) is conservative for smaller bars: a larger
            # d_prime increases the required compression steel.
            d_prime = self.cover + self.link_dia + 12.5
            if self.code == "BS8110":
                span_flex = design_flexure("BS8110", M_u=M_span, b=b_w, d=d, f_cu=self.f_cu, f_y=self.f_y, d_prime=d_prime, min_steel_h=h)
                supp_flex = design_flexure("BS8110", M_u=M_support, b=b_w, d=d, f_cu=self.f_cu, f_y=self.f_y, d_prime=d_prime, min_steel_h=h) if M_support else {"As_req": 0.0, "section_type": "n/a"}
                f_ck = None
            else:
                f_ck = self.f_cu
                span_flex = design_flexure("Eurocode 2", M_Ed=M_span, b=b_w, d=d, f_ck=f_ck, f_yk=self.f_y, d_prime=d_prime)
                supp_flex = design_flexure("Eurocode 2", M_Ed=M_support, b=b_w, d=d, f_ck=f_ck, f_yk=self.f_y, d_prime=d_prime) if M_support else {"As_req": 0.0, "section_type": "n/a"}

            span_opts = RebarSelector.select_beam_bars(
                span_flex["As_req"], preferred_diameters=(16, 20, 25),
                b_w=b_w, cover=self.cover, link_dia=self.link_dia, max_layers=1,
            )
            supp_opts = RebarSelector.select_beam_bars(
                supp_flex["As_req"], preferred_diameters=(16, 20, 25),
                b_w=b_w, cover=self.cover, link_dia=self.link_dia, max_layers=1,
            )
            span_bars = span_opts[0] if span_opts else {"description": "NO VALID STANDARD ARRANGEMENT", "As_prov": 0}
            supp_bars = supp_opts[0] if supp_opts else (
                {"description": "2Y12 nominal hanger bars", "As_prov": 226.2, "bar_count": 2, "bar_diameter": 12}
                if M_support == 0 else {"description": "NO VALID STANDARD ARRANGEMENT", "As_prov": 0}
            )
            detailing_note = ""
            if not span_opts:
                detailing_note = (
                    "No single-layer bar arrangement fits the beam width for the required span steel. "
                    "Widen the beam, increase its depth, or design a two-layer arrangement with a revised "
                    "effective depth — the effective depth used here assumes one layer."
                )
            elif not supp_opts and M_support > 0:
                detailing_note = (
                    "No single-layer bar arrangement fits the beam width for the required support steel. "
                    "Widen the beam or design a two-layer arrangement with a revised effective depth."
                )

            if span_bars["As_prov"] <= 0:
                # No valid bar arrangement exists for the flexural demand.
                # Do not call the shear/deflection routines with As=0: they
                # correctly reject it, but that would crash the whole design
                # instead of returning a controlled FAIL.
                shear = {
                    "status": "FAIL", "v": None, "vc": None, "v_max": None,
                    "asv_sv_req": None,
                    "message": "Shear not determined: no valid longitudinal bar arrangement fits the section.",
                }
            elif self.code == "BS8110":
                shear = BS8110.design_shear(V_design, b_w, d, self.f_cu, self.f_yv, span_bars["As_prov"])
            else:
                ec2_shear = Eurocode2.design_shear(V_design, b_w, d, f_ck, self.f_yv, span_bars["As_prov"])
                shear = {
                    "status": ec2_shear["status"], "v": ec2_shear["v"], "vc": ec2_shear["vrdc"],
                    "v_max": ec2_shear["v_rd_max"], "asv_sv_req": ec2_shear["asw_sv_req"], "message": ec2_shear["message"],
                }

            if shear["status"] != "FAIL" and shear.get("asv_sv_req") is not None:
                max_spacing_factor = 0.75
                max_code_spacing = 250
                if shear["asv_sv_req"] > 0:
                    area_two_leg = 2 * math.pi * self.link_dia ** 2 / 4
                    raw_sv = area_two_leg / shear["asv_sv_req"]
                    # Spacing must not exceed the required value. Rounding
                    # down to a 25 mm module is safe; forcing the result back
                    # up to a 75 mm "practical minimum" is NOT — it would
                    # provide fewer links than the design requires.
                    spacing = min(int(raw_sv // 25) * 25, int(max_spacing_factor * d), max_code_spacing)
                    if spacing < 75:
                        shear = dict(shear)
                        shear["status"] = "FAIL"
                        shear["message"] = (
                            f"Required link spacing is {raw_sv:.0f} mm, below the 75 mm practical minimum. "
                            "Increase the section depth/width or use a larger link diameter — do not "
                            "schedule the 75 mm minimum as if it satisfied the design."
                        )
                        link_schedule = (
                            "Shear reinforcement: NOT DETAILABLE — required link spacing < 75 mm; "
                            "increase section or link size"
                        )
                    else:
                        prefix_bar = "Y" if self.code == "BS8110" else "H"
                        link_schedule = f"{prefix_bar}{self.link_dia} 2-leg links @ {spacing}mm c/c"
                else:
                    spacing = max(min(int(max_spacing_factor * d), max_code_spacing), 75)
                    prefix_bar = "Y" if self.code == "BS8110" else "H"
                    link_schedule = f"{prefix_bar}{self.link_dia} 2-leg links @ {spacing}mm c/c (nominal)"
            else:
                link_schedule = "Shear reinforcement: NOT DETERMINED — see shear audit"

            actual_span_d = self.spans[i] * 1000 / d
            if span_bars["As_prov"] <= 0:
                deflection_status = "NOT CHECKED"
                allowable_span_d = None
            elif self.code == "BS8110":
                basic_ratio = 26.0 if n >= 2 else 20.0
                defl = BS8110.deflection_check(b_w, d, M_span, span_flex["As_req"], span_bars["As_prov"], self.f_y, basic_ratio=basic_ratio)
                deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
                allowable_span_d = round(defl["allowable_span_d"], 2)
            else:
                # EN 1992-1-1 Cl. 7.4.2 span/effective-depth screening.
                # K = 1.0 simply supported, 1.3 end span, 1.5 interior span.
                if n == 1:
                    k_system = 1.0
                elif i == 0 or i == n - 1:
                    k_system = 1.3
                else:
                    k_system = 1.5
                defl = Eurocode2.span_depth_limit(
                    f_ck, span_flex["As_req"], span_bars["As_prov"], b_w, d,
                    K=k_system, As_comp=span_flex.get("As_comp", 0.0), f_yk=self.f_y,
                )
                deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
                allowable_span_d = round(defl["allowable_span_d"], 2)

            tag = f"Span {i+1}"
            audit.add(f"{tag} — Flexure at span", CheckStatus.PASS if span_bars["As_prov"] >= span_flex["As_req"] else CheckStatus.FAIL,
                      demand=span_flex["As_req"], capacity=span_bars["As_prov"], unit="mm²")
            audit.add(f"{tag} — Flexure at support", CheckStatus.PASS if supp_bars["As_prov"] >= supp_flex["As_req"] else CheckStatus.FAIL,
                      demand=supp_flex["As_req"], capacity=supp_bars["As_prov"], unit="mm²")
            audit.add(f"{tag} — Shear", CheckStatus.PASS if shear["status"] == "PASS" else CheckStatus.FAIL if shear["status"] == "FAIL" else CheckStatus.NOT_CHECKED,
                      demand=shear.get("v"), capacity=shear.get("v_max"), unit="N/mm²", message=shear.get("message", ""))
            if deflection_status == "NOT CHECKED":
                audit.add(
                    f"{tag} — Deflection (span/depth screening)", CheckStatus.NOT_CHECKED,
                    demand=round(actual_span_d, 2), unit="span/d",
                    message="Deflection not assessed because no valid longitudinal bar arrangement was selected.",
                )
            elif self.code == "BS8110":
                audit.add(f"{tag} — Deflection (span/depth screening)", CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
                          demand=round(actual_span_d, 2), capacity=allowable_span_d, unit="span/d",
                          message="Simplified BS 8110 3.4.6 screening check; not a full long-term deflection calculation.")
            else:
                audit.add(f"{tag} — Deflection (span/depth screening)", CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
                          demand=round(actual_span_d, 2), capacity=allowable_span_d, unit="span/d",
                          message="EN 1992-1-1 7.4.2 span/depth screening using Expressions (7.16) and "
                                  "the UK NA cap; not a full long-term deflection calculation.")
            if detailing_note:
                audit.add(f"{tag} — Bar fit", CheckStatus.FAIL,
                          message=detailing_note)

            span_results.append({
                "span_index": i, "length_m": self.spans[i], "b_w": b_w, "h_overall": h, "d_eff_mm": d,
                "gk_total_kN_m": round(gk_total_list[i], 3), "qk_total_kN_m": round(qk_total_list[i], 3),
                "w_ult_kN_m": round(gamma_g * gk_total_list[i] + gamma_q * qk_total_list[i], 3),
                "M_span_kNm": round(M_span, 3), "M_support_kNm": round(M_support, 3), "V_design_kN": round(V_design, 3),
                "M_left_support_kNm": round(envelope[i].M_left_support_kNm, 3),
                "M_right_support_kNm": round(envelope[i].M_right_support_kNm, 3),
                "span_bars": span_bars, "supp_bars": supp_bars, "link_schedule": link_schedule,
                "shear_status": shear["status"], "deflection_status": deflection_status,
                "actual_span_d": round(actual_span_d, 2), "allowable_span_d": allowable_span_d,
                "detailing_note": detailing_note,
            })

        governing = max(span_results, key=lambda s: s["span_bars"]["As_prov"] + s["supp_bars"]["As_prov"])
        # Pair the permanent and variable reactions at the SAME support.
        # Taking max(Gk) and max(Qk) independently can sum reactions from two
        # different supports and overstate the column load.
        reaction_index = max(
            range(n + 1), key=lambda j: gk_reactions[j] + qk_reactions[j]
        )
        reaction_gk = gk_reactions[reaction_index]
        reaction_qk = qk_reactions[reaction_index]

        overall_shear_status = "FAIL" if any(s["shear_status"] == "FAIL" for s in span_results) else (
            "NOT CHECKED" if any(s["shear_status"] == "NOT CHECKED" for s in span_results) else "PASS")
        overall_deflection_status = "FAIL" if any(s["deflection_status"] == "FAIL" for s in span_results) else (
            "NOT CHECKED" if any(s["deflection_status"] == "NOT CHECKED" for s in span_results) else "PASS")

        return {
            "analysis_method": "Matrix (slope-deflection) analysis with BS 8110/EC2-style pattern loading — arbitrary spans, independent length/width/depth per span.",
            "num_spans": n,
            "spans_detail": span_results,
            "gk_total_kN_m": governing["gk_total_kN_m"],
            "qk_total_kN_m": governing["qk_total_kN_m"],
            "w_ult_kN_m": round(gamma_g * governing["gk_total_kN_m"] + gamma_q * governing["qk_total_kN_m"], 3),
            "M_span_kNm": governing["M_span_kNm"],
            "M_support_kNm": governing["M_support_kNm"],
            "V_support_kN": governing["V_design_kN"],
            "span_bars": governing["span_bars"],
            "supp_bars": governing["supp_bars"],
            "link_schedule": governing["link_schedule"],
            "shear_status": overall_shear_status,
            "actual_span_d": governing["actual_span_d"],
            "allowable_span_d": governing["allowable_span_d"],
            "deflection_status": overall_deflection_status,
            "reaction_to_column_kN": round(reaction_gk + reaction_qk, 3),
            "reaction_gk_to_column_kN": round(reaction_gk, 3),
            "reaction_qk_to_column_kN": round(reaction_qk, 3),
            "audit": audit.as_dict(),
            "limitations": [
                "Both beam ends are assumed simply supported — fixed/built-in ends and cantilever overhangs are not yet implemented.",
                "Pattern loading covers all-spans-loaded, each single span loaded, alternate spans, and each adjacent pair; it does not search every possible 2^n combination, though these cases govern the vast majority of practical UDL-only continuous beams.",
                "Only uniformly distributed load is modelled — point loads are not yet supported.",
                "Deflection is a simplified span/effective-depth screening check, not a full long-term deflection analysis. Compression-steel modification is not applied to the BS 8110 check.",
                "EC2 shear uses the variable strut inclination method with cot(theta)=2.5; a full theta-optimisation and detailed link curtailment are not implemented.",
                "Only rectangular sections are supported — T-beam/L-beam (flanged section) design is not yet implemented.",
                "Beam bars are assumed to fit in ONE layer; arrangements needing two layers are reported as a FAIL rather than silently reducing the effective depth.",
                "The flat top-level fields (M_span_kNm, span_bars, etc.) report the GOVERNING span (the one with the largest reinforcement demand); see 'spans_detail' for the full per-span breakdown.",
            ],
        }
