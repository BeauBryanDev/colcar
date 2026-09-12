
from __future__ import annotations

from typing import Any

# Shared shape for a defect argument. `severidad` is Spanish because that is
# what the pricing catalog is keyed on -- see app/rag/pricing_rag.py.
_DEFECT_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pieza": {
            "type": "string",
            "description": (
                "Nombre de la pieza en ingles, exactamente como aparece en el "
                "reporte de inspeccion (por ejemplo front_bumper, "
                "back_left_door, front_glass, tire). No lo traduzcas."
            ),
        },
        "tipo_defecto": {
            "type": "string",
            "description": (
                "Tipo de defecto en ingles, exactamente como aparece en el "
                "reporte (scratch, dent, crack, glass_shatter, lamp_broken, "
                "tire_flat, Bulge, Cracks, 'Flat spots', Pitting, Puncture). "
                "No lo traduzcas."
            ),
        },
        "severidad": {
            "type": "string",
            "enum": ["leve", "moderado", "grave"],
            "description": "Severidad calculada por el sistema de vision.",
        },
    },
    "required": ["pieza", "tipo_defecto", "severidad"],
}

# Tool definitions handed to Claude.

QUERY_PRICING_BATCH: dict[str, Any] = {
    "name": "query_pricing_batch",
    "description": (
        "Consulta el catalogo de precios de Beau Auto-Repairs para TODOS los "
        "defectos detectados en la inspeccion, de una sola vez.\n\n"
        "Llamala UNA sola vez por conversacion, con la lista completa de "
        "defectos. No la llames una vez por defecto.\n\n"
        "Debes llamarla siempre antes de mencionar cualquier valor en pesos: "
        "es la unica fuente de precios. Nunca estimes, calcules ni inventes un "
        "precio por tu cuenta.\n\n"
        "Devuelve un objeto con 'items' (precio por defecto), 'resumen' (con "
        "total_cop ya calculado) e 'instrucciones'. El total viene sumado: "
        "usalo tal cual y no vuelvas a sumar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "defects": {
                "type": "array",
                "description": "Lista completa de defectos detectados.",
                "items": _DEFECT_ITEM,
            }
        },
        "required": ["defects"],
    },
}


QUERY_COMPLIANCE: dict[str, Any] = {
    "name": "query_compliance",
    "description": (
        "Consulta la normativa colombiana de Revision Tecnico-Mecanica (RTM) "
        "para los defectos detectados: NTC 5375 y Resolucion 3768 de 2013.\n\n"
        "Llamala UNA sola vez por conversacion, con la lista completa de "
        "defectos, antes de afirmar que el vehiculo pasa o no pasa la RTM.\n\n"
        "Solo devuelve resultados para defectos que la norma realmente cubre "
        "(llantas, vidrios, luces, espejos y corrosion). Los defectos "
        "puramente esteticos, como un rayon o una abolladura en la carroceria, "
        "devuelven una lista vacia: eso significa que NO son causal de rechazo "
        "en la RTM, y asi debes explicarlo.\n\n"
        "Cada resultado indica 'vinculante'. Si es false, se trata de un "
        "concepto juridico orientativo: puedes mencionarlo como contexto, pero "
        "NUNCA como causal de rechazo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "defects": {
                "type": "array",
                "description": "Lista completa de defectos detectados.",
                "items": _DEFECT_ITEM,
            }
        },
        "required": ["defects"],
    },
}


QUERY_CAR_SPECS: dict[str, Any] = {
    "name": "query_car_specs",
    "description": (
        "Consulta la ficha tecnica del motor del vehiculo inspeccionado "
        "(cilindraje, cilindros, combustible, traccion, transmision y, si "
        "esta disponible, potencia y torque) en una base de datos externa.\n\n"
        "Llamala UNA sola vez por conversacion, y solo cuando el usuario "
        "pregunte por el motor, la mecanica, el consumo o las "
        "especificaciones tecnicas de su vehiculo. No la llames para el "
        "diagnostico de carroceria ni para cotizar.\n\n"
        "No recibe argumentos: el vehiculo (marca, modelo, año) ya esta "
        "registrado en la sesion desde el inicio de la inspeccion y se usa "
        "automaticamente.\n\n"
        "Nunca afirmes una cifra de motor sin haber llamado esta tool. Los "
        "campos en null no estan disponibles: dilo asi, no los inventes."
    ),
    # No properties on purpose: the vehicle identity is a server-side fact
    # (same rule as the brand multiplier in query_pricing_batch).
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


CHECK_REPAIR_PRICES: dict[str, Any] = {
    "name": "check_repair_prices",
    "description": (
        "Consulta precios de referencia del catalogo de Beau Auto-Repairs para "
        "reparaciones que el USUARIO pregunta, aunque NO hayan sido detectadas "
        "en la inspeccion: 'cuanto cuesta arreglar una abolladura en el capo', "
        "'que vale cambiar el parabrisas', 'que reparaciones hacen en farolas'.\n\n"
        "NO la uses para cotizar los defectos detectados: para eso esta "
        "query_pricing_batch. Usala cuando la pregunta sea hipotetica o sobre "
        "una pieza o defecto distinto a los del reporte.\n\n"
        "Envia una consulta por cada pregunta. Traduce lo que dice el usuario "
        "al nombre en ingles de la pieza (capo -> hood, parabrisas -> "
        "front_glass, farola -> front_light, parachoques -> front_bumper, "
        "llanta -> tire, rin -> wheel) y del defecto (abolladura -> dent, "
        "rayon -> scratch, grieta -> crack, vidrio roto -> glass_shatter, "
        "farola rota -> lamp_broken, pinchazo -> Puncture). Si el usuario no "
        "dice la severidad, omitela y recibiras las tres; si no dice el "
        "defecto, omitelo y recibiras todos los servicios de la pieza.\n\n"
        "Nunca digas un precio sin haber llamado esta tool o "
        "query_pricing_batch. Los precios ya incluyen el ajuste por marca."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "consultas": {
                "type": "array",
                "description": "Una consulta por pregunta del usuario.",
                "items": {
                    "type": "object",
                    "properties": {
                        "pieza": {
                            "type": "string",
                            "description": (
                                "Pieza en ingles: front_bumper, back_bumper, "
                                "hood, trunk, tailgate, front_door, "
                                "front_left_door, front_right_door, back_door, "
                                "back_left_door, back_right_door, front_glass, "
                                "back_glass, front_light, front_left_light, "
                                "front_right_light, back_light, back_left_light, "
                                "back_right_light, left_mirror, right_mirror, "
                                "tire, wheel."
                            ),
                        },
                        "tipo_defecto": {
                            "type": "string",
                            "description": (
                                "Opcional. Defecto en ingles: scratch, dent, "
                                "crack, glass_shatter, lamp_broken, tire_flat, "
                                "Bulge, Cracks, 'Flat spots', Pitting, Puncture."
                            ),
                        },
                        "severidad": {
                            "type": "string",
                            "enum": ["leve", "moderado", "grave"],
                            "description": "Opcional. Omitela para recibir las tres.",
                        },
                    },
                    "required": ["pieza"],
                },
            }
        },
        "required": ["consultas"],
    },
}


CHECK_AVAILABILITY: dict[str, Any] = {
    "name": "check_availability",
    "description": (
        "Verifica si una fecha y hora estan libres para agendar en el taller "
        "Beau Auto-Repairs. El taller atiende un solo vehiculo a la vez.\n\n"
        "Llamala ANTES de make_appointment, en cuanto el usuario proponga una "
        "fecha y hora concretas, para saber si hay cupo. Si devuelve "
        "disponible=false, dile al usuario que ese horario esta ocupado y pide "
        "otro; no llames make_appointment para ese horario. Si devuelve "
        "disponible=true, continua reuniendo los datos y pide confirmacion "
        "antes de agendar.\n\n"
        "Fecha en formato AAAA-MM-DD y hora HH:MM (24 h, hora de Colombia)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "fecha": {"type": "string", "description": "Fecha, formato AAAA-MM-DD."},
            "hora": {"type": "string", "description": "Hora, formato HH:MM en 24 horas."},
        },
        "required": ["fecha", "hora"],
    },
}


MAKE_APPOINTMENT: dict[str, Any] = {
    "name": "make_appointment",
    "description": (
        "Agenda una cita en el taller Beau Auto-Repairs para reparar el "
        "vehiculo de esta inspeccion.\n\n"
        "Llamala SOLO cuando el usuario haya dicho de forma explicita que si "
        "quiere agendar, y ya tengas: nombre, telefono, correo, placa, fecha "
        "(AAAA-MM-DD) y hora (HH:MM, 24 h, hora de Colombia). Si falta "
        "cualquiera, pideselo antes; no la llames para 'probar'.\n\n"
        "La inspeccion, la marca/modelo/ano y el costo estimado se toman "
        "automaticamente de la sesion: no los envies. La placa SI la envias: "
        "solo el usuario la conoce.\n\n"
        "Si el resultado trae 'error', la cita NO se creo: explica el motivo "
        "(fecha pasada, domingo, fuera de horario, dato faltante) y pide el "
        "dato o una nueva fecha. Si trae 'codigo', la cita SI se creo: "
        "entrega ese codigo al usuario tal cual, con la fecha y hora."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "confirmado": {
                "type": "boolean",
                "description": (
                    "true unicamente si el usuario confirmo de forma explicita "
                    "que quiere agendar la cita."
                ),
            },
            "nombre_cliente": {"type": "string", "description": "Nombre completo."},
            "telefono": {"type": "string", "description": "Telefono de contacto."},
            "email": {"type": "string", "description": "Correo electronico."},
            "placa": {
                "type": "string",
                "description": (
                    "Placa del carro tal como la dio el usuario, formato "
                    "colombiano ABC123 (tres letras, tres numeros)."
                ),
            },
            "fecha": {
                "type": "string",
                "description": "Fecha deseada, formato AAAA-MM-DD.",
            },
            "hora": {
                "type": "string",
                "description": "Hora deseada, formato HH:MM en 24 horas.",
            },
            "notas": {
                "type": "string",
                "description": "Opcional: comentarios del usuario para el taller.",
            },
        },
        "required": [
            "confirmado", "nombre_cliente", "telefono", "email", "placa",
            "fecha", "hora",
        ],
    },
}


QUERY_EMAIL_AND_PLATE_NUMBER: dict[str, Any] = {
    "name": "query_email_and_plate_number",
    "description": (
        "Verifica si un cliente es NUEVO (sin citas previas) consultando su "
        "correo y placa contra los registros del taller.\n\n"
        "Llamala SOLO cuando el usuario se queje del precio o pida una rebaja "
        "o descuento. No la llames de forma proactiva ni al inicio: el "
        "descuento de bienvenida no se ofrece salvo que el usuario no este seguro y pida regalo.\n\n"
        "Devuelve es_usuario_nuevo. Si es true, el usuario califica para el "
        "descuento de primera cita y puedes ofrecerselo. Si es false, no "
        "califica y no debes ofrecerlo. Necesitas correo y placa (ABC123) "
        "validos; si faltan, pideselos antes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Correo electronico del usuario."},
            "placa": {
                "type": "string",
                "description": "Placa del carro, formato colombiano ABC123.",
            },
        },
        "required": ["email", "placa"],
    },
}
 
 
GRANT_DISCOUNT: dict[str, Any] = {
    "name": "grant_discount",
    "description": (
        "Aplica el descuento de bienvenida de 10% sobre el estimado de la "
        "cotizacion, para un cliente NUEVO que acepto la oferta.\n\n"
        "Llamala SOLO despues de que query_email_and_plate_number haya "
        "devuelto es_usuario_nuevo=true y el usuario haya aceptado el "
        "descuento. La tool vuelve a verificar la elegibilidad por su cuenta: "
        "si el usuario no es nuevo, no aplica nada, sin importar lo que digas.\n\n"
        "Si devuelve descuento_aplicado=true, entrega al usuario el "
        "codigo_descuento tal cual y el nuevo total, y explicale que debe "
        "presentar ese codigo el dia de la cita. Si devuelve false, explica el "
        "motivo (no es nuevo, ya tenia descuento, o falta la cotizacion). "
        "Necesita correo y placa validos, los mismos que verificaste."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Correo del usuario, el mismo verificado."},
            "placa": {
                "type": "string",
                "description": "Placa del carro, formato ABC123, la misma verificada.",
            },
        },
        "required": ["email", "placa"],
    },
}


RESCHEDULE_APPOINTMENT: dict[str, Any] = {
    "name": "reschedule_appointment",
    "description": (
        "Cambia la fecha y hora de una cita YA EXISTENTE, para un usuario que "
        "vuelve al chat pidiendo mover su cita.\n\n"
        "Antes de llamarla necesitas: el codigo de la cita (pidesela al "
        "usuario si no la tiene a mano), su correo y su placa -- los tres se "
        "verifican contra la cita antes de mover nada. Si no coinciden, la "
        "tool rechaza y debes pedir al usuario que revise los datos, sin "
        "asumir cual esta mal.\n\n"
        "Tambien necesitas la nueva fecha (AAAA-MM-DD) y hora (HH:MM, 24h). "
        "Si el nuevo horario ya esta ocupado, la tool lo dice explicitamente: "
        "pide otra fecha u hora, no insistas con la misma.\n\n"
        "No necesitas preguntar ni registrar el motivo del cambio; el usuario "
        "puede explicarlo si quiere, pero no se guarda en ningun lado."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "codigo_cita": {"type": "string", "description": "Codigo de 6 caracteres de la cita."},
            "email": {"type": "string", "description": "Correo del usuario, para verificar."},
            "placa": {"type": "string", "description": "Placa del carro, formato ABC123, para verificar."},
            "fecha": {"type": "string", "description": "Nueva fecha, formato AAAA-MM-DD."},
            "hora": {"type": "string", "description": "Nueva hora, formato HH:MM en 24 horas."},
        },
        "required": ["codigo_cita", "email", "placa", "fecha", "hora"],
    },
}
 
 
CANCEL_APPOINTMENT: dict[str, Any] = {
    "name": "cancel_appointment",
    "description": (
        "Cancela una cita YA EXISTENTE, cuando el usuario diga explicitamente "
        "que ya no quiere o no puede asistir.\n\n"
        "Igual que reschedule_appointment: necesitas el codigo de la cita, "
        "correo y placa, y se verifican contra la cita antes de cancelar "
        "nada. Confirma con el usuario antes de llamarla -- no canceles solo "
        "porque menciono la posibilidad, espera confirmacion explicita.\n\n"
        "No preguntes ni registres el motivo de la cancelacion."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "codigo_cita": {"type": "string", "description": "Codigo de 6 caracteres de la cita."},
            "email": {"type": "string", "description": "Correo del usuario, para verificar."},
            "placa": {"type": "string", "description": "Placa del carro, formato ABC123, para verificar."},
        },
        "required": ["codigo_cita", "email", "placa"],
    },
}

TOOLS: list[dict[str, Any]] = [
    QUERY_PRICING_BATCH,
    QUERY_COMPLIANCE,
    QUERY_CAR_SPECS,
    CHECK_REPAIR_PRICES,
    CHECK_AVAILABILITY,
    MAKE_APPOINTMENT,
    QUERY_EMAIL_AND_PLATE_NUMBER,
    GRANT_DISCOUNT,
    RESCHEDULE_APPOINTMENT,
    CANCEL_APPOINTMENT
]

TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in TOOLS)
