"""
Models: acceso a datos con SQL directo (async).

Cada `*_model.py` recibe una instancia de `Database` y expone métodos async que
retornan dicts. El esquema (tablas y SPs) vive en SQL plano en `database/`.

Patrón: Routes → Controllers → Models → Database
"""
