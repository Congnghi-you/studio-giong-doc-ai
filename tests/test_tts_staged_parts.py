# -*- coding: utf-8 -*-
import unittest
import json
import app

class TestTTSStagedParts(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_split_preview_empty(self):
        res = self.client.post("/api/split-preview", json={"text": ""})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_parts"], 0)
        self.assertEqual(len(data["parts"]), 0)

    def test_split_preview_multiple_parts(self):
        # Create a text with 4,500 words
        paragraphs = []
        for p in range(5):
            para = " ".join([f"word{p}_{i}" for i in range(900)]) + "."
            paragraphs.append(para)
        text = "\n\n".join(paragraphs)

        res = self.client.post("/api/split-preview", json={"text": text})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["total_parts"], 3)
        self.assertEqual(len(data["parts"]), data["total_parts"])
        for part in data["parts"]:
            self.assertIn("index", part)
            self.assertIn("word_count", part)
            self.assertIn("est_seconds", part)
            self.assertLessEqual(part["word_count"], 2000)

    def test_html_contains_parts_section_and_functions(self):
        with open("templates/index.html", "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="ttsPartsSection"', html)
        self.assertIn('id="audioPartsList"', html)
        self.assertIn("function splitTextIntoPartsJS", html)
        self.assertIn("function renderAllPartCards", html)
        self.assertIn("function generateSinglePart", html)
        self.assertIn("function retrySinglePart", html)

    def test_download_endpoint_with_sample_file(self):
        import os
        test_filename = "test_download_file.mp3"
        test_path = os.path.join(app.AUDIO_DIR, test_filename)
        with open(test_path, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00")
        try:
            res = self.client.get(f"/api/download/{test_filename}")
            self.assertEqual(res.status_code, 200)
            self.assertIn("attachment", res.headers.get("Content-Disposition", ""))
            self.assertIn(test_filename, res.headers.get("Content-Disposition", ""))
            res.close()
        finally:
            if os.path.exists(test_path):
                os.remove(test_path)

if __name__ == "__main__":
    unittest.main()
