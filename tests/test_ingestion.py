from pipeline.pdf_reader import PDFPlanReader


def test_dxf_exports_produce_valid_readable_dxf():
    import ezdxf
    import io as _io
    from elements.beam import ContinuousBeam
    from elements.column import ColumnDesign
    from elements.footing import PadFooting
    from core.dxf_export import generate_beam_dxf, generate_column_dxf, generate_footing_dxf

    beam = ContinuousBeam(spans=[5, 5], b_w=250, h_overall=450, gk_slab=5, qk_slab=3,
                           wall_height=3, wall_thick=0.15, wall_unit_weight=19, f_cu=25, f_y=460, code="BS8110")
    b_res = beam.design_beam()
    beam_bytes = generate_beam_dxf(b_res, b_w=250, h_overall=450, cover=25, code="BS8110")
    beam_doc = ezdxf.read(_io.StringIO(beam_bytes.decode("utf-8")))
    assert len(list(beam_doc.modelspace())) > 0

    col = ColumnDesign(b=300, h=300, num_floors=3, Gk_beam_per_floor=60, Qk_beam_per_floor=30, f_cu=30, f_y=460, code="BS8110")
    col_res = col.design_column()
    col_bytes = generate_column_dxf(col_res, b=300, h=300, cover=25, code="BS8110")
    col_doc = ezdxf.read(_io.StringIO(col_bytes.decode("utf-8")))
    assert len(list(col_doc.modelspace())) > 0

    footing = PadFooting(N_service=500, N_ultimate=750, col_cx=300, col_cy=300, q_allowable=150, code="BS8110")
    L, Bd, _ = footing.size_plan_dimensions()
    f_res = footing.design_reinforcement_and_shear(L, Bd)
    foot_bytes = generate_footing_dxf(f_res, L, Bd, 300, 300, code="BS8110")
    foot_doc = ezdxf.read(_io.StringIO(foot_bytes.decode("utf-8")))
    assert len(list(foot_doc.modelspace())) > 0



def test_pdf_reader_returns_none_not_fabricated_defaults_when_nothing_found():
    # Minimal valid PDF with no structural text at all: nothing should be
    # silently defaulted to a plausible-looking number like 4.0/5.0 m or
    # 1350mm/150mm — the caller must be told nothing was detected.
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()

    parsed = PDFPlanReader.extract_plan_parameters(pdf_bytes)

    assert parsed["spans_detected"] is False
    assert parsed["spans_m"] is None
    assert parsed["slab_thick_detected"] is False
    assert parsed["detected_slab_thick"] is None
    assert parsed["pad_dim_detected"] is False
    assert parsed["detected_pad_dim"] is None
    assert parsed["fcu_detected"] is False
    assert parsed["fcu"] is None


def test_pdf_reader_detects_and_flags_explicit_values():
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "GRID SPANS 4000 5000 SLAB THICKNESS = 175MM BASE 1200MM CLASS 30")
    pdf_bytes = doc.tobytes()

    parsed = PDFPlanReader.extract_plan_parameters(pdf_bytes)

    assert parsed["spans_detected"] is True
    assert 4.0 in parsed["spans_m"] and 5.0 in parsed["spans_m"]
    assert parsed["slab_thick_detected"] is True
    assert parsed["detected_slab_thick"] == 175.0
    assert parsed["pad_dim_detected"] is True
    assert parsed["detected_pad_dim"] == 1200.0
    assert parsed["fcu_detected"] is True
    assert parsed["fcu"] == 30.0
