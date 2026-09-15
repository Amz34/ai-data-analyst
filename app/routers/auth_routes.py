import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from .. import auth
from ..db import get_db
from ..models import Org, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    org_name: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v):
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("password needs letters and digits")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "org": {"id": user.org.id, "name": user.org.name},
    }


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already registered")
    org = Org(name=body.org_name.strip())
    db.add(org)
    db.flush()
    user = User(
        org_id=org.id,
        email=body.email.lower(),
        name=body.name.strip(),
        hashed_password=auth.hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": auth.create_token(user.id, org.id), "user": _user_payload(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not auth.verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    return {"token": auth.create_token(user.id, user.org_id), "user": _user_payload(user)}


@router.get("/me")
def me(user: User = Depends(auth.get_current_user)):
    return _user_payload(user)
