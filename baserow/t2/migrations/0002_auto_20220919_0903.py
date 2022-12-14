# Generated by Django 3.2.12 on 2022-09-19 09:03

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0074_auto_20220530_0919'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('t2', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RowComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('updated_on', models.DateTimeField(auto_now=True)),
                ('row_id', models.PositiveIntegerField(help_text='The id of the row the comment is for.')),
                ('comment', models.TextField(help_text='The users comment.')),
                ('table', models.ForeignKey(help_text='The table the row this comment is for is found in. ', on_delete=django.db.models.deletion.CASCADE, to='database.table')),
                ('user', models.ForeignKey(help_text='The user who made the comment.', on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'database_rowcomment',
                'ordering': ('-created_on',),
            },
        ),
        migrations.AddIndex(
            model_name='rowcomment',
            index=models.Index(fields=['table', 'row_id', '-created_on'], name='database_ro_table_i_e8263d_idx'),
        ),
    ]
