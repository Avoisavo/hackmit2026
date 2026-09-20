import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from robot.local_settings import ENV_FILE, read_settings
from robot.control_plane import AudioProviders


class LocalSettingsTests(unittest.TestCase):
    def test_source_is_repository_env_independent_of_working_directory(self):
        self.assertEqual(ENV_FILE, Path(__file__).resolve().parents[2] / '.env.local')

    def test_file_values_load_and_explicit_environment_wins_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'settings'
            source.write_text('DEEPGRAM_API_KEY=file-test\nELEVENLABS_API_KEY="voice-test"\nELEVENLABS_VOICE_ID=voice-id\nEMPTY=\nUNSET\n')
            with patch.dict(os.environ, {'DEEPGRAM_API_KEY': 'environment-test'}, clear=True):
                values = read_settings(source)
                self.assertEqual(dict(os.environ), {'DEEPGRAM_API_KEY': 'environment-test'})
            audio = AudioProviders(values)
            self.assertEqual(audio.deepgram, 'environment-test')
            self.assertEqual(audio.elevenlabs, 'voice-test')
            self.assertEqual(audio.voice_id, 'voice-id')
            self.assertEqual(values['EMPTY'], '')
            self.assertNotIn('UNSET', values)

    def test_missing_file_supports_environment_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_settings(Path(tmp) / 'missing', {'ROBOT_IP': 'test-ip'}), {'ROBOT_IP': 'test-ip'})

    def test_explicit_empty_setting_does_not_reenable_file_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'settings'
            source.write_text('ELEVENLABS_API_KEY=test-file\n')
            self.assertEqual(AudioProviders(read_settings(source, {'ELEVENLABS_API_KEY': ''})).elevenlabs, '')
