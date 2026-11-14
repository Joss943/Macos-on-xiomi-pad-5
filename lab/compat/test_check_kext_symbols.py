import unittest

import check_kext_symbols
from test_inspect_iohid_vtable import _fileset_with_vtable


class CheckKextSymbolsTests(unittest.TestCase):
    def test_reports_resolved_and_missing_imports(self):
        report = check_kext_symbols.check(_fileset_with_vtable(3), ["__ZTV11IOHIDDevice", "__ZNotThere"])
        self.assertEqual(report["imports"], 2)
        self.assertEqual(report["resolved"], 1)
        self.assertEqual(report["missing"], ["__ZNotThere"])
        self.assertEqual(report["resolved_by_member"], {"com.apple.iokit.IOHIDFamily": 1})


if __name__ == "__main__":
    unittest.main()
