from core.help_assistant import search


def test_status_meaning_query_finds_the_right_faq_entry():
    results = search("what does not checked mean")
    assert results, "expected at least one match"
    top_ids = [e["id"] for _, e in results]
    assert "status-meaning" in top_ids or "not-checked-vs-pass" in top_ids


def test_dxf_query_finds_dxf_faq():
    results = search("my dxf file will not open in autocad")
    assert results
    assert results[0][1]["id"] == "dxf-wont-open"


def test_linking_checkbox_query_finds_linking_faq():
    results = search("what does the pull beam reaction checkbox do")
    assert results
    top_ids = [e["id"] for _, e in results]
    assert "linking-checkboxes" in top_ids


def test_irrelevant_query_returns_nothing_rather_than_a_bad_guess():
    results = search("what is the capital of france")
    assert results == []


def test_dynamic_entries_surface_real_audit_messages_not_invented_text():
    fake_results = {
        "beam": {
            "audit": {
                "checks": [
                    {"name": "Shear", "status": "FAIL", "message": "Applied shear exceeds concrete strut crushing capacity."}
                ]
            },
            "limitations": ["Deflection is a screening check, not a full analysis."],
        }
    }
    results = search("beam shear fail", design_results=fake_results)
    assert results
    answers = [e["answer"] for _, e in results]
    assert "Applied shear exceeds concrete strut crushing capacity." in answers


def test_footing_result_wrapped_in_result_key_is_still_searchable():
    fake_results = {
        "footing": {
            "result": {
                "audit": {"checks": [{"name": "Service bearing pressure", "status": "FAIL", "message": "Bearing exceeds allowable soil capacity."}]},
                "limitations": [],
            },
            "pad_L": 1.5,
            "pad_B": 1.5,
        }
    }
    results = search("footing bearing pressure fail", design_results=fake_results)
    assert results
    answers = [e["answer"] for _, e in results]
    assert "Bearing exceeds allowable soil capacity." in answers
