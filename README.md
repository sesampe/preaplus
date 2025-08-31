# Delirio Picante WhatsApp Bot 🌶️

Un bot de WhatsApp inteligente para Delirio Picante, especializado en atención al cliente para una tienda virtual de salsas picantes. Utiliza inteligencia artificial para responder consultas sobre productos, precios, y características, mientras mantiene una personalidad amigable y profesional.

## Características Principales 🚀

- **Asistente Virtual Inteligente (Kitu 🌶️)**
  - Respuestas contextuales usando GPT-4 y Claude
  - Fallback automático entre proveedores de IA
  - Sistema de retry inteligente para manejar rate limits
  - Personalidad consistente y amigable

- **Integración con WhatsApp Business API**
  - Implementado con la biblioteca Heyoo
  - Manejo de mensajes de texto y audio
  - Envío de catálogos y ubicaciones
  - Notificaciones automáticas al dueño

- **Gestión de Productos**
  - Integración con Google Drive para catálogo
  - Información actualizada de productos y precios
  - Manejo de disponibilidad de stock
  - Compartir ubicaciones de puntos de entrega

- **Características Técnicas**
  - Arquitectura asíncrona con FastAPI
  - Sistema de logging robusto
  - Manejo de errores y recuperación
  - Patrón Singleton para servicios críticos
  - Tipado estático con type hints

## Estructura del Proyecto 📁

```
delirio-bot/
├── main.py                 # Punto de entrada FastAPI
├── api/
│   ├── routes.py          # Endpoints y webhook
│   └── health.py          # Monitoreo de salud
├── core/
│   ├── settings.py        # Configuración y variables de entorno
│   └── logger.py          # Sistema de logging
├── services/
│   ├── llm_client.py      # Cliente de IA (GPT/Claude)
│   ├── drive.py           # Integración con Google Drive
│   └── audio_processing.py # Procesamiento de mensajes de audio
└── requirements.txt        # Dependencias del proyecto
```

## Requisitos Previos 📋

- Python 3.8+
- Cuenta de WhatsApp Business API
- Claves de API para:
  - OpenAI GPT-4
  - Anthropic Claude
  - Google Drive
  - WhatsApp Business API

## Instalación 🛠️

1. **Clonar el repositorio**
```bash
git clone <repository-url>
cd delirio-bot
```

2. **Crear y activar entorno virtual**
```bash
python -m venv venv
# En Windows:
venv\Scripts\activate
# En Unix/MacOS:
source venv/bin/activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**

Crea un archivo `.env` en la raíz del proyecto:
```env
# API Keys
OPENAI_API_KEY=tu_api_key_openai
CLAUDE_API_KEY=tu_api_key_claude
HEYOO_TOKEN=tu_token_whatsapp
HEYOO_PHONE_ID=tu_phone_id

# Configuración
OPENAI_MODEL=gpt-4
CLAUDE_MODEL=claude-3-sonnet-20240229
OWNER_PHONE_NUMBER=tu_numero_telefono

# Google Drive
GOOGLE_CREDENTIALS_PATH=path/to/credentials.json
```

## Uso 🚀

1. **Iniciar el servidor**
```bash
uvicorn main:app --reload
```

2. **Endpoints principales**

- `POST /webhook`: Recibe mensajes de WhatsApp
- `POST /send`: Envía mensajes manuales
- `GET /health`: Estado del servicio

## Características del Asistente Virtual 🤖

Kitu 🌶️ está programado para:

- Responder preguntas sobre productos y precios
- Compartir el catálogo de productos
- Proporcionar información de envíos
- Compartir ubicaciones de puntos de entrega
- Derivar a atención humana cuando sea necesario
- Mantener un tono amigable y profesional

## Contribución 🤝

Si deseas contribuir al proyecto:

1. Haz un Fork del repositorio
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Licencia 📄

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## Contacto 📧

Para soporte o consultas, contacta al equipo de desarrollo.
