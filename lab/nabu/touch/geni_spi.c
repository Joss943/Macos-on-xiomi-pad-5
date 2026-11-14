/*
 * Qualcomm QUPv3 GENI SPI master, FIFO mode, polled. See geni_spi.h.
 */
#include "geni_spi.h"

#define R(spi, off)      ((spi)->io.read32((spi)->io.context, (off)))
#define W(spi, off, v)   ((spi)->io.write32((spi)->io.context, (off), (v)))
#define NOW(spi)         ((spi)->io.now_us((spi)->io.context))

#define GENI_PACK_START_SHIFT 5u
#define GENI_PACK_DIR_SHIFT   4u
#define GENI_PACK_LEN_SHIFT   1u
#define GENI_PACK_STOP        1u
#define GENI_PACK_VECTOR_SHIFT 10u
#define GENI_CANCEL_WAIT_US   1000u

void
geni_spi_packing_cfg(uint32_t bits_per_word, uint32_t words_per_fifo, bool msb_first,
    uint32_t *cfg0, uint32_t *cfg1)
{
	uint32_t vector[4] = { 0, 0, 0, 0 };
	const uint32_t bytes_per_word = (bits_per_word + 7u) / 8u;
	const uint32_t vectors = bytes_per_word * words_per_fifo;
	*cfg0 = 0;
	*cfg1 = 0;
	if (bits_per_word == 0 || vectors == 0 || vectors > 4) {
		return;
	}
	/* One vector per byte lane: where it starts, which way it shifts, how long it is. */
	for (uint32_t lane = 0; lane < vectors; lane++) {
		const uint32_t word = lane / bytes_per_word;
		const uint32_t byte_in_word = lane % bytes_per_word;
		const uint32_t remaining = bits_per_word - 8u * byte_in_word;
		const uint32_t length = (remaining < 8u ? remaining : 8u) - 1u;
		uint32_t start;
		if (msb_first) {
			start = 8u * bytes_per_word * word + (bits_per_word - 1u) - 8u * byte_in_word;
		} else {
			start = 8u * bytes_per_word * word + 8u * byte_in_word;
		}
		vector[lane] = (start << GENI_PACK_START_SHIFT) |
		    ((msb_first ? 1u : 0u) << GENI_PACK_DIR_SHIFT) |
		    (length << GENI_PACK_LEN_SHIFT);
	}
	vector[vectors - 1] |= GENI_PACK_STOP;
	*cfg0 = vector[0] | (vector[1] << GENI_PACK_VECTOR_SHIFT);
	*cfg1 = vector[2] | (vector[3] << GENI_PACK_VECTOR_SHIFT);
}

int
geni_spi_probe(struct geni_spi *spi)
{
	if (spi == NULL || spi->io.read32 == NULL || spi->io.write32 == NULL || spi->io.now_us == NULL) {
		return GENI_SPI_EINVAL;
	}
	if (GENI_FW_PROTOCOL(R(spi, GENI_FW_REVISION_RO)) != GENI_PROTOCOL_SPI) {
		return GENI_SPI_ENOTSPI;
	}
	const uint32_t param = R(spi, SE_HW_PARAM_0);
	const uint32_t width_bits = GENI_HW_TX_FIFO_WIDTH(param);
	spi->fifo_depth_words = spi->large_fifo ? GENI_HW_TX_FIFO_DEPTH_256(param) : GENI_HW_TX_FIFO_DEPTH(param);
	spi->fifo_width_bytes = width_bits / 8u;
	if (spi->fifo_width_bytes != 4u || spi->fifo_depth_words < 2u) {
		/* The byte-lane packing below assumes 32-bit FIFO words. */
		return GENI_SPI_EINVAL;
	}
	if (spi->timeout_us == 0) {
		spi->timeout_us = 100000u;
	}
	return GENI_SPI_OK;
}

int
geni_spi_configure(struct geni_spi *spi, const struct geni_spi_config *config)
{
	if (spi == NULL || config == NULL || spi->fifo_width_bytes != 4u || config->chip_select > 3u ||
	    config->mode > 3u || config->clk_div == 0 || config->clk_div > 0xFFFu || config->clk_sel > 7u) {
		return GENI_SPI_EINVAL;
	}
	uint32_t cfg0, cfg1;
	geni_spi_packing_cfg(8u, 4u, true, &cfg0, &cfg1);

	W(spi, SE_GENI_CLK_SEL, config->clk_sel);
	W(spi, GENI_SER_M_CLK_CFG,
	    (((uint32_t)config->clk_div << GENI_CLK_DIV_SHIFT) & GENI_CLK_DIV_MASK) | GENI_SER_CLK_EN);
	W(spi, SE_SPI_LOOPBACK, 0);
	W(spi, SE_SPI_DEMUX_SEL, config->chip_select);
	W(spi, SE_SPI_CPHA, (config->mode & 1u) ? GENI_SPI_CPHA : 0);
	W(spi, SE_SPI_CPOL, (config->mode & 2u) ? GENI_SPI_CPOL : 0);
	W(spi, SE_SPI_DEMUX_OUTPUT_INV, 0);
	W(spi, SE_SPI_WORD_LEN, 8u - GENI_SPI_MIN_WORD_LEN);
	W(spi, SE_GENI_TX_PACKING_CFG0, cfg0);
	W(spi, SE_GENI_TX_PACKING_CFG1, cfg1);
	W(spi, SE_GENI_RX_PACKING_CFG0, cfg0);
	W(spi, SE_GENI_RX_PACKING_CFG1, cfg1);
	W(spi, SE_GENI_BYTE_GRAN, 0);
	W(spi, SE_GENI_DMA_MODE_EN, R(spi, SE_GENI_DMA_MODE_EN) & ~GENI_DMA_MODE_EN);
	W(spi, SE_GENI_TX_WATERMARK_REG, 0);
	W(spi, SE_GENI_M_IRQ_EN, R(spi, SE_GENI_M_IRQ_EN) | GENI_M_CMD_DONE | GENI_M_ERRORS |
	    GENI_M_CMD_CANCEL_DONE | GENI_M_CMD_ABORT_DONE | GENI_M_RX_FIFO_WATERMARK |
	    GENI_M_RX_FIFO_LAST | GENI_M_TX_FIFO_WATERMARK);
	W(spi, SE_GENI_M_IRQ_CLEAR, 0xFFFFFFFFu);
	return GENI_SPI_OK;
}

static void
geni_spi_stop(struct geni_spi *spi)
{
	W(spi, SE_GENI_M_CMD_CTRL_REG, GENI_M_CMD_CANCEL);
	uint64_t deadline = NOW(spi) + GENI_CANCEL_WAIT_US;
	while (!(R(spi, SE_GENI_M_IRQ_STATUS) & GENI_M_CMD_CANCEL_DONE)) {
		if (NOW(spi) > deadline) {
			W(spi, SE_GENI_M_CMD_CTRL_REG, GENI_M_CMD_ABORT);
			deadline = NOW(spi) + GENI_CANCEL_WAIT_US;
			while (!(R(spi, SE_GENI_M_IRQ_STATUS) & GENI_M_CMD_ABORT_DONE) && NOW(spi) <= deadline) {
			}
			break;
		}
	}
	W(spi, SE_GENI_M_IRQ_CLEAR, 0xFFFFFFFFu);
}

static uint32_t
geni_spi_fill_tx(struct geni_spi *spi, const uint8_t *tx, uint32_t len, uint32_t offset)
{
	while (offset < len) {
		const uint32_t queued = R(spi, SE_GENI_TX_FIFO_STATUS) & GENI_TX_FIFO_WC_MASK;
		if (queued >= spi->fifo_depth_words) {
			break;
		}
		uint32_t word = 0;
		for (uint32_t lane = 0; lane < 4u && offset < len; lane++, offset++) {
			word |= (uint32_t)tx[offset] << (8u * lane);
		}
		W(spi, SE_GENI_TX_FIFOn, word);
	}
	return offset;
}

static uint32_t
geni_spi_drain_rx(struct geni_spi *spi, uint8_t *rx, uint32_t len, uint32_t offset)
{
	const uint32_t status = R(spi, SE_GENI_RX_FIFO_STATUS);
	const uint32_t words = status & GENI_RX_FIFO_WC_MASK;
	uint32_t available = words * 4u;
	if (status & GENI_RX_LAST) {
		const uint32_t valid = GENI_RX_LAST_VALID(status);
		if (valid != 0 && valid < 4u && available >= 4u) {
			available -= 4u - valid;
		}
	}
	for (uint32_t w = 0; w < words; w++) {
		const uint32_t word = R(spi, SE_GENI_RX_FIFOn);
		for (uint32_t lane = 0; lane < 4u && available > 0; lane++, available--) {
			if (offset < len) {
				rx[offset++] = (uint8_t)(word >> (8u * lane));
			}
		}
	}
	return offset;
}

int
geni_spi_transfer(struct geni_spi *spi, const uint8_t *tx, uint8_t *rx, uint32_t len)
{
	if (spi == NULL || spi->fifo_width_bytes != 4u || len == 0 || len > GENI_SPI_TRANS_LEN_MAX ||
	    (tx == NULL && rx == NULL)) {
		return GENI_SPI_EINVAL;
	}
	uint32_t opcode = 0;
	W(spi, SE_GENI_M_IRQ_CLEAR, 0xFFFFFFFFu);
	if (tx != NULL) {
		opcode |= GENI_SPI_TX_ONLY;
		W(spi, SE_SPI_TX_TRANS_LEN, len);
	}
	if (rx != NULL) {
		opcode |= GENI_SPI_RX_ONLY;
		W(spi, SE_SPI_RX_TRANS_LEN, len);
	}
	/* No FRAGMENTATION parameter: chip select is released when the command ends. */
	W(spi, SE_GENI_M_CMD0, opcode << GENI_M_OPCODE_SHIFT);

	uint32_t tx_off = 0, rx_off = 0;
	bool done = false;
	unsigned idle_after_done = 0;
	const uint64_t deadline = NOW(spi) + spi->timeout_us;
	for (;;) {
		const uint32_t irq = R(spi, SE_GENI_M_IRQ_STATUS);
		if (irq & GENI_M_ERRORS) {
			W(spi, SE_GENI_M_IRQ_CLEAR, irq);
			geni_spi_stop(spi);
			return GENI_SPI_EHW;
		}
		if (tx != NULL) {
			tx_off = geni_spi_fill_tx(spi, tx, len, tx_off);
		}
		const uint32_t before = rx_off;
		if (rx != NULL) {
			rx_off = geni_spi_drain_rx(spi, rx, len, rx_off);
		}
		if (irq != 0) {
			W(spi, SE_GENI_M_IRQ_CLEAR, irq);
		}
		if (irq & GENI_M_CMD_DONE) {
			done = true;
		}
		if (done && (tx == NULL || tx_off == len) && (rx == NULL || rx_off == len)) {
			return GENI_SPI_OK;
		}
		if (done && rx_off == before && ++idle_after_done > 4u) {
			return GENI_SPI_ESHORT;
		}
		if (NOW(spi) > deadline) {
			geni_spi_stop(spi);
			return GENI_SPI_ETIMEDOUT;
		}
	}
}
