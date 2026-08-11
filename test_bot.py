import unittest
from unittest.mock import patch

import bot


class BotTests(unittest.TestCase):
    def test_extract_item_id_from_permalink(self):
        url = "https://produto.mercadolivre.com.br/MLB-1234567890-produto-_JM"
        self.assertEqual(bot.extract_item_id(url), "MLB1234567890")

    def test_extract_item_id_from_query(self):
        url = "https://www.mercadolivre.com.br/produto?pdp_filters=item_id%3AMLB987654321"
        self.assertEqual(bot.extract_item_id(url), "MLB987654321")

    def test_calculate_discount(self):
        self.assertEqual(bot.calculate_discount(200, 120), 40)
        self.assertEqual(bot.calculate_discount(None, 120), 0)
        self.assertEqual(bot.calculate_discount(100, 100), 0)

    def test_brl(self):
        self.assertEqual(bot.brl(1299.9), "R$ 1.299,90")

    def test_caption_escapes_title(self):
        item = {
            "title": "TV <Nova> & Boa",
            "price": 1200,
            "original_price": 2000,
        }
        caption = bot.offer_caption(item, 40)
        self.assertIn("TV &lt;Nova&gt; &amp; Boa", caption)
        self.assertIn("40% OFF", caption)

    @patch("bot.utc_now")
    def test_does_not_repeat_unchanged_offer(self, mocked_now):
        from datetime import datetime, timezone

        mocked_now.return_value = datetime(2026, 8, 11, tzinfo=timezone.utc)
        previous = {
            "price": 100,
            "discount": 40,
            "posted_at": "2026-08-10T00:00:00+00:00",
        }
        self.assertFalse(bot.should_repost(previous, 100, 40))
        self.assertTrue(bot.should_repost(previous, 89, 40))
        self.assertTrue(bot.should_repost(previous, 100, 45))


if __name__ == "__main__":
    unittest.main()
