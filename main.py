from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, APIRouter
from starlette.exceptions import HTTPException

from routes.home import home
from routes.expenditures import expenditures

from templates import templates

app = FastAPI()
root = APIRouter()

home.include_router(expenditures)
root.include_router(home)
app.include_router(root)

app.mount("/static", StaticFiles(directory="static"), name="static")


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
