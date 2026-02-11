# Pre-commit Hooks

El proyecto utiliza pre-commit para ejecutar automáticamente validaciones y formateo de código antes de cada commit.

## ¿Qué es Pre-commit?

Pre-commit es un framework de git hooks que ejecuta scripts automáticamente antes de crear un commit. Ayuda a mantener calidad de código sin esfuerzo manual.

## Instalación

### Primera Vez

```bash
# Instalar hooks (solo una vez por repositorio)
uv run pre-commit install
```

Esto instala los hooks en `.git/hooks/pre-commit`.

## Hooks Configurados

Ver `.pre-commit-config.yaml` para configuración completa.

### 1. Standard File Checks

**Repo**: `pre-commit/pre-commit-hooks`

- **trailing-whitespace**: Elimina espacios al final de líneas
- **end-of-file-fixer**: Asegura que archivos terminen con nueva línea
- **check-yaml**: Valida sintaxis de archivos YAML
- **check-toml**: Valida sintaxis de archivos TOML
- **check-json**: Valida sintaxis de archivos JSON
- **check-added-large-files**: Previene commits de archivos >500KB
- **check-merge-conflict**: Detecta markers de conflictos de merge
- **check-case-conflict**: Detecta conflictos de nombres (case-sensitive)
- **mixed-line-ending**: Normaliza line endings a LF
- **check-docstring-first**: Verifica que docstrings estén antes del código
- **debug-statements**: Detecta `print()`, `pdb.set_trace()`, etc.

### 2. Ruff (Linter y Formateador)

**Repo**: `astral-sh/ruff-pre-commit`

Ruff reemplaza múltiples herramientas:
- **flake8**: Linting
- **isort**: Ordenamiento de imports
- **black**: Formateo de código
- **pyupgrade**: Modernización de sintaxis

**Configuración:**

```yaml
- id: ruff
  name: Ruff linter
  args: [--fix, --exit-non-zero-on-fix]
- id: ruff-format
  name: Ruff formatter
```

**Lo que hace:**
- Ordena imports automáticamente
- Formatea código según PEP 8
- Detecta errores comunes (variables no usadas, imports incorrectos, etc.)
- Moderniza sintaxis (f-strings, type hints, etc.)

### 3. Detect Secrets

**Repo**: `Yelp/detect-secrets`

Previene commits de credenciales y secretos.

**Configuración:**

```yaml
- id: detect-secrets
  args: ['--baseline', '.secrets.baseline']
  exclude: package.lock.json|uv.lock
```

**Detecta:**
- API keys
- Passwords en código
- Tokens de autenticación
- AWS keys
- Private keys

**Baseline**: `.secrets.baseline` contiene secretos conocidos que son seguros (ej: ejemplos en docs).

### 4. Bandit (Security Linter)

**Repo**: `PyCQA/bandit`

Analiza código Python en busca de vulnerabilidades de seguridad.

**Configuración:**

```yaml
- id: bandit
  args: ["-c", "pyproject.toml"]
  exclude: ^tests/
```

**Detecta:**
- Uso de `eval()`, `exec()`
- SQL injection potencial
- Hardcoded passwords
- Uso inseguro de `pickle`
- Weak crypto
- etc.

## Uso

### Automático (Cada Commit)

Cuando haces `git commit`, los hooks se ejecutan automáticamente:

```bash
git add .
git commit -m "feat: agregar nuevo endpoint"

# Pre-commit ejecuta automáticamente:
# ✓ Trim trailing whitespace
# ✓ Fix end of files
# ✓ Check YAML syntax
# ✓ Ruff linter
# ✓ Ruff formatter
# ✓ Detect secrets
# ✓ Bandit security checks
```

### Manual (Todos los Archivos)

```bash
# Ejecutar en todos los archivos
uv run pre-commit run --all-files

# Ejecutar hook específico
uv run pre-commit run ruff --all-files
uv run pre-commit run bandit --all-files
```

### Skip Hooks (No Recomendado)

```bash
# Saltar pre-commit (SOLO en casos excepcionales)
git commit -m "mensaje" --no-verify
```

**Advertencia**: Solo usa `--no-verify` si realmente es necesario (ej: commit de emergencia).

## Flujo de Trabajo

### Caso 1: Todo OK

```bash
$ git commit -m "feat: agregar endpoint de usuarios"

Trim trailing whitespace.................................................Passed
Fix end of files.........................................................Passed
Check YAML..............................................................Passed
Check TOML..............................................................Passed
Ruff linter.............................................................Passed
Ruff formatter..........................................................Passed
Detect secrets..........................................................Passed
Bandit security checks..................................................Passed

[main a1b2c3d] feat: agregar endpoint de usuarios
 1 file changed, 15 insertions(+)
```

### Caso 2: Auto-fix

```bash
$ git commit -m "feat: agregar endpoint"

Trim trailing whitespace.................................................Failed
- hook id: trailing-whitespace
- files were modified by this hook

Ruff linter.............................................................Failed
- hook id: ruff
- files were modified by this hook

# Los archivos fueron modificados automáticamente
# Re-stage y commit nuevamente

$ git add .
$ git commit -m "feat: agregar endpoint"

Trim trailing whitespace.................................................Passed
Ruff linter.............................................................Passed
# ... resto de checks

[main a1b2c3d] feat: agregar endpoint
 1 file changed, 15 insertions(+)
```

### Caso 3: Error que Requiere Corrección Manual

```bash
$ git commit -m "feat: agregar endpoint"

Bandit security checks..................................................Failed
- hook id: bandit
- exit code: 1

>> Issue: [B108:hardcoded_tmp_directory] Probable insecure usage of temp file/directory.
   Severity: Medium   Confidence: Medium
   Location: app/routes/users.py:15

# Corregir manualmente
$ vim app/routes/users.py

# Re-stage y commit
$ git add .
$ git commit -m "feat: agregar endpoint"
```

## Configuración de Ruff

Puedes configurar Ruff en `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]  # Line too long (si prefieres líneas más largas)

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

## Configuración de Bandit

En `pyproject.toml`:

```toml
[tool.bandit]
exclude_dirs = ["tests", ".venv"]
skips = ["B101"]  # Skip assert_used (útil en tests)
```

## Baseline de Secrets

### Crear/Actualizar Baseline

```bash
# Crear baseline inicial
uv run detect-secrets scan --baseline .secrets.baseline

# Actualizar baseline (después de agregar secretos legítimos)
uv run detect-secrets scan --baseline .secrets.baseline --update
```

### Auditar Secrets

```bash
# Ver todos los secretos detectados
uv run detect-secrets audit .secrets.baseline
```

**Ejemplo de uso:**

1. Detecta "secret" en archivo `.env.example`
2. Marcas como falso positivo en audit
3. No se detectará en futuros commits

## Actualizar Hooks

```bash
# Actualizar versiones de hooks
uv run pre-commit autoupdate

# Verificar que todo funciona
uv run pre-commit run --all-files
```

## CI/CD Integration

Para ejecutar en CI (GitHub Actions, GitLab CI, etc.):

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - run: pip install pre-commit
      - run: pre-commit run --all-files
```

## Troubleshooting

### Pre-commit no se ejecuta

**Problema**: Commits se crean sin ejecutar hooks.

**Solución**:

```bash
# Reinstalar hooks
uv run pre-commit install
```

### Ruff falla en archivos modificados

**Problema**: Ruff modifica archivos y falla.

**Solución**: Es comportamiento esperado. Re-stage y commit:

```bash
git add .
git commit -m "mensaje"
```

### Bandit falso positivo

**Problema**: Bandit reporta falso positivo.

**Solución**: Agregar `# nosec` al final de la línea:

```python
# Ejemplo: hardcoded password en test
TEST_PASSWORD = "test123"  # nosec B105
```

O excluir check específico en `pyproject.toml`:

```toml
[tool.bandit]
skips = ["B105"]  # Skip hardcoded_password_string
```

### Detect-secrets bloquea commit legítimo

**Problema**: Secreto legítimo (ejemplo en docs) bloquea commit.

**Solución**: Actualizar baseline:

```bash
uv run detect-secrets scan --baseline .secrets.baseline --update
uv run detect-secrets audit .secrets.baseline
# Marcar como falso positivo
git add .secrets.baseline
git commit -m "update secrets baseline"
```

## Mejores Prácticas

### 1. Ejecutar Antes de Commit

```bash
# Antes de commit, ejecutar manualmente
uv run pre-commit run --all-files

# Luego commit
git add .
git commit -m "mensaje"
```

### 2. Commits Pequeños

Hacer commits pequeños facilita la corrección de errores detectados por hooks.

### 3. No Saltar Hooks Sin Razón

```bash
# ❌ Evitar
git commit --no-verify

# ✅ Mejor
# Corregir el error que causa que el hook falle
```

### 4. Mantener Hooks Actualizados

```bash
# Mensualmente
uv run pre-commit autoupdate
```

## Recursos

- [Pre-commit Documentation](https://pre-commit.com/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [detect-secrets Documentation](https://github.com/Yelp/detect-secrets)

---

**Siguiente**: [Mejores Prácticas](best-practices.md)
