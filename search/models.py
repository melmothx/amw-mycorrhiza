from django.db import models
from datetime import datetime

class Site(models.Model):
    OAI_DC = "oai_dc"
    MARC21 = "marc21"
    OAI_PMH_METADATA_FORMATS = [
        (OAI_DC, "Dublin Core"),
        (MARC21, "MARC XML"),
    ]
    title = models.CharField(max_length=255)
    url = models.URLField(max_length=255)
    last_harvested = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)
    oai_set = models.CharField(max_length=64, blank=True)
    oai_metadata_format = models.CharField(max_length=32,
                                           choices=OAI_PMH_METADATA_FORMATS,
                                           default=OAI_DC)
    def __str__(self):
        return self.title

    def last_harvested_zulu(self):
        dt = self.last_harvested
        if dt:
            # clone
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            return None

class Harvest(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    datetime = models.DateTimeField()
    logs = models.TextField()
    def __str__(self):
        return self.site.title + ' Harvest ' + self.datetime.strftime('%Y-%m-%dT%H:%M:%SZ')
