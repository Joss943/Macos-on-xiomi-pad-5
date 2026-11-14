/*
 * Host tests for the nabu touch stack: GENI SPI engine, NT36523 protocol and
 * HID report path, run against a behavioural model of a GENI serial engine
 * wired to a fake NT36523. The model encodes the public register semantics
 * as this project reads them; passing proves internal consistency, not
 * behaviour on SM8150 silicon.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "geni_spi.h"
#include "nabu_touch_hid.h"
#include "nt36523.h"

static int failures;
#define CHECK(cond) do { if (!(cond)) { fprintf(stderr, "%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

/* ---------- fake NT36523 ---------- */
struct fake_nt36523 {
	uint8_t mem[0x40000];
	uint32_t page_base;
	uint8_t cmd;
	uint8_t page_bytes[2];
	uint32_t index;
	unsigned transactions;
};

static void
nt_begin(struct fake_nt36523 *d)
{
	d->index = 0;
}

static uint8_t
nt_exchange(struct fake_nt36523 *d, uint8_t mosi)
{
	uint32_t i = d->index++;
	if (i == 0) {
		d->cmd = mosi;
		return 0xAA;
	}
	if (d->cmd == 0xFF) {                      /* page select */
		if (i <= 2) {
			d->page_bytes[i - 1] = mosi;
		}
		if (i == 2) {
			d->page_base = ((uint32_t)d->page_bytes[0] << 15) | ((uint32_t)d->page_bytes[1] << 7);
		}
		return 0;
	}
	if (d->cmd & 0x80) {                       /* write */
		d->mem[(d->page_base | (d->cmd & 0x7Fu)) + i - 1] = mosi;
		return 0;
	}
	if (i == 1) {
		return 0x55;                           /* dummy turnaround byte */
	}
	return d->mem[(d->page_base | (d->cmd & 0x7Fu)) + i - 2];
}

static void
nt_end(struct fake_nt36523 *d)
{
	d->transactions++;
}

/* ---------- behavioural GENI serial engine ---------- */
#define FIFO_WORDS 16u
struct fake_geni {
	uint32_t regs[0x1000 / 4];
	uint32_t protocol;
	uint32_t tx[FIFO_WORDS], tx_head, tx_count;
	uint32_t rx[FIFO_WORDS], rx_head, rx_count;
	uint32_t rx_last_valid;                    /* valid bytes of the final RX word, 0 = none pending */
	bool rx_last_in_fifo;
	uint32_t m_irq;
	bool active;
	uint32_t opcode, len, shifted;
	uint32_t cur_tx_word, cur_tx_lanes;
	uint32_t asm_word, asm_lanes;
	bool inject_illegal, stall, cancel_seen;
	uint64_t clock;
	unsigned writes_cmd0;
	struct fake_nt36523 *dev;
};

static void
geni_push_rx(struct fake_geni *g, uint32_t word, bool last, uint32_t valid)
{
	g->rx[(g->rx_head + g->rx_count) % FIFO_WORDS] = word;
	g->rx_count++;
	if (last) {
		g->rx_last_in_fifo = true;
		g->rx_last_valid = valid == 4 ? 0 : valid;
	}
}

static void
geni_step(struct fake_geni *g)
{
	for (unsigned budget = 0; g->active && !g->stall && budget < 5; budget++) {
		if (g->shifted == g->len) {
			g->active = false;
			g->m_irq |= GENI_M_CMD_DONE;
			nt_end(g->dev);
			return;
		}
		if ((g->opcode & GENI_SPI_RX_ONLY) && g->rx_count == FIFO_WORDS) {
			return;                            /* RX full: the clock stalls before any bit moves */
		}
		uint8_t mosi = 0;
		if (g->opcode & GENI_SPI_TX_ONLY) {
			if (g->cur_tx_lanes == 0) {
				if (g->tx_count == 0) {
					return;                    /* starved: wait for the driver */
				}
				g->cur_tx_word = g->tx[g->tx_head];
				g->tx_head = (g->tx_head + 1) % FIFO_WORDS;
				g->tx_count--;
				g->cur_tx_lanes = 4;
			}
			mosi = (uint8_t)(g->cur_tx_word >> (8u * (4u - g->cur_tx_lanes)));
			g->cur_tx_lanes--;
		}
		const uint8_t miso = nt_exchange(g->dev, mosi);
		g->shifted++;
		if (g->opcode & GENI_SPI_RX_ONLY) {
			g->asm_word |= (uint32_t)miso << (8u * g->asm_lanes);
			g->asm_lanes++;
			const bool last = g->shifted == g->len;
			if (g->asm_lanes == 4 || last) {
				geni_push_rx(g, g->asm_word, last, g->asm_lanes);
				g->asm_word = 0;
				g->asm_lanes = 0;
			}
		}
	}
}

static uint32_t
geni_read(void *ctx, uint32_t off)
{
	struct fake_geni *g = ctx;
	g->clock++;
	geni_step(g);
	switch (off) {
	case GENI_FW_REVISION_RO:
		return g->protocol << 8;
	case SE_HW_PARAM_0:
		return (32u << 24) | (FIFO_WORDS << 16);
	case SE_GENI_M_IRQ_STATUS:
		return g->m_irq;
	case SE_GENI_TX_FIFO_STATUS:
		return g->tx_count;
	case SE_GENI_RX_FIFO_STATUS: {
		uint32_t v = g->rx_count;
		if (g->rx_last_in_fifo) {
			v |= GENI_RX_LAST | (g->rx_last_valid << 28);
		}
		return v;
	}
	case SE_GENI_RX_FIFOn: {
		assert(g->rx_count > 0);
		uint32_t w = g->rx[g->rx_head];
		g->rx_head = (g->rx_head + 1) % FIFO_WORDS;
		if (--g->rx_count == 0) {
			g->rx_last_in_fifo = false;
		}
		return w;
	}
	default:
		return g->regs[off / 4];
	}
}

static void
geni_write(void *ctx, uint32_t off, uint32_t v)
{
	struct fake_geni *g = ctx;
	g->clock++;
	switch (off) {
	case SE_GENI_M_IRQ_CLEAR:
		g->m_irq &= ~v;
		break;
	case SE_GENI_TX_FIFOn:
		assert(g->tx_count < FIFO_WORDS);
		g->tx[(g->tx_head + g->tx_count) % FIFO_WORDS] = v;
		g->tx_count++;
		break;
	case SE_GENI_M_CMD0:
		g->writes_cmd0++;
		g->opcode = v >> GENI_M_OPCODE_SHIFT;
		g->len = (g->opcode & GENI_SPI_TX_ONLY) ? g->regs[SE_SPI_TX_TRANS_LEN / 4] : g->regs[SE_SPI_RX_TRANS_LEN / 4];
		g->shifted = 0;
		g->cur_tx_lanes = 0;
		g->asm_lanes = 0;
		g->asm_word = 0;
		g->active = true;
		nt_begin(g->dev);
		if (g->inject_illegal) {
			g->m_irq |= GENI_M_ILLEGAL_CMD;
			g->active = false;
		}
		break;
	case SE_GENI_M_CMD_CTRL_REG:
		if (v & GENI_M_CMD_CANCEL) {
			g->cancel_seen = true;
			g->active = false;
			g->m_irq |= GENI_M_CMD_CANCEL_DONE;
		}
		break;
	default:
		g->regs[off / 4] = v;
		break;
	}
	geni_step(g);
}

static uint64_t
geni_now(void *ctx)
{
	return ((struct fake_geni *)ctx)->clock;
}

static struct fake_geni *
new_geni(struct fake_nt36523 *dev, struct geni_spi *spi)
{
	struct fake_geni *g = calloc(1, sizeof(*g));
	g->protocol = GENI_PROTOCOL_SPI;
	g->dev = dev;
	memset(spi, 0, sizeof(*spi));
	spi->io = (struct geni_mmio){ g, geni_read, geni_write, geni_now };
	spi->timeout_us = 20000;
	return g;
}

/* ---------- tests ---------- */
static void
test_packing(void)
{
	uint32_t c0, c1;
	geni_spi_packing_cfg(8, 4, true, &c0, &c1);
	CHECK(c0 == 0x0007F8FEu && c1 == 0x000FFEFEu);
	geni_spi_packing_cfg(8, 4, false, &c0, &c1);
	CHECK(c0 == 0x0004380Eu && c1 == 0x000C3E0Eu);
	geni_spi_packing_cfg(16, 2, true, &c0, &c1);   /* lanes start at bits 15, 7, 31, 23 */
	CHECK(c0 == ((15u << 5 | 1u << 4 | 7u << 1) | ((7u << 5 | 1u << 4 | 7u << 1) << 10)));
	CHECK(c1 == ((31u << 5 | 1u << 4 | 7u << 1) | ((23u << 5 | 1u << 4 | 7u << 1 | 1u) << 10)));
}

static void
test_probe_and_configure(void)
{
	struct fake_nt36523 *dev = calloc(1, sizeof(*dev));
	struct geni_spi spi;
	struct fake_geni *g = new_geni(dev, &spi);
	g->protocol = 3;                            /* I2C firmware: must be refused */
	CHECK(geni_spi_probe(&spi) == GENI_SPI_ENOTSPI);
	g->protocol = GENI_PROTOCOL_SPI;
	CHECK(geni_spi_probe(&spi) == GENI_SPI_OK);
	CHECK(spi.fifo_depth_words == FIFO_WORDS && spi.fifo_width_bytes == 4);
	struct geni_spi_config cfg = { .chip_select = 0, .mode = 0, .clk_sel = 0, .clk_div = 2 };
	CHECK(geni_spi_configure(&spi, &cfg) == GENI_SPI_OK);
	CHECK(g->regs[SE_SPI_WORD_LEN / 4] == 4);
	CHECK(g->regs[GENI_SER_M_CLK_CFG / 4] == ((2u << 4) | 1u));
	CHECK(g->regs[SE_SPI_CPHA / 4] == 0 && g->regs[SE_SPI_CPOL / 4] == 0);
	CHECK(g->regs[SE_GENI_TX_PACKING_CFG0 / 4] == 0x0007F8FEu);
	CHECK((g->regs[SE_GENI_DMA_MODE_EN / 4] & 1u) == 0);
	cfg.mode = 3;
	CHECK(geni_spi_configure(&spi, &cfg) == GENI_SPI_OK);
	CHECK(g->regs[SE_SPI_CPHA / 4] == GENI_SPI_CPHA && g->regs[SE_SPI_CPOL / 4] == GENI_SPI_CPOL);
	cfg.clk_div = 0;
	CHECK(geni_spi_configure(&spi, &cfg) == GENI_SPI_EINVAL);
	free(g);
	free(dev);
}

static int
nt_read(struct geni_spi *spi, uint32_t address, uint8_t *out, size_t data_len)
{
	uint8_t page[3], tx[128], rx[128];
	nt36523_build_set_page(address, page);
	int rc = geni_spi_transfer(spi, page, NULL, 3);
	if (rc != GENI_SPI_OK) {
		return rc;
	}
	const size_t xfer = nt36523_build_read(address, data_len, tx, sizeof(tx));
	if (xfer == 0) {
		return GENI_SPI_EINVAL;
	}
	rc = geni_spi_transfer(spi, tx, rx, (uint32_t)xfer);
	if (rc != GENI_SPI_OK) {
		return rc;
	}
	return nt36523_extract_read(rx, xfer, out, data_len);
}

static void
test_end_to_end_touch(void)
{
	struct fake_nt36523 *dev = calloc(1, sizeof(*dev));
	struct geni_spi spi;
	struct fake_geni *g = new_geni(dev, &spi);
	struct geni_spi_config cfg = { .clk_div = 2 };
	CHECK(geni_spi_probe(&spi) == GENI_SPI_OK && geni_spi_configure(&spi, &cfg) == GENI_SPI_OK);

	/* Firmware info at EVENT_BUF_ADDR | 0x78: version 0x21 / 0xDE, 2560 x 1600. */
	uint8_t *fw = dev->mem + (NT36523_EVENT_BUF_ADDR | NT36523_EVENT_MAP_FWINFO);
	fw[0] = 0x21; fw[1] = 0xDE; fw[2] = 18; fw[3] = 32; fw[4] = 0x09; fw[5] = 0xFF; fw[6] = 0x06; fw[7] = 0x3F;
	uint8_t info_buf[NT36523_FWINFO_BYTES] = { NT36523_EVENT_MAP_FWINFO };
	CHECK(nt_read(&spi, NT36523_EVENT_BUF_ADDR | NT36523_EVENT_MAP_FWINFO, info_buf + 1, 38) == NT36523_OK);
	struct nt36523_fw_info info;
	CHECK(nt36523_parse_fw_info(info_buf, sizeof(info_buf), &info) == NT36523_OK);
	CHECK(info.valid && info.abs_x_max == 2559 && info.abs_y_max == 1599);

	/* Two fingers in the 65-byte event buffer. */
	uint8_t *ev = dev->mem + NT36523_EVENT_BUF_ADDR;
	memset(ev, 0, 65);
	ev[0] = (1 << 3) | 1; ev[1] = 0x45; ev[2] = 0x34; ev[3] = 0x89; ev[4] = 3; ev[5] = 0x40;
	ev[6] = (2 << 3) | 2; ev[7] = 0x12; ev[8] = 0x34; ev[9] = 0x56; ev[10] = 4; ev[11] = 0x20;
	ev[62] = 0x01;                                 /* pressure high byte, slot 0 */
	uint8_t report[NT36523_REPORT_BYTES] = { 0 };
	CHECK(nt_read(&spi, NT36523_EVENT_BUF_ADDR, report + 1, 65) == NT36523_OK);
	CHECK(memcmp(report + 1, ev, 65) == 0);
	struct nt36523_frame frame;
	CHECK(nt36523_parse_report(report, sizeof(report), info.abs_x_max, info.abs_y_max, 1000, &frame) == NT36523_OK);
	CHECK(frame.kind == NT36523_FRAME_TOUCH && frame.count == 2);
	CHECK(frame.contacts[0].id == 0 && frame.contacts[0].x == 0x458 && frame.contacts[0].y == 0x349);
	CHECK(frame.contacts[0].pressure == 0x140);
	CHECK(frame.contacts[1].id == 1 && frame.contacts[1].phase == NT36523_PHASE_MOVE);

	/* HID: two down, then finger 1 lifts and must be reported released once. */
	struct nabu_touch_hid_state hid = { 0 };
	uint8_t hid_report[NABU_TOUCH_INPUT_REPORT_BYTES];
	CHECK(nabu_touch_hid_pack(&hid, &frame, 10, hid_report, sizeof(hid_report)) == NABU_TOUCH_INPUT_REPORT_BYTES);
	CHECK(hid_report[0] == 1 && hid_report[1] == 1 && hid_report[2] == 0);
	CHECK(hid_report[3] == 0x58 && hid_report[4] == 0x04 && hid_report[5] == 0x49 && hid_report[6] == 0x03);
	CHECK(hid_report[81] == 2 && hid_report[82] == 10 && hid_report[83] == 0);
	frame.count = 1;
	CHECK(nabu_touch_hid_pack(&hid, &frame, 20, hid_report, sizeof(hid_report)) == NABU_TOUCH_INPUT_REPORT_BYTES);
	CHECK(hid_report[81] == 2);
	CHECK(hid_report[9] == 0x00 && hid_report[10] == 1);  /* second slot: id 1, tip released */
	frame.count = 0;
	CHECK(nabu_touch_hid_pack(&hid, &frame, 30, hid_report, sizeof(hid_report)) == NABU_TOUCH_INPUT_REPORT_BYTES);
	CHECK(hid_report[81] == 1 && hid_report[1] == 0 && hid_report[2] == 0);
	CHECK(nabu_touch_hid_pack(&hid, &frame, 40, hid_report, sizeof(hid_report)) == NABU_TOUCH_INPUT_REPORT_BYTES);
	CHECK(hid_report[81] == 0);
	CHECK(dev->transactions == 4);
	free(g);
	free(dev);
}

static void
test_odd_lengths_and_large_reads(void)
{
	struct fake_nt36523 *dev = calloc(1, sizeof(*dev));
	struct geni_spi spi;
	struct fake_geni *g = new_geni(dev, &spi);
	struct geni_spi_config cfg = { .clk_div = 2 };
	CHECK(geni_spi_probe(&spi) == GENI_SPI_OK && geni_spi_configure(&spi, &cfg) == GENI_SPI_OK);
	for (uint32_t i = 0; i < 0x200; i++) {
		dev->mem[0x10000 + i] = (uint8_t)(i * 7 + 3);
	}
	for (size_t n = 1; n <= 120; n++) {             /* every RX_LAST valid-byte case, FIFO wrap */
		uint8_t out[128];
		int rc = nt_read(&spi, 0x10000, out, n);
		if (rc != NT36523_OK) {
			fprintf(stderr, "read of %zu bytes returned %d\n", n, rc);
		}
		CHECK(rc == NT36523_OK);
		CHECK(memcmp(out, dev->mem + 0x10000, n) == 0);
	}
	free(g);
	free(dev);
}

static void
test_errors(void)
{
	struct fake_nt36523 *dev = calloc(1, sizeof(*dev));
	struct geni_spi spi;
	struct fake_geni *g = new_geni(dev, &spi);
	struct geni_spi_config cfg = { .clk_div = 2 };
	uint8_t buf[8] = { 0 };
	CHECK(geni_spi_probe(&spi) == GENI_SPI_OK && geni_spi_configure(&spi, &cfg) == GENI_SPI_OK);
	CHECK(geni_spi_transfer(&spi, buf, buf, 0) == GENI_SPI_EINVAL);
	CHECK(geni_spi_transfer(&spi, NULL, NULL, 4) == GENI_SPI_EINVAL);
	g->inject_illegal = true;
	CHECK(geni_spi_transfer(&spi, buf, buf, 8) == GENI_SPI_EHW);
	CHECK(g->cancel_seen);
	g->inject_illegal = false;
	g->cancel_seen = false;
	g->stall = true;
	CHECK(geni_spi_transfer(&spi, buf, buf, 8) == GENI_SPI_ETIMEDOUT);
	CHECK(g->cancel_seen);
	free(g);
	free(dev);
}

static void
test_hid_descriptor(void)
{
	uint8_t desc[NABU_TOUCH_DESCRIPTOR_MAX];
	size_t len = nabu_touch_hid_descriptor(2559, 1599, 1000, desc, sizeof(desc));
	CHECK(len > 0 && len <= sizeof(desc));
	CHECK(nabu_touch_hid_descriptor(2559, 1599, 1000, desc, 16) == 0);
	/* Walk the items: balanced collections, and report sizes add up per report id. */
	int depth = 0;
	uint32_t report_id = 0, size = 0, count = 0, bits[3] = { 0, 0, 0 };
	for (size_t i = 0; i < len;) {
		uint8_t prefix = desc[i];
		uint32_t n = prefix & 3u;
		if (n == 3) {
			n = 4;
		}
		CHECK(i + 1 + n <= len);
		uint32_t v = 0;
		for (uint32_t k = 0; k < n; k++) {
			v |= (uint32_t)desc[i + 1 + k] << (8u * k);
		}
		switch (prefix & 0xFCu) {
		case 0xA0: depth++; break;
		case 0xC0: depth--; CHECK(depth >= 0); break;
		case 0x84: report_id = v; break;
		case 0x74: size = v; break;
		case 0x94: count = v; break;
		case 0x80: case 0xB0: if (report_id < 3) { bits[report_id] += size * count; } break;
		default: break;
		}
		i += 1 + n;
	}
	CHECK(depth == 0);
	CHECK(bits[1] == (NABU_TOUCH_INPUT_REPORT_BYTES - 1u) * 8u);
	CHECK(bits[2] == 8u);
	uint8_t feature[2];
	CHECK(nabu_touch_hid_feature(feature, sizeof(feature)) == 2 && feature[0] == 2 && feature[1] == 10);
}

static void
test_watchdog(void)
{
	struct nt36523_watchdog wd;
	struct nt36523_frame wdf = { .kind = NT36523_FRAME_WATCHDOG }, ok = { .kind = NT36523_FRAME_TOUCH };
	nt36523_watchdog_init(&wd, 0);
	for (int i = 0; i < 10; i++) {
		CHECK(!nt36523_watchdog_should_recover(&wd, &wdf));
	}
	CHECK(!nt36523_watchdog_should_recover(&wd, &ok));
	for (int i = 0; i < 10; i++) {
		CHECK(!nt36523_watchdog_should_recover(&wd, &wdf));
	}
	CHECK(nt36523_watchdog_should_recover(&wd, &wdf));
}

int
main(void)
{
	test_packing();
	test_probe_and_configure();
	test_end_to_end_touch();
	test_odd_lengths_and_large_reads();
	test_errors();
	test_hid_descriptor();
	test_watchdog();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	printf("touch stack: all checks passed\n");
	return 0;
}
