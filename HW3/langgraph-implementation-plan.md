# План реализации на LangGraph

## 1. Предлагаемая структура проекта

```text
business-travel/
├── app/
│   ├── api/                 # REST endpoints и auth
│   ├── rag/                 # ingestion, retrieval, reranking, provenance
│   ├── graphs/
│   │   ├── intake.py        # parse/clarification/policy precheck
│   │   ├── planning.py      # approvals + fan-out/fan-in search
│   │   │   ├── booking.py   # revalidation/booking/compensation
│   │   └── cancellation.py  # quote/confirmation/refund
│   ├── state.py             # TripState и типизированные модели
│   ├── nodes/               # детерминированные nodes и agent nodes
│   ├── policies/            # retrieval и rules engine
│   ├── providers/            # TravelProviderAdapter implementations
│   ├── persistence/          # repositories, checkpoint, audit events
│   └── notifications/       # notification adapter
├── tests/
│   ├── unit/
│   ├── graph/
│   └── contract/
├── migrations/
├── pyproject.toml
└── .env.example
```

## 2. Карта соответствия плана текущему коду

| Архитектурная часть | Реализация в каталоге | Статус |
|---|---|---|
| `TripState` и типизированные модели | `travel_system/state.py` | Реализовано |
| Intake/planning graph | `travel_system/graphs.py:TravelGraphs._build_trip_graph` | Реализовано в vertical slice |
| Human-in-the-loop clarification | `travel_system/graphs.py:TravelGraphs._ask_clarification` | Реализовано через `interrupt` |
| Fan-out/fan-in поиска | `travel_system/graphs.py:TravelGraphs._dispatch_search`, `_search_worker` | Реализовано через `Send`, barrier требует усиления |
| Специализированные search agents | `travel_system/agents.py` | Реализовано на mock adapters |
| Booking graph | `travel_system/graphs.py:TravelGraphs._build_booking_graph` | Реализован demo-flow с interrupt/resume |
| Cancellation graph | `travel_system/graphs.py:TravelGraphs._build_cancellation_graph` | Реализован demo-flow с quote и confirmation |
| Approval interrupt | `travel_system/graphs.py:TravelGraphs._approval_interrupt` | Реализован для conditional policy decision |
| Replanning graph | `travel_system/graphs.py:TravelGraphs._build_replanning_graph` | Реализована маршрутизация причины сбоя |
| RAG ingestion/runtime | `travel_system/rag.py:PolicyRAG` | Реализован SQLite lexical prototype |
| OpenAI-compatible gateway | `travel_system/llm.py:LLMGateway` | Реализован для parser; остальные роли подготовлены |
| PostgreSQL checkpointer | Не реализован | Production backlog |
| Реальные provider adapters, платежи, webhook, Saga | Не реализованы | Production backlog |

Файл `app.py` является тонким HTTP-адаптером: он не содержит бизнес-логику и вызывает `TravelGraphs`. Веб-интерфейс находится в `static/index.html`. Это сознательный вертикальный срез; перед production-кодированием необходимо разнести методы `TravelGraphs` по модулям `graphs/intake.py`, `graphs/planning.py`, `graphs/booking.py`, `graphs/cancellation.py` и выделить nodes из `travel_system/graphs.py`.

## 3. Разделение ответственности

### Специализированные агенты

- `request_parser_agent`: свободный текст → `TripRequest` с confidence и списком неопределённостей.
- `clarification_agent`: формирует короткие вопросы только по отсутствующим или противоречивым полям.
- `transport_search_agent`: ищет авиабилеты/жд-билеты и нормализует offers.
- `hotel_search_agent`: ищет отели и проверяет условия проживания.
- `transfer_search_agent`: подбирает трансфер и проверяет стыковки.
- `visa_insurance_agent`: определяет применимость документов и ищет соответствующие услуги.
- `booking_agent`: координирует выбранные offers, но вызывает только Booking Service tools.
- `cancellation_refund_agent`: формирует отмену и контролирует возврат через Cancellation Service tools.
- `replanning_agent`: классифицирует ошибку и выбирает ветку нового поиска, согласования или manual review.
- `policy_explanation_agent`: объясняет применённые правила по результату детерминированного движка.
- `alternative_explainer_agent`: готовит понятное сравнение вариантов без изменения цены, условий или policy decision.

Каждый агент получает собственный узкий prompt, Pydantic output schema и минимальный allow-list tools. Search-агенты могут вызывать только `search`/`check_availability`; `booking_agent` — только hold/book/status; `cancellation_refund_agent` — quote/cancel/refund. Ни один LLM-агент не выполняет платёж напрямую.

### RAG-контур нормативных документов

RAG состоит из двух разных жизненных циклов:

- `policy_ingestion_graph`: получает документ из корпоративного хранилища, извлекает текст и metadata, нормализует и chunk-ит документ, строит embeddings, индексирует chunks, запускает regression-проверки и публикует версию;
- `policy_runtime_retrieval`: строит запрос по `TripRequest`, делает hybrid search, фильтрует effective dates и scope, rerank-ит результаты и передаёт в rules engine контекст с citations.

Рекомендуемые модели:

```python
class PolicyChunk(TypedDict):
    policy_id: str
    version: str
    chunk_id: str
    text: str
    source_uri: str
    page: int | None
    section: str | None
    effective_from: date
    effective_to: date | None
    scope: dict[str, str]
    content_hash: str

class PolicyDecision(TypedDict):
    decision: Literal["allowed", "denied", "conditional", "manual_review"]
    policy_refs: list[str]
    citations: list[str]
    rule_code: str
    evaluated_values: dict[str, Any]
    explanation: str
```

Ingestion публикует документ только после проверки уникальности версии, полноты provenance, корректности дат и прохождения эталонных policy cases. Runtime никогда не использует документ со статусом draft/rejected и сохраняет snapshot использованных chunks в `TripState` и audit store.

### Графы и маршрутизация

- `intake_graph`: `parse_request` → `retrieve_policy_context` → `check_completeness_against_policy` → `ask_clarification` или `policy_evaluator`.
- После каждого ответа пользователя выполняется переход обратно к `parse_request`, затем повторяются `retrieve_policy_context` и `check_completeness_against_policy`.
- `policy_ingestion_graph`: отдельный фоновый/admin-граф `load_policy_document` → `extract_text` → `normalize_and_chunk` → `generate_embeddings` → `index_chunks` → `run_policy_regression` → `publish_policy_version`. Он не запускается как часть конкретной командировки.
- `planning_graph`: `policy_evaluator` → `create_approval_plan` → `dispatch_search_tasks` → specialized search agents → `collect_search_results` → `build_alternatives`.
- `booking_graph`: `await_user_selection` → `booking_agent` → `revalidate_selection` → `booking_coordinator` → `document_issuer` → `notify_user`.
- `cancellation_graph`: `load_itinerary` → `cancellation_refund_agent` → `retrieve_cancellation_policy` → `refund_calculator` → `await_cancel_confirmation` → `cancellation_coordinator`.
- `replanning_graph`: `replanning_agent` → compensation/status check → new search or policy re-evaluation.

`retrieve_policy_context` выполняет hybrid search по keyword и embeddings, фильтрует chunks по effective dates/scope, передаёт результаты в `context_assembler`, а затем в детерминированный `policy_evaluator`. В state сохраняется snapshot использованных chunks, включая `policy_id`, `version`, `chunk_id`, `citation` и `content_hash`.

### Детерминированные узлы

- валидация схемы и дат;
- определение missing fields;
- выбор версии политики по effective dates;
- расчёт лимитов, бюджета, штрафов и маршрута согласований;
- fan-out/fan-in и контроль обязательных задач;
- проверка hold/цены перед покупкой;
- идемпотентность, компенсации и переходы состояний.

LLM не вызывает платёжные или booking API напрямую. Он использует только типизированные tools, а каждый tool проверяет права, case state и idempotency key.

## 4. Контракт узлов графа

Каждый node принимает `TripState`, не мутирует его напрямую и возвращает частичное обновление:

```python
StateUpdate = dict[str, Any]
Node = Callable[[TripState, RuntimeContext], StateUpdate]
```

Каждый переход должен создавать audit event:

```python
AuditEvent(
    case_id=state["case_id"],
    event_type="POLICY_CHECK_COMPLETED",
    from_status="POLICY_CHECK",
    to_status="APPROVAL_PENDING",
    actor="system",
    policy_refs=[...],
    correlation_id=runtime.correlation_id,
)
```

## 5. Human-in-the-loop

Точки `interrupt()`:

1. `clarification_required` — ожидание ответов на вопросы.
2. `approval_pending` — ожидание руководителя/финансов.
3. `awaiting_selection` — выбор альтернативы.
4. `purchase_confirmation` — явное подтверждение покупки с итоговой ценой.
5. `cancellation_confirmation` — подтверждение штрафов и суммы возврата.
6. `manual_review` — неопределённый статус поставщика или исключение политики.

Каждое прерывание должно быть возобновляемым по `thread_id=case_id`, иметь TTL и хранить checkpoint в PostgreSQL. Повторная отправка ответа не должна создавать вторую бронь.

## 6. Fan-out/fan-in

Планировщик создаёт `SearchTask` для каждого применимого сервиса. LangGraph запускает worker через `Send("search_worker", task)`. Reducer добавляет результаты по `task_id`, а barrier пропускает план дальше только когда:

- завершены все mandatory tasks;
- optional tasks либо завершены, либо явно помечены `skipped`;
- ошибки классифицированы как retryable или terminal.

## 7. Перепланирование и Saga

`replan_router` классифицирует событие:

- `expired_hold` — повторно запросить доступность и построить варианты;
- `price_changed` — пересчитать бюджет, при необходимости вернуть в approval;
- `unavailable` — исключить offer и повторить поиск;
- `partial_booking` — выполнить compensating cancellation и показать статус;
- `provider_unknown` — проверить статус по reference, затем manual review;
- `user_requested` — уточнить новые ограничения.

Для каждой брони хранится saga step. Компенсация выполняется в обратном порядке, но только для фактически подтверждённых ресурсов.

## 8. Минимальные интерфейсы

```python
class PolicyService(Protocol):
    async def retrieve(self, request: TripRequest) -> list[PolicyReference]: ...
    async def evaluate(self, request: TripRequest, refs: list[PolicyReference]) -> list[PolicyDecision]: ...

class TravelProviderAdapter(Protocol):
    async def search(self, task: SearchTask) -> list[Offer]: ...
    async def hold(self, offer: Offer, key: str) -> Hold: ...
    async def book(self, hold: Hold, key: str) -> Booking: ...
    async def get_status(self, provider_reference: str) -> Booking: ...
    async def cancel(self, booking: Booking, key: str) -> CancellationResult: ...

class CaseRepository(Protocol):
    async def load(self, case_id: str) -> TripCase: ...
    async def save(self, case: TripCase, expected_version: int) -> None: ...
    async def append_event(self, event: AuditEvent) -> None: ...
```

## 9. Безопасность и эксплуатация

- OIDC/JWT и RBAC: employee, manager, finance, travel_manager, policy_admin.
- Secret manager для ключей поставщиков и LLM; платёжные реквизиты не попадают в state и prompts.
- PII redaction до LLM; разрешённый контекст ограничивается необходимыми полями.
- Correlation ID во всех API, задачах, webhook и audit events.
- Метрики: время до вопросов, policy rejection rate, search success rate, hold expiry rate, booking success rate, compensation success rate, cancellation/refund SLA, стоимость LLM.
- Трассировка LangGraph node transitions и provider calls без содержимого секретов.
- Webhook поставщика проверяется по подписи и дедуплицируется по event ID.

## 10. План разработки после ревью

1. Утвердить policy document format, матрицу ролей и источники поставщиков.
2. Зафиксировать обязательные поля `TripRequest`, статусы и SLA.
3. Реализовать intake graph с PostgreSQL checkpointer и human interrupt.
4. Добавить policy ingestion/retrieval и детерминированные проверки.
5. Реализовать mock adapters и planning graph с параллельным поиском.
6. Добавить альтернативы, selection и purchase confirmation.
7. Реализовать booking saga, webhook/status reconciliation и replanning.
8. Реализовать cancellation graph и расчёт refund quote.
9. Подключить реальные provider adapters по контрактным тестам.
10. Провести chaos-тесты: timeout, duplicate request, price change, partial booking, expired hold и provider outage.
