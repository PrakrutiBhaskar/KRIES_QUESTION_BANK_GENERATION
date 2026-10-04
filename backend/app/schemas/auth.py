"""Request / response models for /auth."""
from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Deliberately loose: one "@", something on each side, a dot in the domain.
# Real verification is a confirmation email, not a regex.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8
# scrypt has no 72-byte limit like bcrypt, but cap it so a huge body can't be
# used to burn CPU/memory.
MAX_PASSWORD_LENGTH = 128


def _clean_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL_RE.match(v):
        raise ValueError("enter a valid email address")
    return v


class SignUpIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    role: Literal["Teacher", "Student"] = "Teacher"

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _clean_email(v)

    @field_validator("password")
    @classmethod
    def _password_has_letter_and_digit(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("password must contain at least one letter and one number")
        return v


class LoginIn(BaseModel):
    email: str
    # No strength rules here: only sign-up enforces them.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class ForgotPasswordIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _clean_email(v)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=2048)
    # Same strength rules as sign-up.
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def _password_has_letter_and_digit(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("password must contain at least one letter and one number")
        return v


class MessageOut(BaseModel):
    message: str


Theme = Literal["light", "dark", "system"]
Difficulty = Literal["easy", "medium", "hard", "mixed"]
QuestionTypeChoice = Literal["MCQ", "Short", "Long", "Fill", "Match", "Mixed"]
Marks = Literal[1, 2, 3, 5]


class PreferencesOut(BaseModel):
    """What the Settings page edits. Missing keys fall back to these defaults."""

    model_config = ConfigDict(extra="ignore")

    theme: Theme = "light"
    notifications: bool = True
    default_question_count: int = Field(default=10, ge=3, le=30)
    default_difficulty: Difficulty = "mixed"
    default_question_type: QuestionTypeChoice = "Mixed"
    default_marks: Marks = 2


class PreferencesPatch(BaseModel):
    """Any subset of the preferences; omitted keys are left as they are."""

    model_config = ConfigDict(extra="forbid")

    theme: Theme | None = None
    notifications: bool | None = None
    default_question_count: int | None = Field(default=None, ge=3, le=30)
    default_difficulty: Difficulty | None = None
    default_question_type: QuestionTypeChoice | None = None
    default_marks: Marks | None = None


class ProfileUpdateIn(BaseModel):
    """PATCH /auth/me. Only the fields that are sent change.

    `email` is declared only so the endpoint can answer it with a clear 403:
    an account's email address is its identity and can't be edited.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=100)
    role: Literal["Teacher", "Student"] | None = None
    preferences: PreferencesPatch | None = None
    email: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = " ".join(v.split())
        if not v:
            raise ValueError("name must not be blank")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: Literal["Teacher", "Student", "Admin"]
    preferences: PreferencesOut = Field(default_factory=PreferencesOut)

    @field_validator("preferences", mode="before")
    @classmethod
    def _default_preferences(cls, v):
        return {} if v is None else v


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds.")
    user: UserOut
