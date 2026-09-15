-- 小时活跃度（按行为类型）
SELECT
    EXTRACT(HOUR FROM TO_TIMESTAMP(timestamp)) AS hour,
    behavior_type,
    COUNT(*)                                    AS cnt
FROM user_behavior
GROUP BY hour, behavior_type
ORDER BY hour, behavior_type;