from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from . import live_views
from . import telemetry_views

app_name = "www"
urlpatterns = [
    path("live/api/devices/", telemetry_views.devices, name="telemetry-devices"),
    path("live/api/devices/<slug:device_id>/assign/", telemetry_views.assign, name="telemetry-assign"),
    path("live/api/devices/<slug:device_id>/telemetry/", telemetry_views.ingest, name="telemetry-ingest"),
    path("live/api/devices/<slug:device_id>/", telemetry_views.detail, name="telemetry-detail"),
    path("live/", live_views.page, name="livecoach"),
    path("live/sprint/", live_views.page, {"activity": "sprint"}, name="livecoach-sprint"),
    path("live/training/", live_views.page, {"activity": "training"}, name="livecoach-training"),
    path("live/endurance/", live_views.page, {"activity": "endurance"}, name="livecoach-endurance"),
    path("live/api/kart-reports/", live_views.kart_reports, name="livecoach-kart-reports"),
    path("live/api/sessions/<uuid:pk>/kart-reports/", live_views.save_kart_report, name="livecoach-save-kart-report"),
    path("live/login/", auth_views.LoginView.as_view(template_name="livecoach/login.html", redirect_authenticated_user=True), name="livecoach-login"),
    path("live/samenvattingen/", live_views.summary, name="livecoach-summary"),
    path("live/api/", live_views.overview, name="livecoach-overview"),
    path("live/api/start/", live_views.start, name="livecoach-start"),
    path("live/api/connect/", live_views.connect, name="livecoach-connect"),
    path("live/api/simulate/", live_views.simulate, name="livecoach-simulate"),
    path("live/api/simulations/<uuid:pk>/action/", live_views.simulation_action, name="livecoach-simulation-action"),
    path("live/api/sessions/<uuid:pk>/", live_views.detail, name="livecoach-detail"),
    path("live/api/sessions/<uuid:pk>/action/", live_views.action, name="livecoach-action"),
    path("live/api/sessions/<uuid:pk>/discard/", live_views.discard, name="livecoach-discard"),
    path("live/api/sessions/<uuid:pk>/events/", live_views.stream, name="livecoach-events"),
    path("live/api/sessions/<uuid:pk>/export/", live_views.export, name="livecoach-export"),
    path("", views.index, name="index"),
    path("calendar", views.calendar, name="calendar-legacy"),
    path("calendar/", views.calendar, name="calendar"),
    path("beheer/login/", auth_views.LoginView.as_view(
        template_name="management/login.html", redirect_authenticated_user=True,
    ), name="login"),
    path("beheer/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("beheer/", views.manage, name="manage"),
    path("beheer/kalender/nieuw/", views.calendar_edit, name="calendar-add"),
    path("beheer/kalender/<int:pk>/", views.calendar_edit, name="calendar-edit"),
    path("beheer/kalender/<int:pk>/verwijderen/", views.calendar_delete, name="calendar-delete"),
    path("beheer/fotos/nieuw/", views.image_edit, name="image-add"),
    path("beheer/fotos/<int:pk>/", views.image_edit, name="image-edit"),
    path("beheer/fotos/<int:pk>/verwijderen/", views.image_delete, name="image-delete"),
    path("beheer/trofeeen/nieuw/", views.trophy_edit, name="trophy-add"),
    path("beheer/trofeeen/<int:pk>/", views.trophy_edit, name="trophy-edit"),
    path("beheer/trofeeen/<int:pk>/verwijderen/", views.trophy_delete, name="trophy-delete"),
    path("beheer/over-mij/", views.website_edit, name="website-edit"),
    path("beheer/websitefotos/", views.website_images_edit, name="website-images"),
    path("media/<path:path>", views.media, name="media"),
    path("health/", views.health, name="health"),
    path("googlebfb2a3256d6cae08.html", views.google, name="site-verification"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
]
