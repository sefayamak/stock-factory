import pytest
from stock_factory.scoring import ScoreInput, score
from stock_factory.vector.procedural_vector import (
    generate_polygon_icon, generate_repeating_pattern, validate_genuine_vector,
)
from stock_factory.acceptance_learning import LearningStore, RejectionRecord, MAGNIFIC_BASELINE


def test_score_defaults_to_zero_with_low_confidence():
    result = score(ScoreInput())
    assert result['priority_score'] == 0.0
    assert result['confidence'] == 'low_confidence_mostly_assumed'


def test_score_marks_observed_fields():
    inputs = ScoreInput(demand_evidence=0.8, historical_acceptance_rate=0.7,
                         revenue_signal=0.5, commercial_applicability=0.6, timeliness=0.4,
                         observed_fields={'demand_evidence', 'historical_acceptance_rate', 'revenue_signal', 'commercial_applicability', 'timeliness'})
    result = score(inputs)
    assert result['priority_score'] > 0
    assert result['confidence'] == 'observed'
    assert result['breakdown']['demand_evidence']['observed'] is True
    assert result['breakdown']['competition']['observed'] is False


def test_polygon_icon_is_genuine_vector():
    asset = generate_polygon_icon(sides=6)
    ok, reason = validate_genuine_vector(asset.svg)
    assert ok, reason
    assert '<polygon' in asset.svg


def test_pattern_is_genuine_vector():
    asset = generate_repeating_pattern(grid=4)
    ok, _ = validate_genuine_vector(asset.svg)
    assert ok
    assert asset.svg.count('<circle') == 16


def test_raster_in_svg_wrapper_is_rejected():
    fake = '<svg><image href="data:image/png;base64,abc" /></svg>'
    ok, reason = validate_genuine_vector(fake)
    assert not ok and reason == 'raster_embedded_in_svg_container'


def test_learning_store_records_and_summarizes(tmp_path):
    store = LearningStore(tmp_path)
    store.record_rejection(RejectionRecord('a1', 'magnific', 'weak_anatomy', None, True))
    store.record_acceptance('a2', 'adobe')
    summary = store.summary()
    assert summary['baseline'] == MAGNIFIC_BASELINE
    assert summary['logged_accepted'] == 1
    assert summary['logged_rejection_by_category'] == {'weak_anatomy': 1}


def test_learning_store_rejects_unknown_category(tmp_path):
    store = LearningStore(tmp_path)
    with pytest.raises(ValueError):
        store.record_rejection(RejectionRecord('a1', 'magnific', 'made_up_reason', None, True))


def test_genuine_svg_vector_passes_qc():
    from stock_factory.qc import validate_svg_vector
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0 L10 10"/></svg>'
    ok, reason = validate_svg_vector(svg.encode('utf-8'))
    assert ok and reason == 'pass'


def test_embedded_raster_image_tag_rejected():
    from stock_factory.qc import validate_svg_vector
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><image href="photo.png" width="10" height="10"/></svg>'
    ok, reason = validate_svg_vector(svg.encode('utf-8'))
    assert not ok and reason == 'embedded_raster_image_tag'


def test_embedded_base64_raster_data_uri_rejected():
    from stock_factory.qc import validate_svg_vector
    svg = ('<svg xmlns="http://www.w3.org/2000/svg">'
           '<image href="data:image/png;base64,AAAA" width="10" height="10"/></svg>')
    ok, reason = validate_svg_vector(svg.encode('utf-8'))
    assert not ok and reason == 'embedded_raster_data_uri'


def test_svg_with_no_vector_geometry_rejected():
    from stock_factory.qc import validate_svg_vector
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><title>empty</title></svg>'
    ok, reason = validate_svg_vector(svg.encode('utf-8'))
    assert not ok and reason == 'no_vector_geometry_found'


def test_malformed_svg_rejected():
    from stock_factory.qc import validate_svg_vector
    ok, reason = validate_svg_vector(b'<svg><path d="M0 0"></svg_oops>')
    assert not ok and reason.startswith('invalid_svg_xml')


def test_non_svg_root_rejected():
    from stock_factory.qc import validate_svg_vector
    ok, reason = validate_svg_vector(b'<notsvg><path d="M0 0"/></notsvg>')
    assert not ok and reason == 'not_an_svg_root_element'


def test_procedural_vector_module_output_passes_svg_qc():
    from stock_factory.qc import validate_svg_vector
    from stock_factory.vector.procedural_vector import generate_polygon_icon
    asset = generate_polygon_icon(sides=6)
    ok, reason = validate_svg_vector(asset.svg.encode('utf-8'))
    assert ok and reason == 'pass'
