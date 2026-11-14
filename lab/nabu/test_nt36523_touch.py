import unittest

from nt36523_touch import (
    TouchReportError,
    WatchdogRecoveryTracker,
    parse_report,
)


def set_contact(packet, slot, identifier, event, x, y, width, pressure):
    offset = 1 + slot * 6
    packet[offset] = (identifier << 3) | event
    packet[offset + 1] = x >> 4
    packet[offset + 2] = y >> 4
    packet[offset + 3] = ((x & 0x0F) << 4) | (y & 0x0F)
    packet[offset + 4] = width
    packet[offset + 5] = pressure & 0xFF


class NT36523TouchParserTests(unittest.TestCase):
    def test_decodes_multitouch_coordinates_and_pressure_extension(self):
        packet = bytearray(66)
        set_contact(packet, 0, 1, 1, 0x456, 0x789, 0, 0x34)
        set_contact(packet, 1, 4, 2, 0x321, 0x654, 7, 0x56)
        packet[63] = 0x01
        packet[64] = 0x02

        frame = parse_report(bytes(packet), max_x=0xFFF, max_y=0xFFF)

        self.assertEqual(frame.recovery, None)
        self.assertEqual(frame.contacts[0].identifier, 0)
        self.assertEqual(frame.contacts[0].phase, "down")
        self.assertEqual((frame.contacts[0].x, frame.contacts[0].y), (0x456, 0x789))
        self.assertEqual((frame.contacts[0].width, frame.contacts[0].pressure), (1, 0x134))
        self.assertEqual(frame.contacts[1].identifier, 3)
        self.assertEqual(frame.contacts[1].phase, "move")
        self.assertEqual(frame.contacts[1].pressure, 0x256)

    def test_ignores_released_bad_id_and_out_of_range_contacts(self):
        packet = bytearray(66)
        set_contact(packet, 0, 1, 0, 100, 100, 2, 2)
        set_contact(packet, 1, 11, 1, 100, 100, 2, 2)
        set_contact(packet, 2, 3, 1, 0x400, 100, 2, 2)
        set_contact(packet, 3, 4, 1, 100, 100, 2, 2)

        frame = parse_report(bytes(packet), max_x=0x3FF, max_y=0x3FF)

        self.assertEqual([contact.identifier for contact in frame.contacts], [3])

    def test_reports_controller_recovery_patterns(self):
        firmware = bytearray(66)
        firmware[1:7] = bytes((0x77,)) * 6
        watchdog = bytearray(66)
        watchdog[1:7] = bytes((0xFD, 0xFE, 0xFD, 0xFE, 0xFD, 0xFE))

        self.assertEqual(parse_report(bytes(firmware), max_x=1, max_y=1).recovery, "firmware-reset")
        self.assertTrue(parse_report(bytes(watchdog), max_x=1, max_y=1).watchdog_pattern)

    def test_watchdog_requires_eleven_consecutive_marked_frames(self):
        watchdog = bytearray(66)
        watchdog[1:7] = bytes((0xFD, 0xFE, 0xFD, 0xFE, 0xFD, 0xFE))
        watchdog_frame = parse_report(bytes(watchdog), max_x=1, max_y=1)
        tracker = WatchdogRecoveryTracker()

        for _ in range(10):
            self.assertFalse(tracker.should_recover(watchdog_frame))
        self.assertTrue(tracker.should_recover(watchdog_frame))
        self.assertEqual(tracker.consecutive_frames, 0)

    def test_normal_frame_clears_watchdog_streak(self):
        watchdog = bytearray(66)
        watchdog[1:7] = bytes((0xFD,)) * 6
        watchdog_frame = parse_report(bytes(watchdog), max_x=1, max_y=1)
        normal_frame = parse_report(bytes(66), max_x=1, max_y=1)
        tracker = WatchdogRecoveryTracker()

        for _ in range(10):
            self.assertFalse(tracker.should_recover(watchdog_frame))
        self.assertFalse(tracker.should_recover(normal_frame))
        for _ in range(10):
            self.assertFalse(tracker.should_recover(watchdog_frame))
        self.assertFalse(tracker.should_recover(normal_frame))

    def test_rejects_truncated_packets_and_invalid_limits(self):
        with self.assertRaises(TouchReportError):
            parse_report(bytes(65), max_x=1, max_y=1)
        with self.assertRaises(TouchReportError):
            parse_report(bytes(66), max_x=0, max_y=1)


if __name__ == "__main__":
    unittest.main()
