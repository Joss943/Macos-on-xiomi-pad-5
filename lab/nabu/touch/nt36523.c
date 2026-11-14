/*
 * Novatek NT36523 SPI protocol for Xiaomi Pad 5 (nabu). See nt36523.h.
 */
#include "nt36523.h"

#include <string.h>

size_t
nt36523_build_set_page(uint32_t address, uint8_t out[3])
{
	out[0] = 0xFF;
	out[1] = (uint8_t)((address >> 15) & 0xFFu);
	out[2] = (uint8_t)((address >> 7) & 0xFFu);
	return 3;
}

size_t
nt36523_build_read(uint32_t address, size_t data_len, uint8_t *tx, size_t tx_cap)
{
	const size_t xfer = data_len + 2u;
	if (tx == NULL || data_len == 0 || xfer > tx_cap) {
		return 0;
	}
	memset(tx, 0, xfer);
	tx[0] = (uint8_t)(address & 0x7Fu);   /* bit 7 clear selects a read */
	return xfer;
}

int
nt36523_extract_read(const uint8_t *rx, size_t xfer_len, uint8_t *out, size_t data_len)
{
	if (rx == NULL || out == NULL) {
		return NT36523_EINVAL;
	}
	if (xfer_len < data_len + 2u) {
		return NT36523_ESHORT;
	}
	memcpy(out, rx + 2, data_len);
	return NT36523_OK;
}

int
nt36523_parse_fw_info(const uint8_t *buf, size_t len, struct nt36523_fw_info *info)
{
	if (buf == NULL || info == NULL) {
		return NT36523_EINVAL;
	}
	if (len < NT36523_FWINFO_BYTES) {
		return NT36523_ESHORT;
	}
	memset(info, 0, sizeof(*info));
	info->fw_ver = buf[1];
	info->x_num = buf[3];
	info->y_num = buf[4];
	info->abs_x_max = (uint16_t)((buf[5] << 8) | buf[6]);
	info->abs_y_max = (uint16_t)((buf[7] << 8) | buf[8]);
	info->max_button_num = buf[11];
	/* The firmware stores its version and its complement; anything else is noise. */
	info->valid = ((unsigned)buf[1] + (unsigned)buf[2]) == 0xFFu &&
	    info->abs_x_max != 0 && info->abs_y_max != 0;
	return NT36523_OK;
}

static bool
nt36523_status_bytes_are(const uint8_t *status, uint8_t a, uint8_t b)
{
	for (unsigned i = 0; i < 6; i++) {
		if (status[i] != a && status[i] != b) {
			return false;
		}
	}
	return true;
}

int
nt36523_parse_report(const uint8_t *packet, size_t len, uint16_t max_x, uint16_t max_y,
    uint16_t max_pressure, struct nt36523_frame *frame)
{
	if (packet == NULL || frame == NULL || max_x == 0 || max_y == 0 || max_pressure == 0) {
		return NT36523_EINVAL;
	}
	if (len < NT36523_REPORT_BYTES) {
		return NT36523_ESHORT;
	}
	memset(frame, 0, sizeof(*frame));
	const uint8_t *status = packet + 1;
	if (nt36523_status_bytes_are(status, 0x77, 0x77)) {
		frame->kind = NT36523_FRAME_FIRMWARE_RESET;
		return NT36523_OK;
	}
	if (nt36523_status_bytes_are(status, 0xFD, 0xFE)) {
		frame->kind = NT36523_FRAME_WATCHDOG;
		return NT36523_OK;
	}
	frame->kind = NT36523_FRAME_TOUCH;
	for (unsigned slot = 0; slot < NT36523_MAX_CONTACTS; slot++) {
		const uint8_t *p = packet + 1 + 6u * slot;
		const unsigned id = p[0] >> 3;
		const unsigned event = p[0] & 0x07u;
		if (id < 1 || id > NT36523_MAX_CONTACTS ||
		    (event != NT36523_PHASE_DOWN && event != NT36523_PHASE_MOVE)) {
			continue;
		}
		const unsigned x = ((unsigned)p[1] << 4) | (p[3] >> 4);
		const unsigned y = ((unsigned)p[2] << 4) | (p[3] & 0x0Fu);
		if (x > max_x || y > max_y) {
			continue;
		}
		unsigned pressure = p[5];
		if (slot < 2) {
			pressure |= (unsigned)packet[63 + slot] << 8;
		}
		if (pressure == 0) {
			pressure = 1;
		}
		if (pressure > max_pressure) {
			pressure = max_pressure;
		}
		struct nt36523_contact *c = &frame->contacts[frame->count++];
		c->id = (uint8_t)(id - 1);
		c->phase = (uint8_t)event;
		c->x = (uint16_t)x;
		c->y = (uint16_t)y;
		c->width = p[4] ? p[4] : 1;
		c->pressure = (uint16_t)pressure;
	}
	return NT36523_OK;
}

void
nt36523_watchdog_init(struct nt36523_watchdog *wd, uint8_t confirmation_frames)
{
	wd->confirmation_frames = confirmation_frames ? confirmation_frames : NT36523_WATCHDOG_FRAMES;
	wd->streak = 0;
}

bool
nt36523_watchdog_should_recover(struct nt36523_watchdog *wd, const struct nt36523_frame *frame)
{
	if (frame->kind == NT36523_FRAME_FIRMWARE_RESET) {
		wd->streak = 0;
		return true;
	}
	if (frame->kind == NT36523_FRAME_WATCHDOG) {
		if (++wd->streak >= wd->confirmation_frames) {
			wd->streak = 0;
			return true;
		}
		return false;
	}
	wd->streak = 0;
	return false;
}
