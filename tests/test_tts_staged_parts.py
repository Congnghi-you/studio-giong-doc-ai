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

if __name__ == "__main__":
    unittest.main()
