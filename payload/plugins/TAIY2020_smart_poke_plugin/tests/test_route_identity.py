import unittest

from core.common import extract_message_route_components


class RouteIdentityTests(unittest.TestCase):
    def test_top_level_route_identity_takes_priority(self):
        message = {"account_id": " top-account ", "scope": " top-scope "}
        additional = {
            "platform_io_account_id": "fallback-account",
            "platform_io_scope": "fallback-scope",
        }

        self.assertEqual(
            extract_message_route_components(message, additional),
            ("top-account", "top-scope"),
        )

    def test_additional_config_is_compatibility_fallback(self):
        message = {"account_id": "", "scope": None}
        additional = {"self_id": "legacy-account", "connection_id": "legacy-scope"}

        self.assertEqual(
            extract_message_route_components(message, additional),
            ("legacy-account", "legacy-scope"),
        )

    def test_missing_route_identity_returns_empty_strings(self):
        self.assertEqual(extract_message_route_components({}, {}), ("", ""))
        self.assertEqual(extract_message_route_components(None, None), ("", ""))


if __name__ == "__main__":
    unittest.main()
