/*
 * Qualcomm QUPv3 GENI serial engine, SPI master, FIFO mode, polled.
 *
 * Independent implementation from the register map published in the public
 * headers include/linux/soc/qcom/geni-se.h and drivers/spi/spi-geni-qcom.c
 * (Linux v6.12): offsets, bit fields and the documented FIFO packing rule.
 * No code was copied. MMIO goes through caller-supplied accessors so the same
 * file builds in a kext and in host tests.
 *
 * On nabu the touch controller sits on QUPv3 wrapper 2, SE1 (0x00C84000,
 * GIC SPI 583, pins GPIO 23-26). This engine assumes, and checks, that the
 * boot firmware already loaded the SPI protocol firmware into the SE. It
 * does not program GCC clocks, TLMM pin functions or interconnect votes.
 */
#ifndef NABU_GENI_SPI_H
#define NABU_GENI_SPI_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Serial engine register offsets. */
#define GENI_SER_M_CLK_CFG        0x048u
#define GENI_FW_REVISION_RO       0x068u
#define SE_GENI_CLK_SEL           0x07Cu
#define SE_SPI_CPHA               0x224u
#define SE_SPI_LOOPBACK           0x22Cu
#define SE_SPI_CPOL               0x230u
#define SE_SPI_DEMUX_OUTPUT_INV   0x24Cu
#define SE_SPI_DEMUX_SEL          0x250u
#define SE_GENI_BYTE_GRAN         0x254u
#define SE_GENI_DMA_MODE_EN       0x258u
#define SE_GENI_TX_PACKING_CFG0   0x260u
#define SE_GENI_TX_PACKING_CFG1   0x264u
#define SE_SPI_WORD_LEN           0x268u
#define SE_SPI_TX_TRANS_LEN       0x26Cu
#define SE_SPI_RX_TRANS_LEN       0x270u
#define SE_GENI_RX_PACKING_CFG0   0x284u
#define SE_GENI_RX_PACKING_CFG1   0x288u
#define SE_GENI_M_CMD0            0x600u
#define SE_GENI_M_CMD_CTRL_REG    0x604u
#define SE_GENI_M_IRQ_STATUS      0x610u
#define SE_GENI_M_IRQ_EN          0x614u
#define SE_GENI_M_IRQ_CLEAR       0x618u
#define SE_GENI_TX_FIFOn          0x700u
#define SE_GENI_RX_FIFOn          0x780u
#define SE_GENI_TX_FIFO_STATUS    0x800u
#define SE_GENI_RX_FIFO_STATUS    0x804u
#define SE_GENI_TX_WATERMARK_REG  0x80Cu
#define SE_HW_PARAM_0             0xE24u

/* Fields. */
#define GENI_FW_PROTOCOL(v)       (((v) >> 8) & 0xFFu)
#define GENI_PROTOCOL_SPI         1u
#define GENI_SER_CLK_EN           (1u << 0)
#define GENI_CLK_DIV_SHIFT        4u
#define GENI_CLK_DIV_MASK         0xFFF0u
#define GENI_DMA_MODE_EN          (1u << 0)
#define GENI_M_OPCODE_SHIFT       27u
#define GENI_M_PARAMS_MASK        0x07FFFFFFu
#define GENI_M_CMD_ABORT          (1u << 1)
#define GENI_M_CMD_CANCEL         (1u << 2)
#define GENI_M_CMD_DONE           (1u << 0)
#define GENI_M_CMD_OVERRUN        (1u << 1)
#define GENI_M_ILLEGAL_CMD        (1u << 2)
#define GENI_M_CMD_FAILURE        (1u << 3)
#define GENI_M_CMD_CANCEL_DONE    (1u << 4)
#define GENI_M_CMD_ABORT_DONE     (1u << 5)
#define GENI_M_RX_FIFO_RD_ERR     (1u << 24)
#define GENI_M_RX_FIFO_WR_ERR     (1u << 25)
#define GENI_M_RX_FIFO_WATERMARK  (1u << 26)
#define GENI_M_RX_FIFO_LAST       (1u << 27)
#define GENI_M_TX_FIFO_RD_ERR     (1u << 28)
#define GENI_M_TX_FIFO_WR_ERR     (1u << 29)
#define GENI_M_TX_FIFO_WATERMARK  (1u << 30)
#define GENI_M_ERRORS             (GENI_M_CMD_OVERRUN | GENI_M_ILLEGAL_CMD | GENI_M_CMD_FAILURE | \
	                           GENI_M_RX_FIFO_RD_ERR | GENI_M_RX_FIFO_WR_ERR | \
	                           GENI_M_TX_FIFO_RD_ERR | GENI_M_TX_FIFO_WR_ERR)
#define GENI_TX_FIFO_WC_MASK      0x0FFFFFFFu
#define GENI_RX_FIFO_WC_MASK      0x01FFFFFFu
#define GENI_RX_LAST              (1u << 31)
#define GENI_RX_LAST_VALID(v)     (((v) >> 28) & 0x7u)
#define GENI_HW_TX_FIFO_WIDTH(v)  (((v) >> 24) & 0x3Fu)
#define GENI_HW_TX_FIFO_DEPTH(v)  (((v) >> 16) & 0x3Fu)
#define GENI_HW_TX_FIFO_DEPTH_256(v) (((v) >> 16) & 0xFFu)
#define GENI_SPI_TX_ONLY          1u
#define GENI_SPI_RX_ONLY          2u
#define GENI_SPI_MIN_WORD_LEN     4u
#define GENI_SPI_TRANS_LEN_MAX    0x00FFFFFFu
#define GENI_SPI_CPHA             (1u << 0)
#define GENI_SPI_CPOL             (1u << 2)

struct geni_mmio {
	void *context;
	uint32_t (*read32)(void *context, uint32_t offset);
	void (*write32)(void *context, uint32_t offset, uint32_t value);
	uint64_t (*now_us)(void *context);
};

struct geni_spi {
	struct geni_mmio io;
	uint32_t fifo_depth_words;
	uint32_t fifo_width_bytes;
	uint32_t timeout_us;
	bool large_fifo;   /* QUP >= 3.10 encodes depth in 8 bits; SM8150 does not */
};

struct geni_spi_config {
	uint8_t chip_select;   /* 0..3 */
	uint8_t mode;          /* SPI mode 0..3 */
	uint8_t clk_sel;       /* SE clock source index chosen with the GCC rate */
	uint16_t clk_div;      /* SE clock divider, 1..4095 */
};

enum geni_spi_result {
	GENI_SPI_OK = 0,
	GENI_SPI_ENOTSPI = -1,   /* SE firmware is not the SPI protocol */
	GENI_SPI_EINVAL = -2,
	GENI_SPI_ETIMEDOUT = -3,
	GENI_SPI_EHW = -4,       /* sequencer reported an error */
	GENI_SPI_ESHORT = -5,    /* command finished before all RX bytes arrived */
};

/* Packing vectors for 8-bit SPI words, four per FIFO word, MSB first. */
void geni_spi_packing_cfg(uint32_t bits_per_word, uint32_t words_per_fifo, bool msb_first,
    uint32_t *cfg0, uint32_t *cfg1);

int geni_spi_probe(struct geni_spi *spi);
int geni_spi_configure(struct geni_spi *spi, const struct geni_spi_config *config);
/* Full duplex when both buffers are given; either may be NULL. */
int geni_spi_transfer(struct geni_spi *spi, const uint8_t *tx, uint8_t *rx, uint32_t len);

#ifdef __cplusplus
}
#endif

#endif /* NABU_GENI_SPI_H */
