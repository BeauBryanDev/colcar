#
# MongoDB collection models -- the durable shape of an inspection and an
# appointment. Plain pydantic, not an ORM.

from app.models.appointment import AppointmentDocument, CarInfo, Customer
from app.models.inspection import DefectRecord, InspectionDocument
from app.models.user import UserDocument, UserRole, normalize_username

__all__ = [
    "AppointmentDocument",
    "CarInfo",
    "Customer",
    "DefectRecord",
    "InspectionDocument",
    "UserDocument",
    "UserRole",
    "normalize_username",
]
