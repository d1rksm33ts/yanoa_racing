from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from .models import CalendarEvent, ImageEvent, Trophy, Website

class PublicSiteTests(TestCase):
    def setUp(self):
        Website.objects.create(aboutme="<p>Test profile</p>", age="18", weight="66 kg", height="1.87 m")
        Trophy.objects.create(year="2026", gold=1, silver=2, bronze=3)
        self.race = CalendarEvent.objects.create(
            location="Genk", country="BE", date=date.today() + timedelta(days=10),
            championship="SWS", title="Sprint", confirmed=True,
        )
        ImageEvent.objects.create(
            season="2025", filter="2025", image="photo.jpg", location="Genk",
            event="SWS", date=date(2025, 1, 1),
        )

    def test_home_renders_current_content(self):
        response = self.client.get(reverse("www:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Genk")
        self.assertContains(response, "Test profile")
        self.assertContains(response, "photo.webp")
        self.assertContains(response, 'id="hero"')
        self.assertContains(response, "portfolio-container")

    def test_calendar_api_returns_json(self):
        response = self.client.get(reverse("www:calendar"), {"year": self.race.date.year})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["location"], "Genk")
        self.assertEqual(response.json()[0]["type"], "Sprint")

    def test_legacy_calendar_endpoint_remains_compatible(self):
        response = self.client.get("/calendar", {"get": "season"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["endurance"], 0)

    def test_health_does_not_cache(self):
        response = self.client.get(reverse("www:health"))
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_sitemap_is_xml(self):
        response = self.client.get(reverse("www:sitemap"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/xml"))
