from baserow.contrib.database.table.models import Table

from baserow.core.mixins import CreatedAndUpdatedOnMixin
from django.db import models

class AdditionalTableData(CreatedAndUpdatedOnMixin):
    table=models.ForeignKey(Table,on_delete=models.CASCADE,null=False,blank=False)
    can_edit=models.BooleanField(default=False,blank=False,null=False)

    def __str__(self):
        return self.table.name