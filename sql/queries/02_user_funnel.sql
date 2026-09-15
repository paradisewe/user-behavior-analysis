-- 用户级漏斗：只要用户曾经有过该行为即计入
WITH user_flags AS (
    SELECT
        user_id,
        MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy
    FROM user_behavior
    GROUP BY user_id
)
SELECT 'pv'   AS stage, SUM(has_pv)   AS users, 1.0000 AS conversion FROM user_flags
UNION ALL
SELECT 'fav',  SUM(has_fav),  ROUND(SUM(has_fav)::DOUBLE  / NULLIF(SUM(has_pv), 0), 4) FROM user_flags
UNION ALL
SELECT 'cart', SUM(has_cart), ROUND(SUM(has_cart)::DOUBLE / NULLIF(SUM(has_pv), 0), 4) FROM user_flags
UNION ALL
SELECT 'buy',  SUM(has_buy),  ROUND(SUM(has_buy)::DOUBLE  / NULLIF(SUM(has_pv), 0), 4) FROM user_flags;