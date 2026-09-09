from fastapi.responses import HTMLResponse
from fastapi import Request, Depends, APIRouter

from templates import templates
from utils.functions import decode_token, tx

home = APIRouter(prefix="/home")

@home.get("/", response_class=HTMLResponse, dependencies=[Depends(decode_token)])
@tx
async def welcome(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html"
    )
