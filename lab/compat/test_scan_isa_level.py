import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import scan_isa_level as scan  # noqa: E402

PROBE = """
.text
.globl _f
_f:
  pacibsp
  retab
  braa x1, x2
  ldraa x0, [x1, #16]
  pacga x0, x1, x2
  fjcvtzs w0, d1
  ldapur x0, [x1, #8]
  cfinv
  sb
  wfet x0
  cpyfp [x0]!, [x1]!, x2!
  abs x0, x1
  abs v0.4s, v1.4s
  msr dit, #1
  mrs x0, s3_4_c15_c10_6
  tlbi rvae1is, x0
  tlbi vmalle1is
  ldapr x0, [x1]
  sdot v0.4s, v1.16b, v2.16b
  casal x0, x1, [x2]
  autiasp
  ret
"""


class ClassifyTests(unittest.TestCase):
    def test_allowed_on_kryo485(self):
        for mnemonic, ops in (("ldapr", "x0, [x1]"), ("casal", "x0, x1, [x2]"), ("sdot", ""),
                              ("abs.4s", "v0, v1"), ("tlbi", "vmalle1is"), ("ret", ""),
                              ("mrs", "x0, CNTVCT_EL0"), ("dc", "cvap, x0")):
            self.assertIsNone(scan.classify(mnemonic, ops), mnemonic)

    def test_trapping(self):
        cases = {
            ("retab", ""): "FEAT_PAuth non-HINT (v8.3)",
            ("ldapur", "x0, [x1, #0x8]"): "FEAT_LRCPC2 (v8.4)",
            ("abs", "x0, x1"): "FEAT_CSSC (v8.9)",
            ("cpyfp", "[x0]!, [x1]!, x2!"): "FEAT_MOPS (v8.8)",
            ("msr", "DIT, #0x1"): "FEAT_DIT (v8.4)",
            ("mrs", "x0, S3_4_C15_C10_6"): "Apple IMPLEMENTATION DEFINED sysreg",
            ("tlbi", "rvae1is, x0"): "FEAT_TLBIRANGE (v8.4)",
            ("bc.eq", "0x10"): "FEAT_HBC (v8.8)",
            ("ld1w", "{ z0.s }, p0/z, [x0]"): "FEAT_SVE/SME",
        }
        for (mnemonic, ops), feature in cases.items():
            self.assertEqual(scan.classify(mnemonic, ops), feature, mnemonic)

    def test_listing_counts(self):
        listing = "       0: \tpacibsp\n       4: \tretab\n       8: \tldapr\tx0, [x1]\n"
        report = scan.scan_listing(listing)
        self.assertEqual(report["instructions"], 3)
        self.assertEqual(report["pauth_hint_nops"], 1)
        self.assertEqual(report["by_feature"], {"FEAT_PAuth non-HINT (v8.3)": 1})


@unittest.skipUnless(shutil.which("llvm-mc-18") and shutil.which("llvm-objdump-18"), "LLVM 18 tools absent")
class EndToEndTests(unittest.TestCase):
    def test_probe_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "probe.s")
            obj = os.path.join(tmp, "probe.o")
            with open(source, "w") as handle:
                handle.write(PROBE)
            subprocess.run(["llvm-mc-18", "-triple=arm64-apple-macos14", "-mattr=+all",
                            "-filetype=obj", source, "-o", obj], check=True)
            listing = scan.disassemble(obj, ["llvm-objdump-18"])
        report = scan.scan_listing(listing)
        self.assertEqual(report["pauth_hint_nops"], 2)
        self.assertEqual(report["by_feature"]["FEAT_PAuth non-HINT (v8.3)"], 4)
        for feature in ("FEAT_JSCVT (v8.3)", "FEAT_LRCPC2 (v8.4)", "FEAT_FlagM (v8.4)", "FEAT_SB (v8.5)",
                        "FEAT_WFxT (v8.7)", "FEAT_MOPS (v8.8)", "FEAT_CSSC (v8.9)", "FEAT_DIT (v8.4)",
                        "Apple IMPLEMENTATION DEFINED sysreg", "FEAT_TLBIRANGE (v8.4)"):
            self.assertEqual(report["by_feature"].get(feature), 1, feature)
        self.assertEqual(report["trapping_or_foreign"], 14)


if __name__ == "__main__":
    unittest.main()
