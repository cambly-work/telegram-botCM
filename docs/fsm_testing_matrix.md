# Матрица FSM-сценариев и проверка

## RegistrationStates
| Состояние | Триггер/действие | Следующее состояние | Ожидаемый ответ | Шаги проверки |
|-----------|------------------|---------------------|-----------------|---------------|
| `None` → `waiting_email` | Пользователь запускает `/start`, в профиле отсутствует email | `RegistrationStates.waiting_email` | «Укажи email для связи» | Проверено unit-тестом `test_registration_smoke_flow`: после запуска `/start` без email состояние `waiting_email`, отправлен локализованный текст. 【F:handlers/__init__.py†L6799-L6821】【F:tests/test_fsm_smoke.py†L119-L175】 |
| `None` → `waiting_phone` | Пользователь запускает `/start`, email заполнен, телефона нет | `RegistrationStates.waiting_phone` | «Укажи номер телефона» | Покрыто unit-тестом `test_registration_smoke_flow`: после пропуска email состояние переключается на `waiting_phone`. 【F:handlers/__init__.py†L6823-L6845】【F:tests/test_fsm_smoke.py†L139-L158】 |
| `waiting_email` (валидный email) | Ответ с корректным email | `RegistrationStates.waiting_phone` | «Укажи номер телефона» | Проверено в `test_registration_smoke_flow`: после валидного email состояние `waiting_phone`. 【F:handlers.py†L6268-L6287】【F:tests/test_fsm_smoke.py†L162-L174】 |
| `waiting_email` (невалидный email) | Ответ с ошибочным email | `RegistrationStates.waiting_email` | «Формат неверный. Пример: name@mail.com» | Проверено в `test_registration_smoke_flow`: состояние не меняется, сообщение о валидации. 【F:handlers.py†L6272-L6277】【F:tests/test_fsm_smoke.py†L157-L160】 |
| `waiting_phone` (валидный номер) | Ответ с корректным телефоном | `None` | Сообщение о завершении регистрации и клавиатура меню | Проверено в `test_registration_smoke_flow`: состояние очищается, отправлен финальный текст. 【F:handlers.py†L6290-L6313】【F:tests/test_fsm_smoke.py†L171-L175】 |
| `waiting_phone` (невалидный номер) | Ответ с ошибочным телефоном | `RegistrationStates.waiting_phone` | «Формат неверный. Пример: +79991234567» | Проверено в `test_registration_smoke_flow`: состояние не меняется, сообщение о валидации. 【F:handlers.py†L6294-L6299】【F:tests/test_fsm_smoke.py†L166-L170】 |

## HWStates
| Состояние | Триггер/действие | Следующее состояние | Ожидаемый ответ | Шаги проверки |
|-----------|------------------|---------------------|-----------------|---------------|
| `waiting_answer` | Ответ на домашнее задание | `HWStates.waiting_feedback` | Подтверждение и запрос оценки урока | Проверено smoke-тестом `test_hw_answer_to_feedback_transition`. 【F:handlers.py†L6354-L6385】【F:tests/test_fsm_smoke.py†L178-L197】 |
| `waiting_feedback` | Выбор оценки/текстовый отзыв | `None` | Благодарность и клавиатура «После урока» | Проверено в `test_hw_feedback_custom_text`. 【F:handlers.py†L6390-L6419】【F:tests/test_fsm_smoke.py†L200-L218】 |
| `waiting_question` | Отправка вопроса по уроку | `None` и `last_lesson` обновлён | Подтверждение с каналом поддержки, уведомление админов | Проверено тестом `test_notify_admins_error_path_keeps_flow`. 【F:handlers.py†L7419-L7465】【F:tests/test_fsm_smoke.py†L292-L312】 |

## BroadcastStates
| Состояние | Триггер/действие | Следующее состояние | Ожидаемый ответ | Шаги проверки |
|-----------|------------------|---------------------|-----------------|---------------|
| `waiting_confirm` + кнопка «Изменить текст» | `EDIT_BROADCAST_BUTTON` | `BroadcastStates.waiting_body` | Запрос нового текста рассылки | Проверено в `test_admin_broadcast_edit_transition`. 【F:handlers.py†L12248-L12261】【F:tests/test_fsm_smoke.py†L315-L329】 |
| `waiting_confirm` + кнопка «Изменить сегмент» | `CHANGE_BROADCAST_SEGMENT_BUTTON` | `BroadcastStates.waiting_segment` | Запрос выбора сегмента | Smoke-проверка `test_admin_broadcast_change_segment_transition`. 【F:handlers.py†L12282-L12289】【F:tests/test_fsm_smoke.py†L332-L343】 |
| `waiting_template_title` | Название шаблона | `BroadcastStates.waiting_confirm` | Сообщение «Шаблон сохранён ✅» и клавиатура подтверждения | Проверено тестом `test_admin_broadcast_save_template_transition`. 【F:handlers.py†L12292-L12331】【F:tests/test_fsm_smoke.py†L347-L370】 |

## Проверка уведомлений и отмен
- Отправка заявки на тестирование (`test_collect_name`) уведомляет админов и завершается клавиатурой меню — покрыто тестом `test_notify_admins_on_test_request`. 【F:handlers.py†L7088-L7178】【F:tests/test_fsm_smoke.py†L222-L265】
- Отмена заявки в состояниях TestStates отправляет уведомление об отмене — проверено в `test_notify_admins_on_test_cancel`. 【F:handlers.py†L7545-L7603】【F:tests/test_fsm_smoke.py†L268-L289】
- Ошибка отправки уведомления по вопросу урока не ломает сценарий — проверено в `test_notify_admins_error_path_keeps_flow`. 【F:handlers.py†L7435-L7465】【F:tests/test_fsm_smoke.py†L292-L312】

## Дополнительные шаги проверки
1. Запустить `pytest tests/test_fsm_smoke.py` для smoke-проверки ключевых переходов и уведомлений.
2. При изменениях сценариев обновлять таблицу и покрытие тестами, чтобы фиксации состояний оставались в актуальном состоянии.
3. Вручную проверить локализованные тексты при необходимости, опираясь на подсказки в матрице и тестах. 【F:tests/test_fsm_smoke.py†L77-L370】
