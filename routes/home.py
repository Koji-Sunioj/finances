from fastapi import Request, Depends, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from passlib.context import CryptContext

from templates import templates
from utils.functions import decode_token, create_token, breadcrumbs, execute_db, tx

pwd_context = CryptContext(schemes="sha256_crypt")

home = APIRouter(prefix="/home")


@home.post("/", response_class=HTMLResponse)
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
            return RedirectResponse(
                "/?alert=unauthorized&username=%s" % payload["username"],
                status_code=302)

        case "authenticated" | "new-user":
            token_string = create_token(payload["username"])
            request.state.sub = payload["username"]
            request.state.breadcrumbs = breadcrumbs(str(request.url))
            return templates.TemplateResponse(
                request=request,
                name="home.html",
                headers={"Set-Cookie": token_string},
                context={"username": payload["username"]},
            )


@home.get("/", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
@tx
async def welcome(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html"
    )
