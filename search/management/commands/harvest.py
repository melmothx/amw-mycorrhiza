from django.core.management.base import BaseCommand, CommandError
from amwmeta.xapian import harvest, XAPIAN_DB
from search.models import Site, Harvest
from datetime import datetime, timezone
import shutil

class Command(BaseCommand):
    help = "Harvest the sites"
    def add_arguments(self, parser):
        parser.add_argument("--force",
                            action="store_true", # boolean
                            help="Force a full harvest")

    def handle(self, *args, **options):
        forcing = False
        if options['force']:
            forcing = True
            try:
                print("Removing " + XAPIAN_DB)
                shutil.rmtree(XAPIAN_DB)
            except FileNotFoundError:
                pass


        for site in Site.objects.all():
            now = datetime.now(timezone.utc)
            opts = {
                "url": site.url,
                "metadataPrefix": site.oai_metadata_format,
            }
            last_harvested = site.last_harvested_zulu()

            if not forcing:
                opts['from'] = last_harvested

            if site.oai_set:
                opts['set'] = site.oai_set

            logs = harvest(**opts)
            if logs:
                msg = "Total indexed: " + str(len(logs))
                print(msg)
                logs.append(msg)
                site.last_harvested = now
                site.save()
                site.harvest_set.create(datetime=now, logs="\n".join(logs))
