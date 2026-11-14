/*
 * QRTR (IPC router) v1 framing and QMI TLV encoding, kernel-portable C.
 *
 * The nabu WLAN (WCN3990 family, integrated on SM8150 at 0x18800000) is
 * brought up by the modem DSP and controlled through the QMI "WLFW" service
 * (id 0x45, version 1) reached over QRTR. Linux implements QRTR and QMI under
 * the GPL, so this is an independent implementation of the wire formats.
 * Message and TLV identifiers come from the ISC-licensed ath10k files
 * qmi_wlfw_v01.{h,c} (Linux v6.12), whose values are facts of the protocol.
 *
 * No transport is implemented here: QRTR packets still need GLINK/SMEM to
 * reach the modem, and the modem must already be running (see WIFI.md).
 */
#ifndef NABU_QMI_QRTR_H
#define NABU_QMI_QRTR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define QRTR_PROTO_VER_1        1u
#define QRTR_HDR_V1_BYTES       32u
#define QRTR_NODE_BCAST         0xFFFFFFFFu
#define QRTR_PORT_CTRL          0xFFFFFFFEu

enum qrtr_type {
	QRTR_TYPE_DATA = 1, QRTR_TYPE_HELLO = 2, QRTR_TYPE_BYE = 3, QRTR_TYPE_NEW_SERVER = 4,
	QRTR_TYPE_DEL_SERVER = 5, QRTR_TYPE_DEL_CLIENT = 6, QRTR_TYPE_RESUME_TX = 7,
	QRTR_TYPE_EXIT = 8, QRTR_TYPE_PING = 9, QRTR_TYPE_NEW_LOOKUP = 10, QRTR_TYPE_DEL_LOOKUP = 11,
};

struct qrtr_hdr {
	uint32_t type;
	uint32_t src_node;
	uint32_t src_port;
	uint32_t confirm_rx;
	uint32_t size;          /* payload bytes, excluding header and padding */
	uint32_t dst_node;
	uint32_t dst_port;
};

struct qrtr_server {
	uint32_t service;
	uint32_t version;
	uint32_t instance;
	uint32_t node;
	uint32_t port;
};

#define QMI_HDR_BYTES           7u
#define QMI_REQUEST             0u
#define QMI_RESPONSE            2u
#define QMI_INDICATION          4u
#define QMI_TLV_RESULT          0x02u

struct qmi_hdr {
	uint8_t type;
	uint16_t txn_id;
	uint16_t msg_id;
	uint16_t msg_len;
};

struct qmi_writer {
	uint8_t *buf;
	size_t cap;
	size_t len;
	bool overflow;
};

struct qmi_tlv {
	uint8_t type;
	uint16_t len;
	const uint8_t *value;
};

/* WLFW service and the messages of the first handshake steps. */
#define WLFW_SERVICE_ID                 0x45u
#define WLFW_SERVICE_VERSION            0x01u
#define WLFW_IND_REGISTER               0x0020u
#define WLFW_FW_READY_IND               0x0021u
#define WLFW_WLAN_MODE                  0x0022u
#define WLFW_WLAN_CFG                   0x0023u
#define WLFW_CAP                        0x0024u
#define WLFW_BDF_DOWNLOAD               0x0025u
#define WLFW_CAL_REPORT                 0x0026u
#define WLFW_MSA_READY_IND              0x002Bu
#define WLFW_MSA_INFO                   0x002Du
#define WLFW_MSA_READY                  0x002Eu
#define WLFW_HOST_CAP                   0x0034u
#define WLFW_FW_READY_STATUS_BIT        0x1ull     /* fw_status bit in the IND_REGISTER response */
#define WLFW_HOST_CLIENT_ID             0x4B4E454Cu /* value the ath10k host sends; any id works */

/* QRTR */
size_t qrtr_encode(const struct qrtr_hdr *hdr, const void *payload, uint8_t *out, size_t cap);
int qrtr_decode(const uint8_t *packet, size_t len, struct qrtr_hdr *hdr, const uint8_t **payload);
size_t qrtr_encode_new_lookup(uint32_t src_node, uint32_t src_port, uint32_t service, uint32_t version,
    uint32_t instance, uint8_t *out, size_t cap);
int qrtr_parse_server(const struct qrtr_hdr *hdr, const uint8_t *payload, struct qrtr_server *server);

/* QMI */
void qmi_writer_init(struct qmi_writer *w, uint8_t *buf, size_t cap, uint8_t type, uint16_t txn_id,
    uint16_t msg_id);
void qmi_put_tlv(struct qmi_writer *w, uint8_t type, const void *value, uint16_t len);
void qmi_put_u8(struct qmi_writer *w, uint8_t type, uint8_t value);
void qmi_put_u32(struct qmi_writer *w, uint8_t type, uint32_t value);
size_t qmi_finish(struct qmi_writer *w);   /* returns 0 on overflow */
int qmi_decode_hdr(const uint8_t *msg, size_t len, struct qmi_hdr *hdr);
/* Iterate TLVs: *cursor starts at 0; returns 1 with a TLV, 0 at the end, <0 on malformed input. */
int qmi_next_tlv(const uint8_t *msg, size_t len, size_t *cursor, struct qmi_tlv *tlv);
int qmi_find_tlv(const uint8_t *msg, size_t len, uint8_t type, struct qmi_tlv *tlv);
int qmi_result(const uint8_t *msg, size_t len, uint16_t *result, uint16_t *error);

/* WLFW */
size_t wlfw_ind_register_request(uint16_t txn_id, bool xo_cal, uint8_t *out, size_t cap);
/* Parses result TLV and the optional fw_status TLV 0x10. */
int wlfw_ind_register_response(const uint8_t *msg, size_t len, uint16_t *result, bool *fw_ready);

#ifdef __cplusplus
}
#endif

#endif /* NABU_QMI_QRTR_H */
