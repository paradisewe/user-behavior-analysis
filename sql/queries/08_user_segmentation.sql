-- 用户行为深度分层
WITH user_depth AS (
    SELECT
        user_id,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav
    FROM user_behavior
    GROUP BY user_id
)
SELECT
    CASE
        WHEN has_buy  = 1 THEN '已购买'
        WHEN has_cart = 1 THEN '加购未购买'
        WHEN has_fav  = 1 THEN '仅收藏'
        ELSE '仅浏览'
    END                                                  AS behavior_depth,
    COUNT(*)                                             AS users,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2)   AS pct
FROM user_depth
GROUP BY 1
ORDER BY users DESC;