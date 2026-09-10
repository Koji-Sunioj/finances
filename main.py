from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from fastapi import FastAPI, Request, APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from routes.expenditures import expenditures

from templates import templates
from utils.functions import tx, breadcrumbs, create_token, decode_token, cursor

from passlib.context import CryptContext

app = FastAPI()
root = APIRouter()

root.include_router(expenditures)
app.include_router(root)

app.mount("/static", StaticFiles(directory="static"), name="static")

pwd_context = CryptContext(schemes="sha256_crypt")


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    print(exc)
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"status_code": exc.status_code, "error_string": exc.detail},
    )


@root.get("/", response_class=HTMLResponse)
async def sign_in(request: Request, alert: str = None, username: str = None):
    return templates.TemplateResponse(request=request, name="sign-in.html")


@root.post("/", response_class=HTMLResponse)
@tx
async def authenticate(request: Request):
    payload = await request.form()
    account_type = (
        "new-account"
        if "new-account" in payload and payload["new-account"] == "on"
        else "current-user"
    )
    auth_result = "unauthorized"
    user_id = None

    match account_type:
        case "new-account":
            new_user_command = "insert into users (username,password) values (%s,%s) returning username, modified, user_id;"
            cursor.execute(
                new_user_command,
                (payload["username"], pwd_context.hash(payload["password"])),
            )

            if cursor.rowcount > 0:
                auth_result = "new-user"
                user_id = cursor.fetchone()["user_id"]

        case "current-user":
            authenticate_command = (
                "select username, password, user_id from users where username = %s;"
            )
            cursor.execute(authenticate_command, (payload["username"],))
            user = cursor.fetchone()

            pwd_context.verify(payload["password"], user["password"])
            auth_result = "authenticated"
            user_id = user["user_id"]

    match auth_result:
        case "unauthorized":
            return templates.TemplateResponse(
                request=request,
                name="sign-in.html",
                context={"username": payload["username"], "error_code": 401},
                status_code=401,
            )

        case "authenticated" | "new-user":
            token_string = create_token(payload["username"], user_id)
            request.state.sub = payload["username"]
            request.state.breadcrumbs = breadcrumbs(str(request.url))
            request.state.user_id = user_id
            return RedirectResponse(
                "/home", status_code=303, headers={"Set-Cookie": token_string}
            )


@app.get("/home", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
@tx
async def welcome(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")
