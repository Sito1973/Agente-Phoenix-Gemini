import json
import requests
import uvicorn
from bot import run_bot
from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from fastapi import FastAPI, Request
import os
import re
import bot

from starlette.responses import JSONResponse, HTMLResponse

from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv(override=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_system_instruction(caller_value: str) -> str:
    # Obtiene la ruta del archivo instructions.txt
    instructions_path = os.path.join(os.path.dirname(__file__), "instructions.txt")
    with open(instructions_path, "r", encoding="utf-8") as file:
        content = file.read()

    # Define un diccionario con las variables a reemplazar
    variables = {
        "caller": caller_value
    }

    # Patrón para detectar placeholders como {{caller}}
    pattern = re.compile(r'\{\{(\w+)\}\}')

    def replace_placeholder(match):
        key = match.group(1)
        return str(variables.get(key, "[UNDEFINED]"))

    # Realiza la sustitución
    return pattern.sub(replace_placeholder, content)

def caller_normalized(caller: str) -> str:
    digits = "".join(filter(str.isdigit, caller))
    return digits[-10:]



@app.post("/")
async def start_call(request: Request):
    form_data = await request.form()
    data = dict(form_data)
    caller_number = data.get("Caller")
    print("Datos de Twilio:", data)

    normalized = caller_normalized(caller_number)
    bot.caller_phone = normalized
    bot.system_instruction = get_system_instruction(normalized)


    return HTMLResponse(
        content=open("templates/streams.xml").read(),
        media_type="application/xml"
    )



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    start_data = websocket.iter_text()
    await start_data.__anext__()
    call_data = json.loads(await start_data.__anext__())
    print(call_data, flush=True)
    stream_sid = call_data["start"]["streamSid"]
    print("WebSocket connection accepted")
    await run_bot(websocket, stream_sid)


@app.post("/outbound")
async def outbound_call(request: Request):
    try:
        # Suponiendo que recibes JSON con la clave "to_number"
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Formato de entrada no válido. Se espera JSON.")

    to_number = data.get("to_number")
    if not to_number:
        raise HTTPException(status_code=400, detail="El número de destino ('to_number') es requerido.")

    # Configuración de Twilio
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        raise HTTPException(status_code=500, detail="Credenciales de Twilio no configuradas correctamente.")
    client = Client(account_sid, auth_token)

    try:
        call = client.calls.create(
            twiml=open("templates/streams.xml").read(),
            to=to_number,
            from_=os.environ["TWILIO_PHONE_NUMBER"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear la llamada: {e}")

    return JSONResponse({"call_sid": call.sid})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
