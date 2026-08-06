from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.masters.views import (
    ClientCodeViewSet,
    MasterBundleView,
    ProjectViewSet,
    ShiftViewSet,
    WorkTypeViewSet,
    EmployeeSelectionsView,
    ClientCodesForProjectView,
    WorkTypesForClientCodeView,
    EmpGetProjectsView,
    EmpGetClientCodesView,
    EmpGetWorktypesView,
    EmpGetShiftsView,
)

app_name = "masters"

router = DefaultRouter()
router.register("worktypes", WorkTypeViewSet, basename="worktype")
router.register("projects", ProjectViewSet, basename="project")
router.register("clientcodes", ClientCodeViewSet, basename="clientcode")
router.register("shifts", ShiftViewSet, basename="shift")

urlpatterns = [
    path("bundle/", MasterBundleView.as_view(), name="bundle"),
    path("selections/", EmployeeSelectionsView.as_view(), name="selections"),
    path("client_codes_for_project/", ClientCodesForProjectView.as_view(), name="client-codes-for-project"),
    path("work_types_for_client_code/", WorkTypesForClientCodeView.as_view(), name="work-types-for-client-code"),
    path("emp_get_projects/", EmpGetProjectsView.as_view(), name="emp_get_projects"),
    path("emp_get_client_codes/", EmpGetClientCodesView.as_view(), name="emp_get_client_codes"),
    path("emp_get_worktypes/", EmpGetWorktypesView.as_view(), name="emp_get_worktypes"),
    path("emp_get_shifts/", EmpGetShiftsView.as_view(), name="emp_get_shifts"),
    path("", include(router.urls)),
]
