from django.core.management.base import BaseCommand

from recruitment.skill_model import MODEL_PATH, train_skill_model


class Command(BaseCommand):
    help = "Train the offline, taxonomy-based skill suggestion model."

    def handle(self, *args, **options):
        model = train_skill_model()
        self.stdout.write(self.style.SUCCESS(
            f"Trained {model['model']} on {model['training_documents']} skill profiles. "
            f"Saved to {MODEL_PATH}"
        ))
