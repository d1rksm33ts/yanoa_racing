from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("www", "0009_trophy")]
    operations = [
        migrations.AddField(
            model_name="imageevent",
            name="display_image",
            field=models.ImageField(blank=True, upload_to="gallery/display/"),
        ),
        migrations.AddField(
            model_name="imageevent",
            name="thumbnail_image",
            field=models.ImageField(blank=True, upload_to="gallery/thumbs/"),
        ),
    ]
