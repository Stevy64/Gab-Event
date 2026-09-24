from django.db import migrations


def recommend_moyen(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    EventPlan.objects.exclude(slug="moyen").update(is_recommended=False)
    EventPlan.objects.filter(slug="moyen").update(is_recommended=True)


def revert_recommend(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    EventPlan.objects.filter(slug="moyen").update(is_recommended=False)
    EventPlan.objects.filter(slug="petit").update(is_recommended=True)


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0011_event_type_custom"),
    ]

    operations = [
        migrations.RunPython(recommend_moyen, revert_recommend),
    ]
