# Руководство по реализации аналога в BormoClass (Implementation Blueprint)

Этот документ описывает, как в проекте **BormoClass** реализован полноценный **self-hosted open source аналог Google Classroom**, объединяющий классический LMS-функционал Google Класса со встроенной интерактивной школьной доской (автономная замена Google Jamboard) и стандартом приватности Zero-PII (152-ФЗ РФ).

---

## 1. Концепция интерфейса: 4 ключевые вкладки курса

В Google Classroom структура любого курса строится вокруг 4 стандартных экранов, которые интуитивно понятны миллионам преподавателей и учащихся:

```
┌────────────────────────────────────────────────────────────────────────┐
│  [Курс: Физика 9Б]     [ 1. Лента ]  [ 2. Задания ]  [ 3. Люди ]  [ 4. Оценки ] │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Лента (Stream):**
   - Баннер курса (название, раздел, код курса с кнопкой быстрого копирования).
   - Виджет «Срок сдачи: Ближайшие задания» (для учеников — что сдать сегодня/завтра; для учителя — что требует проверки).
   - Поле «Опубликовать запись для класса» (с прикреплением файлов/досок).
   - Хронологическая лента объявлений и автоматических уведомлений о новых заданиях с комментариями.

2. **Задания (Classwork):**
   - Кнопка действия **«+ Создать»** (доступна только учителям):
     - *Задание* (с баллами, дедлайном, прикреплением шаблона интерактивной доски).
     - *Вопрос* (быстрый опрос/дискуссия).
     - *Материал* (конспект, видео, справочник).
     - *Тема* (создание нового раздела).
     - *Использовать повторно* (копирование задания из другого класса).
   - Список заданий, сгруппированных по темам (`Topics`) с возможностью drag-and-drop сортировки.

3. **Люди (People):**
   - Блок «Преподаватели»: список учителей + кнопка «Пригласить преподавателя».
   - Блок «Учащиеся»: счетчик учеников, кнопка «Пригласить учащихся», код курса, список учеников с аватарками и действиями (исключить, отправить письмо, заблокировать комментарии).

4. **Оценки (Grades / Журнал):**
   - Матричная таблица (Gradebook):
     - Строки: Ученики (с алфавитной сортировкой).
     - Колонки: Опубликованные задания с указанием максимального балла и даты.
     - Ячейки: Статус сдачи (`Сдано`, `Не сдано`, `Черновик оценки`, `Выставленный балл`).
     - Столбец «Общий средний балл» (с учетом весов категорий, если включено).

---

## 2. Уникальная фича BormoClass: Интеграция с Whiteboard (Интерактивной доской)

В оригинальном Google Classroom материалы часто прикрепляются из Google Docs/Drive. В BormoClass в качестве киллер-фичи выступает **встроенная интерактивная онлайн-доска**:

### Сценарий использования:
1. **Шаблон доски для каждого ученика («Создать копию для каждого учащегося»):**
   - Преподаватель готовит доску с условиями задач, схемами или чертежами.
   - При создании задания выбирает: *«Интерактивная доска: создать персональную копию для каждого ученика»*.
   - При открытии задания ученик получает свой независимый экземпляр доски (`board_id`).
2. **Блокировка редактирования при сдаче (`TURNED_IN`):**
   - Как только ученик нажимает кнопку «Сдать работу», сервер BormoClass переводит его права на доску в режим `READ_ONLY`.
   - Преподаватель открывает сданную доску ученика, делает пометки красным маркером, оставляет стикеры с комментариями и выставляет балл.
3. **Возврат на доработку (`RETURNED`):**
   - Преподаватель нажимает «Вернуть», права редактирования возвращаются ученику, и он исправляет ошибки прямо на доске.

---

## 3. Рекомендуемая схема базы данных (SQLAlchemy / SQLite / PostgreSQL)

```python
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SQLEnum, Table
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class CourseState(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    PROVISIONED = "PROVISIONED"

class CourseRole(str, Enum):
    OWNER = "OWNER"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"

class WorkType(str, Enum):
    ASSIGNMENT = "ASSIGNMENT"
    QUESTION = "QUESTION"
    MATERIAL = "MATERIAL"

class SubmissionState(str, Enum):
    NEW = "NEW"
    CREATED = "CREATED"
    TURNED_IN = "TURNED_IN"
    RETURNED = "RETURNED"
    RECLAIMED = "RECLAIMED_BY_STUDENT"


class Course(Base):
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    section = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    room = Column(String(100), nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    enrollment_code = Column(String(16), unique=True, index=True, nullable=False)
    state = Column(SQLEnum(CourseState), default=CourseState.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = relationship("CourseMember", back_populates="course", cascade="all, delete-orphan")
    topics = relationship("Topic", back_populates="course", cascade="all, delete-orphan")
    works = relationship("CourseWork", back_populates="course", cascade="all, delete-orphan")
    announcements = relationship("Announcement", back_populates="course", cascade="all, delete-orphan")


class CourseMember(Base):
    __tablename__ = "course_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    role = Column(SQLEnum(CourseRole), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="members")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String(36), primary_key=True)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False)
    name = Column(String(255), nullable=False)
    position = Column(Integer, default=0)

    course = relationship("Course", back_populates="topics")
    works = relationship("CourseWork", back_populates="topic")


class CourseWork(Base):
    __tablename__ = "course_works"

    id = Column(String(36), primary_key=True)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False)
    topic_id = Column(String(36), ForeignKey("topics.id"), nullable=True)
    creator_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    work_type = Column(SQLEnum(WorkType), default=WorkType.ASSIGNMENT)
    max_points = Column(Float, default=100.0)
    due_date = Column(DateTime, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Интеграция с доской: если задана, копируется каждому ученику
    template_board_id = Column(String(64), nullable=True)

    course = relationship("Course", back_populates="works")
    topic = relationship("Topic", back_populates="works")
    submissions = relationship("StudentSubmission", back_populates="course_work", cascade="all, delete-orphan")


class StudentSubmission(Base):
    __tablename__ = "student_submissions"

    id = Column(String(36), primary_key=True)
    course_work_id = Column(String(36), ForeignKey("course_works.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    state = Column(SQLEnum(SubmissionState), default=SubmissionState.NEW)
    draft_grade = Column(Float, nullable=True)
    assigned_grade = Column(Float, nullable=True)
    is_late = Column(Boolean, default=False)
    board_id = Column(String(64), nullable=True) # Персональная доска ученика
    text_content = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    returned_at = Column(DateTime, nullable=True)

    course_work = relationship("CourseWork", back_populates="submissions")
```

---

## 4. Спецификация REST API для BormoClass (FastAPI)

### 4.1. Управление курсами (`/api/v1/courses`)
- `GET /api/v1/courses` — список курсов пользователя (активные / архивные).
- `POST /api/v1/courses` — создание курса (автогенерация `enrollment_code`).
- `GET /api/v1/courses/{course_id}` — информация о курсе, настройки.
- `PATCH /api/v1/courses/{course_id}` — редактирование (название, аудитория).
- `POST /api/v1/courses/{course_id}/archive` — архивация курса.
- `POST /api/v1/courses/join` — вступление в курс по `enrollment_code`.

### 4.2. Участники (`/api/v1/courses/{course_id}/members`)
- `GET /api/v1/courses/{course_id}/members` — список преподавателей и студентов.
- `POST /api/v1/courses/{course_id}/invite` — приглашение участника по email.
- `DELETE /api/v1/courses/{course_id}/members/{user_id}` — исключение участника.

### 4.3. Задания и материалы (`/api/v1/courses/{course_id}/works`)
- `GET /api/v1/courses/{course_id}/works` — список всех тем и заданий (для вкладки «Задания»).
- `POST /api/v1/courses/{course_id}/works` — создание задания (автосоздание сабмишенов для всех студентов).
- `GET /api/v1/courses/{course_id}/works/{work_id}` — детальный просмотр задания.
- `PATCH /api/v1/courses/{course_id}/works/{work_id}` — обновление параметров, баллов, дедлайна.
- `DELETE /api/v1/courses/{course_id}/works/{work_id}` — удаление задания.

### 4.4. Сдача и оценивание (`/api/v1/courses/{course_id}/works/{work_id}/submissions`)
- `GET /api/v1/courses/{course_id}/works/{work_id}/submissions` — сводная таблица сдачи задания (для преподавателя).
- `GET /api/v1/courses/{course_id}/works/{work_id}/my-submission` — просмотр своей сдачи (для ученика).
- `POST /api/v1/courses/{course_id}/works/{work_id}/turn-in` — ученик нажимает «Сдать» (проверка дедлайна, расчет `is_late`, блокировка доски).
- `POST /api/v1/courses/{course_id}/works/{work_id}/reclaim` — ученик отменяет отправку для правок.
- `PATCH /api/v1/courses/{course_id}/works/{work_id}/submissions/{submission_id}` — выставление `draft_grade` преподавателем.
- `POST /api/v1/courses/{course_id}/works/{work_id}/submissions/{submission_id}/return` — перенос `draft_grade` в `assigned_grade`, возврат работы.

### 4.5. Журнал оценок (`/api/v1/courses/{course_id}/gradebook`)
- `GET /api/v1/courses/{course_id}/gradebook` — матричные данные: студенты, все задания курса и выставленные оценки.
