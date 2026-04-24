from fastapi import FastAPI

app = FastAPI(
    title="AparCaceres API",
    description="API para localización de aparcamientos públicos en Cáceres usando RedisDB",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {"status": "Backend configurado y listo"}
