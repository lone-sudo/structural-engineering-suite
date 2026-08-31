import numpy as np
import plotly.graph_objects as go

class DiagramPlotter:
    """Generates analytical Bending Moment (BMD) and Shear Force (SFD) diagrams."""

    @staticmethod
    def plot_beam_bmd_sfd(span_m: float, w_ult_kN_m: float, num_spans: int = 2) -> go.Figure:
        """Plots live continuous beam shear force and bending moment diagrams."""
        total_length = span_m * num_spans
        x = np.linspace(0, total_length, 250)
        
        # Approximate multi-span continuous beam internal forces under UDL
        # Single span vs Multi-span moment envelopes
        if num_spans == 1:
            # Simply supported / pin-fixed idealization
            sfd = w_ult_kN_m * (span_m / 2.0 - x)
            bmd = (w_ult_kN_m * x / 2.0) * (span_m - x)
        else:
            # 2-span continuous distribution
            # Intermediate support reaction R_B = 1.25 * w * L
            sfd = np.zeros_like(x)
            bmd = np.zeros_like(x)
            for i, xi in enumerate(x):
                if xi <= span_m:
                    sfd[i] = 0.375 * w_ult_kN_m * span_m - w_ult_kN_m * xi
                    bmd[i] = (0.375 * w_ult_kN_m * span_m * xi) - (0.5 * w_ult_kN_m * xi**2)
                else:
                    x_rel = xi - span_m
                    sfd[i] = 0.625 * w_ult_kN_m * span_m - w_ult_kN_m * x_rel
                    bmd[i] = -0.125 * w_ult_kN_m * (span_m**2) + (0.625 * w_ult_kN_m * span_m * x_rel) - (0.5 * w_ult_kN_m * x_rel**2)

        fig = go.Figure()

        # 1. Bending Moment Diagram (BMD) - Plotted on tension side / standard civil convention
        fig.add_trace(go.Scatter(
            x=x, y=bmd, mode='lines', name='BMD (kNm)',
            line=dict(color='#e67e22', width=2.5),
            fill='tozeroy', fillcolor='rgba(230, 126, 34, 0.18)'
        ))

        # 2. Shear Force Diagram (SFD)
        fig.add_trace(go.Scatter(
            x=x, y=sfd, mode='lines', name='SFD (kN)',
            line=dict(color='#2980b9', width=2.0, dash='dash'),
            fill='tozeroy', fillcolor='rgba(41, 128, 185, 0.10)'
        ))

        # Support lines
        for s in range(num_spans + 1):
            fig.add_vline(x=s * span_m, line=dict(color='#7f8c8d', width=1.5, dash='dot'))

        fig.update_layout(
            title="Analysis Diagrams: Bending Moment ($M_u$) & Shear Force ($V_u$)",
            xaxis=dict(title="Beam Span Coordinate (m)", zeroline=True, zerolinecolor="#2c3e50"),
            yaxis=dict(title="Force / Moment (kN, kNm)", zeroline=True, zerolinecolor="#2c3e50"),
            hovermode="x unified",
            height=340,
            margin=dict(l=40, r=40, t=40, b=40),
            plot_bgcolor="#fcfcfc"
        )
        return fig