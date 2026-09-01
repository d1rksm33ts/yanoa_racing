from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = "www"
urlpatterns = [
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
    path("media/<path:path>", views.media, name="media"),
    path("health/", views.health, name="health"),
    path("googlebfb2a3256d6cae08.html", views.google, name="site-verification"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
]
