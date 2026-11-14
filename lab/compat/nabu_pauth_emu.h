/*
 * Minimal ARM64 no-PAC execution model for the non-HINT PAuth instructions
 * needed by the nabu/macOS 27.3 compatibility experiment.
 *
 * This is an unauthenticated compatibility model, not cryptographic PAC.
 * Pointers entering it must already be plain virtual addresses. In XNU, the
 * authenticated chained-fixup patch supplies those addresses before code runs.
 */
#ifndef NABU_PAUTH_EMU_H
#define NABU_PAUTH_EMU_H

#include <stdbool.h>
#include <stdint.h>

enum nabu_pauth_op {
	NABU_PAUTH_UNHANDLED = 0,
	NABU_PAUTH_NOP,
	NABU_PAUTH_PACGA,
	NABU_PAUTH_BRANCH,
	NABU_PAUTH_BRANCH_LINK,
	NABU_PAUTH_RETURN,
	NABU_PAUTH_LOAD,
};

struct nabu_pauth_insn {
	enum nabu_pauth_op op;
	uint8_t rd;
	uint8_t rn;
	uint8_t rm;
	bool writeback;
	int32_t offset;
};

struct nabu_pauth_state {
	uint64_t x[31];
	uint64_t sp;
	uint64_t pc;
	uint32_t written; /* x0..x30 use bits 0..30; SP uses bit 31 */
};

enum nabu_pauth_result {
	NABU_PAUTH_DONE = 0,
	NABU_PAUTH_FAULT,
	NABU_PAUTH_NOT_HANDLED,
};

typedef int (*nabu_pauth_read64_fn)(void *context, uint64_t address, uint64_t *value);

static inline bool
nabu_pauth_decode(uint32_t word, struct nabu_pauth_insn *out)
{
	const uint8_t rd = (uint8_t)(word & 31u);
	const uint8_t rn = (uint8_t)((word >> 5) & 31u);
	const uint8_t rm = (uint8_t)((word >> 16) & 31u);
	*out = (struct nabu_pauth_insn){ .op = NABU_PAUTH_UNHANDLED };

	/* PACIA/B/DA/DB, AUTIA/B/DA/DB, zero-modifier variants, XPACI/D. */
	if ((word & 0xFFFF0000u) == 0xDAC10000u) {
		const unsigned opcode = (word >> 10) & 63u;
		if (opcode >= 18u || (opcode >= 8u && rn != 31u)) {
			return false;
		}
		*out = (struct nabu_pauth_insn){ .op = NABU_PAUTH_NOP, .rd = rd, .rn = rn };
		return true;
	}

	/* PACGA: the no-PAC ABI uses one deterministic zero result everywhere. */
	if ((word & 0xFFE0FC00u) == 0x9AC03000u) {
		*out = (struct nabu_pauth_insn){ .op = NABU_PAUTH_PACGA, .rd = rd, .rn = rn, .rm = rm };
		return true;
	}

	/* BRAA/BRAB/BRAAZ/BRABZ and their BLR forms. */
	static const struct {
		uint32_t value;
		uint32_t mask;
		bool link;
	} branches[] = {
		{ 0xD61F081Fu, 0xFFFFFC1Fu, false }, { 0xD61F0C1Fu, 0xFFFFFC1Fu, false },
		{ 0xD63F081Fu, 0xFFFFFC1Fu, true  }, { 0xD63F0C1Fu, 0xFFFFFC1Fu, true  },
		{ 0xD71F0800u, 0xFFFFFC00u, false }, { 0xD71F0C00u, 0xFFFFFC00u, false },
		{ 0xD73F0800u, 0xFFFFFC00u, true  }, { 0xD73F0C00u, 0xFFFFFC00u, true  },
	};
	for (unsigned i = 0; i < sizeof(branches) / sizeof(branches[0]); i++) {
		if ((word & branches[i].mask) == branches[i].value) {
			if (rn == 31u) {
				return false;
			}
			*out = (struct nabu_pauth_insn){
				.op = branches[i].link ? NABU_PAUTH_BRANCH_LINK : NABU_PAUTH_BRANCH,
				.rn = rn,
			};
			return true;
		}
	}

	if (word == 0xD65F0BFFu || word == 0xD65F0FFFu) {
		*out = (struct nabu_pauth_insn){ .op = NABU_PAUTH_RETURN, .rn = 30u };
		return true;
	}

	/* LDRAA/LDRAB, unsigned 64-bit load plus optional pre-index writeback. */
	if ((word & 0xFF200400u) == 0xF8200400u) {
		const uint32_t immediate = (((word >> 22) & 1u) << 9) | ((word >> 12) & 0x1FFu);
		const int32_t signed_immediate = (int32_t)(immediate << 22) >> 22;
		*out = (struct nabu_pauth_insn){
			.op = NABU_PAUTH_LOAD,
			.rd = rd,
			.rn = rn,
			.writeback = ((word >> 11) & 1u) != 0,
			.offset = signed_immediate * 8,
		};
		return true;
	}

	return false;
}

static inline uint64_t
nabu_pauth_read_register(const struct nabu_pauth_state *state, unsigned reg, bool stack_pointer)
{
	if (reg == 31u) {
		return stack_pointer ? state->sp : 0;
	}
	return state->x[reg];
}

static inline void
nabu_pauth_write_register(struct nabu_pauth_state *state, unsigned reg, uint64_t value)
{
	if (reg != 31u) {
		state->x[reg] = value;
		state->written |= 1u << reg;
	}
}

/* Execute one trapped instruction; memory reads are supplied by the caller. */
static inline enum nabu_pauth_result
nabu_pauth_execute(uint32_t word, struct nabu_pauth_state *state,
	    nabu_pauth_read64_fn read64, void *context, uint64_t *fault_address)
{
	struct nabu_pauth_insn insn;
	if (!nabu_pauth_decode(word, &insn)) {
		return NABU_PAUTH_NOT_HANDLED;
	}
	state->written = 0;
	switch (insn.op) {
	case NABU_PAUTH_NOP:
		state->pc += 4;
		break;
	case NABU_PAUTH_PACGA:
		nabu_pauth_write_register(state, insn.rd, 0);
		state->pc += 4;
		break;
	case NABU_PAUTH_BRANCH:
		state->pc = state->x[insn.rn];
		break;
	case NABU_PAUTH_BRANCH_LINK: {
		const uint64_t target = state->x[insn.rn];
		nabu_pauth_write_register(state, 30u, state->pc + 4);
		state->pc = target;
		break;
	}
	case NABU_PAUTH_RETURN:
		state->pc = state->x[30];
		break;
	case NABU_PAUTH_LOAD: {
		const uint64_t base = nabu_pauth_read_register(state, insn.rn, true);
		const uint64_t address = base + (uint64_t)(int64_t)insn.offset;
		uint64_t value = 0;
		if (read64 == 0 || read64(context, address, &value) != 0) {
			if (fault_address != 0) {
				*fault_address = address;
			}
			return NABU_PAUTH_FAULT;
		}
		/* Rt==Rn writeback is constrained-unpredictable; choose writeback then load. */
		if (insn.writeback) {
			if (insn.rn == 31u) {
				state->sp = address;
				state->written |= 1u << 31;
			} else {
				nabu_pauth_write_register(state, insn.rn, address);
			}
		}
		nabu_pauth_write_register(state, insn.rd, value);
		state->pc += 4;
		break;
	}
	default:
		return NABU_PAUTH_NOT_HANDLED;
	}
	return NABU_PAUTH_DONE;
}

#endif /* NABU_PAUTH_EMU_H */

