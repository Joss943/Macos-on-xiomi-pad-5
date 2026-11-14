/*
 * Novatek NT36523 SPI protocol for Xiaomi Pad 5 (nabu), kernel-portable C.
 *
 * Independent implementation of facts documented by the public nabu Linux
 * driver (SeimoDev/linux-xiaomi-nabu @ 4e6d08bb, drivers/input/touchscreen/
 * nt36523): SPI mode 0, 8-bit words, 9.6 MHz; 128-byte address pages selected
 * with a 3-byte 0xFF command; reads clock one extra dummy byte and their data
 * starts at the third received byte; 65-byte touch reports at 0x2FE00.
 * No code was copied. Nothing here touches hardware: callers own the bus.
 */
#ifndef NABU_NT36523_H
#define NABU_NT36523_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NT36523_SPI_HZ              9600000u
#define NT36523_EVENT_BUF_ADDR      0x2FE00u
#define NT36523_EVENT_MAP_RESET_OK  0x60u
#define NT36523_EVENT_MAP_FWINFO    0x78u
#define NT36523_REPORT_BYTES        66u   /* command byte + 65 data bytes */
#define NT36523_FWINFO_BYTES        39u   /* command byte + 38 data bytes */
#define NT36523_MAX_CONTACTS        10u
#define NT36523_WATCHDOG_FRAMES     11u
#define NT36523_DEFAULT_MAX_PRESSURE 1000u

enum nt36523_status {
	NT36523_OK = 0,
	NT36523_EINVAL = -1,
	NT36523_ESHORT = -2,
};

enum nt36523_frame_kind {
	NT36523_FRAME_TOUCH = 0,
	NT36523_FRAME_FIRMWARE_RESET,
	NT36523_FRAME_WATCHDOG,
};

enum nt36523_phase {
	NT36523_PHASE_DOWN = 1,
	NT36523_PHASE_MOVE = 2,
};

struct nt36523_contact {
	uint8_t id;          /* zero-based slot, 0..9 */
	uint8_t phase;       /* enum nt36523_phase */
	uint16_t x;
	uint16_t y;
	uint16_t width;
	uint16_t pressure;
};

struct nt36523_frame {
	uint8_t kind;        /* enum nt36523_frame_kind */
	uint8_t count;
	struct nt36523_contact contacts[NT36523_MAX_CONTACTS];
};

struct nt36523_fw_info {
	bool valid;
	uint8_t fw_ver;
	uint8_t x_num;
	uint8_t y_num;
	uint16_t abs_x_max;
	uint16_t abs_y_max;
	uint8_t max_button_num;
};

struct nt36523_watchdog {
	uint8_t confirmation_frames;
	uint8_t streak;
};

/* 3-byte page-select write: 0xFF, addr[22:15], addr[14:7]. */
size_t nt36523_build_set_page(uint32_t address, uint8_t out[3]);

/*
 * Build the full-duplex transfer for reading `data_len` bytes at `address`
 * (whose page was selected beforehand). Returns the transfer length,
 * data_len + 2, or 0 when `tx_cap` is too small.
 */
size_t nt36523_build_read(uint32_t address, size_t data_len, uint8_t *tx, size_t tx_cap);

/* Copy the read payload, which starts at rx[2], into `out`. */
int nt36523_extract_read(const uint8_t *rx, size_t xfer_len, uint8_t *out, size_t data_len);

/* `buf` has the Linux driver layout: buf[0] = command, buf[1..] = data. */
int nt36523_parse_fw_info(const uint8_t *buf, size_t len, struct nt36523_fw_info *info);

/* Same rules as lab/nabu/nt36523_touch.py: parse_report. */
int nt36523_parse_report(const uint8_t *packet, size_t len, uint16_t max_x, uint16_t max_y,
    uint16_t max_pressure, struct nt36523_frame *frame);

void nt36523_watchdog_init(struct nt36523_watchdog *wd, uint8_t confirmation_frames);
bool nt36523_watchdog_should_recover(struct nt36523_watchdog *wd, const struct nt36523_frame *frame);

#ifdef __cplusplus
}
#endif

#endif /* NABU_NT36523_H */
