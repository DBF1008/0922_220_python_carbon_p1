import os
import shutil
import tempfile
from unittest import TestCase

from mock import patch

from carbon import log
from carbon.tests.util import TestSettings
from carbon.database import WhisperDatabase


GOOD_STORAGE_SCHEMAS = (
    "[default]\n"
    "pattern = .*\n"
    "retentions = 60:1d\n"
)

GOOD_AGGREGATION_SCHEMAS = (
    "[good]\n"
    "pattern = \\.ok$\n"
    "xFilesFactor = 0.5\n"
    "aggregationMethod = average\n"
)

# Mixes one good section and one section whose xFilesFactor is out of bounds.
BAD_AGGREGATION_SCHEMAS = (
    "[good]\n"
    "pattern = \\.ok$\n"
    "xFilesFactor = 0.5\n"
    "aggregationMethod = average\n"
    "\n"
    "[bad]\n"
    "pattern = \\.bad$\n"
    "xFilesFactor = 1.5\n"
    "aggregationMethod = average\n"
)

UNSUPPORTED_METHOD_AGGREGATION_SCHEMAS = (
    "[bad]\n"
    "pattern = \\.bad$\n"
    "xFilesFactor = 0.5\n"
    "aggregationMethod = not-a-real-method\n"
)


class ReloadAggregationSchemasTest(TestCase):
    """Runtime reload must never poison the last known-good schema set."""

    def setUp(self):
        self.conf_dir = tempfile.mkdtemp()
        self.storage_schemas_config = os.path.join(self.conf_dir, 'storage-schemas.conf')
        self.storage_aggregation_config = os.path.join(
            self.conf_dir, 'storage-aggregation.conf')
        with open(self.storage_schemas_config, 'w') as f:
            f.write(GOOD_STORAGE_SCHEMAS)
        with open(self.storage_aggregation_config, 'w') as f:
            f.write(GOOD_AGGREGATION_SCHEMAS)

        settings = TestSettings()
        settings['CONF_DIR'] = self.conf_dir
        settings['LOCAL_DATA_DIR'] = ''
        self._settings_patch = patch('carbon.conf.settings', settings)
        self._settings_patch.start()
        self._database_patch = patch('carbon.state.database', new=WhisperDatabase(settings))
        self._database_patch.start()

        import carbon.storage as storage
        self._schemas_config_patch = patch.object(
            storage, 'STORAGE_SCHEMAS_CONFIG', self.storage_schemas_config)
        self._aggregation_config_patch = patch.object(
            storage, 'STORAGE_AGGREGATION_CONFIG', self.storage_aggregation_config)
        self._schemas_config_patch.start()
        self._aggregation_config_patch.start()

        import carbon.writer as writer
        self.writer = writer
        # Explicitly perform the startup-load equivalent for every test, since
        # the module is imported only once per test process.
        writer.AGGREGATION_SCHEMAS = writer.loadAggregationSchemas()
        self.assertEqual(
            [schema.name for schema in writer.AGGREGATION_SCHEMAS], ['good', 'default'])

    def tearDown(self):
        self._aggregation_config_patch.stop()
        self._schemas_config_patch.stop()
        self._database_patch.stop()
        self._settings_patch.stop()
        shutil.rmtree(self.conf_dir)

    def _setAggregationConfig(self, body):
        with open(self.storage_aggregation_config, 'w') as f:
            f.write(body)

    def test_startup_load_skips_invalid_section(self):
        # Startup path: a bad section must be skipped instead of crashing.
        from carbon.storage import loadAggregationSchemas
        self._setAggregationConfig(BAD_AGGREGATION_SCHEMAS)
        with patch.object(log, 'msg'):
            schema_list = loadAggregationSchemas()
        self.assertEqual([schema.name for schema in schema_list], ['good', 'default'])

    def test_reload_with_bad_section_keeps_known_good_schemas(self):
        good_schemas = self.writer.AGGREGATION_SCHEMAS
        self._setAggregationConfig(BAD_AGGREGATION_SCHEMAS)
        with patch.object(log, 'msg'), patch.object(log, 'err'):
            self.writer.reloadAggregationSchemas()
        # The bad section is skipped but the valid section still reloads.
        self.assertEqual(
            [schema.name for schema in self.writer.AGGREGATION_SCHEMAS], ['good', 'default'])
        self.assertIsNot(self.writer.AGGREGATION_SCHEMAS, good_schemas)

    def test_reload_keeps_previous_schemas_when_loader_raises(self):
        good_schemas = self.writer.AGGREGATION_SCHEMAS
        with patch.object(log, 'msg'), patch.object(log, 'err'):
            with patch.object(self.writer, 'loadAggregationSchemas',
                              side_effect=RuntimeError('boom')):
                self.writer.reloadAggregationSchemas()  # must not raise
        self.assertIs(self.writer.AGGREGATION_SCHEMAS, good_schemas)

    def test_reload_with_only_bad_sections_falls_back_to_default(self):
        self._setAggregationConfig(UNSUPPORTED_METHOD_AGGREGATION_SCHEMAS)
        with patch.object(log, 'msg'), patch.object(log, 'err'):
            self.writer.reloadAggregationSchemas()
        # Every custom section was invalid and skipped; only the default applies.
        self.assertEqual(
            [schema.name for schema in self.writer.AGGREGATION_SCHEMAS], ['default'])
        methods = [schema.archives[1] for schema in self.writer.AGGREGATION_SCHEMAS]
        self.assertNotIn('not-a-real-method', methods)

    def test_reload_rejects_empty_result(self):
        good_schemas = self.writer.AGGREGATION_SCHEMAS
        with patch.object(log, 'msg') as log_mock, patch.object(log, 'err'):
            with patch.object(self.writer, 'loadAggregationSchemas', return_value=[]):
                self.writer.reloadAggregationSchemas()
        self.assertIs(self.writer.AGGREGATION_SCHEMAS, good_schemas)
        self.assertTrue(any('empty' in str(call).lower() for call in log_mock.call_args_list))
