from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from routes.home import home
from routes.expenditures import expenditures

from templates import templates
from utils.functions import tx, execute_db, breadcrumbs, create_token

from passlib.context import CryptContext

app = FastAPI()
root = APIRouter()

home.include_router(expenditures)
root.include_router(home)
app.include_router(root)

app.mount("/static", StaticFiles(directory="static"), name="static")

pwd_context = CryptContext(schemes="sha256_crypt")


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"status_code": exc.status_code, "error_string": exc.detail}
    )


@root.get("/", response_class=HTMLResponse)
async def sign_in(request: Request, alert: str = None, username: str = None):
    if alert == "unauthorized" and username != None:
        return templates.TemplateResponse(
            request=request,
            name="sign-in.html",
            context={"username": username, "alert": alert},
        )
    else:
        return templates.TemplateResponse(request=request, name="sign-in.html")


@root.post("/", response_class=HTMLResponse)
@tx
async def authenticate(request: Request):
    payload = await request.form()
    account_type = "new-account" if "new-account" in payload and payload["new-account"] == "on" else "current-user"
    auth_result = "unauthorized"

    match account_type:
        case "new-account":
            new_user_command = "insert into users (username,password) values (%s,%s) returning username,created;"
            cursor = execute_db(
                new_user_command,
                (payload["username"], pwd_context.hash(payload["password"])),
            )

            if cursor.rowcount > 0:
                auth_result = "new-user"

        case "current-user":
            authenticate_command = (
                "select username, password from users where username = %s;"
            )
            cursor = execute_db(authenticate_command, (payload["username"],))
            user = cursor.fetchone()

            if cursor.rowcount > 0:
                authenticated = pwd_context.verify(
                    payload["password"], user["password"])

                if authenticated:
                    auth_result = "authenticated"

    match auth_result:
        case "unauthorized":
            return templates.TemplateResponse(request=request, name="sign-in.html", 
                context={"username": payload["username"], "error_code": 401}, status_code=401)

        case "authenticated" | "new-user":
            token_string = create_token(payload["username"])
            request.state.sub = payload["username"]
            request.state.breadcrumbs = breadcrumbs(str(request.url))
            return RedirectResponse(
                "/home",
                status_code=303, headers={"Set-Cookie": token_string})
