from fastapi import FastAPI

app = FastAPI(title="PostMortem API", version="1.0.1")

@app.get("/healthz", status_code=200)
async def health_check():
    return {"status":"ok", "service":"PostMortem"}