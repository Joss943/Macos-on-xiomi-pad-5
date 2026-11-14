/*
 * HID multitouch digitizer for the nabu NT36523 panel. See nabu_touch_hid.h.
 */
#include "nabu_touch_hid.h"

#include <string.h>

struct hid_writer {
	uint8_t *out;
	size_t cap;
	size_t len;
	bool overflow;
};

static void
put(struct hid_writer *w, uint8_t byte)
{
	if (w->len < w->cap) {
		w->out[w->len] = byte;
	} else {
		w->overflow = true;
	}
	w->len++;
}

/* Short item with the smallest payload that keeps `value` as a signed quantity. */
static void
item(struct hid_writer *w, uint8_t prefix, int32_t value)
{
	if (value >= -128 && value <= 127) {
		put(w, prefix | 1u);
		put(w, (uint8_t)value);
	} else if (value >= -32768 && value <= 32767) {
		put(w, prefix | 2u);
		put(w, (uint8_t)value);
		put(w, (uint8_t)(value >> 8));
	} else {
		put(w, prefix | 3u);
		for (unsigned i = 0; i < 4; i++) {
			put(w, (uint8_t)((uint32_t)value >> (8u * i)));
		}
	}
}

/* Unsigned-range item, used for usages and sizes that are never negative. */
static void
uitem(struct hid_writer *w, uint8_t prefix, uint32_t value)
{
	if (value <= 0xFFu) {
		put(w, prefix | 1u);
		put(w, (uint8_t)value);
	} else if (value <= 0xFFFFu) {
		put(w, prefix | 2u);
		put(w, (uint8_t)value);
		put(w, (uint8_t)(value >> 8));
	} else {
		put(w, prefix | 3u);
		for (unsigned i = 0; i < 4; i++) {
			put(w, (uint8_t)(value >> (8u * i)));
		}
	}
}

enum {
	MAIN_INPUT = 0x80, MAIN_FEATURE = 0xB0, MAIN_COLLECTION = 0xA0, MAIN_END = 0xC0,
	G_USAGE_PAGE = 0x04, G_LOGICAL_MIN = 0x14, G_LOGICAL_MAX = 0x24, G_PHYSICAL_MIN = 0x34,
	G_PHYSICAL_MAX = 0x44, G_UNIT_EXPONENT = 0x54, G_UNIT = 0x64, G_REPORT_SIZE = 0x74,
	G_REPORT_ID = 0x84, G_REPORT_COUNT = 0x94, L_USAGE = 0x08,
};
enum {
	PAGE_GENERIC_DESKTOP = 0x01, PAGE_DIGITIZER = 0x0D,
	USAGE_X = 0x30, USAGE_Y = 0x31,
	USAGE_TOUCH_SCREEN = 0x04, USAGE_FINGER = 0x22, USAGE_TIP_PRESSURE = 0x30, USAGE_TIP_SWITCH = 0x42,
	USAGE_CONTACT_ID = 0x51, USAGE_CONTACT_COUNT = 0x54, USAGE_CONTACT_COUNT_MAX = 0x55,
	USAGE_SCAN_TIME = 0x56,
	IO_DATA_VAR_ABS = 0x02, IO_CONST = 0x03,
};

static void
field(struct hid_writer *w, uint32_t bits, uint32_t count, uint8_t main_item, uint8_t flags)
{
	uitem(w, G_REPORT_SIZE, bits);
	uitem(w, G_REPORT_COUNT, count);
	uitem(w, main_item, flags);
}

size_t
nabu_touch_hid_descriptor(uint16_t max_x, uint16_t max_y, uint16_t max_pressure, uint8_t *out, size_t cap)
{
	if (out == NULL || max_x == 0 || max_y == 0 || max_pressure == 0) {
		return 0;
	}
	struct hid_writer w = { out, cap, 0, false };
	uitem(&w, G_USAGE_PAGE, PAGE_DIGITIZER);
	uitem(&w, L_USAGE, USAGE_TOUCH_SCREEN);
	uitem(&w, MAIN_COLLECTION, 0x01);                 /* Application */
	uitem(&w, G_REPORT_ID, NABU_TOUCH_INPUT_REPORT_ID);
	for (unsigned slot = 0; slot < NT36523_MAX_CONTACTS; slot++) {
		uitem(&w, G_USAGE_PAGE, PAGE_DIGITIZER);
		uitem(&w, L_USAGE, USAGE_FINGER);
		uitem(&w, MAIN_COLLECTION, 0x02);         /* Logical */
		item(&w, G_LOGICAL_MIN, 0);
		item(&w, G_LOGICAL_MAX, 1);
		uitem(&w, L_USAGE, USAGE_TIP_SWITCH);
		field(&w, 1, 1, MAIN_INPUT, IO_DATA_VAR_ABS);
		field(&w, 7, 1, MAIN_INPUT, IO_CONST);
		item(&w, G_LOGICAL_MAX, NT36523_MAX_CONTACTS - 1);
		uitem(&w, L_USAGE, USAGE_CONTACT_ID);
		field(&w, 8, 1, MAIN_INPUT, IO_DATA_VAR_ABS);
		uitem(&w, G_USAGE_PAGE, PAGE_GENERIC_DESKTOP);
		uitem(&w, G_UNIT_EXPONENT, 0x0E);         /* 10^-2 */
		uitem(&w, G_UNIT, 0x11);                  /* SI linear centimetre */
		item(&w, G_PHYSICAL_MIN, 0);
		item(&w, G_PHYSICAL_MAX, NABU_TOUCH_PHYS_X_TENTH_MM);
		item(&w, G_LOGICAL_MAX, max_x);
		uitem(&w, L_USAGE, USAGE_X);
		field(&w, 16, 1, MAIN_INPUT, IO_DATA_VAR_ABS);
		item(&w, G_PHYSICAL_MAX, NABU_TOUCH_PHYS_Y_TENTH_MM);
		item(&w, G_LOGICAL_MAX, max_y);
		uitem(&w, L_USAGE, USAGE_Y);
		field(&w, 16, 1, MAIN_INPUT, IO_DATA_VAR_ABS);
		uitem(&w, G_USAGE_PAGE, PAGE_DIGITIZER);
		uitem(&w, G_UNIT_EXPONENT, 0);
		uitem(&w, G_UNIT, 0);
		item(&w, G_PHYSICAL_MAX, 0);
		item(&w, G_LOGICAL_MAX, max_pressure);
		uitem(&w, L_USAGE, USAGE_TIP_PRESSURE);
		field(&w, 16, 1, MAIN_INPUT, IO_DATA_VAR_ABS);
		put(&w, MAIN_END);
	}
	uitem(&w, G_USAGE_PAGE, PAGE_DIGITIZER);
	item(&w, G_LOGICAL_MAX, NT36523_MAX_CONTACTS);
	uitem(&w, L_USAGE, USAGE_CONTACT_COUNT);
	field(&w, 8, 1, MAIN_INPUT, IO_DATA_VAR_ABS);
	uitem(&w, G_UNIT_EXPONENT, 0x0C);                 /* 10^-4 */
	uitem(&w, G_UNIT, 0x1001);                        /* SI linear second */
	item(&w, G_LOGICAL_MAX, 0xFFFF);
	item(&w, G_PHYSICAL_MAX, 0xFFFF);
	uitem(&w, L_USAGE, USAGE_SCAN_TIME);
	field(&w, 16, 1, MAIN_INPUT, IO_DATA_VAR_ABS);
	uitem(&w, G_UNIT_EXPONENT, 0);
	uitem(&w, G_UNIT, 0);
	item(&w, G_PHYSICAL_MAX, 0);
	uitem(&w, G_REPORT_ID, NABU_TOUCH_FEATURE_REPORT_ID);
	item(&w, G_LOGICAL_MAX, NT36523_MAX_CONTACTS);
	uitem(&w, L_USAGE, USAGE_CONTACT_COUNT_MAX);
	field(&w, 8, 1, MAIN_FEATURE, IO_DATA_VAR_ABS);
	put(&w, MAIN_END);
	return w.overflow ? 0 : w.len;
}

static void
put16(uint8_t *p, uint16_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
}

size_t
nabu_touch_hid_pack(struct nabu_touch_hid_state *state, const struct nt36523_frame *frame,
    uint16_t scan_time_100us, uint8_t *out, size_t cap)
{
	if (state == NULL || frame == NULL || out == NULL || cap < NABU_TOUCH_INPUT_REPORT_BYTES ||
	    frame->kind != NT36523_FRAME_TOUCH || frame->count > NT36523_MAX_CONTACTS) {
		return 0;
	}
	memset(out, 0, NABU_TOUCH_INPUT_REPORT_BYTES);
	out[0] = NABU_TOUCH_INPUT_REPORT_ID;
	uint16_t now_mask = 0;
	unsigned slots = 0;
	uint8_t *p = out + 1;
	for (unsigned i = 0; i < frame->count; i++) {
		const struct nt36523_contact *c = &frame->contacts[i];
		if (c->id >= NT36523_MAX_CONTACTS || (now_mask & (1u << c->id))) {
			continue;
		}
		now_mask |= (uint16_t)(1u << c->id);
		state->last[c->id] = *c;
		p[0] = 0x01;                              /* tip switch */
		p[1] = c->id;
		put16(p + 2, c->x);
		put16(p + 4, c->y);
		put16(p + 6, c->pressure);
		p += NABU_TOUCH_CONTACT_BYTES;
		slots++;
	}
	const uint16_t lifted = (uint16_t)(state->active_mask & ~now_mask);
	for (unsigned id = 0; id < NT36523_MAX_CONTACTS && slots < NT36523_MAX_CONTACTS; id++) {
		if (!(lifted & (1u << id))) {
			continue;
		}
		const struct nt36523_contact *c = &state->last[id];
		p[0] = 0x00;                              /* tip released at the last position */
		p[1] = (uint8_t)id;
		put16(p + 2, c->x);
		put16(p + 4, c->y);
		p += NABU_TOUCH_CONTACT_BYTES;
		slots++;
	}
	state->active_mask = now_mask;
	out[1 + NT36523_MAX_CONTACTS * NABU_TOUCH_CONTACT_BYTES] = (uint8_t)slots;
	put16(out + 2 + NT36523_MAX_CONTACTS * NABU_TOUCH_CONTACT_BYTES, scan_time_100us);
	return NABU_TOUCH_INPUT_REPORT_BYTES;
}

size_t
nabu_touch_hid_feature(uint8_t *out, size_t cap)
{
	if (out == NULL || cap < 2) {
		return 0;
	}
	out[0] = NABU_TOUCH_FEATURE_REPORT_ID;
	out[1] = NT36523_MAX_CONTACTS;
	return 2;
}
