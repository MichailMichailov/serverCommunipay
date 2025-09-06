from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("common", "0001_initial"),
    ]

    operations = [
        # 1) Снести старую CHECK, если она есть
        migrations.RunSQL(
            sql="""
            ALTER TABLE common_chatlinkintent
            DROP CONSTRAINT IF EXISTS common_chatlinkintent_chat_id_check;
            """,
            reverse_sql="""
            ALTER TABLE common_chatlinkintent
            ADD CONSTRAINT common_chatlinkintent_chat_id_check
              CHECK (chat_id >= 0);
            """,
        ),
        # 2) На всякий — ещё раз зафиксировать тип поля как signed bigint
        migrations.AlterField(
            model_name="chatlinkintent",
            name="chat_id",
            field=models.BigIntegerField(null=True, blank=True),
        ),
    ]