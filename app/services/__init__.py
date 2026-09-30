"""
Services: lógica reutilizable que no pertenece a un solo controller.

- Negocio compartido o transversal (auditoría, notificaciones, cálculos usados por ≥2
  controllers): `class AuditService` que usa models.
- Integraciones con APIs externas: `class XService(ServiceClient)` (app/core/http_client.py).

Nombres: app/services/<name>_service.py → <Name>Service, <Name>ServiceDep.
Prohibido: Request/Response/UploadFile, importar controllers o routes, SQL directo
(eso va en models), crear httpx.AsyncClient propio o devolver httpx.Response.
"""
