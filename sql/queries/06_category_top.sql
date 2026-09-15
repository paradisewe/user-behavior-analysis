-- 购买量 TOP10 类目
SELECT
    category_id,
    COUNT(*)                AS buy_count,
    COUNT(DISTINCT user_id) AS buyer_count
FROM user_behavior
WHERE behavior_type = 'buy'
GROUP BY category_id
ORDER BY buy_count DESC
LIMIT 10;