# Desarrollo: reglas de programación y buenas prácticas

Reglas que se deben seguir al escribir código en este proyecto. `AGENTS.md` solo las resume: aquí está el detalle.
Léelas **bajo demanda**, según lo que vayas a hacer.

| Si vas a… | Lee |
|---|---|
| Escribir cualquier código, crear capas o archivos nuevos | [architecture.md](architecture.md) |
| Agregar o usar una variable de entorno | [configuration.md](configuration.md) |
| Escribir un model, una consulta o un stored procedure | [data-access.md](data-access.md) |
| Crear una feature completa (tabla → route → test) | [new-feature.md](new-feature.md) |
| Consumir una API externa | [external-services.md](external-services.md) |
| Cifrar datos, manejar contraseñas o exponer IDs | [security.md](security.md) |
| Diseñar un endpoint: dónde va cada parámetro, filtros, fechas, orden, status | [api-contract.md](api-contract.md) |
| Crear o cambiar un endpoint (respuestas, errores, paginación, uploads, logging) | [api-conventions.md](api-conventions.md) |
| Escribir tests o verificar calidad (tipos, cobertura, lint) | [testing-and-quality.md](testing-and-quality.md) |
| Usar los agentes de `.agents/` | [agents.md](agents.md) |
| Iniciar un proyecto nuevo desde la plantilla (limpiar el ejemplo) | [starting-new-project.md](starting-new-project.md) |
| Entender el porqué (async, rendimiento, diagnóstico de bloqueos) | [best-practices.md](best-practices.md) |

Estas reglas son imperativas y breves. Para entender cómo funciona cada pieza, ver `docs/features/`.
