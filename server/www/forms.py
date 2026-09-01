from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import CalendarEvent, ImageEvent, Trophy, Website


class DateInput(forms.DateInput):
    input_type = "date"


class CalendarEventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = (
            "date", "location", "country", "championship", "title", "endurance",
            "sws", "confirmed", "heats", "ranking", "price",
        )
        widgets = {"date": DateInput(format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%d"]


class GalleryImageForm(forms.ModelForm):
    photo = forms.ImageField(
        required=False,
        label="Foto",
        help_text="JPEG, PNG of WebP, maximaal 20 MB. Er worden automatisch webversies gemaakt.",
    )

    class Meta:
        model = ImageEvent
        fields = ("season", "date", "event", "location")
        labels = {"season": "Seizoen", "event": "Wedstrijd", "location": "Locatie", "date": "Datum"}
        widgets = {"date": DateInput(format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%d"]
        if not self.instance.pk:
            self.fields["photo"].required = True

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 20 * 1024 * 1024:
            raise forms.ValidationError("De foto mag maximaal 20 MB groot zijn.")
        return photo

    @staticmethod
    def _webp(image, max_size, quality):
        prepared = ImageOps.exif_transpose(image).convert("RGB")
        prepared.thumbnail(max_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        prepared.save(output, format="WEBP", quality=quality, method=6)
        return ContentFile(output.getvalue())

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.filter = instance.season
        photo = self.cleaned_data.get("photo")
        old_files = []
        if photo:
            old_files = [field.name for field in (instance.display_image, instance.thumbnail_image) if field]
            image = Image.open(photo)
            stem = Path(photo.name).stem[:48] or "race"
            filename = f"{stem}-{uuid4().hex[:12]}.webp"
            instance.display_image.save(filename, self._webp(image, (1920, 1920), 86), save=False)
            photo.seek(0)
            instance.thumbnail_image.save(filename, self._webp(Image.open(photo), (900, 900), 82), save=False)
            instance.image = photo.name[:256]
        if commit:
            instance.save()
            for old_file in old_files:
                instance.display_image.storage.delete(old_file)
        return instance


class TrophyForm(forms.ModelForm):
    class Meta:
        model = Trophy
        fields = ("year", "gold", "silver", "bronze")
        labels = {"year": "Jaar", "gold": "Goud", "silver": "Zilver", "bronze": "Brons"}


class WebsiteForm(forms.ModelForm):
    class Meta:
        model = Website
        fields = ("aboutme", "age", "weight", "height")
        labels = {"aboutme": "About Me", "age": "Leeftijd", "weight": "Gewicht", "height": "Lengte"}
        widgets = {"aboutme": forms.Textarea(attrs={"rows": 14})}
