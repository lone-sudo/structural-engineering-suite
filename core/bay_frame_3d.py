import plotly.graph_objects as go


class BayFrame3D:
    @staticmethod
    def plot_3d_geometry(geometry, storey_height=3.0, num_storeys=1, footing_size=1.5):
        """Render the engineer-defined grid/column geometry as a structural schematic."""
        fig = go.Figure()
        x_coords = geometry.x_coords
        y_coords = geometry.y_coords
        total_height = float(num_storeys) * float(storey_height)

        # Columns at selected grid intersections.
        for i, j in geometry.columns:
            x, y = x_coords[i], y_coords[j]
            fig.add_trace(go.Scatter3d(
                x=[x, x], y=[y, y], z=[0, total_height],
                mode="lines", line=dict(width=8), showlegend=False,
                hovertemplate=f"Column C{i+1}{j+1}<br>X={x:.2f} m<br>Y={y:.2f} m<extra></extra>",
            ))

        # Beams between adjacent selected columns at each elevated level.
        for level in range(1, int(num_storeys) + 1):
            z = level * storey_height
            for (a, b) in geometry.beam_edges:
                x1, y1 = x_coords[a[0]], y_coords[a[1]]
                x2, y2 = x_coords[b[0]], y_coords[b[1]]
                fig.add_trace(go.Scatter3d(
                    x=[x1, x2], y=[y1, y2], z=[z, z],
                    mode="lines", line=dict(width=6), showlegend=False,
                    hovertemplate=f"Beam L{level}<br>{x1:.2f},{y1:.2f} → {x2:.2f},{y2:.2f}<extra></extra>",
                ))

        # Light slab outlines; deliberately schematic rather than architectural.
        for level in range(1, int(num_storeys) + 1):
            z = level * storey_height
            fig.add_trace(go.Scatter3d(
                x=[x_coords[0], x_coords[-1], x_coords[-1], x_coords[0], x_coords[0]],
                y=[y_coords[0], y_coords[0], y_coords[-1], y_coords[-1], y_coords[0]],
                z=[z] * 5,
                mode="lines", line=dict(width=2, dash="dot"), showlegend=False,
                hovertemplate=f"Slab level {level}<extra></extra>",
            ))

        # Footing markers only under selected columns.
        half = footing_size / 2.0
        for i, j in geometry.columns:
            x, y = x_coords[i], y_coords[j]
            fx = [x-half, x+half, x+half, x-half, x-half]
            fy = [y-half, y-half, y+half, y+half, y-half]
            fig.add_trace(go.Scatter3d(
                x=fx, y=fy, z=[0]*5, mode="lines", line=dict(width=4),
                showlegend=False, hovertemplate=f"Pad footing at C{i+1}{j+1}<extra></extra>",
            ))

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            scene=dict(
                xaxis=dict(title="X (m)"), yaxis=dict(title="Y (m)"), zaxis=dict(title="Height (m)"),
                aspectmode="data", camera=dict(eye=dict(x=1.6, y=-1.6, z=1.2)),
            ), margin=dict(l=0, r=0, t=10, b=10), height=540,
        )
        return fig

    @staticmethod
    def plot_3d_bay(lx=4.0, ly=4.0, storey_height=3.0, num_storeys=2, footing_size=1.5):
        """Backward-compatible one-bay wrapper."""
        from core.geometry import GridGeometry
        geometry = GridGeometry((lx,), (ly,), ((0, 0), (1, 0), (1, 1), (0, 1)))
        return BayFrame3D.plot_3d_geometry(geometry, storey_height, num_storeys, footing_size)


plot_3d_building_bay = BayFrame3D.plot_3d_bay
