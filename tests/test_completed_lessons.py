import sqlite3
from collections import defaultdict


def calculate_completed_4of4(connection: sqlite3.Connection) -> int:
    query = """
        SELECT COUNT(*) AS c
        FROM (
            SELECT user_id
            FROM funnel_progress
            WHERE hw_status = 'submitted'
            GROUP BY user_id
            HAVING COUNT(DISTINCT CASE
                WHEN lesson_num BETWEEN 1 AND 4 THEN lesson_num
            END) = 4
        ) AS completed
    """
    cursor = connection.execute(query)
    row = cursor.fetchone()
    return row[0] if row else 0


def test_completed_lessons_query_matches_manual_count():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE funnel_progress (user_id INTEGER, lesson_num INTEGER, hw_status TEXT)"
    )

    sample_rows = [
        (1, 1, "submitted"),
        (1, 2, "submitted"),
        (1, 3, "submitted"),
        (1, 4, "submitted"),  # user 1 -> counted
        (2, 1, "submitted"),
        (2, 2, "submitted"),
        (2, 3, "submitted"),  # user 2 missing lesson 4 -> not counted
        (3, 1, "submitted"),
        (3, 2, "submitted"),
        (3, 3, "submitted"),
        (3, 4, "pending"),  # user 3 has non-submitted lesson -> not counted
        (4, 1, "submitted"),
        (4, 2, "submitted"),
        (4, 3, "submitted"),
        (4, 4, "submitted"),
        (4, 5, "submitted"),  # lesson outside 1-4 shouldn't affect count
        (5, 1, "submitted"),
        (5, 2, "submitted"),
        (5, 3, "submitted"),
        (5, 4, "submitted"),
    ]  # user 4 and 5 -> counted

    conn.executemany(
        "INSERT INTO funnel_progress (user_id, lesson_num, hw_status) VALUES (?, ?, ?)",
        sample_rows,
    )

    sql_result = calculate_completed_4of4(conn)

    # manual calculation for comparison
    lessons_by_user: dict[int, set[int]] = defaultdict(set)
    for user_id, lesson_num, status in sample_rows:
        if status == "submitted" and 1 <= lesson_num <= 4:
            lessons_by_user[user_id].add(lesson_num)

    manual_count = sum(1 for lessons in lessons_by_user.values() if len(lessons) == 4)

    assert sql_result == manual_count == 3


if __name__ == "__main__":
    test_completed_lessons_query_matches_manual_count()
    print("All checks passed.")
