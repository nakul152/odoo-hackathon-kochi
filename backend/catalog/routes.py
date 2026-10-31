from fastapi import APIRouter, Depends

from backend.security import require_roles
from backend.catalog.products import router as products_router
from backend.catalog.plans import router as plans_router
from backend.catalog.templates import router as templates_router
from backend.catalog.subscriptions import router as subscriptions_router

# only logged-in admins and staff can use these routes
staff_only = [Depends(require_roles("admin", "staff"))]

router = APIRouter()
router.include_router(products_router, dependencies=staff_only)
router.include_router(plans_router, dependencies=staff_only)
router.include_router(templates_router, dependencies=staff_only)
router.include_router(subscriptions_router, dependencies=staff_only)