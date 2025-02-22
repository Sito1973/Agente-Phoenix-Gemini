import os
import sys
import requests
import json
import asyncio

from dotenv import load_dotenv
from loguru import logger
from datetime import datetime

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.serializers.twilio import TwilioFrameSerializer

from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.services.gemini_multimodal_live.gemini import GeminiMultimodalLiveLLMService

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class N8nAPI:
    def __init__(self):
        self.crear_pedido_webhook_url = os.environ.get("N8N_CREAR_PEDIDO_WEBHOOK_URL")
        # Puedes añadir más URLs de webhook si lo necesitas
        logger.info("Inicializado N8nAPI con las URLs")

    def crear_pedido(self, payload):
        """Envía el pedido al webhook de n8n"""
        logger.debug("Enviando pedido a n8n con payload: %s", payload)
        response = requests.post(self.crear_pedido_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar pedido: %s %s",
                    response.status_code, response.text)
        return response

# Carga las instrucciones desde instructions.txt
instructions_path = "instructions.txt"
if os.path.exists(instructions_path):
    with open(instructions_path, "r", encoding="utf-8") as file:
        system_instruction = file.read()
else:
    system_instruction = "Task description: Default instruction text"

# Carga la configuración de tools desde tools_crear_pedido.json
tools_file = "tools_crear_pedido.json"
if os.path.exists(tools_file):
    with open(tools_file, "r", encoding="utf-8") as f:
        tools = json.load(f)
else:
    tools = []

# Función síncrona que contiene la lógica actual de crear_pedido
def _crear_pedido_sync(nombre_cliente: str, pedido_cliente: str, valor_total: float) -> str:
    logger.info(f"Iniciando crear_pedido para {nombre_cliente} con pedido: {pedido_cliente}, total: {valor_total}")
    try:
        n8n_api = N8nAPI()
        payload =  {
                "tool_code": "crear_pedido",
                "datos": {
                    "nombre_cliente": nombre_cliente,
                    "pedido_cliente": pedido_cliente,
                    "valor_total": valor_total
                }
            }
        
        logger.debug(f"Payload enviado a n8n: {payload}")
        response = n8n_api.crear_pedido(payload)
        if response.status_code in [200, 201]:
            return f"Pedido creado exitosamente para {nombre_cliente}. Recibirás un mensaje por WhatsApp con las formas de pago."
        else:
            logger.error(f"Error al enviar pedido a n8n: {response.text}")
            return "Lo siento, hubo un problema al crear tu pedido. Por favor, intenta de nuevo."
    except Exception as e:
        logger.exception(f"Error en crear_pedido: {e}")
        return "Ocurrió un error al procesar tu pedido. Por favor, intenta más tarde."

# Wrapper asíncrono que ejecuta la función síncrona en un hilo separado
async def crear_pedido(nombre_cliente: str, pedido_cliente: str, valor_total: float, *args, **kwargs) -> str:
    return await asyncio.to_thread(_crear_pedido_sync, nombre_cliente, pedido_cliente, valor_total)

async def run_bot(websocket_client, stream_sid):
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=TwilioFrameSerializer(stream_sid),
        ),
    )

    llm = GeminiMultimodalLiveLLMService(
        api_key=os.environ['GOOGLE_API_KEY'],
        system_instruction=system_instruction,
        tools=tools,
        voice_id="Charon",                    # Voices: Aoede, Charon, Fenrir, Kore, Puck
        transcribe_user_audio=False,          # Enable speech-to-text for user input
        transcribe_model_audio=False,         # Enable speech-to-text for model responses
    )
    llm.register_function("crear_pedido", crear_pedido)

    context = OpenAILLMContext(
        [{"role": "user", "content": "Hola gracias por comunicarte a Bandidos, como te puedo colaborar?"}],
    )
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            # stt,  # Speech-To-Text
            context_aggregator.user(),
            llm,  # LLM
            # tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
