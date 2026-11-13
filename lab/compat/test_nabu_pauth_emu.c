#include "nabu_pauth_emu.h"

#include <assert.h>
#include <stddef.h>

struct memory {
	uint64_t address;
	uint64_t value;
	int fail;
};

static int
read64(void *context, uint64_t address, uint64_t *value)
{
	struct memory *memory = context;
	if (memory->fail || address != memory->address) {
		return -1;
	}
	*value = memory->value;
	return 0;
}

int
main(void)
{
	struct nabu_pauth_state state = { 0 };
	struct memory memory = { 0 };
	uint64_t fault = 0;

	/* PACIA x0, x1 becomes a no-op and leaves the pointer unchanged. */
	state.x[0] = 0x12340000u;
	state.pc = 0x1000u;
	assert(nabu_pauth_execute(0xDAC10020u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[0] == 0x12340000u && state.pc == 0x1004u);
	state.x[7] = 0x98760000u;
	assert(nabu_pauth_execute(0xDAC11107u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[7] == 0x98760000u && state.pc == 0x1008u);
	state.x[5] = 0xABC000u;
	assert(nabu_pauth_execute(0xDAC123E5u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[5] == 0xABC000u && state.pc == 0x100Cu);
	state.x[9] = 0xDEF000u;
	assert(nabu_pauth_execute(0xDAC143E9u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[9] == 0xDEF000u && state.pc == 0x1010u);

	/* PACGA has the same deterministic zero result as the offline lowering. */
	state.x[1] = 0xDEADBEEFu;
	state.pc = 0x1800u;
	assert(nabu_pauth_execute(0x9AC33041u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[1] == 0 && state.pc == 0x1804u);

	/* Authenticated branch and return use their plain register targets. */
	state.x[1] = 0x7000u;
	state.pc = 0x1900u;
	assert(nabu_pauth_execute(0xD71F0820u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.pc == 0x7000u);
	state.x[30] = 0x7100u;
	assert(nabu_pauth_execute(0xD65F0FFFu, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.pc == 0x7100u);

	/* BLRAAZ x4 branches and captures the return address before changing PC. */
	state.x[4] = 0x8000u;
	state.pc = 0x2000u;
	assert(nabu_pauth_execute(0xD63F089Fu, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[30] == 0x2004u && state.pc == 0x8000u);

	/* LDRAA x2, [x3, #-0x40]! reads first, then applies base writeback. */
	state.x[3] = 0x5000u;
	state.pc = 0x3000u;
	memory.address = 0x4FC0u;
	memory.value = 0xABCDEF00u;
	assert(nabu_pauth_execute(0xF87F8C62u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[2] == 0xABCDEF00u && state.x[3] == 0x4FC0u && state.pc == 0x3004u);

	/* SP can be the base; XZR discards the loaded word but writeback remains. */
	state.sp = 0x9000u;
	state.pc = 0x4000u;
	memory.address = 0x9010u;
	memory.value = 7u;
	assert(nabu_pauth_execute(0xF8202FFFu, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.sp == 0x9010u && state.pc == 0x4004u);

	/* The chosen constrained-unpredictable alias behavior is writeback then load. */
	state.x[3] = 0x6000u;
	state.pc = 0x4800u;
	memory.address = 0x6008u;
	memory.value = 0x76543210u;
	assert(nabu_pauth_execute(0xF8201C63u, &state, read64, &memory, &fault) == NABU_PAUTH_DONE);
	assert(state.x[3] == 0x76543210u && state.pc == 0x4804u);

	/* A failed load reports its address and leaves every register untouched. */
	state.x[5] = 0x10000u;
	state.pc = 0x5000u;
	memory.fail = 1;
	assert(nabu_pauth_execute(0xF82004A6u, &state, read64, &memory, &fault) == NABU_PAUTH_FAULT);
	assert(fault == 0x10000u && state.x[5] == 0x10000u && state.pc == 0x5000u);

	/* An unallocated zero-modifier form must remain an ordinary undefined instruction. */
	assert(nabu_pauth_execute(0xDAC13047u, &state, read64, &memory, &fault) == NABU_PAUTH_NOT_HANDLED);
	assert(nabu_pauth_execute(0xDAC14029u, &state, read64, &memory, &fault) == NABU_PAUTH_NOT_HANDLED);

	/* Exhaustively check the signed 10-bit LDRA immediate decoder. */
	for (uint32_t immediate = 0; immediate < 1024u; immediate++) {
		const uint32_t word = 0xF8200400u | (((immediate >> 9) & 1u) << 22) |
		    ((immediate & 0x1FFu) << 12) | (1u << 11) | (3u << 5) | 2u;
		struct nabu_pauth_insn decoded;
		const int32_t signed_units = immediate & 0x200u ? (int32_t)immediate - 1024 : (int32_t)immediate;
		assert(nabu_pauth_decode(word, &decoded));
		assert(decoded.op == NABU_PAUTH_LOAD && decoded.offset == signed_units * 8 && decoded.writeback);
	}
	return 0;
}

