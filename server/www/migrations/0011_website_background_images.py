from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("www", "0010_imageevent_uploaded_images")]
    operations = [
        migrations.AddField(
            model_name="website",
            name="hero_image",
            field=models.ImageField(blank=True, upload_to="site/"),
        ),
        migrations.AddField(
            model_name="website",
            name="about_image",
            field=models.ImageField(blank=True, upload_to="site/"),
        ),
        migrations.AddField(
            model_name="website",
            name="sponsors_image",
            field=models.ImageField(blank=True, upload_to="site/"),
        ),
    ]
