from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import CalendarEvent, ImageEvent, Trophy, Website

class PublicSiteTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=Path(self.media_directory.name))
        self.media_override.enable()
        self.user = get_user_model().objects.create_user("editor", password="safe-test-password")
        Website.objects.create(aboutme="<p>Test profile</p>", age="18", weight="66 kg", height="1.87 m")
        Trophy.objects.create(year="2026", gold=1, silver=2, bronze=3)
        Trophy.objects.create(year="2025", gold=7, silver=6, bronze=2)
        Trophy.objects.create(year="2024", gold=8, silver=1, bronze=5)
        Trophy.objects.create(year="2023", gold=1, silver=2, bronze=1)
        self.race = CalendarEvent.objects.create(
            location="Genk", country="BE", date=date.today() + timedelta(days=10),
            championship="SWS", title="Sprint", confirmed=True,
        )
        ImageEvent.objects.create(
            season="2025", filter="2025", image="photo.jpg", location="Genk",
            event="SWS", date=date(2025, 1, 1),
        )

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    def test_home_renders_current_content(self):
        response = self.client.get(reverse("www:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Genk")
        self.assertContains(response, "Test profile")
        self.assertContains(response, "photo.webp")
        self.assertContains(response, 'id="hero"')
        self.assertContains(response, "portfolio-container")
        self.assertContains(response, 'data-default-filter=".filter-2025"')
        self.assertNotContains(response, 'loading="lazy"')
        self.assertContains(response, 'href="/beheer/"')
        self.assertContains(response, "hero-bg.jpg")
        self.assertContains(response, "me.jpg")
        self.assertContains(response, "testimonials-bg.jpg")
        self.assertContains(response, 'data-filter=".filter-2026"')
        self.assertContains(response, 'data-filter=".filter-2025" class="filter-active"')
        self.assertEqual([item.year for item in response.context["trophies_left"]], ["2026", "2025", "2024"])
        self.assertEqual([item.year for item in response.context["trophies_right"]], ["2023"])

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

    def test_management_requires_login_and_uses_dedicated_login(self):
        response = self.client.get(reverse("www:manage"))
        self.assertRedirects(response, "/beheer/login/?next=/beheer/")
        response = self.client.get(reverse("www:login"))
        self.assertContains(response, "Welkom terug")
        response = self.client.post(reverse("www:login"), {
            "username": "editor", "password": "safe-test-password",
        })
        self.assertRedirects(response, reverse("www:manage"))

    def test_editor_can_add_calendar_event(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("www:calendar-add"), {
            "date": "2027-04-12", "location": "Spa", "country": "BE",
            "championship": "SWS", "title": "Sprint Cup", "confirmed": "on",
            "heats": "3", "ranking": "1", "price": "120",
        })
        self.assertRedirects(response, f"{reverse('www:manage')}#calendar")
        self.assertTrue(CalendarEvent.objects.filter(location="Spa", confirmed=True).exists())

    def test_editor_can_upload_and_serve_gallery_image(self):
        image_data = BytesIO()
        Image.new("RGB", (1400, 900), "#e4a619").save(image_data, "JPEG")
        upload = SimpleUploadedFile("race.jpg", image_data.getvalue(), content_type="image/jpeg")
        self.client.force_login(self.user)
        response = self.client.post(reverse("www:image-add"), {
            "season": "2026", "date": "2026-08-20", "event": "Finale",
            "location": "Genk", "photo": upload,
        })
        self.assertRedirects(response, f"{reverse('www:manage')}#images")
        gallery_image = ImageEvent.objects.latest("pk")
        self.assertTrue(gallery_image.display_image.name.endswith(".webp"))
        self.assertTrue(gallery_image.thumbnail_image.storage.exists(gallery_image.thumbnail_image.name))
        media_response = self.client.get(gallery_image.thumbnail_url)
        self.assertEqual(media_response.status_code, 200)
        self.assertEqual(media_response["Content-Type"], "image/webp")

    def test_photo_editor_shows_current_and_new_photo_comparison(self):
        self.client.force_login(self.user)
        gallery_image = ImageEvent.objects.get(image="photo.jpg")
        response = self.client.get(reverse("www:image-edit", args=[gallery_image.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Huidige foto")
        self.assertContains(response, "Nieuwe foto")
        self.assertContains(response, gallery_image.display_url)
        self.assertContains(response, "data-new-photo-image")
        self.assertContains(response, "management.js")

    def test_management_gallery_can_filter_by_year(self):
        ImageEvent.objects.create(
            season="2024", filter="2024", image="historic.jpg", location="Spa",
            event="Historic", date=date(2024, 7, 1),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("www:manage"), {"photo_year": "2025"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SWS")
        self.assertNotContains(response, "Historic")
        self.assertEqual(response.context["selected_image_season"], "2025")
        self.assertEqual(response.context["image_seasons"], ["2026", "2025", "2024"])

    def test_current_photo_year_becomes_default_after_first_upload(self):
        ImageEvent.objects.create(
            season="2026", filter="2026", image="new-season.jpg", location="Genk",
            event="New season", date=date(2026, 2, 1),
        )
        response = self.client.get(reverse("www:index"))
        self.assertEqual(response.context["photo_default_year"], "2026")
        self.assertContains(response, 'data-filter=".filter-2026" class="filter-active"')
        self.assertContains(response, 'data-default-filter=".filter-2026"')

    def test_editor_can_update_trophies_and_about_me(self):
        self.client.force_login(self.user)
        trophy = Trophy.objects.get(year="2026")
        response = self.client.post(reverse("www:trophy-edit", args=[trophy.pk]), {
            "year": "2026", "gold": "4", "silver": "3", "bronze": "2",
        })
        self.assertRedirects(response, f"{reverse('www:manage')}#trophies")
        trophy.refresh_from_db()
        self.assertEqual(trophy.gold, 4)
        website = Website.objects.last()
        response = self.client.post(reverse("www:website-edit"), {
            "aboutme": "<p>Updated profile</p>", "age": "19",
            "weight": "67 kg", "height": "1.88 m",
        })
        self.assertRedirects(response, f"{reverse('www:manage')}#about")
        website.refresh_from_db()
        self.assertEqual(website.aboutme, "<p>Updated profile</p>")

    def test_editor_can_compare_and_replace_website_images(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("www:website-images"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hoofdfoto")
        self.assertContains(response, "About Me-foto")
        self.assertContains(response, "Achtergrond sponsoring")
        self.assertEqual(response.content.count(b"data-photo-comparison"), 3)

        image_data = BytesIO()
        Image.new("RGB", (1800, 1200), "#282b30").save(image_data, "JPEG")
        upload = SimpleUploadedFile("new-hero.jpg", image_data.getvalue(), content_type="image/jpeg")
        response = self.client.post(reverse("www:website-images"), {"hero_upload": upload})
        self.assertRedirects(response, f"{reverse('www:manage')}#site-images")
        website = Website.objects.last()
        self.assertTrue(website.hero_image.name.endswith(".webp"))
        self.assertTrue(website.hero_image.storage.exists(website.hero_image.name))
        self.assertIn("/media/site/hero-", website.hero_image_url)
        self.assertIn("/static/", website.about_image_url)

    def test_destructive_editor_actions_are_post_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("www:calendar-delete", args=[self.race.pk])).status_code, 405)
        self.assertTrue(CalendarEvent.objects.filter(pk=self.race.pk).exists())
