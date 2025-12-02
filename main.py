from fastapi import FastAPI

app = FastAPI()


@app.get("/test/ping", tags=["test"])
async def ping():
    return {"message": "pong!"}
