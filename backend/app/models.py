from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, StringConstraints, model_validator


class Status(str, Enum):
    RUNNING = "RUNNING"
    DOWN = "DOWN"
    IDLE = "IDLE"
    SETUP = "SETUP"
    TESTING = "TESTING/RECOVERY"


class Role(str, Enum):
    OPERATOR = "operator"
    TECHNICIAN = "technician"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


CATEGORIES = ["Feeder", "Nozzle / Head", "Vision / Camera", "Conveyor / Transport", "Motion / Servo",
              "Pneumatic / Vacuum", "Electrical", "Software / Program", "Material", "Process / Quality",
              "Other", "Unclassified"]
Category = Literal[tuple(CATEGORIES)]

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class ProblemIn(BaseModel):
    description: Text
    category: Category = "Unclassified"
    root_cause: OptText = ""


class ProblemUpdate(BaseModel):
    description: Optional[Text] = None
    category: Optional[Category] = None
    root_cause: Optional[OptText] = None
    status: Optional[Literal["OPEN", "RESOLVED"]] = None
    expected_revision: int  # rejects edits made from a stale screen


class StatusChange(BaseModel):
    status: Status
    note: OptText = ""
    # Used only when this change opens a downtime event:
    problem: Optional[ProblemIn] = None
    occurred_at: Optional[AwareDatetime] = None


class ActionIn(BaseModel):
    type: Literal["TROUBLESHOOTING", "CORRECTIVE"]
    description: Text


class PartIn(BaseModel):
    part_name: Name
    part_number: OptText = ""
    quantity: int = Field(1, ge=1, le=10000)
    source: Literal["STORE", "DONOR_MACHINE", "OTHER"] = "STORE"
    donor_machine: OptText = ""
    donor_details: OptText = ""

    @model_validator(mode="after")
    def donor_required(self):
        if self.source == "DONOR_MACHINE" and not self.donor_machine:
            raise ValueError("Donor machine is required when the part comes from a donor machine")
        return self


class AttendanceIn(BaseModel):
    technician_name: Optional[Name] = None  # defaults to the signed-in user
    arrived_at: Optional[AwareDatetime] = None
    note: OptText = ""


class CheckoutIn(BaseModel):
    left_at: Optional[AwareDatetime] = None


class RecoveryIn(BaseModel):
    production_confirmed: bool
    verification_note: Text
    recovered_at: Optional[AwareDatetime] = None


def within_bcrypt_limit(value: str) -> str:
    if len(value.encode()) > 72:
        raise ValueError("Password is too long (72 bytes maximum)")
    return value


NewPassword = Annotated[str, Field(min_length=10), AfterValidator(within_bcrypt_limit)]


class LoginIn(BaseModel):
    username: Name
    password: str = Field(min_length=1, max_length=72)


class UserIn(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9._-]{3,40}$")]
    full_name: Name
    role: Role
    password: NewPassword


class UserUpdate(BaseModel):
    full_name: Optional[Name] = None
    role: Optional[Role] = None
    active: Optional[bool] = None
    password: Optional[NewPassword] = None


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=72)
    new_password: NewPassword
