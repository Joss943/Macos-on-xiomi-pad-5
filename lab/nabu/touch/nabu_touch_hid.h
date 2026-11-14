/*
 * HID multitouch digitizer description and input reports for the nabu
 * NT36523 panel. Pure data transformation; no IOKit dependency, so it can
 * be unit-tested on a host and linked into the kext unchanged.
 *
 * Input report 1 (84 bytes):  report id, 10 x contact {flags, id, x16, y16,
 * pressure16}, contact count, scan time (100 us units).
 * Feature report 2 (2 bytes): report id, contact count maximum (10).
 */
#ifndef NABU_TOUCH_HID_H
#define NABU_TOUCH_HID_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "nt36523.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NABU_TOUCH_INPUT_REPORT_ID   1u
#define NABU_TOUCH_FEATURE_REPORT_ID 2u
#define NABU_TOUCH_CONTACT_BYTES     8u
#define NABU_TOUCH_INPUT_REPORT_BYTES (1u + NT36523_MAX_CONTACTS * NABU_TOUCH_CONTACT_BYTES + 1u + 2u)
#define NABU_TOUCH_DESCRIPTOR_MAX    1024u
/* Xiaomi Pad 5: 11-inch 16:10 panel, about 237 mm x 148 mm. */
#define NABU_TOUCH_PHYS_X_TENTH_MM   2370u
#define NABU_TOUCH_PHYS_Y_TENTH_MM   1480u

struct nabu_touch_hid_state {
	uint16_t active_mask;                      /* contacts reported down last frame */
	struct nt36523_contact last[NT36523_MAX_CONTACTS];
};

/* Returns the descriptor length, or 0 when `cap` is too small or limits are zero. */
size_t nabu_touch_hid_descriptor(uint16_t max_x, uint16_t max_y, uint16_t max_pressure,
    uint8_t *out, size_t cap);

/*
 * Pack one frame. Contacts that disappeared since the previous frame are sent
 * once more with the tip switch cleared, so the host sees every release.
 * Returns the report length or 0 for frames that are not touch frames.
 */
size_t nabu_touch_hid_pack(struct nabu_touch_hid_state *state, const struct nt36523_frame *frame,
    uint16_t scan_time_100us, uint8_t *out, size_t cap);

size_t nabu_touch_hid_feature(uint8_t *out, size_t cap);

#ifdef __cplusplus
}
#endif

#endif /* NABU_TOUCH_HID_H */
