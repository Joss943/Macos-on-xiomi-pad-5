/*
 * QRTR v1 framing and QMI TLV encoding. See qmi_qrtr.h.
 */
#include "qmi_qrtr.h"

#include <string.h>

static void
le32(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)v;
	p[1] = (uint8_t)(v >> 8);
	p[2] = (uint8_t)(v >> 16);
	p[3] = (uint8_t)(v >> 24);
}

static uint32_t
rd32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint16_t
rd16(const uint8_t *p)
{
	return (uint16_t)(p[0] | (p[1] << 8));
}

size_t
qrtr_encode(const struct qrtr_hdr *hdr, const void *payload, uint8_t *out, size_t cap)
{
	const size_t padded = (hdr->size + 3u) & ~(size_t)3u;
	const size_t total = QRTR_HDR_V1_BYTES + padded;
	if (out == NULL || total > cap || (hdr->size != 0 && payload == NULL)) {
		return 0;
	}
	le32(out + 0, QRTR_PROTO_VER_1);
	le32(out + 4, hdr->type);
	le32(out + 8, hdr->src_node);
	le32(out + 12, hdr->src_port);
	le32(out + 16, hdr->confirm_rx);
	le32(out + 20, hdr->size);
	le32(out + 24, hdr->dst_node);
	le32(out + 28, hdr->dst_port);
	if (hdr->size != 0) {
		memcpy(out + QRTR_HDR_V1_BYTES, payload, hdr->size);
	}
	memset(out + QRTR_HDR_V1_BYTES + hdr->size, 0, padded - hdr->size);
	return total;
}

int
qrtr_decode(const uint8_t *packet, size_t len, struct qrtr_hdr *hdr, const uint8_t **payload)
{
	if (packet == NULL || hdr == NULL || len < QRTR_HDR_V1_BYTES || rd32(packet) != QRTR_PROTO_VER_1) {
		return -1;
	}
	hdr->type = rd32(packet + 4);
	hdr->src_node = rd32(packet + 8);
	hdr->src_port = rd32(packet + 12);
	hdr->confirm_rx = rd32(packet + 16);
	hdr->size = rd32(packet + 20);
	hdr->dst_node = rd32(packet + 24);
	hdr->dst_port = rd32(packet + 28);
	if (hdr->size > len - QRTR_HDR_V1_BYTES) {
		return -1;
	}
	if (payload != NULL) {
		*payload = packet + QRTR_HDR_V1_BYTES;
	}
	return 0;
}

size_t
qrtr_encode_new_lookup(uint32_t src_node, uint32_t src_port, uint32_t service, uint32_t version,
    uint32_t instance, uint8_t *out, size_t cap)
{
	uint8_t ctrl[20];
	le32(ctrl + 0, QRTR_TYPE_NEW_LOOKUP);
	le32(ctrl + 4, service);
	le32(ctrl + 8, (version & 0xFFu) | (instance << 8));
	le32(ctrl + 12, 0);
	le32(ctrl + 16, 0);
	const struct qrtr_hdr hdr = {
		.type = QRTR_TYPE_NEW_LOOKUP, .src_node = src_node, .src_port = src_port,
		.size = sizeof(ctrl), .dst_node = QRTR_NODE_BCAST, .dst_port = QRTR_PORT_CTRL,
	};
	return qrtr_encode(&hdr, ctrl, out, cap);
}

int
qrtr_parse_server(const struct qrtr_hdr *hdr, const uint8_t *payload, struct qrtr_server *server)
{
	if (hdr == NULL || payload == NULL || server == NULL ||
	    (hdr->type != QRTR_TYPE_NEW_SERVER && hdr->type != QRTR_TYPE_DEL_SERVER) || hdr->size < 20u ||
	    rd32(payload) != hdr->type) {
		return -1;
	}
	const uint32_t instance = rd32(payload + 8);
	server->service = rd32(payload + 4);
	server->version = instance & 0xFFu;
	server->instance = instance >> 8;
	server->node = rd32(payload + 12);
	server->port = rd32(payload + 16);
	return 0;
}

static void
qmi_put(struct qmi_writer *w, const void *data, size_t len)
{
	if (w->len + len > w->cap) {
		w->overflow = true;
	} else if (len != 0) {
		memcpy(w->buf + w->len, data, len);
	}
	w->len += len;
}

void
qmi_writer_init(struct qmi_writer *w, uint8_t *buf, size_t cap, uint8_t type, uint16_t txn_id, uint16_t msg_id)
{
	w->buf = buf;
	w->cap = cap;
	w->len = 0;
	w->overflow = false;
	const uint8_t hdr[QMI_HDR_BYTES] = {
		type, (uint8_t)txn_id, (uint8_t)(txn_id >> 8), (uint8_t)msg_id, (uint8_t)(msg_id >> 8), 0, 0,
	};
	qmi_put(w, hdr, sizeof(hdr));
}

void
qmi_put_tlv(struct qmi_writer *w, uint8_t type, const void *value, uint16_t len)
{
	const uint8_t tl[3] = { type, (uint8_t)len, (uint8_t)(len >> 8) };
	qmi_put(w, tl, sizeof(tl));
	qmi_put(w, value, len);
}

void
qmi_put_u8(struct qmi_writer *w, uint8_t type, uint8_t value)
{
	qmi_put_tlv(w, type, &value, 1);
}

void
qmi_put_u32(struct qmi_writer *w, uint8_t type, uint32_t value)
{
	uint8_t bytes[4];
	le32(bytes, value);
	qmi_put_tlv(w, type, bytes, sizeof(bytes));
}

size_t
qmi_finish(struct qmi_writer *w)
{
	const size_t payload = w->len - QMI_HDR_BYTES;
	if (w->overflow || payload > 0xFFFFu) {
		return 0;
	}
	w->buf[5] = (uint8_t)payload;
	w->buf[6] = (uint8_t)(payload >> 8);
	return w->len;
}

int
qmi_decode_hdr(const uint8_t *msg, size_t len, struct qmi_hdr *hdr)
{
	if (msg == NULL || hdr == NULL || len < QMI_HDR_BYTES) {
		return -1;
	}
	hdr->type = msg[0];
	hdr->txn_id = rd16(msg + 1);
	hdr->msg_id = rd16(msg + 3);
	hdr->msg_len = rd16(msg + 5);
	return (size_t)hdr->msg_len + QMI_HDR_BYTES <= len ? 0 : -1;
}

int
qmi_next_tlv(const uint8_t *msg, size_t len, size_t *cursor, struct qmi_tlv *tlv)
{
	struct qmi_hdr hdr;
	if (cursor == NULL || tlv == NULL || qmi_decode_hdr(msg, len, &hdr) != 0) {
		return -1;
	}
	const size_t end = QMI_HDR_BYTES + hdr.msg_len;
	size_t at = QMI_HDR_BYTES + *cursor;
	if (at == end) {
		return 0;
	}
	if (at + 3u > end) {
		return -1;
	}
	tlv->type = msg[at];
	tlv->len = rd16(msg + at + 1);
	if (at + 3u + tlv->len > end) {
		return -1;
	}
	tlv->value = msg + at + 3;
	*cursor += 3u + tlv->len;
	return 1;
}

int
qmi_find_tlv(const uint8_t *msg, size_t len, uint8_t type, struct qmi_tlv *tlv)
{
	size_t cursor = 0;
	int rc;
	while ((rc = qmi_next_tlv(msg, len, &cursor, tlv)) == 1) {
		if (tlv->type == type) {
			return 1;
		}
	}
	return rc;
}

int
qmi_result(const uint8_t *msg, size_t len, uint16_t *result, uint16_t *error)
{
	struct qmi_tlv tlv;
	if (qmi_find_tlv(msg, len, QMI_TLV_RESULT, &tlv) != 1 || tlv.len != 4) {
		return -1;
	}
	*result = rd16(tlv.value);
	*error = rd16(tlv.value + 2);
	return 0;
}

size_t
wlfw_ind_register_request(uint16_t txn_id, bool xo_cal, uint8_t *out, size_t cap)
{
	/* TLV types follow the field order of wlfw_ind_register_req_msg_v01. */
	struct qmi_writer w;
	qmi_writer_init(&w, out, cap, QMI_REQUEST, txn_id, WLFW_IND_REGISTER);
	qmi_put_u8(&w, 0x10, 1);                           /* fw_ready_enable */
	qmi_put_u8(&w, 0x13, 1);                           /* msa_ready_enable */
	qmi_put_u32(&w, 0x15, WLFW_HOST_CLIENT_ID);        /* client_id */
	if (xo_cal) {
		qmi_put_u8(&w, 0x1A, 1);                       /* xo_cal_enable */
	}
	return qmi_finish(&w);
}

int
wlfw_ind_register_response(const uint8_t *msg, size_t len, uint16_t *result, bool *fw_ready)
{
	struct qmi_hdr hdr;
	uint16_t error = 0;
	if (qmi_decode_hdr(msg, len, &hdr) != 0 || hdr.type != QMI_RESPONSE || hdr.msg_id != WLFW_IND_REGISTER ||
	    qmi_result(msg, len, result, &error) != 0) {
		return -1;
	}
	*fw_ready = false;
	struct qmi_tlv tlv;
	if (qmi_find_tlv(msg, len, 0x10, &tlv) == 1 && tlv.len == 8) {
		*fw_ready = (rd32(tlv.value) & (uint32_t)WLFW_FW_READY_STATUS_BIT) != 0;
	}
	return 0;
}
