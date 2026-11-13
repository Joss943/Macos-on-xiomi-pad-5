from __future__ import annotations

import unittest

import scan_kernelcache_fixups
from test_inspect_iohid_vtable import _fileset_with_chained_vtable


class KernelCacheFixupScanTests(unittest.TestCase):
    def test_counts_authenticated_and_plain_kernel_cache_pointers(self):
        report = scan_kernelcache_fixups.scan_kernelcache(
            _fileset_with_chained_vtable(4, empty_last=True)
        )
        self.assertEqual(report["pointer_cells"], 4)
        self.assertEqual(report["authenticated_pointer_cells"], 2)
        self.assertEqual(report["unauthenticated_pointer_cells"], 2)
        self.assertEqual(report["multi_start_pages"], 0)
        self.assertFalse(report["kernelcache_modified"])


if __name__ == "__main__":
    unittest.main()
