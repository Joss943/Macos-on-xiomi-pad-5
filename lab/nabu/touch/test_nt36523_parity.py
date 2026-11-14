"""Differential test: the C NT36523 decoder must match the validated Python parser."""
import ctypes
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import nt36523_touch as reference  # noqa: E402


class Contact(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint8), ("phase", ctypes.c_uint8), ("x", ctypes.c_uint16),
                ("y", ctypes.c_uint16), ("width", ctypes.c_uint16), ("pressure", ctypes.c_uint16)]


class Frame(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_uint8), ("count", ctypes.c_uint8), ("contacts", Contact * 10)]


class FwInfo(ctypes.Structure):
    _fields_ = [("valid", ctypes.c_bool), ("fw_ver", ctypes.c_uint8), ("x_num", ctypes.c_uint8),
                ("y_num", ctypes.c_uint8), ("abs_x_max", ctypes.c_uint16), ("abs_y_max", ctypes.c_uint16),
                ("max_button_num", ctypes.c_uint8)]


@unittest.skipUnless(shutil.which("cc"), "no C compiler")
class ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = os.path.join(cls.tmp.name, "libnt36523.so")
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
                        os.path.join(HERE, "nt36523.c"), "-o", lib], check=True)
        cls.lib = ctypes.CDLL(lib)
        cls.lib.nt36523_parse_report.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint16,
                                                 ctypes.c_uint16, ctypes.c_uint16, ctypes.POINTER(Frame)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def c_parse(self, packet, max_x, max_y, max_p):
        frame = Frame()
        rc = self.lib.nt36523_parse_report(packet, len(packet), max_x, max_y, max_p, ctypes.byref(frame))
        self.assertEqual(rc, 0)
        return frame

    def compare(self, packet, max_x, max_y, max_p=1000):
        expected = reference.parse_report(packet, max_x=max_x, max_y=max_y, max_pressure=max_p)
        frame = self.c_parse(packet, max_x, max_y, max_p)
        kind = {None: 0, "firmware-reset": 1}.get(expected.recovery, 1)
        if expected.watchdog_pattern:
            kind = 2
        self.assertEqual(frame.kind, kind)
        got = [(c.id, "down" if c.phase == 1 else "move", c.x, c.y, c.width, c.pressure)
               for c in frame.contacts[:frame.count]]
        want = [(c.identifier, c.phase, c.x, c.y, c.width, c.pressure) for c in expected.contacts]
        self.assertEqual(got, want, packet.hex())

    def test_random_packets_match_reference(self):
        rng = random.Random(0x36523)
        for _ in range(20000):
            packet = bytearray(rng.getrandbits(8) for _ in range(66))
            for slot in range(10):
                if rng.random() < 0.5:
                    packet[1 + slot * 6] = (rng.randint(0, 12) << 3) | rng.choice((0, 1, 2, 3))
            self.compare(bytes(packet), rng.choice((0xFFF, 2559, 1599, 1)), rng.choice((0xFFF, 1599, 2559)),
                         rng.choice((1000, 255, 1)))

    def test_status_patterns_match_reference(self):
        for status in (b"\x77" * 6, b"\xfd\xfe\xfd\xfe\xfd\xfe", b"\xfd" * 6, b"\xfe" * 6, b"\x77" * 5 + b"\xfd"):
            packet = bytes(1) + status + bytes(59)
            self.compare(packet, 0xFFF, 0xFFF)

    def test_fw_info_layout(self):
        buf = bytearray(39)
        buf[1], buf[2], buf[3], buf[4] = 0x12, 0xED, 18, 32
        buf[5:9] = bytes((0x0A, 0x00, 0x06, 0x40))
        info = FwInfo()
        self.assertEqual(self.lib.nt36523_parse_fw_info(bytes(buf), 39, ctypes.byref(info)), 0)
        self.assertTrue(info.valid)
        self.assertEqual((info.fw_ver, info.x_num, info.y_num, info.abs_x_max, info.abs_y_max),
                         (0x12, 18, 32, 2560, 1600))
        buf[2] = 0
        self.lib.nt36523_parse_fw_info(bytes(buf), 39, ctypes.byref(info))
        self.assertFalse(info.valid)


if __name__ == "__main__":
    unittest.main()
