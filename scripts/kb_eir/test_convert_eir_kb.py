"""Unit tests for the eir KB preprocessing helpers (TASK-BE-069).

Run: ``python3 -m unittest scripts.kb_eir.test_convert_eir_kb`` (or from scripts/kb_eir:
``python3 -m unittest test_convert_eir_kb``).
"""
import unittest

import convert_eir_kb as c


class DomainMapping(unittest.TestCase):
    def test_billing_segment_maps_to_billing(self):
        self.assertEqual("billing", c.domain_from_url("https://www.eir.ie/helpandsupport/billing/my-first-bill/"))

    def test_moving_home_maps_to_commercial(self):
        self.assertEqual("commercial", c.domain_from_url("https://www.eir.ie/helpandsupport/moving-home/"))

    def test_fibre_maps_to_support(self):
        self.assertEqual("support", c.domain_from_url("https://www.eir.ie/helpandsupport/fibre-broadband/x/"))

    def test_unknown_segment_defaults_to_support(self):
        self.assertEqual("support", c.domain_from_url("https://www.eir.ie/helpandsupport/brand-new-thing/"))


class Slug(unittest.TestCase):
    def test_slug_from_url_strips_host_and_prefix(self):
        self.assertEqual(
            "billing-my-bundle-allowances",
            c.slug_from_url("https://www.eir.ie/helpandsupport/billing/my-bundle-allowances/"))

    def test_segment_detects_device_tutorials(self):
        self.assertEqual("smartphonehelp", c.url_segment(
            "https://www.eir.ie/helpandsupport/smartphonehelp/?page=device/apple/iphone-11"))


class CleanBody(unittest.TestCase):
    RAW = "\n".join([
        "Skip to main content",
        "- [Personal](https://www.eir.ie/)",
        "- [Business](https://www.eir.ie/business)",
        "Featured",
        "[Shop](https://www.eir.ie/x)",
        "- [Home](https://www.eir.ie/)",
        "- [Support](https://www.eir.ie/helpandsupport/)",
        "- My bundle allowances",
        "# My bundle allowances",
        "[Back to Support Home](https://www.eir.ie/helpandsupport/)",
        "**Your landline plan allowances**",
        "",
        "- Unlimited local and national calls to all Irish landlines.",
        "- Covers calls less than 60 minutes long.",
        "Chat",
        "Back to the top",
        "- [Broadband](https://www.eir.ie/shop/broadband/)",
        "eir and open eir are trading names of eircom Limited.",
    ])

    def test_strips_nav_header_sibling_links_and_footer(self):
        body = c.clean_body(self.RAW)
        self.assertIn("# My bundle allowances", body)
        self.assertIn("**Your landline plan allowances**", body)
        self.assertIn("Unlimited local and national calls", body)
        # nav header + mega-nav links gone
        self.assertNotIn("Skip to main content", body)
        self.assertNotIn("[Personal]", body)
        self.assertNotIn("[Shop]", body)
        self.assertNotIn("Featured", body)
        # sibling-nav link under the H1 gone
        self.assertNotIn("Back to Support Home", body)
        # footer gone (cut at "Back to the top")
        self.assertNotIn("Back to the top", body)
        self.assertNotIn("[Broadband]", body)
        self.assertNotIn("trading names", body)

    def test_derive_title_prefers_first_heading(self):
        body = c.clean_body(self.RAW)
        self.assertEqual("My bundle allowances", c.derive_title(body, "Support | Generic"))

    def test_build_document_emits_canonical_front_matter(self):
        raw = (
            '---\nurl: "https://www.eir.ie/helpandsupport/billing/my-bundle-allowances/"\n'
            'title: "Support | My bundle allowances"\n---\n\n' + self.RAW
        )
        content, info = c.build_document(raw, min_chars=20)
        self.assertEqual("billing", info["domain"])
        self.assertIn("domain: billing", content)
        self.assertIn("language: en", content)
        self.assertIn("audience: customer", content)
        self.assertIn("source: eir-helpcentre", content)
        self.assertIn("# My bundle allowances", content)

    def test_strips_image_tiles_and_mangled_link_tails_but_keeps_inline_link_prose(self):
        raw = "\n".join([
            "### Help",
            "![](https://www.eir.ie/opencms/export/a.png)![](https://www.eir.ie/opencms/export/b.png)](https://www.eir.ie/x/)",
            "[![The eir app dashboard](https://www.eir.ie/opencms/export/tile.png)\\\\",
            "](https://apps.apple.com/ie/app/eir/id6482999932)",
            "To change your appointment, [please fill out the form](https://www.eir.ie/helpandsupport/forms/).",
        ])
        body = c.clean_body(raw)
        self.assertIn("### Help", body)
        # image rows + nav tiles + dangling link tails are gone
        self.assertNotIn("![", body)
        self.assertNotIn("opencms/export", body)
        self.assertNotIn("apps.apple.com", body)
        # a prose line that merely contains an inline link is preserved
        self.assertIn("To change your appointment", body)

    def test_nav_only_page_is_dropped(self):
        raw = (
            '---\nurl: "https://www.eir.ie/helpandsupport/billing/"\ntitle: "Billing"\n---\n\n'
            "- [Home](https://www.eir.ie/)\n- [Billing](https://www.eir.ie/helpandsupport/billing/)\n"
            "Back to the top\n"
        )
        self.assertIsNone(c.build_document(raw, min_chars=200))


if __name__ == "__main__":
    unittest.main()
