# Руководство по ручной проверке админского раздела пользователей

## 1. Сценарии переходов состояний `AdminUserStates`

| Сценарий | Стартовое состояние | Действие | Новое состояние | Ожидаемые сообщения |
| --- | --- | --- | --- | --- |
| Выбор сегмента | `AdminUserStates.choosing_segment` | Админ нажимает на кнопку сегмента после перехода в раздел «📋 Управление участницами» | `AdminUserStates.browsing_users` | Бот показывает первую страницу списка участниц выбранного сегмента с пагинацией. 【F:handlers.py†L5414-L5435】 |
| Листание назад | `AdminUserStates.browsing_users` | Кнопка «⏪ Назад» при наличии предыдущей страницы | `AdminUserStates.browsing_users` | Обновлённый список, страница уменьшается на 1 (не меньше 1). 【F:handlers.py†L5438-L5448】 |
| Листание вперёд | `AdminUserStates.browsing_users` | Кнопка «⏩ Далее» до достижения последней страницы | `AdminUserStates.browsing_users` | Обновлённый список, страница увеличивается до `total_pages`. 【F:handlers.py†L5451-L5463】 |
| Открытие карточки | `AdminUserStates.browsing_users` | Нажатие на кнопку с именем участницы на текущей странице | `AdminUserStates.viewing_user` | Бот присылает карточку участницы с клавиатурой действий. 【F:handlers.py†L5466-L5475】 |
| Возврат к списку | `AdminUserStates.viewing_user` или `AdminUserStates.waiting_contacts` | Кнопка «🔙 К списку» | `AdminUserStates.browsing_users` | Возвращает список участниц на последней странице просмотра. 【F:handlers.py†L5478-L5489】 |
| Возврат к сегментам | Любое состояние (`choosing_segment`, `browsing_users`, `viewing_user`, `waiting_contacts`) | Кнопка «📂 Сегменты» | `AdminUserStates.choosing_segment` | Повторно выводится меню выбора сегмента. 【F:handlers.py†L5492-L5503】 |
| Выдача доступа | `AdminUserStates.viewing_user` или `AdminUserStates.waiting_contacts` | Кнопка «Выдать доступ» | `AdminUserStates.viewing_user` | Статус меняется на `member_active`, показывается уведомление «Доступ выдан ✅». 【F:handlers.py†L5506-L5529】 |
| Отзыв доступа | `AdminUserStates.viewing_user` или `AdminUserStates.waiting_contacts` | Кнопка «Отозвать доступ» | `AdminUserStates.viewing_user` | Статус меняется на `member_expired`, уведомление «Доступ отозван». 【F:handlers.py†L5532-L5551】 |
| Переход к обновлению контактов | `AdminUserStates.viewing_user` | Кнопка «Обновить контакты» | `AdminUserStates.waiting_contacts` | Пояснение о формате `email=`/`phone=` и клавиатура карточки. 【F:handlers.py†L5554-L5569】 |
| Сохранение контактов | `AdminUserStates.waiting_contacts` | Отправка строки с параметрами `email=` и/или `phone=` | `AdminUserStates.viewing_user` | Уведомление «Контакты обновлены», карточка пересобирается. 【F:handlers.py†L5572-L5633】 |

## 2. Ошибки при обновлении контактов и проверка логов

- Валидация email: при ошибке бот отвечает «email невалиден. Попробуй снова или вернись к карточке.» и остаётся в `waiting_contacts`. 【F:handlers.py†L5600-L5603】
- Валидация телефона: при ошибке бот отвечает «phone невалиден. Попробуй снова или вернись к карточке.» и остаётся в `waiting_contacts`. 【F:handlers.py†L5610-L5614】
- Отсутствие параметров: ответ «Не нашла данных для обновления. Укажи email=... и/или phone=...». 【F:handlers.py†L5619-L5621】

После успешных действий фиксируются записи в `admin_log`:

| Действие | Код события | Как проверить |
| --- | --- | --- |
| Выдача доступа | `set_paid` | `SELECT created_at, admin_id, payload FROM admin_log WHERE action = 'set_paid' ORDER BY created_at DESC LIMIT 10;` |
| Отзыв доступа | `revoke_access` | `SELECT created_at, admin_id, payload FROM admin_log WHERE action = 'revoke_access' ORDER BY created_at DESC LIMIT 10;` |
| Обновление контактов | `bind_contacts` | `SELECT created_at, admin_id, payload FROM admin_log WHERE action = 'bind_contacts' ORDER BY created_at DESC LIMIT 10;` |

Функция `log_admin_action` пишет события в таблицу и логирует результат через `logger`. 【F:handlers.py†L509-L530】【F:schema.sql†L252-L275】

## 3. Фикстуры для ручных проверок

Воспользуйтесь скриптом [`fixtures/admin_users_manual.sql`](../fixtures/admin_users_manual.sql) для наполнения таблицы `users` тестовыми данными. Он создаёт 5 пользователей с разными статусами и сроками доступа.

Пример загрузки (PostgreSQL):

```bash
psql "$DATABASE_URL" -f fixtures/admin_users_manual.sql
```

После загрузки можно использовать сегменты «Активные», «Истёкшие» и «Лиды» для отработки сценариев выдачи/отзыва доступа.

## 4. Шаги по выдаче/отзыву доступа и проверке профиля

1. Админ открывает категорию «👥 Пользователи» → пункт «📋 Управление участницами» → выбирает сегмент и нужную карточку.
2. Для выдачи доступа нажимает «Выдать доступ». Статус меняется на `member_active`, поле `access_until` заполняется значением 1 января 2030 года. 【F:handlers.py†L5512-L5524】
3. Для отзыва доступа нажимает «Отозвать доступ». Статус меняется на `member_expired`, `access_until` очищается. 【F:handlers.py†L5534-L5544】
4. Для проверки отображения статуса участница (или админ от её лица) открывает профиль командой `/profile` или через меню. В блоке «Статус» должна появиться подпись и строка о доступе согласно текущему состоянию. 【F:handlers.py†L2848-L2920】
5. Подтвердите, что в `admin_log` есть записи с соответствующими действиями (`set_paid`/`revoke_access`). 【F:handlers.py†L5524-L5528】【F:handlers.py†L5546-L5550】

> Примечание: для тестирования обновления контактов убедитесь, что уникальные индексы на email/phone позволяют сохранять уникальные значения. 【F:schema.sql†L45-L68】
