WITH base AS (
    SELECT p.player_id,
           MAX(CASE WHEN e.event_name = 'companion_affinity_unlocked' THEN 1 ELSE 0 END) AS companion_adopter,
           MAX(CASE WHEN e.event_name = 'celestial_runway_joined' THEN 1 ELSE 0 END) AS runway_participant
    FROM players p LEFT JOIN gameplay_events e USING (player_id)
    WHERE p.signup_date <= '2026-05-01'
    GROUP BY p.player_id
), d30 AS (
    SELECT DISTINCT p.player_id
    FROM players p JOIN sessions s ON s.player_id = p.player_id
      AND s.session_date = date(p.signup_date, '+30 day')
)
SELECT companion_adopter, runway_participant, COUNT(*) AS players,
       SUM(CASE WHEN d30.player_id IS NOT NULL THEN 1 ELSE 0 END) AS d30_players,
       ROUND(1.0 * SUM(CASE WHEN d30.player_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 4) AS d30_retention
FROM base LEFT JOIN d30 USING (player_id)
GROUP BY companion_adopter, runway_participant
ORDER BY companion_adopter, runway_participant;
