# Диаграммы состояний системы оформления командировок

## Жизненный цикл командировки

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Parsing: получен свободный текст
    Parsing --> RuntimeRAG: предварительные параметры извлечены
    RuntimeRAG --> CompletenessCheck: применимые правила найдены
    RuntimeRAG --> ManualReview: нет действующего контекста или конфликт версий
    CompletenessCheck --> Clarification: обязательные поля по правилам отсутствуют
    Clarification --> Parsing: пользователь ответил, RAG запускается повторно
    CompletenessCheck --> PolicyCheck: данные полны по найденным правилам
    PolicyCheck --> ApprovalPending: требуется согласование
    PolicyCheck --> Planning: согласование не требуется
    ApprovalPending --> Planning: все согласования получены
    ApprovalPending --> Replanning: отказ или изменение условий
    Replanning --> Clarification: нужны новые данные
    Replanning --> Planning: условия изменены
    Planning --> Searching: план утверждён
    Searching --> AvailabilityCheck: все обязательные поисковые задачи завершены
    AvailabilityCheck --> AlternativesReady: варианты доступны
    AvailabilityCheck --> Replanning: нет доступности или изменилась цена
    AlternativesReady --> AwaitingSelection: варианты показаны пользователю
    AwaitingSelection --> Revalidation: пользователь выбрал вариант
    AwaitingSelection --> Replanning: пользователь попросил изменить условия
    Revalidation --> Booking: вариант всё ещё доступен
    Revalidation --> Replanning: hold истёк или цена изменилась
    Booking --> PartialBooking: часть бронирований успешна
    Booking --> Documents: все бронирования успешны
    PartialBooking --> Compensation: отменить уже созданные брони
    Compensation --> Replanning: компенсация завершена или требует решения
    Documents --> Confirmed: документы выпущены
    Confirmed --> CancellationRequested: пользователь запросил отмену
    CancellationRequested --> CancellationQuote: рассчитаны штрафы и возвраты
    CancellationQuote --> CancellationConfirmed: пользователь подтвердил отмену
    CancellationQuote --> Confirmed: пользователь отказался от отмены
    CancellationConfirmed --> Cancelled: брони отменены и возвраты запущены
    Confirmed --> Completed: поездка завершена
    Completed --> [*]
    Cancelled --> [*]
    Replanning --> Failed: превышен лимит попыток
    Failed --> [*]
    ManualReview --> [*]
```

## Состояние параллельного поиска

```mermaid
stateDiagram-v2
    [*] --> SearchPlanCreated
    SearchPlanCreated --> FanOut
    FanOut --> TransportSearchAgent
    FanOut --> HotelSearchAgent
    FanOut --> TransferSearchAgent
    FanOut --> VisaInsuranceAgent: применимо по политике
    TransportSearchAgent --> TransportResult
    HotelSearchAgent --> HotelResult
    TransferSearchAgent --> TransferResult
    VisaInsuranceAgent --> VisaInsuranceResult
    TransportSearchAgent --> SearchRetry: timeout/provider error
    HotelSearchAgent --> SearchRetry: timeout/provider error
    TransferSearchAgent --> SearchRetry: timeout/provider error
    VisaInsuranceAgent --> SearchRetry: timeout/provider error
    SearchRetry --> TransportSearchAgent: retry transport
    SearchRetry --> HotelSearchAgent: retry hotel
    SearchRetry --> TransferSearchAgent: retry transfer
    SearchRetry --> VisaInsuranceAgent: retry visa/insurance
    TransportResult --> FanIn
    HotelResult --> FanIn
    TransferResult --> FanIn
    VisaInsuranceResult --> FanIn
    FanIn --> SearchComplete: все обязательные задачи завершены
    FanIn --> SearchDegraded: необязательная задача недоступна
    SearchComplete --> [*]
    SearchDegraded --> [*]
```

## Состояние отдельной брони

За переходами `Revalidated → BookingRequested` и `CancellationRequested → Cancelled` стоят специализированные `Booking Agent` и `Cancellation & Refund Agent`. Они принимают решение о следующем действии, но фактические операции выполняются детерминированными компонентами Booking Service.

```mermaid
stateDiagram-v2
    [*] --> Candidate
    Candidate --> HoldRequested
    HoldRequested --> Held: поставщик подтвердил hold
    HoldRequested --> Unavailable: мест нет
    Held --> Revalidated: перед финальным оформлением
    Held --> HoldExpired: TTL истёк
    Revalidated --> BookingRequested: цена и доступность неизменны
    Revalidated --> Changed: цена/условия изменились
    BookingRequested --> Booked: подтверждён booking reference
    BookingRequested --> BookingUnknown: timeout после запроса
    BookingUnknown --> StatusChecked
    StatusChecked --> Booked: найдено подтверждение
    StatusChecked --> ReplanRequired: подтверждение не найдено
    Booked --> CancellationRequested
    CancellationRequested --> Cancelled: поставщик отменил бронь
    CancellationRequested --> CancellationFailed: ошибка отмены
    Held --> ReplanRequired: другая часть маршрута недоступна
    HoldExpired --> ReplanRequired
    Unavailable --> ReplanRequired
    Changed --> ReplanRequired
    CancellationFailed --> ManualReview
    ReplanRequired --> [*]
    Cancelled --> [*]
    ManualReview --> [*]
```

## Наполнение RAG нормативными документами

```mermaid
stateDiagram-v2
    [*] --> DocumentDetected
    DocumentDetected --> Extracting
    Extracting --> Normalizing
    Normalizing --> Chunking
    Chunking --> Embedding
    Embedding --> Indexing
    Indexing --> Validation
    Validation --> Published: metadata, provenance и regression checks passed
    Validation --> Rejected: ошибки формата, конфликт версии или неполная provenance
    Published --> [*]
    Rejected --> [*]
```

## Runtime-поиск и применение RAG

```mermaid
stateDiagram-v2
    [*] --> QueryBuilding
    QueryBuilding --> HybridRetrieval: параметры поездки нормализованы
    HybridRetrieval --> Reranking
    Reranking --> ContextAssembly
    ContextAssembly --> PolicyEvaluation: найдены действующие фрагменты
    ContextAssembly --> ManualReview: нет контекста или конфликт версий
    PolicyEvaluation --> Allowed: ограничения соблюдены
    PolicyEvaluation --> Conditional: требуется согласование или исключение
    PolicyEvaluation --> Denied: нарушение обязательного правила
    Allowed --> PlanCreation
    Conditional --> ApprovalPending
    Denied --> ReplanningOrReject
    ApprovalPending --> PlanCreation: согласование получено
    ApprovalPending --> ReplanningOrReject: отказ или изменение условий
    PlanCreation --> [*]
    ManualReview --> [*]
    ReplanningOrReject --> [*]
```

## Связь диаграмм

Наполнение RAG не является частью каждого пользовательского запроса: это отдельный управляемый контур, который обновляет базу знаний. Основной workflow использует только опубликованные версии документов. В состоянии `PolicyCheck` запускается runtime-поиск RAG, после чего результат поступает в `PolicyEvaluation`; при отсутствии проверяемого контекста автоматическое бронирование блокируется и создаётся `ManualReview`.

Жизненный цикл командировки является родительским. В состоянии `Searching` раскрывается диаграмма параллельного поиска. После `AvailabilityCheck` каждая найденная возможность представлена отдельной сущностью и проходит жизненный цикл брони. События `HoldExpired`, `Changed`, `Unavailable`, `BookingUnknown` и `PartialBooking` возвращают родительский процесс в `Replanning`. После `Confirmed` запускается тот же booking state machine в обратной ветке отмены.

Между состояниями действуют следующие связи:

| Контур | Вход | Результат | Использование |
|---|---|---|---|
| RAG ingestion | Новая/изменённая инструкция или регламент | Опубликованные chunks, embeddings, metadata и provenance | Доступно для будущих кейсов |
| RAG runtime | Нормализованный TripRequest | Релевантный контекст и ссылки на правила | Состояние `PolicyCheck` |
| Policy evaluation | RAG-контекст | `Allowed`, `Conditional`, `Denied` или `ManualReview` | Создание плана и согласований |
| Booking workflow | Выбранная альтернатива | Брони, документы или `Replanning` | Состояния `Booking` и `Confirmed` |
| Cancellation workflow | Подтверждённая поездка | Quote, отмена и возврат | Ветка после `Confirmed` |

При публикации новой версии RAG не изменяет уже завершённый кейс: историческое решение ссылается на зафиксированные `policy_id`, `version`, `citation` и хэш фрагмента. Новая версия применяется только к новым проверкам или явно запущенному перепланированию.
