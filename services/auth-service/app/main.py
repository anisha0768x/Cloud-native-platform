from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Helio Authentication Service", version="1.0.0")
ACCESS = "helio-local-access-token"
REFRESH = "helio-local-refresh-token"
USER = {"id":"usr-anisha","name":"Anisha Verma","email":"operator@helio.dev","role":"Platform Operator","permissions":["services:read","alerts:acknowledge","scaling:trigger","logs:analyze"]}

class Credentials(BaseModel): email: str; password: str
class RefreshRequest(BaseModel): refresh_token: str
def payload(): return {"access_token":ACCESS,"refresh_token":REFRESH,"token_type":"bearer","expires_at":(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(),"user":USER}
def principal(authorization: str | None):
    if authorization != f"Bearer {ACCESS}": raise HTTPException(401,"Invalid or expired access token")

@app.get("/health")
def health(): return {"status":"ok","service":"auth-service"}
@app.post("/api/v1/auth/login")
def login(body: Credentials):
    if body.email != USER["email"] or body.password != "demo123": raise HTTPException(401,"Invalid credentials")
    return payload()
@app.post("/api/v1/auth/refresh")
def refresh(body: RefreshRequest):
    if body.refresh_token != REFRESH: raise HTTPException(401,"Refresh token is invalid")
    return payload()
@app.get("/api/v1/auth/me")
def me(authorization: str | None = Header(default=None)):
    principal(authorization); return USER
@app.get("/api/v1/auth/rbac/check")
def check(permission: str, authorization: str | None = Header(default=None)):
    principal(authorization); return {"allowed": permission in USER["permissions"],"permission":permission,"decision_id":str(uuid4())}
