import os
import tempfile
import unittest
from unittest.mock import patch

import app as app_module


class FreeTTSQuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "quota.sqlite3")
        self.usage_db_patch = patch.object(app_module, "FREE_TTS_USAGE_DB", self.db_path)
        self.usage_db_patch.start()
        self.addCleanup(self.usage_db_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_completed_audio_uses_actual_duration_and_duplicate_is_idempotent(self):
        client_key = "test-client"
        request_key = "job:0"
        usage_day = "2025-01-15"

        self.assertTrue(app_module.reserve_free_tts_usage(
            client_key, request_key, "fingerprint", usage_day
        ))
        remaining = app_module.finish_free_tts_usage(
            client_key, request_key, 91.25, usage_day
        )

        self.assertEqual(remaining, 2400 - 91.25)
        self.assertFalse(app_module.reserve_free_tts_usage(
            client_key, request_key, "fingerprint", usage_day
        ))
        self.assertEqual(
            app_module.finish_free_tts_usage(client_key, request_key, 200, usage_day),
            remaining,
        )

    def test_reservations_cannot_exceed_daily_limit(self):
        client_key = "test-client"
        usage_day = "2025-01-15"
        for index in range(4):
            app_module.reserve_free_tts_usage(
                client_key, f"job-{index}:0", f"fingerprint-{index}", usage_day
            )

        with self.assertRaises(app_module.FreeTTSQuotaError) as error:
            app_module.reserve_free_tts_usage(
                client_key, "job-over-limit:0", "fingerprint", usage_day
            )

        self.assertEqual(error.exception.code, "daily_quota_exceeded")

    def test_fingerprint_mismatch_is_rejected(self):
        app_module.reserve_free_tts_usage("test-client", "job:0", "first", "2025-01-15")

        with self.assertRaises(app_module.FreeTTSQuotaError) as error:
            app_module.reserve_free_tts_usage("test-client", "job:0", "different", "2025-01-15")

        self.assertEqual(error.exception.code, "duplicate_request")

    def test_generate_rejects_audio_over_ten_minutes_and_releases_quota(self):
        audio_dir = os.path.join(self.temp_dir.name, "audio")
        work_dir = os.path.join(self.temp_dir.name, "work")
        os.makedirs(audio_dir)

        async def create_audio(_text, _voice, _rate, _pitch, _volume, output_path, _work_dir):
            with open(output_path, "wb") as audio_file:
                audio_file.write(b"mock-mp3")

        job_id = "a" * 32
        with (
            patch.object(app_module, "AUDIO_DIR", audio_dir),
            patch.object(app_module, "TTS_WORK_DIR", work_dir),
            patch.object(app_module, "generate_speech_async", create_audio),
            patch.object(app_module, "get_media_duration_seconds", return_value=600.01),
        ):
            response = app_module.app.test_client().post(
                "/api/generate",
                json={"text": "hello", "job_id": job_id},
            )

        filename = f"audio_{job_id}_001_giong_cua_toi.mp3"
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["code"], "job_limit_exceeded")
        self.assertFalse(os.path.exists(os.path.join(audio_dir, filename)))
        connection = app_module._connect_free_tts_usage_db()
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM free_tts_usage").fetchone()[0],
                0,
            )
        finally:
            connection.close()

    def test_generate_records_measured_duration(self):
        audio_dir = os.path.join(self.temp_dir.name, "audio")
        work_dir = os.path.join(self.temp_dir.name, "work")
        os.makedirs(audio_dir)

        async def create_audio(_text, _voice, _rate, _pitch, _volume, output_path, _work_dir):
            with open(output_path, "wb") as audio_file:
                audio_file.write(b"mock-mp3")

        job_id = "b" * 32
        with (
            patch.object(app_module, "AUDIO_DIR", audio_dir),
            patch.object(app_module, "TTS_WORK_DIR", work_dir),
            patch.object(app_module, "generate_speech_async", create_audio),
            patch.object(app_module, "get_media_duration_seconds", return_value=75.5),
        ):
            response = app_module.app.test_client().post(
                "/api/generate",
                json={"text": "hello", "job_id": job_id},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["audio_duration_seconds"], 75.5)
        self.assertEqual(response.get_json()["daily_tts_minutes_remaining"], 38.74)


if __name__ == "__main__":
    unittest.main()
