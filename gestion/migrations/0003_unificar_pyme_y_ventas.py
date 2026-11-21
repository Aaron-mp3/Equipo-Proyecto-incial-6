import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    - Los productos pasan a pertenecer a PerfilPyme (antes PerfilDueno).
      Los productos existentes conservan su dueno_id: el código anterior ya
      trataba el id de la PYME como id del dueño.
    - Se elimina PerfilDueno, que quedó duplicado.
    - La contraseña admite el hash completo (128 caracteres).
    - Nuevo modelo Venta para guardar el historial en la base de datos.
    """

    dependencies = [
        ('gestion', '0002_perfilpyme'),
    ]

    operations = [
        migrations.AlterField(
            model_name='perfilpyme',
            name='contrasena',
            field=models.CharField(max_length=128),
        ),
        migrations.AlterField(
            model_name='producto',
            name='dueno',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='productos',
                to='gestion.perfilpyme',
            ),
        ),
        migrations.AlterField(
            model_name='producto',
            name='precio_costo',
            field=models.IntegerField(help_text='Precio de compra: costo para valorizar inventario'),
        ),
        migrations.AlterField(
            model_name='producto',
            name='precio_venta',
            field=models.IntegerField(help_text='Precio al que se vende al público'),
        ),
        migrations.DeleteModel(
            name='PerfilDueno',
        ),
        migrations.CreateModel(
            name='Venta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre_producto', models.CharField(max_length=150)),
                ('cantidad', models.PositiveIntegerField()),
                ('precio_unitario', models.IntegerField()),
                ('ganancia', models.IntegerField(help_text='(precio de venta - precio de costo) x cantidad')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('producto', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='gestion.producto',
                )),
                ('pyme', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ventas',
                    to='gestion.perfilpyme',
                )),
            ],
            options={
                'ordering': ['-fecha', '-id'],
            },
        ),
    ]
