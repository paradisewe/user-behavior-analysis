-- 行为类型分布（全量）
SELECT
    behavior_type,
    COUNT(*)                                            AS cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 4)  AS pct
FROM user_behavior
GROUP BY behavior_type
ORDER BY cnt DESC;