from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from security import verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["Autentikasi"])


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
        )
    token = create_access_token({"sub": user.username})
    return schemas.Token(
        access_token=token,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )
