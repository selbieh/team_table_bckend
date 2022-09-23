from django.db import models

from core.mixins import CreatedAndUpdatedOnMixin


class CrunchBaseLogs(CreatedAndUpdatedOnMixin):
    ORGANIZATION = "organization"
    FOUNDER = "FOUNDER"
    entity_choices=[
        (ORGANIZATION,ORGANIZATION),
        (FOUNDER,FOUNDER)
    ]
    url=models.CharField(max_length=255,null=False,blank=False)
    response=models.JSONField(default=dict)
    entity_type=models.CharField(default='',choices=entity_choices,max_length=25)

