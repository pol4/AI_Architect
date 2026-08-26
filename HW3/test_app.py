import importlib.util
import tempfile
import unittest
from pathlib import Path


LANGGRAPH_AVAILABLE = importlib.util.find_spec("langgraph") is not None


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "Install requirements.txt to run LangGraph tests")
class ArchitectureTests(unittest.TestCase):
    def test_specialized_agents_are_available(self):
        from travel_system.agents import BookingAgent, CancellationRefundAgent, HotelSearchAgent, ReplanningAgent, TransferSearchAgent, TransportSearchAgent
        for agent in (TransportSearchAgent, HotelSearchAgent, TransferSearchAgent, BookingAgent, CancellationRefundAgent, ReplanningAgent):
            self.assertTrue(agent.name)

    def test_rag_ingestion_and_runtime_retrieval(self):
        from travel_system.rag import PolicyRAG
        with tempfile.TemporaryDirectory() as directory:
            rag = PolicyRAG(Path(directory) / "policy.db")
            rag.ingest({"policy_id": "TEST-001", "version": "1", "title": "Лимит гостиницы", "text": "Для гостиницы действует лимит 10000 рублей.", "effective_from": "2026-01-01"})
            context = rag.retrieve({"destination": "гостиница", "budget": 10000})
            self.assertTrue(any(chunk["policy_id"] == "TEST-001" for chunk in context))

    def test_complete_text_request_does_not_require_clarification(self):
        from travel_system.graphs import TravelGraphs
        from travel_system.rag import PolicyRAG
        with tempfile.TemporaryDirectory() as directory:
            graphs = TravelGraphs(PolicyRAG(Path(directory) / "policy.db"))
            config = {"configurable": {"thread_id": "complete-case"}}
            graphs.trip_graph.invoke({"case_id": "complete-case", "request_text": "Поездка из Москвы в Санкт-Петербург с 2026-09-15 по 2026-09-17 для встречи, бюджет 60000 рублей", "user_id": "demo", "audit": []}, config)
            state = graphs.trip_graph.get_state(config).values
            self.assertEqual(state["status"], "awaiting_selection")
            self.assertEqual(state["missing_fields"], [])
            self.assertEqual(state["trip"]["destination"], "Санкт-Петербург")

    def test_trip_graph_contains_langgraph_nodes(self):
        from travel_system.graphs import TravelGraphs
        from travel_system.rag import PolicyRAG
        with tempfile.TemporaryDirectory() as directory:
            graphs = TravelGraphs(PolicyRAG(Path(directory) / "policy.db"))
            self.assertIn("parse_request", graphs.trip_graph.get_graph().nodes)
            self.assertIn("search_worker", graphs.trip_graph.get_graph().nodes)
            self.assertIn("await_selection", graphs.booking_graph.get_graph().nodes)


if __name__ == "__main__":
    unittest.main()
