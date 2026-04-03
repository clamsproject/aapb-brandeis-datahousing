import json
import os
import shutil
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from typing import Union

from mmif.utils.workflow_helper import generate_param_hash


# Minimal MMIF with one view from one app
# probably not a good idea to hardcode half-baked MMIF examples 
# we will figure something out to programmatically generate these in the future
SINGLE_APP_MMIF = json.dumps({
    "metadata": {"mmif": "http://mmif.clams.ai/1.0.4"},
    "documents": [
        {
            "@type": "http://mmif.clams.ai/vocabulary/VideoDocument/v1",
            "properties": {
                "mime": "video",
                "id": "m1",
                "location": "file:///data/cpb-aacip-507-154dn40c26.mp4"
            }
        }
    ],
    "views": [
        {
            "id": "v_0",
            "metadata": {
                "timestamp": "2025-04-20T23:39:11.465689",
                "app": "http://apps.clams.ai/swt-detection/v7.4",
                "contains": {},
                "parameters": {"pretty": "true"}
            },
            "annotations": [
                {
                    "@type": "http://mmif.clams.ai/vocabulary/TimePoint/v4",
                    "properties": {"timePoint": 0, "label": "-", "id": "tp_1"}
                }
            ]
        }
    ]
})

# MMIF with two apps in sequence
TWO_APP_MMIF = json.dumps({
    "metadata": {"mmif": "http://mmif.clams.ai/1.0.4"},
    "documents": [
        {
            "@type": "http://mmif.clams.ai/vocabulary/VideoDocument/v1",
            "properties": {
                "mime": "video",
                "id": "m1",
                "location": "file:///data/cpb-aacip-507-v40js9j432.mp4"
            }
        }
    ],
    "views": [
        {
            "id": "v_0",
            "metadata": {
                "timestamp": "2025-04-20T23:00:00.000000",
                "app": "http://apps.clams.ai/swt-detection/v7.4",
                "contains": {},
                "parameters": {"pretty": "true"}
            },
            "annotations": [
                {
                    "@type": "http://mmif.clams.ai/vocabulary/TimePoint/v4",
                    "properties": {"timePoint": 0, "label": "-", "id": "tp_1"}
                }
            ]
        },
        {
            "id": "v_1",
            "metadata": {
                "timestamp": "2025-04-20T23:10:00.000000",
                "app": "http://apps.clams.ai/doctr-wrapper/v1.2",
                "contains": {},
                "parameters": {"tfLabel": "chyron"}
            },
            "annotations": [
                {
                    "@type": "http://mmif.clams.ai/vocabulary/TextDocument/v1",
                    "properties": {"id": "td_1"}
                }
            ]
        }
    ]
})

# MMIF with no views (only documents)
NO_VIEWS_MMIF = json.dumps({
    "metadata": {"mmif": "http://mmif.clams.ai/1.0.4"},
    "documents": [
        {
            "@type": "http://mmif.clams.ai/vocabulary/VideoDocument/v1",
            "properties": {
                "mime": "video",
                "id": "m1",
                "location": "file:///data/cpb-aacip-507-154dn40c26.mp4"
            }
        }
    ],
    "views": []
})

# temporary directory for all tests
TEMP_STORAGE = tempfile.mkdtemp()

# Using some simple custom logging, should probably use the Python logger.
LOGGING = False
def log(message: str, fname='tmp.log', level='DEBUG'):
    if LOGGING:
        with open(fname, 'a') as fh:
            fh.write(f'{level} {message}\n')


def create_app_for_testing(storage_dir):
    """Create a Flask app configured for testing."""
    log(f'create_app_for_testing :: storage_dir={storage_dir}')
    os.environ['STORAGE_DIR'] = storage_dir
    import api
    # patch the module-level STORAGE_DIR which is set at import time
    api.STORAGE_DIR = storage_dir
    from api import create_app
    app = create_app(build_db=False)
    app.config['TESTING'] = True
    return app


def clear_directory(directory_path: Union[str, Path]) -> list:
    """Irreversibly removes all files and folders inside the specified
    directory. Assumes we have permission to delete."""
    for path_object in Path(directory_path).iterdir():
        if path_object.is_dir():
            shutil.rmtree(path_object)
        else:
            path_object.unlink()


class TestUpload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = TEMP_STORAGE
        Path(cls.tmpdir).mkdir(exist_ok=True)
        clear_directory(cls.tmpdir)

    def setUp(self):
        self.tmpdir = self.__class__.tmpdir
        self.app = create_app_for_testing(self.tmpdir)
        self.client = self.app.test_client()
        # also patch the imported reference in mmif_storage
        self._patcher = mock.patch('api.STORAGE_DIR', self.tmpdir)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_upload_single_app(self):
        resp = self.client.post('/storeapi/upload', data=SINGLE_APP_MMIF)
        data = resp.get_json()
        self.assertIn(resp.status_code, (200, 201))
        self.assertIn(data['status'], ('success', 'warning'))
        # check storage path structure: should be
        # STORAGE_DIR/swt-detection/v7.4/<hash>/cpb-aacip-507-154dn40c26.mmif
        param_hash = generate_param_hash({"pretty": "true"})
        expected = (Path(self.tmpdir) / 'swt-detection' / 'v7.4'
                    / param_hash / 'cpb-aacip-507-154dn40c26.mmif')
        self.assertTrue(expected.exists(), f"Expected {expected} to exist")

    def test_upload_no_source_prefix(self):
        """Workflow ID should NOT have a source document count prefix."""
        resp = self.client.post('/storeapi/upload', data=SINGLE_APP_MMIF)
        self.assertIn(resp.status_code, (200, 201))
        # the first directory under STORAGE_DIR should be an app name,
        # NOT something like "VideoDocument-1"
        children = list(Path(self.tmpdir).iterdir())
        child_names = [c.name for c in children if c.is_dir()]
        for name in child_names:
            log(f'test_upload_no_source_prefix :: {name}')
            self.assertNotIn(
                'Document', name,
                f"Source prefix found in storage path: {name}")

    def test_upload_two_apps(self):
        resp = self.client.post('/storeapi/upload', data=TWO_APP_MMIF)
        data = resp.get_json()
        self.assertIn(resp.status_code, (200, 201))
        self.assertIn(data['status'], ('success', 'warning'))
        hash1 = generate_param_hash({"pretty": "true"})
        hash2 = generate_param_hash({"tfLabel": "chyron"})
        expected = (Path(self.tmpdir)
                    / 'swt-detection' / 'v7.4' / hash1
                    / 'doctr-wrapper' / 'v1.2' / hash2
                    / 'cpb-aacip-507-v40js9j432.mmif')
        self.assertTrue(expected.exists(), f"Expected {expected} to exist")

    def test_upload_writes_param_json(self):
        resp = self.client.post('/storeapi/upload', data=SINGLE_APP_MMIF)
        self.assertIn(resp.status_code, (200, 201))
        param_hash = generate_param_hash({"pretty": "true"})
        param_json_path = (
            Path(self.tmpdir) / 'swt-detection' / 'v7.4' / f'{param_hash}.json')
        self.assertTrue(param_json_path.exists())
        with open(param_json_path) as f:
            saved_params = json.load(f)
        self.assertEqual(saved_params, {"pretty": "true"})

    def test_upload_duplicate_not_overwritten(self):
        self.client.post('/storeapi/upload', data=SINGLE_APP_MMIF)
        resp = self.client.post('/storeapi/upload', data=SINGLE_APP_MMIF)
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['status'], 'warning')
        self.assertIn('already exists', data['message'])

    def test_upload_duplicate_with_overwrite(self):
        self.client.post('/storeapi/upload', data=SINGLE_APP_MMIF)
        resp = self.client.post(
            '/storeapi/upload?overwrite=true', data=SINGLE_APP_MMIF)
        data = resp.get_json()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(data['status'], 'success')
        self.assertIn('overwritten', data['message'])

    def test_upload_no_views(self):
        resp = self.client.post('/storeapi/upload', data=NO_VIEWS_MMIF)
        data = resp.get_json()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(data['status'], 'error')

 
class TestDownload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = TEMP_STORAGE
        Path(cls.tmpdir).mkdir(exist_ok=True)
        clear_directory(cls.tmpdir)

    def setUp(self):
        self.tmpdir = self.__class__.tmpdir
        self.app = create_app_for_testing(self.tmpdir)
        self.client = self.app.test_client()
        self._patcher = mock.patch('api.STORAGE_DIR', self.tmpdir)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def _store_mmif_at(self, workflow_path, guid, content='{}'):
        """Helper to place a MMIF file at the expected storage path."""
        full_path = Path(self.tmpdir) / workflow_path
        full_path.mkdir(parents=True, exist_ok=True)
        mmif_file = full_path / f'{guid}.mmif'
        mmif_file.write_text(content)
        return mmif_file

    def test_download_does_not_crash(self):
        """Regression: download must not crash with a JSON payload."""
        payload = json.dumps({
            "workflow": {"swt-detection/v7.4": {"pretty": "true"}},
            "guid": "no-such-guid"})
        resp = self.client.post(
            '/storeapi/download',
            data=payload,
            content_type='application/json')
        # should not be 500
        self.assertNotEqual(resp.status_code, 500)

    def test_download_empty_params(self):
        """Download with empty params should use the same hash as upload."""
        guid = 'cpb-aacip-test'
        param_hash = generate_param_hash({})
        wf_path = f'swt-detection/v7.4/{param_hash}'
        self._store_mmif_at(wf_path, guid, json.dumps({"empty": True}))
        payload = json.dumps({
            "workflow": {"swt-detection/v7.4": {}},
            "guid": guid})
        resp = self.client.post(
            '/storeapi/download',
            data=payload,
            content_type='application/json')
        data = resp.get_json()
        self.assertEqual(data, {"empty": True})

    def test_download_single_guid(self):
        guid = 'cpb-aacip-507-154dn40c26'
        params = {"pretty": "true"}
        param_hash = generate_param_hash(params)
        wf_path = f'swt-detection/v7.4/{param_hash}'
        mmif_content = json.dumps({"test": "data"})
        self._store_mmif_at(wf_path, guid, mmif_content)
        payload = json.dumps({
            "workflow": {"swt-detection/v7.4": params},
            "guid": guid})
        resp = self.client.post(
            '/storeapi/download',
            data=payload,
            content_type='application/json')
        data = resp.get_json()
        self.assertEqual(data, {"test": "data"})

    def test_download_zero_guid(self):
        guid = 'cpb-aacip-507-154dn40c26'
        params = {"pretty": "true"}
        param_hash = generate_param_hash(params)
        wf_path = f'swt-detection/v7.4/{param_hash}'
        self._store_mmif_at(wf_path, guid)
        payload = json.dumps({
            "workflow": {"swt-detection/v7.4": params}})
        resp = self.client.post(
            '/storeapi/download',
            data=payload,
            content_type='application/json')
        data = resp.get_json()
        self.assertIn('filenames', data)
        self.assertIn(guid, data['filenames'])


class TestUploadDownloadConsistency(unittest.TestCase):
    """Verify that upload and download produce matching storage paths."""

    @classmethod
    def setUpClass(cls):
        log('setUpClass :: setting up test-storage')
        cls.tmpdir = TEMP_STORAGE
        Path(cls.tmpdir).mkdir(exist_ok=True)
        clear_directory(cls.tmpdir)

    def setUp(self):
        self.tmpdir = self.__class__.tmpdir
        self.app = create_app_for_testing(self.tmpdir)
        self.client = self.app.test_client()
        self._patcher = mock.patch('api.STORAGE_DIR', self.tmpdir)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_roundtrip_single_app(self):
        """Upload a MMIF, then download it using the same app+params."""
        # upload
        resp = self.client.post('/storeapi/upload', data=SINGLE_APP_MMIF)
        self.assertIn(resp.status_code, (200, 201))
        # download using equivalent workflow spec
        payload = json.dumps({
            "workflow": {"swt-detection/v7.4": {"pretty": "true"}},
            "guid": "cpb-aacip-507-154dn40c26"})
        resp = self.client.post(
            '/storeapi/download',
            data=payload,
            content_type='application/json')
        # should find and return the uploaded MMIF
        data = resp.get_json()
        self.assertIn('documents', data)
        self.assertIn('views', data)

    def test_roundtrip_two_apps(self):
        """Upload a two-app MMIF, then download it."""
        resp = self.client.post('/storeapi/upload', data=TWO_APP_MMIF)
        log(f'test_roundtrip_two_apps :: {resp}\n')
        self.assertIn(resp.status_code, (200, 201))
        payload = json.dumps({
            "workflow": {
                "swt-detection/v7.4": {"pretty": "true"},
                "doctr-wrapper/v1.2": {"tfLabel": "chyron"}},
            "guid": "cpb-aacip-507-v40js9j432"})
        resp = self.client.post(
            '/storeapi/download',
            data=payload,
            content_type='application/json')
        data = resp.get_json()
        self.assertIn('documents', data)
        self.assertIn('views', data)


if __name__ == '__main__':
    unittest.main()
