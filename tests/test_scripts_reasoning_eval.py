"""Offline checks for the APP scripts/ reasoning-effort eval copy.

No key, no network: deterministic graders, cost math, decision rule,
set shape, key hygiene (env only), and the no-key refusal. Mirrors the
tool-side contract against the copy living next to the checkout.
"""
import importlib.util
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
_SRC = os.path.join(_WS, "src")
for _p in (_SRC, _WS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TOOL = os.path.join(_WS, "scripts", "reasoning_eval.py")
SET = os.path.join(_WS, "scripts", "reasoning_eval_set.json")


def load_mod():
    spec = importlib.util.spec_from_file_location(
        "scripts_reasoning_eval_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GOOD_PLAN = json.dumps({"parts": [
    {"part_id": "p1", "goal": "g1", "files": ["a.md"],
     "check_commands": [["cat", "a.md"]], "depends_on": []},
    {"part_id": "p2", "goal": "g2", "files": ["b.md"],
     "check_commands": [["cat", "b.md"]], "depends_on": ["p1"]}]})
GOOD_ANSWER = json.dumps({"answer": "Exit code 0 means the check passed."})
GOOD_WORKER = json.dumps({"actions": [{"action": "write_file",
                                       "path": "docs/greet.txt",
                                       "content": "hello agent si"}],
                          "done": True})
GOOD_PASS = json.dumps({"result": "PASS", "reasons": ["files match"]})
GOOD_FAIL = json.dumps({"result": "FAIL", "reasons": ["file missing"]})


class ScriptsReasoningEvalTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_mod()

    def test_set_shape_fixed(self):
        data = json.loads(open(SET, encoding="utf-8").read())
        self.assertEqual(len(data["director"]), 4)
        self.assertEqual(len(data["worker"]), 4)
        self.assertEqual(len(data["auditor"]), 4)
        self.assertEqual(len(data["solo"]), 2)
        wrong = [t for t in data["auditor"] if t["expected"] == "FAIL"]
        self.assertEqual(len(wrong), 2)  # 2 seeded wrong

    def test_set_loads_through_copy(self):
        tasks = self.mod.load_set()
        self.assertEqual(len(tasks), 14)
        self.assertEqual(
            sorted({t["role"] for t in tasks}),
            ["auditor", "director", "solo", "worker"])

    def test_grade_director_plan_and_question(self):
        ok, _ = self.mod.grade_director(
            {"kind": "plan", "expected_parts": [2, 3]}, GOOD_PLAN)
        self.assertTrue(ok)
        ok, _ = self.mod.grade_director(
            {"kind": "plan", "expected_parts": [3, 4]}, GOOD_PLAN)
        self.assertFalse(ok)
        ok, _ = self.mod.grade_director({"kind": "question"}, GOOD_ANSWER)
        self.assertTrue(ok)
        ok, _ = self.mod.grade_director({"kind": "question"}, GOOD_PLAN)
        self.assertFalse(ok)

    def test_grade_worker_exact(self):
        task = {"expected": {"path": "docs/greet.txt",
                             "content": "hello agent si"}}
        ok, _ = self.mod.grade_worker(task, GOOD_WORKER)
        self.assertTrue(ok)
        other = json.dumps({"actions": [{"action": "write_file",
                                         "path": "docs/other.txt",
                                         "content": "hello agent si"}],
                            "done": True})
        ok, _ = self.mod.grade_worker(task, other)
        self.assertFalse(ok)

    def test_grade_auditor_verdict_match(self):
        ok, _ = self.mod.grade_auditor({"expected": "PASS"}, GOOD_PASS)
        self.assertTrue(ok)
        ok, _ = self.mod.grade_auditor({"expected": "PASS"}, GOOD_FAIL)
        self.assertFalse(ok)

    def test_grade_solo_word(self):
        ok, _ = self.mod.grade_solo({"expected_word": "mars"},
                                    "The red planet is Mars.")
        self.assertTrue(ok)
        ok, _ = self.mod.grade_solo({"expected_word": "mars"}, "Venus.")
        self.assertFalse(ok)

    def test_cost_math_matches_app_gate(self):
        self.assertAlmostEqual(
            self.mod.cost_usd({"input_tokens": 1000,
                               "output_tokens": 2000}), 0.0005)
        self.assertIsNone(self.mod.cost_usd({}))

    def test_decide_cheapest_within_two_points(self):
        stats = {
            "none": {"pass_at_1": 1.00, "mean_cost_usd": 0.0010,
                     "latency_median_s": 5.0},
            "low": {"pass_at_1": 0.99, "mean_cost_usd": 0.0005,
                    "latency_median_s": 6.0},
            "high": {"pass_at_1": 0.50, "mean_cost_usd": 0.0001,
                     "latency_median_s": 4.0},
        }
        winner, _ = self.mod.decide_role(["none", "low", "high"], stats)
        self.assertEqual(winner, "low")

    def test_key_from_env_only_and_refused_without(self):
        src = open(TOOL, encoding="utf-8").read()
        self.assertIn("AGENT_SI_EVAL_KEY", src)
        self.assertNotIn("add_argument(\"--key", src)
        self.assertNotIn("add_argument('--key", src)
        old = os.environ.pop("AGENT_SI_EVAL_KEY", None)
        try:
            self.assertEqual(self.mod.main(["--probe-only"]), 2)
        finally:
            if old is not None:
                os.environ["AGENT_SI_EVAL_KEY"] = old

    def test_prompts_come_from_app(self):
        tasks = self.mod.load_set()
        first = {role: next(t for t in tasks if t["role"] == role)
                 for role in ("director", "worker", "auditor")}
        self.assertIn("You are the Director",
                      self.mod.director_messages(first["director"])[0]
                      ["content"])
        self.assertIn("You are the worker",
                      self.mod.worker_messages(first["worker"])[0]["content"])

    def test_default_reports_land_next_to_copy(self):
        self.assertTrue(
            self.mod.DEFAULT_JSON.startswith(self.mod.HERE), self.mod.HERE)
        self.assertTrue(
            self.mod.DEFAULT_MD.startswith(self.mod.HERE), self.mod.HERE)


if __name__ == "__main__":
    unittest.main()
