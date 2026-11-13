import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).with_name("arm64e_pauth.py")
SPEC = importlib.util.spec_from_file_location("arm64e_pauth", MODULE)
PAUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAUTH)


class PointerAuthLoweringTests(unittest.TestCase):
    def test_pointer_sign_and_auth_are_nops_without_pauth(self):
        self.assertEqual(PAUTH.lower(0xDAC10041), ("pacia", 0xD503201F))
        self.assertEqual(PAUTH.lower(0xDAC11DEE), ("autdb", 0xD503201F))

    def test_pointer_authentication_hints_are_nops_without_pauth(self):
        self.assertEqual(PAUTH.lower(0xD503233F), ("paciasp", 0xD503201F))
        self.assertEqual(PAUTH.lower(0xD503237F), ("pacibsp", 0xD503201F))
        self.assertEqual(PAUTH.lower(0xD50323BF), ("autiasp", 0xD503201F))
        self.assertEqual(PAUTH.lower(0xD50323FF), ("autibsp", 0xD503201F))
        self.assertEqual(PAUTH.lower(0xD50320FF), ("xpaclri", 0xD503201F))
        self.assertEqual(PAUTH.lower(0xD503211F), ("pacia1716", 0xD503201F))

    def test_large_ldraa_offsets_expand_to_add_and_load(self):
        sequence = PAUTH.lower_sequence(0xF8B3DD68)
        self.assertEqual(sequence.mnemonic, "ldrab")
        self.assertEqual(sequence.replacements, (0x91000000 | (2536 << 10) | (11 << 5) | 11, 0xF9400000 | (11 << 5) | 8))

    def test_negative_ldraa_offset_uses_destination_as_temporary(self):
        sequence = PAUTH.lower_sequence(0xF8F1F7FA)
        self.assertEqual(sequence.mnemonic, "ldrab")
        self.assertEqual(sequence.replacements, (0xD1000000 | (1800 << 10) | (31 << 5) | 26, 0xF9400000 | (26 << 5) | 26))

    def test_ldraa_expansion_rejects_unsafe_register_alias(self):
        with self.assertRaises(ValueError):
            PAUTH.lower_sequence(0xF87AF7FF)

    def test_ldraa_can_use_a_caller_proven_dead_scratch(self):
        sequence = PAUTH.lower_sequence(0xF87AF7FF, scratch_register=16)
        self.assertEqual(sequence.replacements, (0xD1000000 | (648 << 10) | (31 << 5) | 16, 0xF9400000 | (16 << 5) | 31))

    def test_zero_modifier_forms_require_register_31(self):
        self.assertEqual(PAUTH.lower(0xDAC123F0), ("paciza", 0xD503201F))
        with self.assertRaises(ValueError):
            PAUTH.lower(0xDAC12041)

    def test_authenticated_control_flow_keeps_the_target(self):
        self.assertEqual(PAUTH.lower(0xD61F089F), ("braaz", 0xD61F0080))
        self.assertEqual(PAUTH.lower(0xD65F0BFF), ("retaa", 0xD65F03C0))
        with self.assertRaises(ValueError):
            PAUTH.lower(0xD69F0BFF)

    def test_pacga_has_a_defined_zero_result(self):
        self.assertEqual(PAUTH.lower(0x9AC33041), ("pacga", 0xD2800001))

    def test_other_instructions_are_left_alone(self):
        self.assertIsNone(PAUTH.lower(0xD503201F))


if __name__ == "__main__":
    unittest.main()

