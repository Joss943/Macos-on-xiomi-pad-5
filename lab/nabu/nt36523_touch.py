#!/usr/bin/env python3
"""Decode Novatek NT36523 SPI touch reports used by Xiaomi Pad 5 (nabu).

This is a portable report parser, not an SPI driver or a macOS HID driver.
The input includes the leading SPI command byte used by the controller driver.
"""

from __future__ import annotations

from dataclasses import dataclass


REPORT_BYTES = 66
MAX_FINGERS = 10
POINT_BYTES = 6
TOUCH_DOWN = 1
TOUCH_MOVE = 2
DEFAULT_MAX_PRESSURE = 1000


class TouchReportError(ValueError):
    """The touch-controller report is malformed or has invalid parameters."""


@dataclass(frozen=True)
class Contact:
    identifier: int
    phase: str
    x: int
    y: int
    width: int
    pressure: int


@dataclass(frozen=True)
class TouchFrame:
    contacts: tuple[Contact, ...]
    recovery: str | None = None


def parse_report(
    packet: bytes,
    *,
    max_x: int,
    max_y: int,
    max_pressure: int = DEFAULT_MAX_PRESSURE,
) -> TouchFrame:
    """Decode one 66-byte SPI read into active multi-touch contacts.

    `max_x` and `max_y` come from NT36523 firmware-info bytes, so callers do
    not need to assume that every display assembly reports identical limits.
    Contact IDs are returned as zero-based slots, matching the Linux driver.
    """
    if len(packet) < REPORT_BYTES:
        raise TouchReportError(f"touch report needs {REPORT_BYTES} bytes, got {len(packet)}")
    if max_x <= 0 or max_y <= 0 or max_pressure <= 0:
        raise TouchReportError("coordinate and pressure limits must be positive")

    firmware_status = packet[1:7]
    if firmware_status == bytes((0x77,)) * 6:
        return TouchFrame((), recovery="firmware-reset")
    if all(value in (0xFD, 0xFE) for value in firmware_status):
        return TouchFrame((), recovery="watchdog-reset")

    contacts = []
    for slot in range(MAX_FINGERS):
        offset = 1 + POINT_BYTES * slot
        status_id = packet[offset]
        identifier = status_id >> 3
        event = status_id & 0x07
        if not 1 <= identifier <= MAX_FINGERS or event not in (TOUCH_DOWN, TOUCH_MOVE):
            continue

        x = (packet[offset + 1] << 4) | (packet[offset + 3] >> 4)
        y = (packet[offset + 2] << 4) | (packet[offset + 3] & 0x0F)
        if x > max_x or y > max_y:
            continue

        width = packet[offset + 4] or 1
        pressure = packet[offset + 5]
        if slot < 2:
            pressure |= packet[63 + slot] << 8
        pressure = min(pressure or 1, max_pressure)
        contacts.append(Contact(
            identifier=identifier - 1,
            phase="down" if event == TOUCH_DOWN else "move",
            x=x,
            y=y,
            width=width,
            pressure=pressure,
        ))

    return TouchFrame(tuple(contacts))
