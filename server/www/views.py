import mimetypes
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from .forms import CalendarEventForm, GalleryImageForm, TrophyForm, WebsiteForm, WebsiteImagesForm
from .models import CalendarEvent, ImageEvent, Trophy, Website

def index(request):
    today = date.today()
    upcoming = CalendarEvent.objects.filter(date__gte=today).order_by("date", "location")
    season_year = upcoming.values_list("date__year", flat=True).first() or today.year
    populated_photo_years = sorted(
        set(ImageEvent.objects.exclude(season="").values_list("season", flat=True)), reverse=True,
    )
    photo_years = sorted({str(today.year), *populated_photo_years}, reverse=True)
    trophies = list(Trophy.objects.order_by("-year"))
    return render(request, "index.html", {
        "calendar": CalendarEvent.objects.filter(date__year=season_year).order_by("date", "location"),
        "events": ImageEvent.objects.filter(Q(image__gt="") | Q(display_image__gt="")).order_by("-date", "-pk"),
        "next": upcoming.first(),
        "season_year": season_year,
        "photo_years": photo_years,
        "photo_default_year": populated_photo_years[0] if populated_photo_years else photo_years[0],
        "trophies_left": trophies[:3],
        "trophies_right": trophies[3:],
        "website": Website.objects.last(),
    })

def calendar(request):
    events = CalendarEvent.objects.order_by("date", "location")
    year = request.GET.get("year")
    if request.GET.get("get") == "season":
        year = str(date.today().year)
    if year and year.isdigit():
        events = events.filter(date__year=int(year))
    return JsonResponse([{
        "date": event.date.isoformat(),
        "location": event.location,
        "country": event.country,
        "championship": event.championship,
        "title": event.title,
        "type": "Endurance" if event.endurance else "Sprint",
        "endurance": 1 if event.endurance else 0,
        "confirmed": 1 if event.confirmed else 0,
        "sws": 1 if event.sws else 0,
        "heats": event.heats,
        "ranking": event.ranking,
    } for event in events], safe=False)


@login_required
def manage(request):
    image_seasons = sorted(
        {str(date.today().year), *ImageEvent.objects.exclude(season="").values_list("season", flat=True)},
        reverse=True,
    )
    selected_image_season = request.GET.get("photo_year", "")
    images = ImageEvent.objects.order_by("-date", "-pk")
    if selected_image_season in image_seasons:
        images = images.filter(season=selected_image_season)
    return render(request, "management/dashboard.html", {
        "calendar_events": CalendarEvent.objects.order_by("-date", "location"),
        "images": images,
        "image_seasons": image_seasons,
        "selected_image_season": selected_image_season,
        "trophies": Trophy.objects.order_by("-year"),
        "website": Website.objects.last(),
    })


def _edit(request, form_class, instance, title, description, success_message, anchor):
    if request.method == "POST":
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, success_message)
            return redirect(f"{reverse('www:manage')}{anchor}")
    else:
        form = form_class(instance=instance)
    return render(request, "management/form.html", {
        "form": form,
        "title": title,
        "description": description,
    })


@login_required
def calendar_edit(request, pk=None):
    event = get_object_or_404(CalendarEvent, pk=pk) if pk else None
    return _edit(
        request, CalendarEventForm, event,
        "Kalenderwedstrijd aanpassen" if event else "Kalenderwedstrijd toevoegen",
        "Beheer alle kalendergegevens die op de publieke website verschijnen.",
        "De kalenderwedstrijd is opgeslagen.", "#calendar",
    )


@login_required
@require_POST
def calendar_delete(request, pk):
    get_object_or_404(CalendarEvent, pk=pk).delete()
    messages.success(request, "De kalenderwedstrijd is verwijderd.")
    return redirect(f"{reverse('www:manage')}#calendar")


@login_required
def image_edit(request, pk=None):
    image = get_object_or_404(ImageEvent, pk=pk) if pk else None
    return _edit(
        request, GalleryImageForm, image,
        "Foto aanpassen" if image else "Foto toevoegen",
        "Upload een foto en voeg de wedstrijdgegevens toe.",
        "De foto is opgeslagen.", "#images",
    )


@login_required
@require_POST
def image_delete(request, pk):
    image = get_object_or_404(ImageEvent, pk=pk)
    storage = image.display_image.storage if image.display_image else None
    files = [field.name for field in (image.display_image, image.thumbnail_image) if field]
    image.delete()
    if storage:
        for filename in files:
            storage.delete(filename)
    messages.success(request, "De foto is verwijderd.")
    return redirect(f"{reverse('www:manage')}#images")


@login_required
def trophy_edit(request, pk=None):
    trophy = get_object_or_404(Trophy, pk=pk) if pk else None
    return _edit(
        request, TrophyForm, trophy,
        "Trofeeën aanpassen" if trophy else "Trofeejaar toevoegen",
        "Werk het aantal podiumplaatsen voor dit jaar bij.",
        "De trofeeën zijn opgeslagen.", "#trophies",
    )


@login_required
@require_POST
def trophy_delete(request, pk):
    get_object_or_404(Trophy, pk=pk).delete()
    messages.success(request, "Het trofeejaar is verwijderd.")
    return redirect(f"{reverse('www:manage')}#trophies")


@login_required
def website_edit(request):
    return _edit(
        request, WebsiteForm, Website.objects.last(), "About Me aanpassen",
        "Pas de profieltekst en de gegevens naast de foto aan.",
        "About Me is opgeslagen.", "#about",
    )


@login_required
def website_images_edit(request):
    website = Website.objects.last() or Website.objects.create(aboutme="")
    if request.method == "POST":
        form = WebsiteImagesForm(request.POST, request.FILES, instance=website)
        if form.is_valid():
            form.save()
            messages.success(request, "De websitefoto's zijn opgeslagen.")
            return redirect(f"{reverse('www:manage')}#site-images")
    else:
        form = WebsiteImagesForm(instance=website)
    comparisons = (
        {"field": form["hero_upload"], "current_url": website.hero_image_url, "hint": "Bovenaan de hoofdpagina"},
        {"field": form["about_upload"], "current_url": website.about_image_url, "hint": "Naast de About Me-tekst"},
        {"field": form["sponsors_upload"], "current_url": website.sponsors_image_url, "hint": "Achter de sponsorlogo's"},
    )
    return render(request, "management/site_images.html", {"form": form, "comparisons": comparisons})


@cache_control(public=True, max_age=31536000, immutable=True)
def media(request, path):
    root = settings.MEDIA_ROOT.resolve()
    file_path = (root / Path(path)).resolve()
    if not file_path.is_relative_to(root) or not file_path.is_file():
        raise Http404
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(file_path.open("rb"), content_type=content_type)

@cache_control(no_store=True)
def health(request):
    return JsonResponse({"status": "ok"})

def google(request):
    return HttpResponse("google-site-verification: googlebfb2a3256d6cae08.html", content_type="text/plain")

def sitemap(request):
    body = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://racing.yanoa.be/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>
</urlset>"""
    return HttpResponse(body, content_type="application/xml")
