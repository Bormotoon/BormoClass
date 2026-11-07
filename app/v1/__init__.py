from fastapi import APIRouter

from app.v1.router_users import router as users_router
from app.v1.router_courses import router as courses_router
from app.v1.router_roster import router as roster_router
from app.v1.router_announcements import router as announcements_router
from app.v1.router_classwork import router as classwork_router
from app.v1.router_submissions import router as submissions_router
from app.v1.router_rubrics_grades import router as rubrics_grades_router

v1_router = APIRouter()

v1_router.include_router(users_router)
v1_router.include_router(courses_router)
v1_router.include_router(roster_router)
v1_router.include_router(announcements_router)
v1_router.include_router(classwork_router)
v1_router.include_router(submissions_router)
v1_router.include_router(rubrics_grades_router)
