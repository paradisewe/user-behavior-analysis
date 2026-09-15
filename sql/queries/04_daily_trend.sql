-- 每日 DAU 与购买趋势
WITH daily AS (
    SELECT
        DATE_TRUNC('day', TO_TIMESTAMP(timestamp))::DATE AS date,
        COUNT(DISTINCT user_id)                          AS dau
    FROM user_behavior
    GROUP BY 1
),
daily_buy AS (
    SELECT
        DATE_TRUNC('day', TO_TIMESTAMP(timestamp))::DATE AS date,
        COUNT(*)                                         AS buy_count,
        COUNT(DISTINCT user_id)                          AS buy_users
    FROM user_behavior
    WHERE behavior_type = 'buy'
    GROUP BY 1
)
SELECT
    d.date,
    d.dau,
    COALESCE(b.buy_count, 0) AS buy_count,
    COALESCE(b.buy_users, 0) AS buy_users
FROM daily d
LEFT JOIN daily_buy b USING (date)
ORDER BY d.date;