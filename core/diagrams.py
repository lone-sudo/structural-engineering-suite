import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class DiagramPlotter:
    """Generates bending-moment and shear-force diagrams from the ACTUAL
    continuous-beam analysis results, not a hard-coded two-span formula.

    The previous implementation plotted a fixed wL^2/8 / 0.375wL pattern for
    any equal-span beam and used the governing span's load for every span.
    That did not represent the calculation that produced the reinforcement,
    so it has been replaced by a plot built directly from the per-span
    end moments and shears in ``spans_detail``.
    """

    @staticmethod
    def plot_beam_diagrams(spans_detail, default_w_ult: float | None = None) -> go.Figure:
        if not spans_detail:
            raise ValueError("At least one span result is required.")

        x_all, m_all, v_all = [], [], []
        supports = [0.0]
        offset = 0.0
        for i, span in enumerate(spans_detail):
            L = float(span["length_m"])
            w = float(span.get("w_ult_kN_m", default_w_ult or 0.0))
            M_left = abs(float(span.get("M_left_support_kNm", 0.0)))
            M_right = abs(float(span.get("M_right_support_kNm", 0.0)))
            V_left = float(span.get("V_left_kN", 0.0))

            x = np.linspace(0.0, L, 81)
            # Sagging-positive internal moment for a UDL span with hogging
            # end moments of magnitude M_left / M_right.
            m = w * x * (L - x) / 2.0 - (M_left * (1.0 - x / L) + M_right * (x / L))
            v = V_left - w * x

            if i > 0:
                x = x[1:]
                m = m[1:]
                v = v[1:]
            x_all.extend((x + offset).tolist())
            m_all.extend(m.tolist())
            v_all.extend(v.tolist())
            offset += L
            supports.append(offset)

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
            subplot_titles=("Bending moment (kNm)", "Shear force (kN)"),
        )

        fig.add_trace(
            go.Scatter(
                x=x_all, y=m_all, mode="lines", name="BMD",
                line=dict(color="#d35400", width=2.4),
                fill="tozeroy", fillcolor="rgba(211, 84, 0, 0.16)",
                hovertemplate="x=%{x:.2f} m<br>M=%{y:.1f} kNm<extra></extra>",
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x_all, y=v_all, mode="lines", name="SFD",
                line=dict(color="#2471a3", width=2.0),
                hovertemplate="x=%{x:.2f} m<br>V=%{y:.1f} kN<extra></extra>",
            ),
            row=2, col=1,
        )

        for s in supports:
            for row in (1, 2):
                fig.add_vline(
                    x=s, line=dict(color="#7f8c8d", width=1.2, dash="dot"),
                    row=row, col=1,
                )

        fig.update_xaxes(title_text="Beam length (m)", row=2, col=1)
        fig.update_yaxes(title_text="M (kNm)", row=1, col=1, zeroline=True, zerolinecolor="#566573")
        fig.update_yaxes(title_text="V (kN)", row=2, col=1, zeroline=True, zerolinecolor="#566573")
        fig.update_layout(
            height=520,
            margin=dict(l=50, r=30, t=50, b=40),
            paper_bgcolor="white",
            plot_bgcolor="white",
            template="plotly_white",
            hovermode="x unified",
            showlegend=False,
        )
        return fig

    @staticmethod
    def plot_beam_bmd_sfd(span_m: float, w_ult_kN_m: float, num_spans: int = 2) -> go.Figure:
        """Deprecated: idealised equal-span preview only.

        Kept for callers that only have a span/load pair. New code should
        use :meth:`plot_beam_diagrams` with the real analysis results.
        """
        span_m = float(span_m)
        w = float(w_ult_kN_m)
        if num_spans == 1:
            detail = [{
                "length_m": span_m, "w_ult_kN_m": w,
                "M_left_support_kNm": 0.0, "M_right_support_kNm": 0.0,
                "V_left_kN": w * span_m / 2.0,
            }]
        else:
            # Exact equal-span, all-spans-loaded elastic result for a
            # two-span preview; not used for design.
            detail = []
            for i in range(int(num_spans)):
                detail.append({
                    "length_m": span_m, "w_ult_kN_m": w,
                    "M_left_support_kNm": 0.0 if i == 0 else w * span_m**2 / 8.0,
                    "M_right_support_kNm": 0.0 if i == int(num_spans) - 1 else w * span_m**2 / 8.0,
                    "V_left_kN": 0.375 * w * span_m if i == 0 else 0.625 * w * span_m,
                })
        return DiagramPlotter.plot_beam_diagrams(detail)
