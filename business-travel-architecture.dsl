workspace {
    model {
        employee = person "Сотрудник" {
            description "Создаёт командировку в свободной форме, отвечает на вопросы, выбирает вариант, подтверждает бронирование или отмену"
        }
        manager = person "Руководитель" {
            description "Согласует цель, сроки и бюджет по матрице полномочий"
        }
        finance = person "Финансовый контролёр" {
            description "Проверяет cost center, лимиты и финансовые последствия"
        }
        travelManager = person "Travel manager" {
            description "Обрабатывает исключения и ручные операции"
        }
        policyAdmin = person "Администратор политик" {
            description "Публикует и архивирует нормативные документы компании"
        }

        identity = softwareSystem "Корпоративная IAM" {
            description "Аутентификация, роли, подразделение, cost center и полномочия пользователя"
        }
        policySource = softwareSystem "Корпоративное хранилище нормативных документов" {
            description "Официальные документы и версии политик командировок"
        }
        travelProviders = softwareSystem "Travel providers" {
            description "Авиакомпании, РЖД, гостиницы, трансферные и страховые сервисы"
        }
        financeSystem = softwareSystem "Финансовая система" {
            description "Бюджеты, cost center, платежи и возвраты"
        }
        notification = softwareSystem "Корпоративные уведомления" {
            description "Email, мессенджер и push-уведомления"
        }
        documentSystem = softwareSystem "ЭДО / Архив документов" {
            description "Хранение приказов, ваучеров, билетов и документов отмены"
        }
        llmProvider = softwareSystem "LLM Provider" {
            description "Модель для извлечения смысла, формирования вопросов и объяснения вариантов; не является источником правил"
        }

        travel = softwareSystem "Business Travel Automation" {
            description "Мультиагентная система автоматического оформления, бронирования, перепланирования и отмены командировок"

            portal = container "Employee Portal / Travel API" {
                description "Принимает свободный текст, показывает вопросы и альтернативы, получает подтверждения"
                technology "Web UI / REST API"
            }
            orchestrator = container "LangGraph Orchestrator" {
                description "Долгоживущий stateful workflow с human-in-the-loop, checkpoint и маршрутизацией"
                technology "Python / LangGraph"

                intakeController = component "Intake Controller" {
                    description "Создаёт TripCase, принимает текст, управляет циклом уточнений"
                    technology "LangGraph node"
                }
                requestParser = component "Request Parser Agent" {
                    description "Извлекает предварительный структурированный TripRequest из произвольного текста; не определяет полноту сам"
                    technology "LLM structured output / Pydantic"
                }
                policyQueryBuilder = component "Policy Query Builder" {
                    description "Формирует запрос в RAG по известным параметрам поездки и контексту сотрудника"
                    technology "Deterministic query builder"
                }
                completenessChecker = component "Policy-Aware Completeness Checker" {
                    description "Сопоставляет TripRequest с найденными policy fragments и определяет обязательные/missing fields"
                    technology "Rules evaluation"
                }
                clarificationManager = component "Clarification Manager" {
                    description "Определяет missing fields, формирует вопросы и приостанавливает граф до ответа"
                    technology "LangGraph interrupt"
                }
                planBuilder = component "Travel Plan Builder" {
                    description "Строит план процедур, согласований и параллельных поисковых задач"
                    technology "LangGraph node"
                }
                fanOutFanIn = component "Search Fan-out/Fan-in" {
                    description "Запускает независимые задачи транспорта, отеля, трансфера и документов и собирает результаты"
                    technology "LangGraph Send / reducers"
                }
                approvalRouter = component "Approval Router" {
                    description "Применяет матрицу полномочий и запускает нужные согласования"
                    technology "Policy decision result"
                }
                selectionInterrupt = component "Selection & Confirmation" {
                    description "Показывает альтернативы и ожидает явного выбора/подтверждения пользователя"
                    technology "LangGraph interrupt/resume"
                }
                replanRouter = component "Replan Router" {
                    description "Возвращает процесс к поиску, согласованию или уточнению после сбоя/изменения условий"
                    technology "Deterministic routing"
                }
                cancellationFlow = component "Cancellation Flow" {
                    description "Рассчитывает штрафы, запрашивает подтверждение отмены и запускает компенсации"
                    technology "LangGraph subgraph"
                }
                bookingCoordinator = component "Booking Coordinator" {
                    description "Проверяет hold, вызывает бронирование идемпотентно и отслеживает partial booking"
                    technology "Saga / idempotency keys"
                }

                intakeController -> requestParser "Передаёт свободный текст"
                requestParser -> policyQueryBuilder "Передаёт предварительные параметры"
                completenessChecker -> clarificationManager "Есть missing/ambiguous fields"
                clarificationManager -> requestParser "Ответ пользователя: повторный parse и RAG"
                completenessChecker -> planBuilder "Все обязательные поля по политике заполнены"
                planBuilder -> approvalRouter "Передаёт процедуры и условия"
                approvalRouter -> fanOutFanIn "Согласования пройдены"
                fanOutFanIn -> selectionInterrupt "Передаёт проверенные альтернативы"
                selectionInterrupt -> bookingCoordinator "Пользователь подтвердил вариант"
                bookingCoordinator -> replanRouter "Ошибка, истёк hold или изменилась цена"
                replanRouter -> fanOutFanIn "Повторить поиск"
                replanRouter -> approvalRouter "Нужно новое согласование"
                bookingCoordinator -> cancellationFlow "Поездка оформлена и запрошена отмена"
            }
            policy = container "Policy Knowledge & Decision Service" {
                description "Индексирует нормативные документы, извлекает применимые нормы и детерминированно проверяет ограничения"
                technology "Python / Hybrid Search / Rules Engine"

                documentIngestor = component "Policy Ingestor" {
                    description "Загружает документы, извлекает текст, версии, даты действия и область применимости"
                    technology "PDF/DOCX parser"
                }
                policyIndexer = component "Policy Indexer" {
                    description "Строит полнотекстовый и векторный индекс нормативных фрагментов"
                    technology "PostgreSQL FTS / pgvector"
                }
                documentChunker = component "Document Normalizer & Chunker" {
                    description "Очищает документы, выделяет заголовки и пункты, режет текст на фрагменты с сохранением provenance"
                    technology "Python / PDF-DOCX parser"
                }
                embeddingGenerator = component "Embedding Generator" {
                    description "Создаёт embeddings для фрагментов политик при публикации и переиндексации"
                    technology "Embedding model"
                }
                policyRetriever = component "Hybrid Policy Retriever" {
                    description "Находит действующие фрагменты по стране, подразделению, датам и типу поездки через keyword + vector search"
                    technology "BM25 + vector search"
                }
                reranker = component "Policy Reranker" {
                    description "Переранжирует найденные фрагменты по релевантности и applicability"
                    technology "Cross-encoder / deterministic filters"
                }
                contextAssembler = component "RAG Context Assembler" {
                    description "Формирует компактный контекст с цитатами, policy_id, версией и effective dates"
                    technology "Structured context"
                }
                rulesEngine = component "Policy Rules Engine" {
                    description "Проверяет лимиты, допустимые классы, бюджет, визы и необходимость согласования"
                    technology "JSON Rules / Python"
                }
                explanationBuilder = component "Policy Explanation Builder" {
                    description "Возвращает decision, policy_id, версию, пункт и цитату для аудита"
                    technology "Structured decision"
                }

                documentIngestor -> documentChunker "Передаёт извлечённый текст и metadata"
                documentChunker -> embeddingGenerator "Передаёт нормализованные chunks"
                embeddingGenerator -> policyIndexer "Индексирует embeddings"
                policyIndexer -> policyRetriever "Предоставляет keyword/vector index"
                policyRetriever -> reranker "Передаёт кандидатов"
                reranker -> contextAssembler "Передаёт релевантные fragments"
                contextAssembler -> rulesEngine "Передаёт RAG-контекст с provenance"
                policyRetriever -> rulesEngine "Передаёт применимые нормы"
                rulesEngine -> explanationBuilder "Формирует объяснение решения"
            }
            policyStore = container "Policy Knowledge Base" {
                description "Версионированное хранилище исходных документов, chunks, embeddings и metadata с provenance"
                technology "Object Storage + PostgreSQL/pgvector"
            }
            agents = container "Travel Agent Workers" {
                description "Специализированные агенты поиска, бронирования, отмены/возврата и перепланирования; финансовые операции делегируются детерминированным сервисам"
                technology "Python / LangGraph workers"

                transportAgent = component "Transport Search Agent" {
                    description "Ищет авиабилеты и железнодорожные билеты, проверяет маршрут, багаж и возвратность"
                    technology "Provider adapter"
                }
                hotelAgent = component "Hotel Search Agent" {
                    description "Ищет отели по лимитам, датам, расположению и условиям отмены"
                    technology "Provider adapter"
                }
                transferAgent = component "Transfer Search Agent" {
                    description "Ищет трансфер и проверяет время стыковки с транспортом"
                    technology "Provider adapter"
                }
                visaInsuranceAgent = component "Visa & Insurance Agent" {
                    description "Определяет необходимость визы/страховки и подбирает услугу при применимости"
                    technology "Policy-aware worker"
                }
                bookingAgent = component "Booking Agent" {
                    description "Координирует выбранные offers, повторную проверку и запрос финального бронирования через Booking Service"
                    technology "LangGraph worker"
                }
                cancellationRefundAgent = component "Cancellation & Refund Agent" {
                    description "Готовит операцию отмены, объясняет штрафы и контролирует возврат через Booking Service и Finance System"
                    technology "LangGraph worker"
                }
                replanningAgent = component "Replanning Agent" {
                    description "Анализирует причину сбоя, меняет ограничения и запускает повторный поиск или согласование"
                    technology "LangGraph worker"
                }
                availabilityChecker = component "Availability Checker" {
                    description "Повторно проверяет цену, остаток мест, правила тарифа и TTL hold"
                    technology "Provider adapter"
                }
                alternativeBuilder = component "Alternative Builder" {
                    description "Комбинирует предложения в несколько сопоставимых вариантов с полной стоимостью и рисками"
                    technology "Deterministic scoring"
                }

                transportAgent -> availabilityChecker "Проверяет ticket offer"
                hotelAgent -> availabilityChecker "Проверяет hotel offer"
                transferAgent -> availabilityChecker "Проверяет transfer offer"
                visaInsuranceAgent -> availabilityChecker "Проверяет service offer"
                bookingAgent -> availabilityChecker "Повторно проверяет выбранные offers"
                replanningAgent -> alternativeBuilder "Запрашивает новые комбинации offers"
                cancellationRefundAgent -> bookingAgent "Получает данные оформленной поездки"
                availabilityChecker -> alternativeBuilder "Передаёт доступные offers"
            }
            booking = container "Booking & Compensation Service" {
                description "Единый шлюз бронирований, hold, оплаты, отмены и компенсирующих действий"
                technology "Python / REST / Saga"

                holdManager = component "Hold Manager" {
                    description "Создаёт и отслеживает временную фиксацию предложения и TTL"
                    technology "Redis / provider APIs"
                }
                reservationExecutor = component "Reservation Executor" {
                    description "Выполняет идемпотентное финальное бронирование и оплату"
                    technology "REST adapters"
                }
                bookingStatusTracker = component "Booking Status Tracker" {
                    description "Обрабатывает polling/webhooks и устраняет неизвестный статус брони"
                    technology "Events / webhooks"
                }
                compensationManager = component "Compensation Manager" {
                    description "Отменяет уже созданные части брони при partial booking"
                    technology "Saga compensations"
                }
                cancellationManager = component "Cancellation Manager" {
                    description "Отменяет подтверждённые брони и запускает возврат денежных средств"
                    technology "REST adapters"
                }

                holdManager -> reservationExecutor "Передаёт действующий hold"
                reservationExecutor -> bookingStatusTracker "Передаёт booking request"
                bookingStatusTracker -> compensationManager "Partial/unknown booking"
                cancellationManager -> bookingStatusTracker "Отслеживает возврат"
            }
            caseStore = container "Trip Case & Audit Store" {
                description "Хранит TripCase, версии политик, согласования, альтернативы, брони и неизменяемый audit trail"
                technology "PostgreSQL / object storage"
            }
            llmGateway = container "LLM Gateway" {
                description "Единый безопасный клиент LLM с JSON Schema, redaction, лимитами и выбором провайдера"
                technology "Python / OpenAI-compatible client"
            }
            notificationAdapter = container "Notification Adapter" {
                description "Отправляет вопросы, варианты, статусы брони, документы и результаты отмены"
                technology "Email / messenger adapters"
            }

            portal -> orchestrator "Создаёт кейс, отвечает на вопросы, выбирает/подтверждает вариант" "HTTPS/JSON"
            orchestrator -> policy "Получает нормы и решения" "REST"
            orchestrator -> agents "Запускает параллельные поисковые задачи" "Internal API"
            orchestrator -> booking "Выполняет hold, бронирование и отмену" "REST"
            orchestrator -> caseStore "Сохраняет состояние и аудит" "SQL"
            orchestrator -> llmGateway "Извлекает смысл и формирует вопросы/объяснения" "Internal API"
            orchestrator -> notificationAdapter "Запрашивает уведомления" "Internal API"
            policy -> policySource "Ingestion: получает новые и изменённые документы" "HTTPS/API"
            policy -> policyStore "Сохраняет chunks, embeddings, версии и provenance; runtime retrieval" "SQL/vector/object API"
            policyAdmin -> policy "Публикует и активирует версии правил" "HTTPS"
            agents -> travelProviders "Ищут и проверяют offers" "HTTPS/API"
            booking -> travelProviders "Hold, book, cancel, refund" "HTTPS/API"
            booking -> financeSystem "Проверяет/резервирует/возвращает бюджет" "HTTPS/API"
            notificationAdapter -> notification "Отправляет уведомления" "HTTPS/API"
            notificationAdapter -> documentSystem "Передаёт документы" "HTTPS/API"
            llmGateway -> llmProvider "Вызывает LLM без необезличенных ПДн" "HTTPS"
            employee -> portal "Описывает и подтверждает командировку"
            manager -> portal "Согласует командировку"
            finance -> portal "Согласует бюджет"
            travelManager -> portal "Обрабатывает исключение"
            identity -> portal "Аутентификация и контекст пользователя" "OIDC"
        }
    }

    views {
        systemLandscape "C1-Context" {
            title "C1 — System Context: автоматическое оформление командировок"
            include employee
            include manager
            include finance
            include travelManager
            include policyAdmin
            include travel
            include identity
            include policySource
            include travelProviders
            include financeSystem
            include notification
            include documentSystem
            include llmProvider
            autoLayout lr
        }
        container travel "C2-Containers" {
            title "C2 — Containers: Business Travel Automation"
            include *
            autoLayout lr
        }
        component orchestrator "C3-Orchestrator" {
            title "C3 — Components: LangGraph Orchestrator"
            include *
            autoLayout lr
        }
        component policy "C3-Policy" {
            title "C3 — Components: Policy Knowledge & Decision Service"
            include *
            autoLayout lr
        }
        component agents "C3-Agents" {
            title "C3 — Components: Travel Agent Workers"
            include *
            autoLayout lr
        }
        component booking "C3-Booking" {
            title "C3 — Components: Booking & Compensation Service"
            include *
            autoLayout lr
        }
        dynamic travel "D1-BookingJourney" {
            title "Dynamic View — Оформление командировки"
            employee -> portal "1. Отправляет свободный запрос"
            portal -> orchestrator "2. Создаёт TripCase"
            orchestrator -> llmGateway "3. Извлекает параметры"
            orchestrator -> policy "4. Находит и применяет действующие нормы"
            orchestrator -> portal "5. Задаёт уточняющие вопросы"
            employee -> portal "6. Отвечает на вопросы"
            orchestrator -> policy "7. Проверяет бюджет и согласования"
            manager -> portal "8. Согласует при необходимости"
            orchestrator -> agents "9. Запускает параллельный поиск"
            agents -> travelProviders "10. Ищут и проверяют offers"
            agents -> orchestrator "11. Возвращают альтернативы"
            orchestrator -> portal "12. Показывает варианты"
            employee -> portal "13. Подтверждает вариант"
            orchestrator -> booking "14. Повторно проверяет и бронирует"
            booking -> travelProviders "15. Hold и финальное оформление"
            booking -> financeSystem "16. Резервирует бюджет"
            orchestrator -> notificationAdapter "17. Отправляет подтверждение и документы"
            autoLayout lr
        }
        dynamic travel "D2-Replanning" {
            title "Dynamic View — Перепланирование после сбоя"
            booking -> orchestrator "1. Возвращает timeout, price change или partial booking"
            orchestrator -> booking "2. Запускает компенсацию уже созданных броней"
            booking -> travelProviders "3. Отменяет частичные брони"
            orchestrator -> policy "4. Повторно проверяет правила при изменении условий"
            orchestrator -> agents "5. Повторяет поиск недостающих частей"
            agents -> orchestrator "6. Возвращает новые альтернативы"
            orchestrator -> portal "7. Запрашивает новый выбор"
            autoLayout lr
        }
        dynamic travel "D3-PolicyIngestion" {
            title "Dynamic View — Наполнение RAG нормативными документами"
            policyAdmin -> policy "1. Публикует новую версию документа"
            policy -> policySource "2. Получает исходный документ и metadata"
            policy -> policyStore "3. Сохраняет chunks, embeddings и provenance"
            autoLayout lr
        }
        styles {
            element "Person" {
                shape person
                background #08427b
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Component" {
                background #85bbf0
                color #1a1a1a
            }
        }
    }
}