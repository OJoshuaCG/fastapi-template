# Comenzar desde 0

Iniciamos `uv`

```
uv init
```

Instalamos FastAPI
```
uv add fastapi[standard]
```

Ejecutamos FastAPI, para acceder a la aplicacion nos dirigimos a [localhost:8000/docs](http://localhost:8000/docs)

```
uv run uvicorn main:app --reload
```

Si lo deseamos, podemos especificar el puerto y permitir el acceso a cualquier host.
Por ejemplo, el siguiente comando nos permitira acceder a traves de [localhost:8080/docs](http://localhost:8080/docs)

```
uv run uvicorn main:app --reload --port 80 --host 0.0.0.0

```
