"""Unit tests for drive_archive.py using a fake Drive service -- no real
Google credentials or network access are needed or used."""
import hashlib
import json
from pathlib import Path

import pytest

from stock_factory import drive_archive


def _clear_all_drive_config(monkeypatch):
    for name in (
        'GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET', 'GOOGLE_OAUTH_REFRESH_TOKEN',
        'GOOGLE_SERVICE_ACCOUNT_JSON', 'DRIVE_ADOBE_FOLDER_ID', 'DRIVE_MAGNIFIC_FOLDER_ID',
    ):
        monkeypatch.setattr(f'stock_factory.config.{name}', '')


def test_not_configured_is_a_safe_noop(tmp_path, monkeypatch):
    _clear_all_drive_config(monkeypatch)
    f = tmp_path / 'a.jpg'
    f.write_bytes(b'x' * 10)
    result = drive_archive.archive(f, 'adobe')
    assert result == {'archived': False, 'queue': 'adobe', 'reason': 'drive_not_configured', 'file': 'a.jpg'}


def test_is_configured_requires_folder_ids_even_with_oauth(monkeypatch):
    _clear_all_drive_config(monkeypatch)
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_ID', 'id')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_SECRET', 'secret')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_REFRESH_TOKEN', 'refresh')
    assert drive_archive.is_configured() is False  # no folder IDs yet
    monkeypatch.setattr('stock_factory.config.DRIVE_ADOBE_FOLDER_ID', 'adobe-folder')
    monkeypatch.setattr('stock_factory.config.DRIVE_MAGNIFIC_FOLDER_ID', 'magnific-folder')
    assert drive_archive.is_configured() is True


def test_is_configured_true_via_oauth_without_service_account(monkeypatch):
    _clear_all_drive_config(monkeypatch)
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_ID', 'id')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_SECRET', 'secret')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_REFRESH_TOKEN', 'refresh')
    monkeypatch.setattr('stock_factory.config.DRIVE_ADOBE_FOLDER_ID', 'adobe-folder')
    monkeypatch.setattr('stock_factory.config.DRIVE_MAGNIFIC_FOLDER_ID', 'magnific-folder')
    assert drive_archive._oauth_configured() is True
    assert drive_archive._service_account_configured() is False
    assert drive_archive.is_configured() is True


def test_build_oauth_credentials_refreshes_with_refresh_token(monkeypatch):
    _clear_all_drive_config(monkeypatch)
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_ID', 'cid')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_SECRET', 'csecret')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_REFRESH_TOKEN', 'rtoken')

    refreshed = {'called': False}

    class _FakeCreds:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def refresh(self, request):
            refreshed['called'] = True

    monkeypatch.setattr(drive_archive, 'Credentials', _FakeCreds)
    monkeypatch.setattr(drive_archive, 'Request', lambda: None)

    creds = drive_archive._build_oauth_credentials()

    assert refreshed['called'] is True
    assert creds.kwargs['refresh_token'] == 'rtoken'
    assert creds.kwargs['client_id'] == 'cid'
    assert creds.kwargs['client_secret'] == 'csecret'
    assert creds.kwargs['scopes'] == drive_archive.OAUTH_SCOPES


def test_build_service_raises_clear_error_when_not_configured(monkeypatch):
    _clear_all_drive_config(monkeypatch)
    with pytest.raises(RuntimeError, match='not configured'):
        drive_archive._build_service()


def test_build_service_prefers_oauth_over_service_account(monkeypatch):
    _clear_all_drive_config(monkeypatch)
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_ID', 'cid')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_CLIENT_SECRET', 'csecret')
    monkeypatch.setattr('stock_factory.config.GOOGLE_OAUTH_REFRESH_TOKEN', 'rtoken')
    monkeypatch.setattr('stock_factory.config.GOOGLE_SERVICE_ACCOUNT_JSON', '{"type": "service_account"}')

    calls = {'oauth': 0, 'service_account': 0}
    monkeypatch.setattr(drive_archive, '_build_oauth_credentials', lambda: calls.__setitem__('oauth', calls['oauth'] + 1) or object())
    monkeypatch.setattr('googleapiclient.discovery.build', lambda *a, **k: 'fake-service')

    result = drive_archive._build_service()
    assert result == 'fake-service'
    assert calls['oauth'] == 1


def test_unknown_queue_raises(tmp_path):
    f = tmp_path / 'a.jpg'
    f.write_bytes(b'x')
    with pytest.raises(ValueError):
        drive_archive.archive(f, 'bogus')


class _FakeFilesResource:
    def __init__(self):
        self.store: dict[str, dict] = {}
        self._next_id = 1
        self.create_calls = 0
        self.list_calls = 0
        self.get_media_calls = 0
        self.delete_calls = 0

    def list(self, q, fields, pageSize):  # noqa: N803 -- mirrors Drive API kwarg casing
        self.list_calls += 1
        matches = [v for v in self.store.values() if not v.get('trashed')]
        return _FakeRequest({'files': matches})

    def create(self, body, media_body, fields):
        self.create_calls += 1
        file_id = f'file-{self._next_id}'
        self._next_id += 1
        data = Path(media_body._filename).read_bytes()
        self.store[file_id] = {
            'id': file_id, 'name': body['name'], 'properties': body.get('properties', {}),
            'data': data, 'trashed': False,
        }
        return _FakeRequest({'id': file_id, 'properties': body.get('properties', {})})

    def get_media(self, fileId):  # noqa: N803
        self.get_media_calls += 1
        return _FakeRequest(self.store[fileId]['data'])

    def delete(self, fileId):  # noqa: N803
        self.delete_calls += 1
        self.store.pop(fileId, None)
        return _FakeRequest(None)


class _FakeRequest:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _FakeService:
    def __init__(self):
        self._files = _FakeFilesResource()

    def files(self):
        return self._files


@pytest.fixture
def fake_service(monkeypatch):
    svc = _FakeService()
    monkeypatch.setattr(drive_archive, '_build_service', lambda: svc)
    monkeypatch.setattr('stock_factory.config.GOOGLE_SERVICE_ACCOUNT_JSON', '{"type": "service_account"}')
    monkeypatch.setattr('stock_factory.config.DRIVE_ADOBE_FOLDER_ID', 'adobe-folder')
    monkeypatch.setattr('stock_factory.config.DRIVE_MAGNIFIC_FOLDER_ID', 'magnific-folder')
    return svc


def test_archive_uploads_and_verifies_checksum(tmp_path, fake_service, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    f = tmp_path / 'photo-001.jpg'
    f.write_bytes(b'fake jpeg bytes' * 1000)
    expected_sha256 = hashlib.sha256(f.read_bytes()).hexdigest()

    result = drive_archive.archive(f, 'adobe')

    assert result['archived'] is True
    assert result['sha256'] == expected_sha256
    assert result['duplicate'] is False
    assert fake_service.files().create_calls == 1
    assert fake_service.files().get_media_calls == 1

    log_path = tmp_path / 'state' / 'drive_archive_log.jsonl'
    assert log_path.exists()
    logged = json.loads(log_path.read_text().strip().splitlines()[-1])
    assert logged['sha256'] == expected_sha256
    assert logged['file'] == 'photo-001.jpg'


def test_archive_skips_duplicate_by_name_and_sha256(tmp_path, fake_service, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    f = tmp_path / 'photo-002.jpg'
    f.write_bytes(b'same content' * 500)

    first = drive_archive.archive(f, 'magnific')
    second = drive_archive.archive(f, 'magnific')

    assert first['duplicate'] is False
    assert second['duplicate'] is True
    assert second['drive_file_id'] == first['drive_file_id']
    # Only one real upload happened; the second call was short-circuited.
    assert fake_service.files().create_calls == 1


def test_integrity_check_raises_on_mismatch(tmp_path, fake_service, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    f = tmp_path / 'photo-003.jpg'
    f.write_bytes(b'original bytes')

    real_create = fake_service.files().create

    def tampering_create(body, media_body, fields):
        resp = real_create(body, media_body, fields)
        file_id = resp.execute()['id']
        fake_service.files().store[file_id]['data'] = b'corrupted bytes'
        return resp

    monkeypatch.setattr(fake_service.files(), 'create', tampering_create)

    with pytest.raises(RuntimeError, match='integrity check failed'):
        drive_archive.archive(f, 'adobe')


def test_retry_eventually_succeeds(monkeypatch):
    calls = {'n': 0}

    def flaky():
        calls['n'] += 1
        if calls['n'] < 3:
            raise ConnectionError('transient')
        return 'ok'

    monkeypatch.setattr(drive_archive.time, 'sleep', lambda _: None)
    result = drive_archive._with_retries(flaky, what='test')
    assert result == 'ok'
    assert calls['n'] == 3


def test_retry_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(drive_archive.time, 'sleep', lambda _: None)

    def always_fails():
        raise ConnectionError('still down')

    with pytest.raises(RuntimeError, match='failed after 4 attempts'):
        drive_archive._with_retries(always_fails, what='test')


def test_verify_with_test_artifact_not_configured(monkeypatch):
    monkeypatch.setattr('stock_factory.config.GOOGLE_SERVICE_ACCOUNT_JSON', '')
    monkeypatch.setattr('stock_factory.config.DRIVE_ADOBE_FOLDER_ID', '')
    monkeypatch.setattr('stock_factory.config.DRIVE_MAGNIFIC_FOLDER_ID', '')
    result = drive_archive.verify_with_test_artifact()
    assert result == {'verified': False, 'reason': 'drive_not_configured'}


def test_verify_with_test_artifact_uploads_reads_back_and_deletes(fake_service):
    result = drive_archive.verify_with_test_artifact()
    assert result['verified'] is True
    assert 'sha256' in result
    # The test artifact must not be left behind in the target folder.
    assert fake_service.files().store == {}
