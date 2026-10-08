# Platform routing

| Platform | Preferred route | Name-based discovery | Required access |
| --- | --- | --- | --- |
| Steam | Store review endpoint | Steam store search resolves app ID | None for public reviews |
| Bilibili | Public web search and reply endpoints | Search video by Chinese alias | May change; use conservative rate limits |
| Reddit | Official OAuth API | Global or subreddit search query | Reddit client credentials |
| YouTube | YouTube Data API v3 | `search.list`, then `commentThreads.list` | API key and quota |
| Weibo | Approved Open/Commercial API | Provider content search | Approved API scope/token; otherwise export |
| Xiaohongshu | Licensed provider or authorized browser session | Provider search | Approved access; otherwise export |
| Douyin | Approved Open/Game Partner API or licensed provider | Provider video search | Approved scope/token; otherwise export |
| Discord | Authorized server export or bot | Channel selection, not public search | Server/admin authorization |

For Weibo, Xiaohongshu, and Douyin, do not promise one-click coverage without confirmed access. If a browser is available and the user has an authenticated session, collect only publicly visible content within that session and stop at CAPTCHA or access barriers. The portable fallback is `scripts/gamepulse.py import` with an authorized CSV or JSON export.

Always report `collected`, `unavailable`, or `disabled` per source in the run manifest.
