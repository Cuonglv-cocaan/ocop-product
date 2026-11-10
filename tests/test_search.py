import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd

from streamlit.testing.v1 import AppTest

from src import search


class SearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = pd.DataFrame([
            dict(source="TIKI", product_id="001", product_name="Tea", price="100",
                 ocop_stars="4", province_name="Hanoi", category_name="Drinks"),
            dict(source="OTHER", product_id="001", product_name="Other tea", price="200",
                 ocop_stars="3", province_name="Hue", category_name="Drinks"),
        ])

    async def test_blank_question_skips_database(self):
        with patch.object(search, "read_products") as read:
            answer, products, contexts = await search.search_products_async("  ")
        self.assertTrue(answer)
        self.assertEqual((products, contexts), ([], []))
        read.assert_not_called()

    async def test_invalid_parameters(self):
        for kwargs in [dict(top_k=0), dict(top_k=21), dict(candidate_k=1),
                       dict(top_k=True), dict(top_k=2.5), dict(candidate_k=5.5),
                       dict(min_stars=2), dict(max_price=-1), dict(max_price=float("nan"))]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                await search.search_products_async("tea", **kwargs)

    async def test_empty_catalog(self):
        with patch.object(search, "read_products", return_value=pd.DataFrame()), \
                patch.object(search, "get_vector_store", new_callable=AsyncMock) as store:
            _, products, contexts = await search.search_products_async("tea")
        self.assertEqual((products, contexts), ([], []))
        store.assert_not_awaited()

    async def test_filters_exclude_all(self):
        with patch.object(search, "read_products", return_value=self.rows), \
                patch.object(search, "get_vector_store", new_callable=AsyncMock) as store:
            answer, products, _ = await search.search_products_async("tea", max_price=50)
        self.assertEqual(products, [])
        self.assertIn("Không có gợi ý phù hợp", answer)
        self.assertIn("ngân sách", answer)
        self.assertIn("Drinks", answer)
        store.assert_not_awaited()

    async def test_ranking_deduplication_current_data_and_source_keys(self):
        docs = [SimpleNamespace(metadata=m, page_content="Old price: 999") for m in [
            dict(source="TIKI", product_id="missing"),
            dict(source="tiki", product_id="001"),
            dict(source="TIKI", product_id="001"),
            dict(source="OTHER", product_id="001"),
        ]]
        store = SimpleNamespace(asimilarity_search=AsyncMock(return_value=docs))
        chain = SimpleNamespace(ainvoke=AsyncMock(return_value=json.dumps({"answer": "Answer", "recommendations": [dict(source="TIKI", product_id="001"), dict(source="OTHER", product_id="001")]})))
        with patch.object(search, "read_products", return_value=self.rows), \
                patch.object(search, "_retrieve_documents", new=store.asimilarity_search), \
                patch.object(search, "_get_answer_chain", return_value=chain):
            answer, products, contexts = await search.search_products_async("tea", top_k=2)
        self.assertEqual(answer, "Answer")
        self.assertEqual([p["source"] for p in products], ["TIKI", "OTHER"])
        self.assertEqual(json.loads(contexts[0])["price"], 100)
        chain.ainvoke.assert_awaited_once()

    async def test_combined_filters_and_top_k(self):
        store = SimpleNamespace(asimilarity_search=AsyncMock(return_value=[
            SimpleNamespace(metadata=dict(source=s, product_id="001"))
            for s in ["OTHER", "TIKI"]]))
        chain = SimpleNamespace(ainvoke=AsyncMock(return_value=json.dumps({"answer": "Answer", "recommendations": [dict(source="TIKI", product_id="001")]})))
        with patch.object(search, "read_products", return_value=self.rows), \
                patch.object(search, "_retrieve_documents", new=store.asimilarity_search), \
                patch.object(search, "_get_answer_chain", return_value=chain):
            _, products, _ = await search.search_products_async(
                "tea", category_filter="drinks", province_filter="HANOI",
                min_stars=4, max_price=100, source_filter="tiki", top_k=1)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["source"], "TIKI")

    async def test_no_matching_vectors_skips_llm(self):
        store = SimpleNamespace(asimilarity_search=AsyncMock(return_value=[]))
        with patch.object(search, "read_products", return_value=self.rows), \
                patch.object(search, "_retrieve_documents", new=store.asimilarity_search), \
                patch.object(search, "_get_answer_chain") as chain:
            answer, products, _ = await search.search_products_async("tea")
        self.assertEqual(products, [])
        self.assertIn("Không có gợi ý phù hợp", answer)
        self.assertIn("hướng tìm kiếm tương tự", answer)
        self.assertNotIn("embeddings", answer)
        chain.assert_not_called()

    def test_number_and_serialization(self):
        for value in [None, True, "invalid", "120.000 d", float("inf"), float("nan")]:
            self.assertIsNone(search._number(value))
        product = search._serialize_product(dict(product_id="001", price=-1))
        self.assertEqual(product["product_id"], "001")
        self.assertIsNone(product["price"])
        self.assertTrue(product["province_name"])

    def test_budget_formats_and_followup(self):
        for text, amount in [("dưới 300000 đồng", 300000), ("dưới 300.000đ", 300000),
                             ("tối đa 300k", 300000), ("ngân sách 1,5 triệu", 1500000),
                             ("dưới 1.500 nghìn", 1500000), ("dưới 1.000.000k", 1000000000)]:
            with self.subTest(text=text):
                self.assertEqual(search._budget(text), amount)
        history = [dict(role="user", content="dưới 300k")]
        self.assertEqual(search._budget("Có trà không?", history), 300000)
        self.assertEqual(search._budget("dưới 100k", history), 100000)
        self.assertIsNone(search._budget("không giới hạn ngân sách", history))

    async def test_budget_excludes_expensive_cards_before_ranking(self):
        docs = [SimpleNamespace(metadata=dict(source="TIKI", product_id="001"))]
        chain = SimpleNamespace(ainvoke=AsyncMock(return_value=json.dumps({
            "answer": "Tea", "recommendations": [dict(source="TIKI", product_id="001")]})))
        with patch.object(search, "read_products", return_value=self.rows), \
                patch.object(search, "_retrieve_documents", new=AsyncMock(return_value=docs)) as retrieve, \
                patch.object(search, "_get_answer_chain", return_value=chain):
            _, products, _ = await search.search_products_async("dưới 150 đồng")
        self.assertEqual([p["price"] for p in products], [100])
        self.assertEqual(list(retrieve.call_args.args[1]), [("TIKI", "001")])

    async def test_ai_rejection_and_invalid_ids_have_no_cards(self):
        docs = [SimpleNamespace(metadata=dict(source="TIKI", product_id="001"))]
        for response in [dict(answer="Not suitable", recommendations=[]),
                         dict(answer="Unknown", recommendations=[dict(source="TIKI", product_id="fake")]),
                         "invalid"]:
            chain = SimpleNamespace(ainvoke=AsyncMock(return_value=json.dumps(response)))
            with patch.object(search, "read_products", return_value=self.rows), \
                    patch.object(search, "_retrieve_documents", new=AsyncMock(return_value=docs)), \
                    patch.object(search, "_get_answer_chain", return_value=chain):
                _, products, _ = await search.search_products_async("tea")
            self.assertEqual(products, [])


class DiscoveryTests(unittest.TestCase):
    def app(self):
        return AppTest.from_string(
            "from src.search import product_discovery\nproduct_discovery()"
        ).run()

    def test_conversation_followup_rerun_and_clear(self):
        product = dict(product_name="Tea", price=None, ocop_stars=None,
                       province_name="Hue", source="TIKI", source_url="https://example.com/tea")
        search = AsyncMock(return_value=("Try this tea", [product], []))
        with patch("src.search.search_products_async", search):
            app = self.app()
            self.assertFalse(app.exception)
            app.chat_input[0].set_value("Find tea").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state["discovery_messages"]), 2)
            app.run()
            self.assertEqual(search.await_count, 1)
            app.chat_input[0].set_value("Something cheaper").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(search.call_args.kwargs["history"]), 2)
            self.assertEqual(len(app.session_state["discovery_messages"]), 4)
            app.button(key="clear_discovery").click().run()
            self.assertEqual(app.session_state["discovery_messages"], [])

    def test_api_error_keeps_conversation(self):
        with patch("src.search.search_products_async", new=AsyncMock(side_effect=RuntimeError("Unavailable"))):
            app = self.app()
            app.chat_input[0].set_value("Find tea").run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertEqual(app.session_state["discovery_messages"][0]["content"], "Find tea")



if __name__ == "__main__":
    unittest.main()
