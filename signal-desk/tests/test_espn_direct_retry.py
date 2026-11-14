"""Direct ESPN fetches retry brief network faults before spending the scraper fallback."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import espn_sync as es  # noqa: E402

URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/1/schedule"
RESET = RuntimeError("Network error contacting site.api.espn.com: [Errno 104] Connection reset by peer")
TLS = RuntimeError("Network error contacting site.api.espn.com: [SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error")


class DirectRetry(unittest.TestCase):
    def setUp(self):
        es.DIRECT_STATS.update(direct=0, scraper=0, retries=0)
        self.sleep = mock.patch.object(es.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def calls(self, outcomes):
        seq = list(outcomes)
        seen = []

        def fake(url, headers=None, method="GET", payload=None):
            seen.append(url)
            out = seq.pop(0)
            if isinstance(out, Exception):
                raise out
            return out
        mock.patch.object(es, "http_get", side_effect=fake).start()
        return seen

    def test_transient_fault_retried_without_scraper(self):
        seen = self.calls([RESET, TLS, '{"ok": 1}'])
        self.assertEqual(es.scrape(URL, "key"), '{"ok": 1}')
        self.assertEqual(seen, [URL, URL, URL])
        self.assertEqual((es.DIRECT_STATS["direct"], es.DIRECT_STATS["scraper"], es.DIRECT_STATS["retries"]), (1, 0, 2))

    def test_falls_back_only_after_all_direct_attempts(self):
        seen = self.calls([RESET, RESET, RESET, "scraped"])
        self.assertEqual(es.scrape(URL, "key"), "scraped")
        self.assertEqual(seen[:3], [URL, URL, URL])
        self.assertTrue(seen[3].startswith(es.SCRAPER_URL))
        self.assertEqual(es.DIRECT_STATS["scraper"], 1)

    def test_no_key_raises_after_retries(self):
        self.calls([RESET, RESET, RESET])
        with self.assertRaises(RuntimeError):
            es.scrape(URL, "")

    def test_server_errors_and_rate_limit_are_retried(self):
        seen = self.calls([RuntimeError("HTTP 503 from site.api.espn.com: busy"),
                           RuntimeError("HTTP 429 from site.api.espn.com: slow down"), "ok"])
        self.assertEqual(es.scrape(URL, "key"), "ok")
        self.assertEqual(len(seen), 3)

    def test_permanent_client_error_not_retried(self):
        seen = self.calls([RuntimeError("HTTP 404 from site.api.espn.com: missing"), "scraped"])
        self.assertEqual(es.scrape(URL, "key"), "scraped")
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[1].startswith(es.SCRAPER_URL))

    def test_backoff_waits_between_attempts(self):
        self.calls([RESET, RESET, "ok"])
        es.scrape(URL, "key")
        waits = [c.args[0] for c in self.sleep.call_args_list]
        self.assertEqual(waits, [1.5, 3, 8])  # polite delay, then two backoffs


if __name__ == "__main__":
    unittest.main()
