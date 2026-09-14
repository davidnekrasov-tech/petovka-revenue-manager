from fastapi import FastAPI

app = FastAPI(title="Petrovka Revenue Manager")


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Petrovka Revenue Manager"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
