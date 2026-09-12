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
class CarSpecsUnavailableError(AppError):
    """API Ninjas could not be queried (no key, network, non-2xx).

    Raised as an AppError so the agent loop degrades: the diagnosis and the
    quote do not depend on engine data.
    """

    code = "car_specs_unavailable"
    detail = "No se pudo consultar la ficha tecnica del motor en este momento."


class AppointmentUnavailableError(AppError):
    """The appointments store (MongoDB) could not be written or read.

    An AppError so the agent loop degrades: the diagnosis and the quote stay
    intact and Claude tells the customer to call the workshop instead.
    """

    code = "appointment_unavailable"
    detail = (
        "No se pudo registrar la cita en este momento. Comunicate "
        "directamente con Beau Auto-Repairs para agendarla."
    )


class AppointmentNotFoundError(AppError):
    code = "appointment_not_found"
    status_code = status.HTTP_404_NOT_FOUND
    detail = "La cita no existe."


#  Admin authentication
class AuthenticationError(AppError):
    """Bad credentials, or a missing/expired/forged token.

    **One detail string for every cause.** A wrong password, an unknown
    username and a disabled account must be indistinguishable to the caller,
    or the endpoint becomes a user-enumeration oracle. `log_message` carries
    which it actually was, for us.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "credenciales_invalidas"
    detail = "Usuario o contrasena incorrectos."


class TokenExpiredError(AuthenticationError):
    """Separate code so the SPA can redirect to the login page rather than
    showing a wrong-password message. Still a 401."""

    code = "token_expirado"
    detail = "La sesion expiro. Inicia sesion de nuevo."


class AuthorizationError(AppError):
    """Authenticated, but the role is not enough. 403, never 401 -- logging in
    again would not help."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "permiso_denegado"
    detail = "No tienes permisos para esta operacion."


class AuthUnavailableError(AppError):
    """No `JWT_SECRET`, or the users store is unreachable.

    Deliberately does NOT degrade the way the agent tools do: an auth layer
    that fails open is worse than one that fails closed.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "autenticacion_no_disponible"
    detail = "El servicio de autenticacion no esta disponible."


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
    
    return JSONResponse(status_code=exc.status_code, 
                        content=exc.to_payload())


async def validation_error_handler(
                request: Request, 
                exc: RequestValidationError
            ) -> JSONResponse:
    """FastAPI's 422 body is a list of dicts; 
    the frontend expects a string."""
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


async def unhandled_error_handler(request: Request, 
                                  exc: Exception) -> JSONResponse:
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
