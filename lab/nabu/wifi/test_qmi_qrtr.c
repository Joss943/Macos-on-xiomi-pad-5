/* Byte-exact tests of the QRTR/QMI wire formats and the first WLFW message. */
#include <stdio.h>
#include <string.h>

#include "qmi_qrtr.h"

static int failures;
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #c); failures++; } } while (0)

int
main(void)
{
	/* WLFW IND_REGISTER request, txn 1: fw_ready, msa_ready, client id "LENK". */
	static const uint8_t expected[] = {
		0x00, 0x01, 0x00, 0x20, 0x00, 0x0F, 0x00,
		0x10, 0x01, 0x00, 0x01,
		0x13, 0x01, 0x00, 0x01,
		0x15, 0x04, 0x00, 0x4C, 0x45, 0x4E, 0x4B,
	};
	uint8_t msg[64];
	size_t n = wlfw_ind_register_request(1, false, msg, sizeof(msg));
	CHECK(n == sizeof(expected) && memcmp(msg, expected, n) == 0);
	CHECK(wlfw_ind_register_request(1, true, msg, sizeof(msg)) == sizeof(expected) + 4);
	CHECK(msg[5] == 0x13 && msg[22] == 0x1A);
	CHECK(wlfw_ind_register_request(1, false, msg, 10) == 0);

	/* Response: result success, fw_status with FW_READY set. */
	static const uint8_t response[] = {
		0x02, 0x01, 0x00, 0x20, 0x00, 0x12, 0x00,
		0x02, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00,
		0x10, 0x08, 0x00, 0x01, 0, 0, 0, 0, 0, 0, 0,
	};
	uint16_t result = 0xFFFF;
	bool ready = false;
	CHECK(wlfw_ind_register_response(response, sizeof(response), &result, &ready) == 0);
	CHECK(result == 0 && ready);
	CHECK(wlfw_ind_register_response(response, sizeof(response) - 1, &result, &ready) == -1);

	/* TLV iteration stops cleanly and rejects a TLV running past the payload. */
	size_t cursor = 0;
	struct qmi_tlv tlv;
	int count = 0;
	while (qmi_next_tlv(expected, sizeof(expected), &cursor, &tlv) == 1) {
		count++;
	}
	CHECK(count == 3);
	uint8_t bad[sizeof(expected)];
	memcpy(bad, expected, sizeof(bad));
	bad[16] = 0x09;                     /* client_id TLV claims 9 bytes */
	cursor = 0;
	int rc = 0;
	while ((rc = qmi_next_tlv(bad, sizeof(bad), &cursor, &tlv)) == 1) {
	}
	CHECK(rc == -1);

	/* QRTR: lookup of WLFW, then the NEW_SERVER the name service would answer. */
	uint8_t pkt[64];
	n = qrtr_encode_new_lookup(1, 0x4000, WLFW_SERVICE_ID, WLFW_SERVICE_VERSION, 0, pkt, sizeof(pkt));
	CHECK(n == 52);
	struct qrtr_hdr hdr;
	const uint8_t *payload = NULL;
	CHECK(qrtr_decode(pkt, n, &hdr, &payload) == 0);
	CHECK(hdr.type == QRTR_TYPE_NEW_LOOKUP && hdr.dst_node == QRTR_NODE_BCAST && hdr.dst_port == QRTR_PORT_CTRL);
	CHECK(hdr.size == 20 && payload[4] == 0x45 && payload[8] == 0x01);
	uint8_t ctrl[20] = { 4, 0, 0, 0, 0x45, 0, 0, 0, 0x01, 0, 0, 0, 0, 0, 0, 0, 0x0B, 0, 0, 0 };
	ctrl[12] = 3;                        /* modem node 3, port 11 */
	const struct qrtr_hdr srv = { .type = QRTR_TYPE_NEW_SERVER, .src_node = 3, .src_port = QRTR_PORT_CTRL,
		.size = 20, .dst_node = 1, .dst_port = QRTR_PORT_CTRL };
	n = qrtr_encode(&srv, ctrl, pkt, sizeof(pkt));
	CHECK(n == 52);
	struct qrtr_server server;
	CHECK(qrtr_decode(pkt, n, &hdr, &payload) == 0 && qrtr_parse_server(&hdr, payload, &server) == 0);
	CHECK(server.service == 0x45 && server.version == 1 && server.instance == 0 && server.node == 3 && server.port == 11);

	/* Payload padding to 4 bytes, zero-filled; truncated packets refused. */
	const struct qrtr_hdr data = { .type = QRTR_TYPE_DATA, .size = 22, .dst_node = 3, .dst_port = 11 };
	memset(pkt, 0xAA, sizeof(pkt));
	n = qrtr_encode(&data, expected, pkt, sizeof(pkt));
	CHECK(n == 32 + 24 && pkt[32 + 22] == 0 && pkt[32 + 23] == 0);
	CHECK(qrtr_decode(pkt, 40, &hdr, &payload) == -1);
	pkt[0] = 2;
	CHECK(qrtr_decode(pkt, n, &hdr, &payload) == -1);

	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	printf("qmi/qrtr: all checks passed\n");
	return 0;
}
