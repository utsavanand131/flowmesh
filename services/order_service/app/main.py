from fastapi import FastAPI

app = FastAPI(
    title="FlowMesh Order Service",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    return {
        "service": "order-service",
        "status": "healthy",
    }