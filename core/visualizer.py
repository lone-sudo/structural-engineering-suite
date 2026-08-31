import plotly.graph_objects as go
import numpy as np

class SectionVisualizer:
    """Generates 2D parametric cross-section drawings for concrete structural elements."""

    @staticmethod
    def draw_beam_section(b: float, h: float, cover: float, num_top: int, dia_top: int, num_bot: int, dia_bot: int, link_dia: int = 8) -> go.Figure:
        """Renders an interactive 2D cross-section of a reinforced concrete beam."""
        fig = go.Figure()

        # 1. Concrete Outline
        fig.add_shape(
            type="rect", x0=0, y0=0, x1=b, y1=h,
            line=dict(color="#4da6ff", width=2.5),
            fillcolor="rgba(100, 110, 120, 0.25)"
        )

        # 2. Shear Link / Stirrup Outline
        link_x0 = cover + (link_dia / 2.0)
        link_y0 = cover + (link_dia / 2.0)
        link_x1 = b - cover - (link_dia / 2.0)
        link_y1 = h - cover - (link_dia / 2.0)

        fig.add_shape(
            type="rect", x0=link_x0, y0=link_y0, x1=link_x1, y1=link_y1,
            line=dict(color="#e74c3c", width=2.0),
            fillcolor="rgba(0, 0, 0, 0)"
        )

        # 3. Bottom Tension Bars
        bot_y = cover + link_dia + (dia_bot / 2.0)
        if num_bot == 1:
            bot_xs = [b / 2.0]
        else:
            bot_x_start = cover + link_dia + (dia_bot / 2.0)
            bot_x_end = b - cover - link_dia - (dia_bot / 2.0)
            bot_xs = np.linspace(bot_x_start, bot_x_end, num_bot)

        for x in bot_xs:
            fig.add_shape(
                type="circle",
                x0=x - dia_bot/2.0, y0=bot_y - dia_bot/2.0,
                x1=x + dia_bot/2.0, y1=bot_y + dia_bot/2.0,
                fillcolor="#00bcd4", line=dict(color="#ffffff", width=1.0)
            )

        # 4. Top Compression / Hanger Bars
        top_y = h - cover - link_dia - (dia_top / 2.0)
        if num_top == 1:
            top_xs = [b / 2.0]
        else:
            top_x_start = cover + link_dia + (dia_top / 2.0)
            top_x_end = b - cover - link_dia - (dia_top / 2.0)
            top_xs = np.linspace(top_x_start, top_x_end, num_top)

        for x in top_xs:
            fig.add_shape(
                type="circle",
                x0=x - dia_top/2.0, y0=top_y - dia_top/2.0,
                x1=x + dia_top/2.0, y1=top_y + dia_top/2.0,
                fillcolor="#2ecc71", line=dict(color="#ffffff", width=1.0)
            )

        hover_x = list(bot_xs) + list(top_xs)
        hover_y = [bot_y]*len(bot_xs) + [top_y]*len(top_xs)
        hover_text = [f"Bottom Tension Bar: Y{dia_bot}"]*len(bot_xs) + [f"Top Bar: Y{dia_top}"]*len(top_xs)

        fig.add_trace(go.Scatter(
            x=hover_x, y=hover_y, mode="markers",
            marker=dict(size=1, opacity=0),
            text=hover_text, hoverinfo="text"
        ))

        fig.update_layout(
            title=dict(text=f"Beam Section ({int(b)}mm × {int(h)}mm)", font=dict(color="#e0e0e0", size=13)),
            xaxis=dict(title=dict(text="Width (mm)", font=dict(color="#aaaaaa")), tickfont=dict(color="#aaaaaa"), gridcolor="#333333", zeroline=False, range=[-20, b + 20]),
            yaxis=dict(title=dict(text="Depth (mm)", font=dict(color="#aaaaaa")), tickfont=dict(color="#aaaaaa"), gridcolor="#333333", zeroline=False, range=[-20, h + 20]),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.03)",
            showlegend=False,
            height=320,
            margin=dict(l=30, r=30, t=40, b=30)
        )
        return fig

    @staticmethod
    def draw_column_section(b: float, h: float, cover: float, num_bars: int, bar_dia: int, link_dia: int = 8) -> go.Figure:
        """Renders an interactive 2D cross-section of a reinforced concrete column."""
        fig = go.Figure()

        # Concrete Section
        fig.add_shape(
            type="rect", x0=0, y0=0, x1=b, y1=h,
            line=dict(color="#4da6ff", width=2.5),
            fillcolor="rgba(100, 110, 120, 0.25)"
        )

        # Confining Link / Tie
        lx0 = cover + link_dia / 2.0
        ly0 = cover + link_dia / 2.0
        lx1 = b - cover - link_dia / 2.0
        ly1 = h - cover - link_dia / 2.0

        fig.add_shape(
            type="rect", x0=lx0, y0=ly0, x1=lx1, y1=ly1,
            line=dict(color="#e74c3c", width=2.0),
            fillcolor="rgba(0, 0, 0, 0)"
        )

        # Corner bar positions
        c_x0 = cover + link_dia + (bar_dia / 2.0)
        c_x1 = b - cover - link_dia - (bar_dia / 2.0)
        c_y0 = cover + link_dia + (bar_dia / 2.0)
        c_y1 = h - cover - link_dia - (bar_dia / 2.0)

        bar_coords = [(c_x0, c_y0), (c_x1, c_y0), (c_x0, c_y1), (c_x1, c_y1)]
        if num_bars == 6:
            bar_coords.extend([(b/2.0, c_y0), (b/2.0, c_y1)])
        elif num_bars == 8:
            bar_coords.extend([(b/2.0, c_y0), (b/2.0, c_y1), (c_x0, h/2.0), (c_x1, h/2.0)])

        for bx, by in bar_coords:
            fig.add_shape(
                type="circle",
                x0=bx - bar_dia/2.0, y0=by - bar_dia/2.0,
                x1=bx + bar_dia/2.0, y1=by + bar_dia/2.0,
                fillcolor="#00bcd4", line=dict(color="#ffffff", width=1.0)
            )

        fig.add_trace(go.Scatter(
            x=[pt[0] for pt in bar_coords],
            y=[pt[1] for pt in bar_coords],
            mode="markers",
            marker=dict(size=1, opacity=0),
            text=[f"Main Bar: Y{bar_dia}"] * len(bar_coords),
            hoverinfo="text"
        ))

        fig.update_layout(
            title=dict(text=f"Column Section ({int(b)}mm × {int(h)}mm)", font=dict(color="#e0e0e0", size=13)),
            xaxis=dict(title=dict(text="Width (mm)", font=dict(color="#aaaaaa")), tickfont=dict(color="#aaaaaa"), gridcolor="#333333", zeroline=False, range=[-20, b + 20]),
            yaxis=dict(title=dict(text="Depth (mm)", font=dict(color="#aaaaaa")), tickfont=dict(color="#aaaaaa"), gridcolor="#333333", zeroline=False, range=[-20, h + 20]),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.03)",
            showlegend=False,
            height=320,
            margin=dict(l=30, r=30, t=40, b=30)
        )
        return fig

    @staticmethod
    def draw_footing_elevation(pad_L_m: float, pad_h_mm: float, col_dim_mm: float, cover_mm: float = 50.0, bar_dia: int = 12) -> go.Figure:
        """Renders the elevation section of the foundation pad footing and column stub."""
        fig = go.Figure()
        L_mm = pad_L_m * 1000.0

        # Blinding Layer (50mm)
        fig.add_shape(
            type="rect", x0=-40, y0=-40, x1=L_mm + 40, y1=0,
            line=dict(color="#7f8c8d", width=1.0, dash="dot"),
            fillcolor="rgba(120, 120, 120, 0.15)"
        )

        # Main Pad Base
        fig.add_shape(
            type="rect", x0=0, y0=0, x1=L_mm, y1=pad_h_mm,
            line=dict(color="#4da6ff", width=2.5),
            fillcolor="rgba(100, 110, 120, 0.25)"
        )

        # Column Stub
        col_x0 = (L_mm - col_dim_mm) / 2.0
        col_x1 = col_x0 + col_dim_mm
        fig.add_shape(
            type="rect", x0=col_x0, y0=pad_h_mm, x1=col_x1, y1=pad_h_mm + 300.0,
            line=dict(color="#4da6ff", width=2.0),
            fillcolor="rgba(100, 110, 120, 0.35)"
        )

        # Bottom Reinforcement Mat
        mat_y = cover_mm + (bar_dia / 2.0)
        mat_x0 = cover_mm
        mat_x1 = L_mm - cover_mm
        hook_h = min(pad_h_mm - 2*cover_mm, 100.0)

        fig.add_trace(go.Scatter(
            x=[mat_x0, mat_x0, mat_x1, mat_x1],
            y=[mat_y + hook_h, mat_y, mat_y, mat_y + hook_h],
            mode="lines",
            line=dict(color="#00bcd4", width=3.0),
            name="Bottom Rebar Mat"
        ))

        fig.update_layout(
            title=dict(text=f"Footing Elevation ({pad_L_m:.2f}m Base)", font=dict(color="#e0e0e0", size=13)),
            xaxis=dict(title=dict(text="Length (mm)", font=dict(color="#aaaaaa")), tickfont=dict(color="#aaaaaa"), gridcolor="#333333", zeroline=False, range=[-80, L_mm + 80]),
            yaxis=dict(title=dict(text="Height (mm)", font=dict(color="#aaaaaa")), tickfont=dict(color="#aaaaaa"), gridcolor="#333333", zeroline=False, range=[-60, pad_h_mm + 350]),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.03)",
            showlegend=False,
            height=320,
            margin=dict(l=30, r=30, t=40, b=30)
        )
        return fig