import json
from pathlib import Path

from stock_factory import config
from stock_factory.local_pipeline.queue_builder import build_daily_queue
from stock_factory.local_pipeline.models import ProductionItem
from stock_factory.local_pipeline import state_store, orchestrator


def test_build_daily_queue_default_split():
    items = build_daily_queue('2026-11-10')
    photo = [i for i in items if i.content_type == 'photo']
    illustration = [i for i in items if i.content_type == 'illustration']
    assert len(photo) == config.DAILY_PHOTO_TARGET
    assert len(illustration) == config.DAILY_ILLUSTRATION_TARGET
    assert len(items) == config.DAILY_TOTAL_TARGET
    # every item has the required minimum fields populated
    for item in items:
        assert item.item_id
        assert item.date == '2026-11-10'
        assert item.prompt
        assert item.title_seed
        assert item.keyword_seed
        assert item.target_marketplace == 'magnific'
        assert item.status == 'queued'


def test_build_daily_queue_custom_split_and_determinism():
    a = build_daily_queue('2026-11-11', photo_target=3, illustration_target=2)
    b = build_daily_queue('2026-11-11', photo_target=3, illustration_target=2)
    assert len(a) == 5
    assert [i.item_id for i in a] == [i.item_id for i in b]
    assert [i.prompt for i in a] == [i.prompt for i in b]


def test_illustration_prompt_is_distinct_style_from_photo():
    items = build_daily_queue('2026-11-12', photo_target=1, illustration_target=1)
    photo_item = next(i for i in items if i.content_type == 'photo')
    illustration_item = next(i for i in items if i.content_type == 'illustration')
    assert 'vector-style illustration' in illustration_item.prompt
    assert 'vector-style illustration' not in photo_item.prompt


def test_production_item_roundtrip_through_dict():
    item = ProductionItem(
        item_id='PHOTO-20261110-0001', date='2026-11-10', content_type='photo',
        category='test', prompt='a test prompt', title_seed='a test',
        keyword_seed=['a', 'test'], dimensions=(2048, 2048),
    )
    restored = ProductionItem.from_dict(json.loads(json.dumps(item.to_dict())))
    assert restored == item


def test_state_store_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'LOCAL_PIPELINE_STATE_DIR', tmp_path / 'state')

    item = ProductionItem(
        item_id='PHOTO-20261110-0001', date='2026-11-10', content_type='photo',
        category='test', prompt='p', title_seed='t', keyword_seed=['t'],
        status='blocked_provider_not_implemented', retry_count=1, last_error='no provider',
    )
    state_store.record_item(item)
    state_store.record_failure(item, 'generation', 'no provider')

    resumed = state_store.load_today_items('2026-11-10')
    assert resumed['PHOTO-20261110-0001'].status == 'blocked_provider_not_implemented'
    assert resumed['PHOTO-20261110-0001'].retry_count == 1

    summary = state_store.write_daily_summary('2026-11-10', [item])
    assert summary['by_status']['blocked_provider_not_implemented'] == 1
    assert summary['uploaded'] == 0
    assert (tmp_path / 'state' / 'daily_summary' / '2026-11-10.json').exists()


def test_orchestrator_run_daily_blocks_cleanly_without_providers(tmp_path, monkeypatch):
    """With no real browser providers available (the honest state of
    Phase 1), every item must land in blocked_provider_not_implemented,
    be recorded in failures.jsonl, and the run must still complete and
    write a daily summary -- proving the skeleton works end-to-end
    without fabricating a successful generation."""
    monkeypatch.setattr(config, 'LOCAL_PIPELINE_STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr(config, 'LOCAL_PIPELINE_OUTPUT_DIR', tmp_path / 'output')
    monkeypatch.setattr(config, 'DAILY_PHOTO_TARGET', 2)
    monkeypatch.setattr(config, 'DAILY_ILLUSTRATION_TARGET', 1)
    monkeypatch.setattr(config, 'LOCAL_PIPELINE_MAX_RETRIES', 1)

    summary = orchestrator.run_daily('2026-11-13')

    assert summary['queued'] == 3
    assert summary['by_status']['blocked_provider_not_implemented'] == 3
    assert summary['archived'] == 0
    assert summary['uploaded'] == 0
    assert summary['failed'] == 3

    failures_path = tmp_path / 'state' / 'failures.jsonl'
    assert failures_path.exists()
    failure_lines = failures_path.read_text().strip().splitlines()
    assert len(failure_lines) == 3
    for line in failure_lines:
        record = json.loads(line)
        assert record['stage'] == 'generation'


def test_orchestrator_resumes_without_reprocessing_terminal_items(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'LOCAL_PIPELINE_STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr(config, 'LOCAL_PIPELINE_OUTPUT_DIR', tmp_path / 'output')
    monkeypatch.setattr(config, 'DAILY_PHOTO_TARGET', 1)
    monkeypatch.setattr(config, 'DAILY_ILLUSTRATION_TARGET', 0)
    monkeypatch.setattr(config, 'LOCAL_PIPELINE_MAX_RETRIES', 1)

    orchestrator.run_daily('2026-11-14')
    first_failures = (tmp_path / 'state' / 'failures.jsonl').read_text().strip().splitlines()

    # Second run for the same day: retry cap (1) already hit, so no new
    # failure records should be appended for the same item.
    orchestrator.run_daily('2026-11-14')
    second_failures = (tmp_path / 'state' / 'failures.jsonl').read_text().strip().splitlines()

    assert len(second_failures) == len(first_failures)
