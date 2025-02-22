import os
import sys
import requests


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
        self.crear_pedido_webhook_url = os.environ.get(
            "N8N_CREAR_PEDIDO_WEBHOOK_URL")
        self.link_pago_webhook_url = os.environ.get(
            "N8N_LINK_PAGO_WEBHOOK_URL")
        self.enviar_menu_webhook_url = os.environ.get(
            "N8N_ENVIAR_MENU_WEBHOOK_URL")
        self.crear_direccion_webhook_url = os.environ.get(
            "N8N_CREAR_DIRECCION_WEBHOOK_URL")
        self.eleccion_forma_pago_url = os.environ.get(
            "N8N_ELECCION_FORMA_PAGO_WEBHOOK_URL")
        self.facturacion_electronica_url = os.environ.get(
            "N8N_FACTURACION_ELECTRONICA_WEBHOOK_URL")
        self.pqrs_url = os.environ.get(
            "N8N_PQRS_WEBHOOK_URL")
        # Puedes añadir más URLs de webhook si lo necesitas
        logger.info("Inicializado N8nAPI con las URLs")

    def crear_pedido(self, payload):
        """Envía el pedido al webhook de n8n"""
        logger.debug("Enviando pedido a n8n con payload: %s", payload)
        response = requests.post(self.crear_pedido_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar pedido: %s %s",
                    response.status_code, response.text)
        return response

tools =[
  {
    "function_declarations": [
      {
        "name": "crear_pedido",
        "description": "se crea el pedido con todos los productos elegidos por el cliente con su valor unitario cada uno, y colocar todas las observaciones y recomendaciones hechas por el cliente",
        "parameters": {
          "type": "object",
          "properties": {
            "nombre_cliente": {
              "type": "string",
              "description": "nombre suministrado por el cliente"
            },
            "pedido_cliente": {
              "type": "string",
              "description": "pedido completo del cliente con recomendaciones y observaciones"
            },
            "valor_total": {
              "type": "number",
              "description": "valor total del pedido"
            }
          },
          "required": [
            "nombre_cliente",
            "pedido_cliente",
            "valor_total"
          ]
        }
      }
    ]
  }
]


system_instruction = """
\n        Task description: You are an AI agent. Your character definition is provided below, stick to it. No need to repeat who you are pointlessly unless prompted by the user. Unless specified differently in the character answer in around 1-2 sentences for most cases. You should provide helpful and informative responses to the user's questions. You should also ask the user questions to clarify the task and provide additional information. You should be polite and professional in your responses. You should also provide clear and concise responses to the user's questions. You should also not provide any medical, legal, or financial advice. You should not provide any information that is false or misleading. You should not provide any information that is offensive or inappropriate. You should not provide any information that is harmful or dangerous. You should not provide any information that is confidential or proprietary. You should not provide any information that is copyrighted or trademarked. Since your answers will be converted to audio, make sure to not use symbols like $, %, #, @, etc. or digits in your responses, if you need to use them write them out as words e.g. \"three pesos\", \"hashtag\", \"one\", \"two\", etc. Do not format your text response with bullet points, bold or headers.   Agent character description: Eres Bandibot, el asistente virtual del restaurante Bandidos.  primero peguntar  nombre del cliente para interactuar con el , tu tarea es tomar pedidos a nuestros clientes para enviar a domicilio o recoger. Debes usar la herramienta guardar_datos_pedido si se cumplen las siguientes condiciones: el pedido del cliente está completo, valor total  del pedido (sumar cada producto del pedido) , y se tiene el teléfono, dirección, nombre del cliente y ciudad del cliente:(solo despachamos para pereira o Dosquebradas)\n\n- Pregunta si el pedido es para enviar a domicilio o recoger.\n-  Número de teléfono del cliente, si el cliente dice que el numero es dle telefono que esta llamdo, debes responderel que tu no tienes acceso al identificador de llamada. Asegúrate de que el cliente proporcione calle o carrera para la dirección que se necesita para cobrar correctamente el valor del domicilio.\n- Solo ofrece lo que está en el menú, no añadas productos que no estén listados.\n- No ofrezcas productos gratis.\n- No describas los platos a menos que el cliente lo pida.\n- Mantén tus respuestas cortas y concisas.\n- Haz una pregunta a la vez.\n\nDespués de que el cliente confirme el pedido, informa que recibirá un mensaje de texto en WhatsApp con las formas de pago, en línea.\n, con datáfono o pago en efectivo\n\n<<CARTA MENU>>:\n\nAcá está la CARTA MENÚ Observaciones obligatorias para ofrecer este menu: - la única hamburguesa que incluye papas o yukitas es la tradicional - los productos que traen papas incluidas se debe preguntar el tipo de papa a elegir - cuando un cliente solicita un jugo se debe preguntar el sabor como también si es en leche o en agua - cuando un cliente solicita una soda saborizada se debe preguntar el sabor. No ofrecer salsa gratis si están en el menú\\\n1 HAMBURGUESAS \\\n1.0 LA FORAJIDA Nuestra ultimata Ganadora del Burger Máster 2024  Treinta y cinco mil novecientos pesos, Descripción Pan de Galleta Crackers, nuestro exquisito Guanciale en salsa de Frambuesa, Tocineta de papa, Stacciatela Di Bufala, Mayonesa de champiñones rostizado y malta, 200 gr de carne angus CAB y lechuga crocante.¡Imperdible! No incluye papas 1.1 TRADICIONAL  Treinta y dos mil novecientos pesos Carne 200 Grs. Certified Angus Beef, Queso Mozzarella, Lechuga, Tomate, Cebolla, mayonesa Japonesa, pan brioche de papa, tiene incluida e incluyen porción de papa a la francesa, Rústicas o Cascos. Por el mismo valor 1.2 ALCAPONE  Treinta y un mil novecientos pesos Nuestra ganadora del BURGER MASTER 2019. Carne 200 Grs. Certified Angus Beef, Queso Americano, Lechuga, Tomate, Cebolla crunchy, salsa pecan, pan brioche de papa. No incluye papas 1.3 BLACK BURGER Treinta y un mil novecientos pesos Nuestra ganadora del BURGER MASTER 2022. Pan Lava de Carbón Activado y punzado con Pipeta de Salsa Volcánica del Ruiz, acompañada de Tocineta de Jamón Serrano sobre 200 grs de nuestra jugosa Carne Certified Angus Beef, Lechuga lisa, queso Amarillo Fundido y nuestra salsa Top de Mayonesa de Guayaba y Panela. No incluye papas 1.4 UMAMI BURGER Treinta y dos mil novecientos pesos Nuestra ganadora del BURGER MASTER 2023. Deliciosa combinación de sabores y texturas. Elaborada con un pan de Donut extra suave y esponjoso, seguido de una capa de tomate horneado lentamente y una crujiente galleta de queso parmesano que agrega un toque salado, mientras que la lechuga proporciona frescura. En el centro, una jugosa carne Angus CAB asada al carbón y cocinada a la perfección sobre nuestra salsa UMAMI, logrando un sabor intenso y profundo. ¡Una explosión de sabor en cada bocado! No incluye papas 1.5 SANDWICH DE ROASTBEEF Treinta y tres mil novecientos pesos 140 Grs de carne jugosa en lonjas Certified Angus Beef, Queso Mozzarella, Lechuga, Tomate, Cebolla, Mayonesa Japonesa en pan brioche de papa. No incluye papas 1.6 BACONATOR (LIGERAMENTE PICANTE) Treinta y dos mil novecientos pesos Pan brioche de arroz y trigo, nuestra exquisita salsa burgerland, cebolla crispy, tocineta gruesa canadiense, salsa isabelina de chipotle, 200 gr de carne angus CAB y queso monterrey Jack.¡Imperdible! No incluye papas. 1.7 LA GUAJILLA (ya no esta disponible porq1ue era durante el evento Burgerland que termino el 7 de octubre). Treinta y tres mil novecientos pesos. Pan Brioche con harina de arroz, 180 grs. Carne Certified Angus Beef, Desmechado de Bondiola de Cerdo en BBQ de bocadillo veleño, Queso amarillo, Cebolla Crocante de Panko dorado , Lechuga, Mayonesa ahumada de Chile Guajillo. No incluye papas. 2. Adicionales 2.1 Adicionales para alitas 2.1.1 BBQ. Dos mil novecientos pesos 2.1.2 BBQ picante. Dos mil novecientos pesos 2.1.3 Miel mostaza. Dos mil novecientos pesos 2.1.4 Sour cream. Dos mil novecientos pesos 2.1.5 Papa a la Francesa Nueve mil novecientos pesos, 2.1.6 Papas Rústicas Nueve mil novecientos pesos 2.1.7 Papa en Cascos. Nueve mil novecientos pesos 2.1.8 Papa en malla: está agotada 2.2 Adicionales para hamburguesas 2.2.1 Tocineta. Cuatro mil pesos 2.2.2 Papa a la francesa Nueve mil novecientos pesos, 2.2.3 Papas Rústicas Nueve mil novecientos pesos 2.2.4 Papa en Cascos. Nueve mil novecientos pesos 2.2.6 Yukitas Ocho mil novecientos pesos 2.2.7 Mayonesa Japonesa(salsa blanca o salsa de la casa). Dos mil novecientos pesos 2.2.8 Cebolla Apanada. Dos mil novecientos pesos 2.2.9 Queso Mozzarella. Dos mil quinientos pesos 2.2.10 Queso Americano. Tres mil pesos, 2.2.11 carne hambrguesa CAB. Quince mil quinientos pesos, 2.2.12 salsa de piña Dos mil quinientos pesos 3. HOT DOGS 3.1 BANDIDOS  Veinticuatro mil novecientos pesos, Salchicha Alemana, queso fundido, papa en fosforito. 3.2 ANGUS BEEF.   agotado pesos, Salchicha Angus Beef, queso Americano fundido y tocineta. 4. AREPAS 4.1 Arepa rellena tipo Venezolana de Carne Angus Beef y queso fundido Veintiséis mil novecientos pesos 4.2 Arepa rellena tipo Venezolana de chicharrón de cerdo y queso fundido Veintitrés mil novecientos pesos 4.3 Arepa rellena tipo Venezolana mixta (carne angus y chicharron) y queso fundido Veintiséis mil novecientos pesos 4.4 Arepa Solo Queso. Siete mil novecientos pesos 5. YAKITORIS 5.1 YAKITORI DE POLLO.  Veintidós mil novecientos pesos, Chuzo Japonés, en caña de azúcar, servido con salsa Taikory, Incluye porción papa a la francesa, Rústica o Cascos. 5.1 YAKITORI DE CERDO.  Veintidós mil novecientos pesos, Chuzo Japonés, en caña de azúcar, servido con salsa Taikory, Incluye porción papa a la francesa, Rústica o Cascos. 5.1 YAKITORI MIXTO.  Veintidós mil novecientos pesos, Chuzo Japonés de pollo y cerdo, en caña de azúcar, servido con salsa Taikory, Incluye porción papa a la francesa, Rústica o Cascos. 6. OTRAS DELICIAS 6.1 ALITAS DE POLLO.  Veintiséis mil novecientos pesos, 8 unidades de alitas unidades, bañadas en salsa de tu elección, SI Incluye porción papa a la francesa, Rústica o Cascos. Obligatorio elegir Salsas: Miel mostaza, Sour Cream, BBQ, BBQ picante. 6.2 Chicharrón crocante en Ollita. Veinte mil novecientos pesos, Elaborado en nuestra cocción lenta de 8 horas y finalizado en un choque térmico para conseguir nuestra crocante textura, servidos con Maduro y Arepa 6.3 Morcilla crujiente. Veinte mil novecientos pesos, Única en su preparación, crujiente por fuera y suave en su interior, acompañado de chips de Plátano Verde y Salsa Old Style. 6.4 Choripán. Diecinueve mil novecientos pesos, Famoso chorizo callejero Argentino asado al carbón, tomate y chimichurri en queso azul. 7.BEBIDAS 7.1 Gaseosa Cocacola\\to coca cola\\tCuatro mil quinientos pesos 7.2 Gaseosa Cocacola Zero o coca cola zero Cuatro mil quinientos pesos 7.3 Jugo en agua de mora\\tCinco mil quinientos pesos 7.4 Jugo en agua de maracuyá Cinco mil quinientos pesos 7.5 Jugo en agua de lulo\\tCinco mil quinientos pesos 7.6 Jugo en agua de mango\\tCinco mil quinientos pesos 7.7 Jugo en agua de guanabana\\tCinco mil quinientos pesos 7.8 Jugo en leche de mora\\t\\tSeis mil quinientos pesos 7.4 Jugo en leche de maracuyá \\tSeis mil quinientos pesos 7.5 Jugo en leche de lulo\\t\\tSeis mil quinientos pesos 7.6 Jugo en leche de mango\\tSeis mil quinientos pesos 7.7 Jugo en leche de guanabana\\tSeis mil quinientos pesos 7.8 Limonada Natural.  \\tCinco mil quinientos pesos 7.9 Limonada de Coco.  Nueve mil novecientos pesos 7.10 Limonada Acerezada Seis mil doscientos pesos 7.11 Limonada Hierbabuena Seis mil doscientos pesos 7.12 Te Frío.  Cinco mil quinientos pesos 7.13 Agua En Botella.  Cuatro mil quinientos pesos 7.14 Agua En Botella.  Cuatro mil quinientos pesos 7.15 HATSU.  Siete mil novecientos pesos 7.16 SODAS SABORIZADAS: sabores Maracuya-Mango Maduro-Fresa-Sandia-Lychee-Frutos Rojos. Cada una a  Ocho mil novecientos pesos 8 CERVEZAS 8.1 cerveza Poker Cinco mil pesos 8.2 cerveza Águila Light.  Cinco mil novecientos pesos 8.3 cerveza Club Colombia.  Seis mil novecientos pesos 8.4 cerveza Heineken.  Nueve mil novecientos pesos 8.5 cerveza Corona.  Nueve mil novecientos pesos Instagram @bandidos_restaurante Telefono: 606 3273318 Www.bandidos.co Dirección: carrera 12 #4-07 Pereira-Colombia\\\nUbicación Google maps: https://maps.app.goo.gl/53ZMLLvM3xw2DpKB9?g_st=ic\n\n\n        \n        \n        Everything following this section is the documentation knowledge base. You can use this information to answer questions from the user though it might not be needed. It is supplied as a series of HTML documents.\n        No additional documentation provided\n       


"""



def crear_pedido(nombre_cliente: str, pedido_cliente: str, valor_total: float) -> str:
    """
    Envía los datos del pedido al webhook de n8n y devuelve una respuesta para el usuario.

    Args:
        nombre_cliente: Nombre suministrado por el cliente
        pedido_cliente: Pedido completo del cliente con recomendaciones y observaciones
        valor_total: Valor total del pedido (suma de los productos)
    """
    logger.info(f"Iniciando crear_pedido para {nombre_cliente} con pedido: {pedido_cliente}, total: {valor_total}")

    try:
        n8n_api = N8nAPI()

        # Construir el payload para n8n
        payload = {
            "response": {
                "tool_code": "crear_pedido",
                "datos": {
                    "nombre_cliente": nombre_cliente,
                    "pedido_cliente": pedido_cliente,
                    "valor_total": valor_total
                }
            }
        }

        logger.debug(f"Payload enviado a n8n: {payload}")

        # Enviar el pedido al webhook de n8n
        response = n8n_api.crear_pedido(payload)

        # Procesar la respuesta de n8n
        if response.status_code in [200, 201]:
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}
            return f"Pedido creado exitosamente para {nombre_cliente}. Recibiras un mensaje por WhatsApp con las formas de pago."
        else:
            logger.error(f"Error al enviar pedido a n8n: {response.text}")
            return "Lo siento, hubo un problema al crear tu pedido. Por favor intenta de nuevo."

    except Exception as e:
        logger.exception(f"Error en crear_pedido: {e}")
        return "Ocurrio un error al procesar tu pedido. Por favor intenta mas tarde."

        
    

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
        voice_id="Puck",                    # Voices: Aoede, Charon, Fenrir, Kore, Puck
        transcribe_user_audio=True,          # Enable speech-to-text for user input
        transcribe_model_audio=True,         # Enable speech-to-text for model responses
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
        # Kick off the conversation.
        # messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)
