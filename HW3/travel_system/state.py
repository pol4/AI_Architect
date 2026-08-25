from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, Any, Literal, TypedDict


class TripRequest(TypedDict, total=False):
    departure_city: str
    destination: str
    departure_date: str
    return_date: str
    purpose: str
    budget: float
    currency: str
    preferences: dict[str, Any]
    department: str


class PolicyChunk(TypedDict):
    policy_id: str
    version: str
    chunk_id: str
    text: str
    citation: str
    effective_from: str
    effective_to: str | None
    scope: dict[str, str]
    content_hash: str


class PolicyDecision(TypedDict):
    decision: Literal["allowed", "denied", "conditional", "manual_review"]
    policy_refs: list[str]
    citations: list[str]
    rule_code: str
    evaluated_values: dict[str, Any]
    explanation: str


class SearchTask(TypedDict):
    task_id: str
    task_type: Literal["transport", "hotel", "transfer", "visa", "insurance"]
    mandatory: bool
    status: str


class Offer(TypedDict, total=False):
    offer_id: str
    offer_type: str
    provider: str
    title: str
    price: float
    currency: str
    details: str
    cancellation_policy: str
    valid_until: str


class Alternative(TypedDict, total=False):
    alternative_id: str
    title: str
    total_price: float
    currency: str
    policy_refs: list[str]
    offers: list[Offer]
    valid_until: str


class TripState(TypedDict, total=False):
    case_id: str
    user_id: str
    request_text: str
    trip: TripRequest
    missing_fields: list[str]
    questions: list[dict[str, Any]]
    policy_context: list[PolicyChunk]
    policy_decisions: list[PolicyDecision]
    approvals: list[dict[str, Any]]
    approval_decision: str | None
    search_task: SearchTask
    replan_reason: str | None
    plan: dict[str, Any]
    search_tasks: list[SearchTask]
    search_results: Annotated[list[Offer], operator.add]
    alternatives: list[Alternative]
    selected_alternative_id: str | None
    cancel_confirmed: bool
    cancellation_quote: dict[str, Any]
    bookings: list[dict[str, Any]]
    status: str
    next_action: str
    error: dict[str, Any] | None
    audit: Annotated[list[dict[str, Any]], operator.add]


class RuntimeContext(TypedDict, total=False):
    user_id: str
    role: str
    correlation_id: str
