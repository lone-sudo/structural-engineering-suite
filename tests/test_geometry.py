from core.geometry import GridGeometry, parse_spacings


def test_parse_spacings_accepts_comma_and_space_formats():
    assert parse_spacings("4, 5, 6") == (4.0, 5.0, 6.0)
    assert parse_spacings("4 5 6") == (4.0, 5.0, 6.0)


def test_grid_coordinates_and_adjacent_beams():
    g = GridGeometry((4.0, 5.0), (3.0, 3.0), ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)))
    assert g.x_coords == (0.0, 4.0, 9.0)
    assert g.y_coords == (0.0, 3.0, 6.0)
    assert len(g.beam_edges) == 7


def test_geometry_can_have_missing_columns():
    g = GridGeometry((4.0, 4.0), (4.0, 4.0), ((0, 0), (1, 0), (0, 1)))
    assert ((0, 0), (1, 0)) in g.beam_edges
    assert ((0, 0), (0, 1)) in g.beam_edges
    assert len(g.beam_edges) == 2
