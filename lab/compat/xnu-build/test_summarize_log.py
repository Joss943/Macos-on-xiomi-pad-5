import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import summarize_log  # noqa: E402

LOG = """\x1b[34m[info] building\x1b[0m
/w/xnu/osfmk/arm64/cpu.c:944:47: error: use of undeclared identifier 'sysreg_restore'
/w/xnu/osfmk/arm64/cpu.c:944:47: error: use of undeclared identifier 'sysreg_restore'
/w/xnu/osfmk/arm64/sleh.c:3171:2: warning: unused label 'nabu_irq_epilogue' [-Wunused-label]
/w/xnu/bsd/kern/kern_exit.c:10:1: warning: something unrelated
make[2]: *** [cpu.o] Error 1
"""


class SummarizeTests(unittest.TestCase):
    def test_failed_build(self):
        result = summarize_log.summarize(LOG)
        self.assertFalse(result["succeeded"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["line"], "944")
        self.assertEqual([w["path"] for w in result["nabu_warnings"]], ["/w/xnu/osfmk/arm64/sleh.c"])
        self.assertIn("make[2]: *** [cpu.o] Error 1", result["link_and_make"])

    def test_success_banner(self):
        result = summarize_log.summarize("  \U0001f389 XNU Build Done!\n")
        self.assertTrue(result["succeeded"])
        self.assertIn("build finished", summarize_log.markdown(result, "x"))


if __name__ == "__main__":
    unittest.main()
