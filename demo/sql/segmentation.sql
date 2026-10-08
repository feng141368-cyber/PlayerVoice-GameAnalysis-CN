SELECT s.patch_version, p.platform,
       COUNT(*) AS sessions,
       SUM(s.crashed) AS crashed_sessions,
       ROUND(1.0 * SUM(s.crashed) / COUNT(*), 4) AS crash_rate,
       ROUND(AVG(s.duration_minutes), 2) AS avg_session_minutes,
       COUNT(DISTINCT s.player_id) AS active_players
FROM sessions s JOIN players p USING (player_id)
GROUP BY s.patch_version, p.platform
ORDER BY s.patch_version, p.platform;
