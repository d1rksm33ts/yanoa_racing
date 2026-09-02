from pathlib import Path

from django.db import models
from django.templatetags.static import static


class ImageEvent(models.Model):

    season = models.CharField(max_length=4, blank=True)
    filter = models.CharField(max_length=16, blank=True)
    image = models.CharField(max_length=256, blank=True)
    location = models.CharField(max_length=64, blank=True)
    event = models.CharField(max_length=64, blank=True)
    date = models.DateField(blank=True, null=True)
    display_image = models.ImageField(upload_to="gallery/display/", blank=True)
    thumbnail_image = models.ImageField(upload_to="gallery/thumbs/", blank=True)

    def __str__(self):
        return f"{self.event} — {self.location} ({self.date or self.season})"

    @property
    def thumbnail_path(self):
        image = Path(self.image).with_suffix(".webp")
        return f"yanoa_racing/assets/img/thumbs/season-{self.season}/{image.as_posix()}"

    @property
    def display_path(self):
        image = Path(self.image).with_suffix(".webp")
        return f"yanoa_racing/assets/img/display/season-{self.season}/{image.as_posix()}"

    @property
    def thumbnail_url(self):
        if self.thumbnail_image:
            return self.thumbnail_image.url
        return static(self.thumbnail_path)

    @property
    def display_url(self):
        if self.display_image:
            return self.display_image.url
        return static(self.display_path)


class NextEvent(models.Model):

    location = models.CharField(max_length=16)
    date = models.DateField()

    def __str__(self):
        return f"{self.location} — {self.date}"


class Website(models.Model):

    aboutme = models.TextField()
    age = models.CharField(max_length=2, default='16')
    weight = models.CharField(max_length=6, default='65 kg')
    height = models.CharField(max_length=6, default='1.84 m')
    hero_image = models.ImageField(upload_to="site/", blank=True)
    about_image = models.ImageField(upload_to="site/", blank=True)
    sponsors_image = models.ImageField(upload_to="site/", blank=True)

    @property
    def hero_image_url(self):
        return self.hero_image.url if self.hero_image else static("yanoa_racing/assets/img/hero-bg.jpg")

    @property
    def about_image_url(self):
        return self.about_image.url if self.about_image else static("yanoa_racing/assets/img/me.jpg")

    @property
    def sponsors_image_url(self):
        return self.sponsors_image.url if self.sponsors_image else static("yanoa_racing/assets/img/testimonials-bg.jpg")

    def __str__(self):
        return "Website profile"

class Sponsor(models.Model):

    name = models.CharField(max_length=64)
    image = models.CharField(max_length=256, blank=True)
    info = models.CharField(max_length=256)

    def __str__(self):
        return self.name


class CalendarEvent(models.Model):

    location = models.CharField(max_length=16)
    country = models.CharField(max_length=3)
    date = models.DateField()
    championship = models.CharField(max_length=32)
    title = models.CharField(max_length=32)
    endurance = models.BooleanField(default=False)
    sws = models.BooleanField(default=False)
    heats = models.CharField(max_length=128, blank=True)
    ranking = models.CharField(max_length=32, blank=True)
    price = models.PositiveSmallIntegerField(default=0, blank=True)
    confirmed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.date} — {self.location}"

class Trophy(models.Model):

    year = models.CharField(max_length=4)
    gold = models.PositiveSmallIntegerField(default=0, blank=True)
    silver = models.PositiveSmallIntegerField(default=0, blank=True)
    bronze = models.PositiveSmallIntegerField(default=0, blank=True)

    def __str__(self):
        return self.year
