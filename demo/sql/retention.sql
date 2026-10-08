WITH eligible AS (
    SELECT
        player_id,
        signup_date,
        platform,
        CASE WHEN signup_date < '2026-03-01' THEN 'pre_1.3' ELSE 'post_1.3' END AS cohort_period
    FROM players
    WHERE signup_date <= '2026-05-01'
), activity AS (
    SELECT DISTINCT player_id, session_date FROM sessions
)
SELECT
    e.cohort_period,
    e.platform,
    COUNT(*) AS cohort_size,
    SUM(CASE WHEN d1.player_id IS NOT NULL THEN 1 ELSE 0 END) AS d1_players,
    ROUND(1.0 * SUM(CASE WHEN d1.player_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 4) AS d1_retention,
    SUM(CASE WHEN d7.player_id IS NOT NULL THEN 1 ELSE 0 END) AS d7_players,
    ROUND(1.0 * SUM(CASE WHEN d7.player_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 4) AS d7_retention,
    SUM(CASE WHEN d30.player_id IS NOT NULL THEN 1 ELSE 0 END) AS d30_players,
    ROUND(1.0 * SUM(CASE WHEN d30.player_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 4) AS d30_retention
FROM eligible e
LEFT JOIN activity d1 ON d1.player_id = e.player_id AND d1.session_date = date(e.signup_date, '+1 day')
LEFT JOIN activity d7 ON d7.player_id = e.player_id AND d7.session_date = date(e.signup_date, '+7 day')
LEFT JOIN activity d30 ON d30.player_id = e.player_id AND d30.session_date = date(e.signup_date, '+30 day')
GROUP BY e.cohort_period, e.platform
ORDER BY e.cohort_period, e.platform;
