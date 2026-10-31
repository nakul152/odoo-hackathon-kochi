from fastapi import APIRouter

from backend.catalog.products import router as products_router
from backend.catalog.plans import router as plans_router
from backend.catalog.templates import router as templates_router

router = APIRouter()
router.include_router(products_router)
router.include_router(plans_router)
router.include_router(templates_router)