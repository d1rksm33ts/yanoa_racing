from datetime import date

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control

from .models import CalendarEvent, ImageEvent, Trophy, Website

def index(request):
    today = date.today()
    upcoming = CalendarEvent.objects.filter(date__gte=today).order_by("date", "location")
    season_year = upcoming.values_list("date__year", flat=True).first() or today.year
    return render(request, "index.html", {
        "calendar": CalendarEvent.objects.filter(date__year=season_year).order_by("date", "location"),
        "events": ImageEvent.objects.exclude(image="").order_by("-date", "-pk"),
        "next": upcoming.first(),
        "season_year": season_year,
        "trophies": Trophy.objects.order_by("-year"),
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
