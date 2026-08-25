from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .state import Offer, SearchTask, TripRequest

OFFERS: dict[str, list[Offer]] = {
    "transport": [{"offer_id": "flight-1", "offer_type": "flight", "provider": "Demo Airways", "title": "Прямой рейс, эконом", "price": 28500, "currency": "RUB", "details": "Багаж 23 кг, возвратный тариф"}, {"offer_id": "flight-2", "offer_type": "flight", "provider": "Demo Airways", "title": "Рейс с пересадкой", "price": 19200, "currency": "RUB", "details": "Багаж 10 кг, частичный возврат"}],
    "hotel": [{"offer_id": "hotel-1", "offer_type": "hotel", "provider": "Demo Hotels", "title": "Central Business Hotel", "price": 42000, "currency": "RUB", "details": "Завтрак, бесплатная отмена до 24 часов"}, {"offer_id": "hotel-2", "offer_type": "hotel", "provider": "Demo Hotels", "title": "City Apart", "price": 31500, "currency": "RUB", "details": "Без завтрака, отмена со штрафом"}],
    "transfer": [{"offer_id": "transfer-1", "offer_type": "transfer", "provider": "Demo Transfer", "title": "Встреча в аэропорту", "price": 6500, "currency": "RUB", "details": "Комфорт-класс"}],
}


class BaseTravelAgent:
    name = "base"

    def search(self, task: SearchTask, trip: TripRequest) -> list[Offer]:
        return [{**offer, "valid_until": datetime.now(timezone.utc).isoformat()} for offer in OFFERS.get(task["task_type"], [])]


class TransportSearchAgent(BaseTravelAgent):
    name = "transport_search_agent"


class HotelSearchAgent(BaseTravelAgent):
    name = "hotel_search_agent"


class TransferSearchAgent(BaseTravelAgent):
    name = "transfer_search_agent"


class VisaInsuranceAgent(BaseTravelAgent):
    name = "visa_insurance_agent"

    def search(self, task: SearchTask, trip: TripRequest) -> list[Offer]:
        return []


class SupervisorAgent:
    name = "supervisor_agent"

    def choose_stage(self, state: dict[str, Any]) -> str:
        return "research" if not state.get("search_results") else "editing"


class BookingAgent:
    name = "booking_agent"

    def book(self, offers: list[Offer]) -> list[dict[str, Any]]:
        return [{"booking_id": f"booking-{offer['offer_id']}", "offer": offer, "status": "booked"} for offer in offers]


class CancellationRefundAgent:
    name = "cancellation_refund_agent"

    def quote(self, bookings: list[dict[str, Any]]) -> dict[str, Any]:
        total = sum(float(item.get("offer", {}).get("price", 0)) for item in bookings)
        return {"penalty": total * 0.1, "expected_refund": total * 0.9, "currency": "RUB"}


class ReplanningAgent:
    name = "replanning_agent"

    def classify(self, error: str) -> str:
        return "search" if error in {"expired_hold", "unavailable", "price_changed"} else "manual_review"


class SummaryAgent:
    name = "summary_agent"


AGENTS = {agent.name: agent for agent in (TransportSearchAgent(), HotelSearchAgent(), TransferSearchAgent(), VisaInsuranceAgent())}


def search_task(task: SearchTask, trip: TripRequest) -> list[Offer]:
    agent = AGENTS.get(f"{task['task_type']}_search_agent", AGENTS.get("visa_insurance_agent"))
    return agent.search(task, trip) if agent else []


def build_tasks(trip: TripRequest) -> list[SearchTask]:
    international = bool(trip.get("destination")) and str(trip.get("destination")).lower() not in {"москва", "санкт-петербург", "екатеринбург"}
    tasks: list[SearchTask] = [{"task_id": "transport-1", "task_type": "transport", "mandatory": True, "status": "pending"}, {"task_id": "hotel-1", "task_type": "hotel", "mandatory": True, "status": "pending"}, {"task_id": "transfer-1", "task_type": "transfer", "mandatory": False, "status": "pending"}]
    if international:
        tasks.append({"task_id": "visa-1", "task_type": "visa", "mandatory": False, "status": "pending"})
    return tasks
