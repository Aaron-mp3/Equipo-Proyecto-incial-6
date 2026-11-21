import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    - PerfilPyme.foto: foto de perfil opcional.
    - Venta.fecha: ahora se puede indicar (por defecto es la fecha y hora actuales),
      para registrar ventas de días anteriores.
    """

    dependencies = [
        ('gestion', '0003_unificar_pyme_y_ventas'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfilpyme',
            name='foto',
            field=models.FileField(blank=True, upload_to='perfiles/'),
        ),
        migrations.AlterField(
            model_name='venta',
            name='fecha',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
