"""Domain exceptions and their FastAPI handlers.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base for every expected failure.

    detail is shown to the customer; log_message carries the technical
    context that must not be.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "error_interno"
    detail: str = "Ocurrio un error procesando la solicitud."

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        log_message: str | None = None,
    ) -> None:
        
        self.detail = detail or self.detail
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.log_message = log_message or self.detail
        super().__init__(self.log_message)

    def to_payload(self) -> dict:
        return {"detail": self.detail, "code": self.code}


#  Session / request lifecycle  
class SessionNotFoundError(AppError):
    
    status_code = status.HTTP_404_NOT_FOUND
    code = "sesion_no_encontrada"
    detail = "La sesion de inspeccion no existe o ya expiro."


class SessionStateError(AppError):
    """Valid session, wrong state -- e.g. /run before any upload."""

    status_code = status.HTTP_409_CONFLICT
    code = "estado_invalido"
    detail = "La inspeccion no esta en un estado valido para esta operacion."


#   Uploads  
class InvalidUploadError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "archivo_invalido"
    detail = "El archivo enviado no es una imagen valida."


class UploadTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "archivo_muy_grande"
    detail = "La imagen supera el tamano maximo permitido."


#  Vision  
class VisionModelError(AppError):
    """An ONNX model failed to load or infer."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "modelo_vision_no_disponible"
    detail = "El servicio de analisis de imagenes no esta disponible en este momento."


class NoDetectionsError(AppError):
    """Inference ran but found nothing usable.

    Not a server fault -- usually a photo of something that isn't a car, or one
    too dark to read -- so it asks the user for a better image.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "sin_detecciones"
    detail = (
        "No se detectaron piezas del vehiculo en las imagenes. "
        "Intenta con fotos mas claras y a mayor distancia."
    )


#   Knowledge layer 
class ComplianceUnavailableError(AppError):
    """Qdrant unreachable or the embedder failed to load.

    The inspection can still produce a diagnosis and a quote, so callers should
    prefer degrading (skip the legal section) over failing the whole request.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "compliance_no_disponible"
    detail = "No se pudo consultar la normativa RTM en este momento."


class PricingCatalogError(AppError):
    """The catalog JSON is missing or malformed -- a deploy problem."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "catalogo_precios_no_disponible"
    detail = "No se pudo consultar el catalogo de precios en este momento."


#   Agent  
class AgentError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "agente_no_disponible"
    detail = "El asistente no pudo generar una respuesta. Intenta de nuevo."


class AgentLoopLimitError(AgentError):
    """Tool-use loop hit `settings.anthropic_max_tool_iterations`.

    Means the model kept calling tools without concluding; returning an error
    beats billing an unbounded loop.
    """

    code = "limite_iteraciones_agente"
    detail = "El asistente no pudo completar el analisis. Intenta de nuevo."


#   Handlers  
async def app_error_handler(request: Request, 
                            exc: AppError
                            ) -> JSONResponse:
    # 5xx is our fault and gets a stack trace; 4xx is the caller's and doesn't.
    log = logger.exception if exc.status_code >= 500 else logger.warning
    log(
        "%s %s -> %s (%s): %s",
        request.method, 
        request.url.path, 
        exc.status_code, 
        exc.code, 
        exc.log_message,
    )
    
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


async def validation_error_handler(
                request: Request, 
                exc: RequestValidationError
            ) -> JSONResponse:
    """FastAPI's 422 body is a list of dicts; the frontend expects a string."""
    logger.warning(
        "%s %s -> 422 validation: %s",
        request.method, 
        request.url.path, 
        jsonable_encoder(exc.errors()),
    )
    fields = ", ".join(
        str(e.get("loc", ["?"])[-1]) for e in exc.errors()
    ) or "desconocido"
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": f"Datos invalidos en la solicitud: {fields}.",
            "code": "solicitud_invalida",
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort. Never leaks the exception text to the client."""
    logger.exception("%s %s -> unhandled %s", 
                     request.method, 
                     request.url.path,
                     type(exc).__name__
                     )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Ocurrio un error inesperado. Intenta de nuevo.",
            "code": "error_interno",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Call from `app/main.py` right after creating the FastAPI instance."""
    
    app.add_exception_handler(AppError, app_error_handler)
    
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    
    app.add_exception_handler(Exception, unhandled_error_handler)
