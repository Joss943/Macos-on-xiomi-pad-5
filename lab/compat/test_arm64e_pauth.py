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

