import hashlib
import hmac
import json
import os
import tempfile
import unittest
import wave
from unittest.mock import patch

import app as app_module
import saas_billing


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.config = saas_billing.BillingConfig()
        self.config.enabled = True
        self.config.supabase_url = "https://project.supabase.co"
        self.config.supabase_anon_key = "public-anon-key"
        self.config.supabase_service_role_key = "server-secret"
        self.config.paddle_api_key = "paddle-secret"
        self.config.paddle_client_token = "public-client-token"
        self.config.paddle_webhook_secret = "webhook-secret"
        self.config.paddle_annual_price_id = "pri_annual"
        self.config.paddle_lifetime_price_id = "pri_lifetime"
        self.config.paddle_environment = "sandbox"

    def test_public_settings_never_expose_server_secrets(self):
        settings = self.config.public_settings()
        self.assertNotIn("server-secret", json.dumps(settings))
        self.assertNotIn("paddle-secret", json.dumps(settings))
        self.assertNotIn("webhook-secret", json.dumps(settings))
        self.assertTrue(self.config.configured)
        self.assertEqual(settings["annualPriceUsd"], 49.90)
        self.assertEqual(settings["lifetimePriceUsd"], 499.00)
        self.assertEqual(settings["accessDays"], 365)
        self.assertEqual(settings["annualSttMinutesPer30Days"], 3600)
        self.assertEqual(settings["lifetimeSttMinutesPer30Days"], 1_000_000)
        self.assertEqual(settings["sttMaxJobMinutes"], 60)

    def test_billing_requires_distinct_annual_and_lifetime_prices(self):
        self.config.paddle_lifetime_price_id = self.config.paddle_annual_price_id
        self.assertFalse(self.config.configured)

    def test_paddle_signature_verification_checks_body_and_timestamp(self):
        body = b'{"event_id":"evt_test"}'
        timestamp = 1_800_000_000
        digest = hmac.new(
            b"webhook-secret",
            str(timestamp).encode("ascii") + b":" + body,
            hashlib.sha256,
        ).hexdigest()
        header = f"ts={timestamp};h1={digest}"

        self.assertTrue(saas_billing.verify_paddle_signature(
            body, header, "webhook-secret", now=timestamp
        ))
        self.assertFalse(saas_billing.verify_paddle_signature(
            body + b" ", header, "webhook-secret", now=timestamp
        ))
        self.assertFalse(saas_billing.verify_paddle_signature(
            body, header, "webhook-secret", now=timestamp + 301
        ))

    @patch("saas_billing._request_json")
    def test_checkout_is_created_for_server_verified_user_id(self, request_json):
        request_json.return_value = {"data": {"id": "txn_01234567890123456789012345"}}

        transaction_id = saas_billing.create_checkout_transaction(
            self.config, "11111111-1111-4111-8111-111111111111", "annual"
        )

        self.assertEqual(transaction_id, "txn_01234567890123456789012345")
        args, kwargs = request_json.call_args
        self.assertEqual(args[0], "https://sandbox-api.paddle.com/transactions")
        self.assertEqual(kwargs["body"]["items"], [{"price_id": "pri_annual", "quantity": 1}])
        self.assertEqual(
            kwargs["body"]["custom_data"]["supabase_user_id"],
            "11111111-1111-4111-8111-111111111111",
        )

    @patch("saas_billing._request_json")
    def test_lifetime_checkout_uses_server_configured_price(self, request_json):
        request_json.return_value = {"data": {"id": "txn_01234567890123456789012345"}}

        saas_billing.create_checkout_transaction(
            self.config, "11111111-1111-4111-8111-111111111111", "lifetime"
        )

        self.assertEqual(
            request_json.call_args.kwargs["body"]["items"],
            [{"price_id": "pri_lifetime", "quantity": 1}],
        )

    @patch("saas_billing._request_json")
    def test_checkout_rejects_unknown_plan_without_network_access(self, request_json):
        with self.assertRaises(saas_billing.BillingError):
            saas_billing.create_checkout_transaction(
                self.config, "11111111-1111-4111-8111-111111111111", "unexpected"
            )
        request_json.assert_not_called()

    @patch("saas_billing._supabase_rpc")
    def test_webhook_rpc_receives_both_server_configured_prices(self, rpc):
        event = {"event_id": "evt_test"}

        saas_billing.apply_paddle_event(self.config, event)

        self.assertEqual(
            rpc.call_args.args[2]["p_expected_annual_price_id"], "pri_annual"
        )
        self.assertEqual(
            rpc.call_args.args[2]["p_expected_lifetime_price_id"], "pri_lifetime"
        )

    @patch("saas_billing._supabase_rpc")
    def test_billing_quota_is_selected_by_database_entitlement(self, rpc):
        saas_billing.get_billing_status(self.config, "11111111-1111-4111-8111-111111111111")
        status_payload = rpc.call_args.args[2]
        self.assertNotIn("p_monthly_minutes", status_payload)

        saas_billing.reserve_stt_minutes(
            self.config, "11111111-1111-4111-8111-111111111111", 30, "22222222-2222-4222-8222-222222222222"
        )
        reservation_payload = rpc.call_args.args[2]
        self.assertNotIn("p_monthly_minutes", reservation_payload)

    def test_missing_auth_token_fails_before_network_access(self):
        with self.assertRaises(saas_billing.AuthenticationRequired):
            saas_billing.authenticate_access_token(self.config, "")

    @patch("saas_billing._request_json")
    def test_access_token_is_verified_by_supabase(self, request_json):
        user_id = "11111111-1111-4111-8111-111111111111"
        request_json.return_value = {"id": user_id, "email": "user@example.com"}

        user = saas_billing.authenticate_access_token(self.config, "verified-token")

        self.assertEqual(user["id"], user_id)
        self.assertEqual(user["email"], "user@example.com")
        self.assertEqual(
            request_json.call_args.kwargs["headers"]["Authorization"],
            "Bearer verified-token",
        )

    def test_stt_endpoint_requires_auth_when_billing_is_enabled(self):
        with patch.object(app_module, "BILLING_CONFIG", self.config):
            response = app_module.app.test_client().post("/api/transcribe")

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["success"])

    def test_local_stt_remains_available_without_online_billing(self):
        config = saas_billing.BillingConfig()
        config.enabled = False
        with patch.object(app_module, "BILLING_CONFIG", config):
            response = app_module.app.test_client().post("/api/transcribe")

        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.get_json()["error"].lower())

    def test_local_home_page_shows_free_trial_and_no_payment_signup(self):
        config = saas_billing.BillingConfig()
        config.enabled = False
        with patch.object(app_module, "BILLING_CONFIG", config):
            response = app_module.app.test_client().get("/")

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("40 minutes of voice generation per day", page)
        self.assertIn("Up to 10 minutes of audio per generation", page)
        self.assertIn("No credit card or payment method required.", page)
        self.assertNotIn("Voice generation with Edge TTS remains free to try", page)
        self.assertIn('onclick="openFreeSignup()"', page)

    def test_webhook_verifies_raw_body_then_processes_event(self):
        event = {"event_id": "evt_test", "event_type": "transaction.completed", "data": {}}
        body = json.dumps(event, separators=(",", ":")).encode("utf-8")
        with (
            patch.object(app_module, "BILLING_CONFIG", self.config),
            patch.object(saas_billing, "verify_paddle_signature", return_value=True) as verify_signature,
            patch.object(saas_billing, "apply_paddle_event", return_value={"duplicate": False}) as apply_event,
        ):
            response = app_module.app.test_client().post(
                "/api/billing/webhook",
                data=body,
                content_type="application/json",
                headers={"Paddle-Signature": "test-signature"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(verify_signature.call_args.args[0], body)
        self.assertEqual(apply_event.call_args.args[1], event)

    def test_checkout_rejects_unknown_plan(self):
        with patch.object(app_module, "BILLING_CONFIG", self.config):
            response = app_module.app.test_client().post(
                "/api/billing/checkout", json={"plan": "unknown"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_checkout_endpoint_passes_selected_plan_to_server_configuration(self):
        user = {"id": "11111111-1111-4111-8111-111111111111"}
        with (
            patch.object(app_module, "BILLING_CONFIG", self.config),
            patch.object(app_module, "_billing_user_from_request", return_value=user),
            patch.object(
                saas_billing,
                "create_checkout_transaction",
                return_value="txn_01234567890123456789012345",
            ) as create_checkout,
        ):
            response = app_module.app.test_client().post(
                "/api/billing/checkout", json={"plan": "lifetime"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(create_checkout.call_args.args, (self.config, user["id"], "lifetime"))

    def test_audio_duration_helper_reads_wav_media(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, "duration-test.wav")
            with wave.open(audio_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\0\0" * 32000)

            self.assertAlmostEqual(
                app_module.get_media_duration_seconds(audio_path),
                2.0,
                places=1,
            )


if __name__ == "__main__":
    unittest.main()
