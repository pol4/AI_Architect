from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from .agents import BookingAgent, CancellationRefundAgent, ReplanningAgent, build_tasks, search_task
from .llm import LLMGateway
from .rag import PolicyRAG
from .state import TripState


class TravelGraphs:
    def __init__(self, rag: PolicyRAG):
        self.rag = rag
        self.llm = LLMGateway(rag.db_path)
        self.booking_agent = BookingAgent()
        self.cancellation_agent = CancellationRefundAgent()
        self.replanning_agent = ReplanningAgent()
        self.checkpointer = MemorySaver()
        self.trip_graph = self._build_trip_graph()
        self.booking_graph = self._build_booking_graph()
        self.cancellation_graph = self._build_cancellation_graph()
        self.replanning_graph = self._build_replanning_graph()

    def _audit(self, event: str) -> list[dict[str, str]]:
        return [{"event": event, "at": "system"}]

    def _parse_request(self, state: TripState) -> dict[str, Any]:
        text = state.get("request_text", "")
        parsed = self.llm.invoke_json("parser", "Извлеки параметры командировки и верни JSON без выдуманных значений: departure_city, destination, departure_date, return_date, purpose, budget, currency, preferences.", text)
        return {"trip": parsed or {"purpose": text}, "status": "parsed", "audit": self._audit("REQUEST_PARSED")}

    def _retrieve_policy_context(self, state: TripState) -> dict[str, Any]:
        context = self.rag.retrieve(state.get("trip", {}))
        return {"policy_context": context, "status": "policy_context_retrieved", "audit": self._audit("POLICY_CONTEXT_RETRIEVED")}

    def _check_completeness(self, state: TripState) -> dict[str, Any]:
        trip = state.get("trip", {})
        required = ["departure_city", "destination", "departure_date", "return_date", "purpose", "budget"]
        if any(chunk["policy_id"] == "TRAVEL-003" for chunk in state.get("policy_context", [])):
            required.append("passport_data_or_visa_status")
        missing = [field for field in required if not trip.get(field)]
        return {"missing_fields": missing, "status": "clarification_required" if missing else "policy_check", "next_action": "answer_questions" if missing else "plan"}

    def _ask_clarification(self, state: TripState) -> dict[str, Any]:
        answers = interrupt({"type": "clarification", "case_id": state["case_id"], "missing_fields": state.get("missing_fields", [])})
        trip = dict(state.get("trip", {}))
        trip.update(answers or {})
        return {"trip": trip, "status": "answers_received", "next_action": "retrieve_policy_context", "audit": self._audit("CLARIFICATION_RECEIVED")}

    def _evaluate_policy(self, state: TripState) -> dict[str, Any]:
        decisions = self.rag.evaluate(state.get("trip", {}), state.get("policy_context", []))
        status = "approval_pending" if any(item["decision"] == "conditional" for item in decisions) else "planning"
        return {"policy_decisions": decisions, "status": status, "next_action": "approval" if status == "approval_pending" else "plan", "audit": self._audit("POLICY_EVALUATED")}

    def _approval_interrupt(self, state: TripState) -> dict[str, Any]:
        decision = interrupt({"type": "approval", "decisions": state.get("policy_decisions", [])})
        approved = decision.get("decision") == "approved" if isinstance(decision, dict) else False
        return {"approval_decision": "approved" if approved else "rejected", "status": "planning" if approved else "failed", "next_action": "plan" if approved else "manual_review", "audit": self._audit("APPROVAL_RECEIVED")}

    def _create_plan(self, state: TripState) -> dict[str, Any]:
        tasks = build_tasks(state.get("trip", {}))
        return {"plan": {"procedures": ["policy_check", "approval_check", "parallel_search", "alternative_selection", "booking"], "search_tasks": tasks}, "search_tasks": tasks, "status": "searching", "next_action": "search", "audit": self._audit("PLAN_CREATED")}

    def _dispatch_search(self, state: TripState) -> list[Send]:
        return [Send("search_worker", {"case_id": state["case_id"], "trip": state.get("trip", {}), "task": task}) for task in state.get("search_tasks", [])]

    def _search_worker(self, state: TripState) -> dict[str, Any]:
        task = state["task"]
        offers = search_task(task, state.get("trip", {}))
        return {"search_results": offers, "audit": self._audit(f"{task['task_type'].upper()}_SEARCH_COMPLETED")}

    def _collect_results(self, state: TripState) -> dict[str, Any]:
        return {"status": "alternatives_ready", "next_action": "select_alternative", "audit": self._audit("SEARCH_RESULTS_COLLECTED")}

    def _build_alternatives(self, state: TripState) -> dict[str, Any]:
        offers = state.get("search_results", [])
        alternatives = [{"alternative_id": "alt-1", "title": "Оптимальный вариант", "offers": offers, "total_price": sum(float(item.get("price", 0)) for item in offers), "currency": "RUB", "policy_refs": [item["policy_id"] for item in state.get("policy_context", [])]}]
        return {"alternatives": alternatives, "status": "awaiting_selection", "next_action": "select_alternative"}

    def _build_trip_graph(self):
        graph = StateGraph(TripState)
        graph.add_node("parse_request", self._parse_request)
        graph.add_node("retrieve_policy_context", self._retrieve_policy_context)
        graph.add_node("check_completeness", self._check_completeness)
        graph.add_node("ask_clarification", self._ask_clarification)
        graph.add_node("evaluate_policy", self._evaluate_policy)
        graph.add_node("create_plan", self._create_plan)
        graph.add_node("search_worker", self._search_worker)
        graph.add_node("collect_results", self._collect_results)
        graph.add_node("build_alternatives", self._build_alternatives)
        graph.add_edge(START, "parse_request")
        graph.add_edge("parse_request", "retrieve_policy_context")
        graph.add_edge("retrieve_policy_context", "check_completeness")
        graph.add_conditional_edges("check_completeness", lambda state: "ask_clarification" if state.get("missing_fields") else "evaluate_policy")
        graph.add_edge("ask_clarification", "retrieve_policy_context")
        graph.add_conditional_edges("evaluate_policy", lambda state: "approval_interrupt" if state.get("status") == "approval_pending" else "create_plan")
        graph.add_node("approval_interrupt", self._approval_interrupt)
        graph.add_conditional_edges("approval_interrupt", lambda state: "create_plan" if state.get("approval_decision") == "approved" else END)
        graph.add_conditional_edges("create_plan", self._dispatch_search, ["search_worker"])
        graph.add_edge("search_worker", "collect_results")
        graph.add_edge("collect_results", "build_alternatives")
        graph.add_edge("build_alternatives", END)
        return graph.compile(checkpointer=self.checkpointer)

    def _await_selection(self, state: TripState) -> dict[str, Any]:
        if state.get("selected_alternative_id"):
            return {"status": "booking", "next_action": "book"}
        selection = interrupt({"type": "selection", "alternatives": state.get("alternatives", [])})
        return {"selected_alternative_id": selection["alternative_id"], "status": "booking", "next_action": "book"}

    def _book(self, state: TripState) -> dict[str, Any]:
        option = next(item for item in state.get("alternatives", []) if item["alternative_id"] == state["selected_alternative_id"])
        bookings = self.booking_agent.book(option.get("offers", []))
        return {"bookings": bookings, "status": "confirmed", "next_action": "cancel_or_complete", "audit": self._audit("BOOKING_COMPLETED")}

    def _build_booking_graph(self):
        graph = StateGraph(TripState)
        graph.add_node("await_selection", self._await_selection)
        graph.add_node("book", self._book)
        graph.add_edge(START, "await_selection")
        graph.add_edge("await_selection", "book")
        graph.add_edge("book", END)
        return graph.compile(checkpointer=self.checkpointer)

    def _cancellation_quote(self, state: TripState) -> dict[str, Any]:
        quote = self.cancellation_agent.quote(state.get("bookings", []))
        quote["quote_id"] = f"quote-{uuid.uuid4().hex[:8]}"
        return {"cancellation_quote": quote, "status": "cancellation_confirmation"}

    def _cancel(self, state: TripState) -> dict[str, Any]:
        confirmation = {"confirm": state.get("cancel_confirmed", False)} if "cancel_confirmed" in state else interrupt({"type": "cancellation_confirmation", "quote": state["cancellation_quote"]})
        if not confirmation.get("confirm"):
            return {"status": "confirmed", "next_action": "cancel_or_complete"}
        return {"status": "cancelled", "next_action": "none", "audit": self._audit("TRIP_CANCELLED")}

    def _replan(self, state: TripState) -> dict[str, Any]:
        reason = state.get("replan_reason", "unavailable")
        route = self.replanning_agent.classify(reason)
        return {"status": "searching" if route == "search" else "manual_review", "next_action": route, "audit": self._audit("REPLAN_ROUTED")}

    def _build_replanning_graph(self):
        graph = StateGraph(TripState)
        graph.add_node("replanning_agent", self._replan)
        graph.add_edge(START, "replanning_agent")
        graph.add_edge("replanning_agent", END)
        return graph.compile(checkpointer=self.checkpointer)

    def _build_cancellation_graph(self):
        graph = StateGraph(TripState)
        graph.add_node("cancellation_quote", self._cancellation_quote)
        graph.add_node("cancel", self._cancel)
        graph.add_edge(START, "cancellation_quote")
        graph.add_edge("cancellation_quote", "cancel")
        graph.add_edge("cancel", END)
        return graph.compile(checkpointer=self.checkpointer)


def build_trip_graph(db_path: str):
    return TravelGraphs(PolicyRAG(db_path))
