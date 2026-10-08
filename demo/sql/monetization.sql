WITH eligible AS (
    SELECT CASE WHEN signup_date < '2026-03-01' THEN 'pre_1.3' ELSE 'post_1.3' END AS cohort_period,
           COUNT(*) AS players
    FROM players
    GROUP BY 1
), revenue AS (
    SELECT CASE WHEN p.signup_date < '2026-03-01' THEN 'pre_1.3' ELSE 'post_1.3' END AS cohort_period,
           COUNT(DISTINCT t.player_id) AS payers,
           COUNT(*) AS transactions,
           ROUND(SUM(t.amount_usd), 2) AS revenue_usd
    FROM payments t
    JOIN players p USING (player_id)
    GROUP BY 1
)
SELECT e.cohort_period, e.players, COALESCE(r.payers, 0) AS payers,
       ROUND(1.0 * COALESCE(r.payers, 0) / e.players, 4) AS payer_conversion,
       COALESCE(r.transactions, 0) AS transactions, COALESCE(r.revenue_usd, 0) AS revenue_usd,
       ROUND(1.0 * COALESCE(r.revenue_usd, 0) / e.players, 2) AS arpu_usd,
       CASE WHEN r.payers > 0 THEN ROUND(1.0 * r.revenue_usd / r.payers, 2) END AS arppu_usd
FROM eligible e LEFT JOIN revenue r USING (cohort_period)
ORDER BY e.cohort_period;
