-- 用户-商品级漏斗：真实转化效率
WITH first_times AS (
    SELECT
        user_id,
        item_id,
        MIN(CASE WHEN behavior_type = 'pv'   THEN timestamp END) AS t_pv,
        MIN(CASE WHEN behavior_type = 'cart' THEN timestamp END) AS t_cart,
        MIN(CASE WHEN behavior_type = 'buy'  THEN timestamp END) AS t_buy
    FROM user_behavior
    GROUP BY user_id, item_id
)
SELECT
    COUNT(*)                                                          AS user_item_pairs,
    COUNT(*) FILTER (WHERE t_pv IS NOT NULL)                          AS viewed_pairs,
    COUNT(*) FILTER (WHERE t_cart IS NOT NULL AND t_cart >= t_pv)     AS pv_to_cart_pairs,
    COUNT(*) FILTER (WHERE t_buy  IS NOT NULL AND t_buy  >= t_pv)     AS pv_to_buy_pairs,
    COUNT(*) FILTER (WHERE t_buy  IS NOT NULL AND t_buy  >= t_cart)   AS cart_to_buy_pairs,
    ROUND(
        COUNT(*) FILTER (WHERE t_cart IS NOT NULL AND t_cart >= t_pv)::DOUBLE
        / NULLIF(COUNT(*) FILTER (WHERE t_pv IS NOT NULL), 0), 4
    )                                                                  AS pv_to_cart_rate,
    ROUND(
        COUNT(*) FILTER (WHERE t_buy IS NOT NULL AND t_buy >= t_pv)::DOUBLE
        / NULLIF(COUNT(*) FILTER (WHERE t_pv IS NOT NULL), 0), 4
    )                                                                  AS pv_to_buy_rate,
    ROUND(
        COUNT(*) FILTER (WHERE t_buy IS NOT NULL AND t_buy >= t_cart)::DOUBLE
        / NULLIF(COUNT(*) FILTER (WHERE t_cart IS NOT NULL), 0), 4
    )                                                                  AS cart_to_buy_rate
FROM first_times;