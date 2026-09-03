from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, APIRouter
from starlette.exceptions import HTTPException as StarletteHTTPException

from routes.home import home
from routes.expenditures import expenditures

from templates import templates
from functools import wraps


def something(function):
    @wraps(function)
    async def transaction(*args, **kwargs):
        try:
            print("asd")
            executed = await function(*args, **kwargs)
            return executed
        except Exception as error:
            print(error)

    return transaction


app = FastAPI()
root = APIRouter()

home.include_router(expenditures)
root.include_router(home)
app.include_router(root)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    match exc.status_code:
        case 403:
            return templates.TemplateResponse(
                request=request,
                name="403.html"
            )
        case _:
            return templates.TemplateResponse(
                request=request,
                name="404.html"
            )


@root.get("/", response_class=HTMLResponse)
async def sign_in(request: Request, alert: str = None, username: str = None):
    if alert == "unauthorized" and username != None:
        return templates.TemplateResponse(
            request=request,
            name="sign-in.html",
            context={"username": username, "alert": alert},
        )
    return templates.TemplateResponse(request=request, name="sign-in.html")
