from django.contrib import admin

from .models import *


@admin.register(ImageEvent)
class ImageEventAdmin(admin.ModelAdmin):

    list_display = ['season', 'date', 'image', 'filter', 'location', 'event']
    list_filter = ['season', 'filter', 'event', 'location']
    search_fields = []


@admin.register(NextEvent)
class NextEventAdmin(admin.ModelAdmin):

    list_display = ['location', 'date']


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):

    list_display = ['aboutme', 'age', 'weight', 'height']


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):

    list_display = ['name', 'image', 'info']


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):

    list_display = ['date', 'location', 'country', 'championship', 'title', 'endurance', 'sws', 'heats', 'ranking', 'price', 'confirmed']
    list_filter = ['sws', 'endurance', 'country', 'championship']
    list_editable = ['confirmed']

@admin.register(Trophy)
class TrophyAdmin(admin.ModelAdmin):

    list_display = ['year', 'gold', 'silver', 'bronze']
    list_filter = ['year']
    list_editable = ['gold', 'silver', 'bronze']
