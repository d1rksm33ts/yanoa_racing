from django.urls import path
from . import views

app_name = "www"
urlpatterns = [
    path("", views.index, name="index"),
    path("calendar/", views.calendar, name="calendar"),
    path("health/", views.health, name="health"),
    path("googlebfb2a3256d6cae08.html", views.google, name="site-verification"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
]
