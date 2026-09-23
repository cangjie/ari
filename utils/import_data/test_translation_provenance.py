import unittest

import import_artworks
import import_data


def empty_buckets(kinds):
    return {kind: [] for kind in kinds}


class TranslationProvenanceTest(unittest.TestCase):
    def test_artwork_official_confidence_is_recorded_as_ai_translation(self):
        buckets = empty_buckets(import_artworks.CONTENT_KINDS)
        buckets["artwork_name"] = ["Bronze vessel"]
        translations = {
            ("artwork_name", "Bronze vessel"): ("青铜器", "Bronze vessel", "官方"),
        }

        _, _, text_rows, _ = import_artworks.build_content_rows(
            buckets, translations, pairs={},
        )

        self.assertIn((1_000_001, "zh-CN", "青铜器", "AI翻译"), text_rows)

    def test_artwork_doubt_remains_doubt(self):
        buckets = empty_buckets(import_artworks.CONTENT_KINDS)
        buckets["artwork_name"] = ["Bronze vessel"]
        translations = {
            ("artwork_name", "Bronze vessel"): ("青铜器", "Bronze vessel", "存疑"),
        }

        _, _, text_rows, _ = import_artworks.build_content_rows(
            buckets, translations, pairs={},
        )

        self.assertIn((1_000_001, "zh-CN", "青铜器", "存疑"), text_rows)

    def test_source_workbook_bilingual_pair_remains_original(self):
        buckets = empty_buckets(import_artworks.CONTENT_KINDS)
        buckets["artwork_name"] = ["Bronze vessel"]
        translations = {
            ("artwork_name", "Bronze vessel"): ("模型译名", "Bronze vessel", "官方"),
        }
        pairs = {("artwork_name", "Bronze vessel"): "源表译名"}

        _, _, text_rows, _ = import_artworks.build_content_rows(
            buckets, translations, pairs,
        )

        self.assertIn((1_000_001, "zh-CN", "源表译名", "原始"), text_rows)
        self.assertNotIn((1_000_001, "zh-CN", "模型译名", "AI翻译"), text_rows)

    def test_city_official_confidence_keeps_existing_human_review_mapping(self):
        buckets = empty_buckets(import_data.CONTENT_KINDS)
        buckets["city_name"] = ["Beijing"]
        translations = {
            ("city_name", "Beijing"): ("北京", "Beijing", "官方"),
        }

        _, _, text_rows, _ = import_data.build_content_rows(buckets, translations)

        self.assertIn((1, "zh-CN", "北京", "人工校对"), text_rows)


if __name__ == "__main__":
    unittest.main()
