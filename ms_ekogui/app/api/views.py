from fastapi import APIRouter

from app.api.routes import EkoguiRoutes

apiRouter = APIRouter(prefix="/api/v1")
apiRouter.include_router(EkoguiRoutes.router, tags=["Ekogui"])

def getApiRouter():
    return apiRouter
