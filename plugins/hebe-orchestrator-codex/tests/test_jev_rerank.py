"""Offline tests for explicit Jev shortlist reranking."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import jev_rerank as rerank


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "jev_rerank.py"


class RerankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name).resolve() / "shortlist.json"
        self.data = {
            "query": "Where is the deployment decision?",
            "candidates": [
                {"id": "a", "text": "Unrelated interface note.", "metadata": {"source": "s1"}},
                {"id": "b", "text": "Deployment decision recorded here.", "metadata": {"source": "s2"}},
                {"id": "c", "text": "Another unrelated note."},
            ],
        }
        self.write()

    def write(self):
        self.file.write_text(json.dumps(self.data), encoding="utf-8")

    def response(self, values):
        return {"model": "jev-1.test", "answers": {
            f"candidate_{i}": {"type": "noul", "noul": value}
            for i, value in enumerate(values)},
            "usage": {"input_tokens": 120, "output_tokens": 3}}

    def cli(self, *args):
        env = dict(os.environ)
        env.pop("TYPESAFE_API_KEY", None)
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                              text=True, timeout=10, env=env, cwd=ROOT)

    def test_preview_is_local_and_contains_no_input_text(self):
        with mock.patch.object(rerank.jev, "active_credentials", side_effect=AssertionError("credential")), \
                mock.patch.object(rerank.jev, "request_api", side_effect=AssertionError("network")):
            shortlist = rerank.load_shortlist(str(self.file))
            payload, fingerprint = rerank.build_request(shortlist)
            result = rerank.preview(shortlist, payload, fingerprint)
        self.assertFalse(result["network_used"])
        self.assertEqual(result["question_count"], 3)
        self.assertEqual(result["request_fingerprint"], fingerprint)
        self.assertNotIn(self.data["query"], json.dumps(result))
        self.assertNotIn("Deployment decision recorded here", json.dumps(result))
        self.assertEqual(set(payload["questions"]), {"candidate_0", "candidate_1", "candidate_2"})
        example = self.cli("preview", "--file", str(ROOT / "examples" / "jev-rerank.json"))
        self.assertEqual(example.returncode, 0, example.stderr)
        self.assertEqual(json.loads(example.stdout)["candidate_count"], 2)

    def test_evaluate_batches_once_and_sorts_stably(self):
        shortlist = rerank.load_shortlist(str(self.file))
        payload, fingerprint = rerank.build_request(shortlist)
        with mock.patch.object(rerank.jev, "active_credentials", return_value=("fake-key", "test")), \
                mock.patch.object(rerank.jev, "request_api", return_value=self.response([0.2, 0.9, 0.2])) as api:
            result = rerank.evaluate(shortlist, payload, fingerprint)
        api.assert_called_once_with("systemone", "fake-key", payload)
        self.assertEqual([x["id"] for x in result["ranked"]], ["b", "a", "c"])
        self.assertEqual([x["probability"] for x in result["ranked"]], [0.9, 0.2, 0.2])
        self.assertFalse(result["abstained"])
        self.assertEqual(result["provenance"]["response_model"], "jev-1.test")
        self.assertEqual(result["provenance"]["request_fingerprint"], fingerprint)
        self.assertNotIn(self.data["query"], json.dumps(result))
        self.assertNotIn("metadata", json.dumps(result))

    def test_threshold_abstains_and_preserves_local_order(self):
        self.data["threshold"] = 0.8
        self.write()
        shortlist = rerank.load_shortlist(str(self.file))
        payload, fingerprint = rerank.build_request(shortlist)
        result = rerank.rank(shortlist, payload, fingerprint, raw=self.response([0.1, 0.7, 0.2]))
        self.assertTrue(result["abstained"])
        self.assertEqual(result["reason"], "below_threshold")
        self.assertEqual([x["id"] for x in result["ranked"]], ["a", "b", "c"])
        self.assertEqual(result["ranked"][1]["probability"], 0.7)

    def test_credential_and_service_failure_fall_back_without_network_retry(self):
        shortlist = rerank.load_shortlist(str(self.file))
        payload, fingerprint = rerank.build_request(shortlist)
        with mock.patch.object(rerank.jev, "active_credentials", side_effect=rerank.jev.JevError("secret")), \
                mock.patch.object(rerank.jev, "request_api") as api:
            result = rerank.evaluate(shortlist, payload, fingerprint)
        api.assert_not_called()
        self.assertEqual(result["reason"], "credential_unavailable")
        with mock.patch.object(rerank.jev, "active_credentials", return_value=("fake-key", "test")), \
                mock.patch.object(rerank.jev, "request_api", side_effect=rerank.jev.JevError("secret")) as api:
            result = rerank.evaluate(shortlist, payload, fingerprint)
        api.assert_called_once()
        self.assertEqual(result["reason"], "service_unavailable")
        self.assertEqual([x["id"] for x in result["ranked"]], ["a", "b", "c"])
        self.assertNotIn("secret", json.dumps(result))

    def test_malformed_response_is_rejected_without_fallback(self):
        shortlist = rerank.load_shortlist(str(self.file))
        payload, fingerprint = rerank.build_request(shortlist)
        malformed = self.response([0.1, 0.9, 0.2])
        malformed["answers"]["candidate_0"]["extra"] = "unexpected"
        with self.assertRaisesRegex(rerank.jev.JevError, "incompatível"):
            rerank.rank(shortlist, payload, fingerprint, raw=malformed)
        malformed = self.response([0.1, 0.9, 0.2])
        del malformed["answers"]["candidate_2"]
        with self.assertRaisesRegex(rerank.jev.JevError, "incompatível"):
            rerank.rank(shortlist, payload, fingerprint, raw=malformed)

    def test_duplicate_ids_keys_secrets_and_symlinks_are_rejected(self):
        self.data["candidates"][1]["id"] = "a"
        self.write()
        with self.assertRaisesRegex(rerank.jev.JevError, "duplicado"):
            rerank.load_shortlist(str(self.file))
        self.file.write_text('{"query":"x","query":"y","candidates":[]}', encoding="utf-8")
        with self.assertRaisesRegex(rerank.jev.JevError, "duplicada"):
            rerank.load_shortlist(str(self.file))
        self.data["candidates"][1]["id"] = "b"
        self.data["candidates"][0]["metadata"]["api_key"] = "synthetic"
        self.write()
        with self.assertRaisesRegex(rerank.jev.JevError, "credencial"):
            rerank.load_shortlist(str(self.file))
        self.data["candidates"][0]["metadata"] = {"source": "s1"}
        self.write()
        link = self.file.parent / "link.json"
        link.symlink_to(self.file)
        with self.assertRaisesRegex(rerank.jev.JevError, "symlinks"):
            rerank.load_shortlist(str(link))
        directory_link = self.file.parent / "dir-link"
        directory_link.symlink_to(self.file.parent, target_is_directory=True)
        with self.assertRaisesRegex(rerank.jev.JevError, "symlinks"):
            rerank.load_shortlist(str(directory_link / self.file.name))

    def test_evaluate_requires_explicit_send(self):
        result = self.cli("evaluate", "--file", str(self.file))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--send", result.stderr)

    def test_credentials_embedded_in_candidate_text_never_reach_network(self):
        samples = ["github_pat_" + "a" * 24,
                   "https://user:synthetic-private-password@example.invalid/",
                   '{"api_key": "synthetic-private-value"}',
                   "{'password': 'synthetic-private-value'}"]
        with mock.patch.object(rerank.jev, "active_credentials", side_effect=AssertionError("credential")), \
                mock.patch.object(rerank.jev, "request_api", side_effect=AssertionError("network")):
            for value in samples:
                with self.subTest(kind=samples.index(value)):
                    self.data["candidates"][0]["text"] = value
                    self.write()
                    with self.assertRaisesRegex(rerank.jev.JevError, "segredo"):
                        rerank.load_shortlist(str(self.file))

    def test_secret_scan_is_bounded_for_long_unbroken_metadata(self):
        self.data["candidates"][0]["metadata"] = {"source": "a" * 262144}
        self.write()
        result = self.cli("preview", "--file", str(self.file))
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
