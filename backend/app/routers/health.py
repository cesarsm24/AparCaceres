from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
def read_root():
    return {"status": "Backend configurado y listo"}
