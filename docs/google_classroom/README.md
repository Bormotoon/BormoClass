# Официальная документация и архитектурная спецификация Google Classroom

Данный каталог содержит полный комплект официальной документации Google Classroom API v1, руководств разработчика Google Workspace, а также подробную архитектурную спецификацию и схемы данных для реализации аналога в проекте **BormoClass**.

---

## 📁 Структура каталога

```
docs/google_classroom/
├── README.md                                  # Этот файл-навигатор
├── discovery/
│   └── classroom_v1.json                      # Полная официальная схема Google API Discovery v1 (85 схем)
├── architecture/                              # Архитектурная спецификация для BormoClass
│   ├── 01_ENTITIES_AND_RELATIONSHIPS.md       # ERD-диаграмма и реестр всех сущностей (Course, CourseWork, Submission...)
│   ├── 02_LIFECYCLES_AND_WORKFLOWS.md         # Жизненные циклы и стейт-машины (сдача работ, опоздания, оценивание)
│   ├── 03_ROLES_AND_PERMISSIONS.md            # Матрица ролей и прав доступа (RBAC)
│   └── 04_BORMOCLASS_ANALOG_BLUEPRINT.md      # Руководство по реализации в BormoClass (SQLAlchemy, FastAPI, Whiteboard)
├── reference/
│   ├── schemas.md                             # Справочник всех 85 схем и полей данных Google Classroom API
│   └── endpoints.md                           # Справочник всех REST ресурсов, методов и путей API
└── guides/                                    # Скачанные официальные руководства Google Developer
    ├── get-started.md                         # Введение в Classroom API
    ├── api-structure.md                       # Иерархия ресурсов и структура API
    ├── user-types.md                          # Типы пользователей, роли и права
    ├── admin-actions.md                       # Действия школьных администраторов
    ├── grades-concepts.md                     # Концепции оценивания и категории
    ├── manage-courses.md                      # Управление курсами и их состояниями
    ├── manage-coursework.md                   # Управление заданиями, материалами и вопросами
    ├── manage-users.md                        # Управление преподавателями и учениками
    ├── manage-topics.md                       # Управление темами и структурирование курса
    ├── manage-grades.md                       # Управление оценками и периодами
    ├── coursework-integration.md              # Интеграция сдачи работ (Submissions)
    ├── manage-student-groups.md               # Группы учащихся и дифференцированные задания
    ├── manage-guardians.md                    # Управление опекунами/родителями
    ├── manage-invitations.md                  # Приглашения в курсы
    ├── manage-learning-goals.md               # Учебные цели и стандарты
    ├── manage-aliases.md                      # Псевдонимы курсов
    ├── authentication.md                      # Аутентификация и скоупы
    ├── how-requests-work.md                   # Особенности HTTP запросов и масок полей
    ├── prerequisites.md                       # Требования к окружению
    └── user-eligibility.md                    # Проверка прав и доступности фичей для пользователей
```

---

## 🚀 С чего начать изучение для разработки BormoClass?

1. **[Архитектура сущностей и ERD-диаграмма](architecture/01_ENTITIES_AND_RELATIONSHIPS.md)** — чтобы увидеть связи между курсами, темами, заданиями и сдачами.
2. **[Жизненные циклы и стейт-машины](architecture/02_LIFECYCLES_AND_WORKFLOWS.md)** — ключевой документ: как устроен конечный автомат сдачи работ учеником (`NEW` -> `CREATED` -> `TURNED_IN` -> `RETURNED` -> `RECLAIMED`), как рассчитывается признак опоздания (`late`), как работают черновики оценок.
3. **[Руководство по реализации аналога в BormoClass](architecture/04_BORMOCLASS_ANALOG_BLUEPRINT.md)** — готовые модели SQLAlchemy, проектирование 4 вкладок («Лента», «Задания», «Люди», «Оценки») и сценарий интеграции с интерактивной доской BormoClass Whiteboard.
4. **[Справочник схем](reference/schemas.md)** и **[Справочник эндпоинтов](reference/endpoints.md)** — быстрый доступ к любому названию поля, типам и спецификации API Google Classroom.
