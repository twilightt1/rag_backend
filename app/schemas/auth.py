from __future__ import annotations
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator


class RegisterRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    message: str


class OTPVerifyRequest(BaseModel):
    email:    EmailStr
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class OTPVerifyResponse(BaseModel):
    message:      str
    access_token: str
    next:         str = "onboarding"


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class OnboardingRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=50)


class OnboardingResponse(BaseModel):
    access_token:  str
    refresh_token: str
    user:          "UserResponse"


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    user:          "UserResponse"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ForgotPasswordOTPVerifyRequest(BaseModel):
    email:    EmailStr
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ForgotPasswordOTPVerifyResponse(BaseModel):
    reset_token: str
    message:     str


class ResetPasswordRequest(BaseModel):
    token:        str
    new_password: str = Field(min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id:              UUID
    email:           str
    display_name:    str | None
    avatar_url:      str | None
    auth_provider:   str
    role:            str
    is_verified:     bool
    onboarding_done: bool
    created_at:      datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=50)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password:     str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_differ(self) -> "ChangePasswordRequest":
        if self.current_password == self.new_password:
            raise ValueError("New password must differ from current password.")
        return self


class ChangePasswordResponse(BaseModel):
    message: str
