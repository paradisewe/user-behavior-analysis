-- 复购分析
WITH user_buy AS (
    SELECT user_id, COUNT(*) AS buy_cnt
    FROM user_behavior
    WHERE behavior_type = 'buy'
    GROUP BY user_id
)
SELECT
    COUNT(*)                              AS total_buyers,
    COUNT(*) FILTER (WHERE buy_cnt >= 2)  AS repurchase_users,
    ROUND(
        COUNT(*) FILTER (WHERE buy_cnt >= 2)::DOUBLE / COUNT(*),
        4
    )                                     AS repurchase_rate
FROM user_buy;