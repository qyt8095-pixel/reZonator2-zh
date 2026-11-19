"""Tests for the ODR report builder (Phase 4 M4).

Covers: full report on the user's real cavity with the merged example
side-car (all sections except Fox-Li, which is opt-in), section
failure isolation (empty side-car degrades to skipped, never crashes),
the EXAMPLE vs real banner, HTML well-formedness (stdlib parser, no
unclosed tags, all images embedded as data URIs), and the run_odr.py
CLI entry.
"""

import json
import os
import sys
import tempfile
import unittest
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINEERING = os.path.dirname(HERE)
USER_REZ = "/home/hatch/workspace/user/files/upload.rez"

sys.path.insert(0, ENGINEERING)

from demo_odr import SOURCES, _deep_merge  # noqa: E402
from rezeng.odr import build_odr_report  # noqa: E402
from run_odr import main as run_odr_main  # noqa: E402


def merged_demo_eng():
    eng = {}
    for name in SOURCES:
        with open(os.path.join(ENGINEERING, name), encoding="utf-8") as fh:
            _deep_merge(eng, json.load(fh))
    return eng


class _TagChecker(HTMLParser):
    VOID = {"meta", "img", "br", "hr", "link", "input"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.imgs = []
        self.mismatches = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag == "img":
            self.imgs.append(dict(attrs).get("src", ""))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            self.mismatches.append(tag)


class TestOdr(unittest.TestCase):
    def test_full_report_quick(self):
        eng = merged_demo_eng()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.html")
            rep = build_odr_report(USER_REZ, eng=eng, include_foxli=False,
                                   mc_n=40, pump_powers=(5.0,),
                                   example_params=True, out_html=out)
            self.assertEqual(rep["n_sections"], 9)
            self.assertEqual(rep["n_ok"], 8)
            by_id = {s["id"]: s for s in rep["sections"]}
            self.assertEqual(by_id["foxli"]["status"], "skipped")
            self.assertEqual(by_id["cavity"]["status"], "ok")
            self.assertEqual(by_id["zones"]["status"], "ok")
            self.assertEqual(by_id["montecarlo"]["status"], "ok")
            self.assertEqual(by_id["thermal"]["status"], "ok")
            self.assertEqual(by_id["ghosts"]["status"], "ok")
            self.assertEqual(by_id["redlight"]["status"], "ok")
            self.assertEqual(by_id["coating"]["status"], "ok")
            self.assertEqual(by_id["exports"]["status"], "ok")
            self.assertTrue(os.path.exists(out))
            html_text = rep["html"]
            self.assertIn("示例值", html_text)
            self.assertIn("光学设计评审报告", html_text)
            checker = _TagChecker()
            checker.feed(html_text)
            checker.close()
            self.assertEqual(checker.stack, [])
            self.assertEqual(checker.mismatches, [])
            self.assertGreaterEqual(len(checker.imgs), 3)
            self.assertTrue(all(
                src.startswith("data:image/png;base64,")
                for src in checker.imgs))

    def test_empty_eng_degrades_to_skipped(self):
        rep = build_odr_report(USER_REZ, eng={}, include_foxli=False,
                               mc_n=10, pump_powers=(5.0,),
                               example_params=True)
        by_id = {s["id"]: s for s in rep["sections"]}
        self.assertEqual(by_id["cavity"]["status"], "ok")
        self.assertEqual(by_id["zones"]["status"], "ok")
        self.assertEqual(by_id["montecarlo"]["status"], "skipped")
        self.assertEqual(by_id["thermal"]["status"], "skipped")
        self.assertEqual(by_id["foxli"]["status"], "skipped")
        self.assertNotIn("error", [s["status"] for s in rep["sections"]])

    def test_real_flag_changes_banner(self):
        eng = merged_demo_eng()
        rep = build_odr_report(USER_REZ, eng=eng, include_foxli=False,
                               mc_n=10, pump_powers=(5.0,),
                               example_params=False)
        self.assertIn("基于用户提供的真实参数", rep["html"])
        self.assertNotIn("均为示例值", rep["html"])

    def test_cli_entry(self):
        eng = merged_demo_eng()
        with tempfile.TemporaryDirectory() as tmp:
            eng_file = os.path.join(tmp, "demo.eng.json")
            out = os.path.join(tmp, "r.html")
            with open(eng_file, "w", encoding="utf-8") as fh:
                json.dump(eng, fh)
            code = run_odr_main([
                "--rez", USER_REZ, "--eng", eng_file, "--out", out,
                "--mc-n", "10", "--pump", "5"])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(out))
            self.assertGreater(os.path.getsize(out), 10000)


if __name__ == "__main__":
    unittest.main()
