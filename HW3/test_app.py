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
