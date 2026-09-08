# Pydantic models for the API surface.

#  common      base models, casing rules, shared vocabularies
#  inspection  the five endpoints
#  detections  vision output and tool results
#  defects     the agent's final report
#  agent       chat
    
from app.schemas.agent import ChatMessage, ChatRequest, ChatResponse
from app.schemas.common import (
    ApiRequest, ApiResponse, DetectionModel, InspectionStatus, Severidad,
    SeveridadDisplay, StepStatus,
)
from app.schemas.defects import (
    DiagnosedDefect, InspectionReport, LegalCompliance, QuoteSummary,
    RepairEstimate,
)
from app.schemas.detections import (
    AgentDefect, AgentPayload, ComplianceHit, DefectDetection, InspectionSummary,
    PartDetection, PricingItem, PricingResult, PricingSummary, VisionResult,
)
from app.schemas.inspection import (
    InspectionResultResponse, ProcessingStatusResponse, ProcessingStepModel,
    RunInspectionRequest, RunInspectionResponse, StartInspectionRequest,
    StartInspectionResponse, UploadedFileInfo, UploadFilesResponse, VehicleInfo,
)

__all__ = [
    "ApiRequest", "ApiResponse", "DetectionModel", "InspectionStatus",
    "Severidad", "SeveridadDisplay", "StepStatus",
    "StartInspectionRequest", "StartInspectionResponse", "VehicleInfo",
    "UploadFilesResponse", "UploadedFileInfo",
    "RunInspectionRequest", "RunInspectionResponse",
    "ProcessingStatusResponse", "ProcessingStepModel",
    "InspectionResultResponse",
    "VisionResult", "PartDetection", "DefectDetection", "InspectionSummary",
    "AgentPayload", "AgentDefect",
    "PricingResult", "PricingItem", "PricingSummary", "ComplianceHit",
    "InspectionReport", "DiagnosedDefect", "RepairEstimate", "LegalCompliance",
    "QuoteSummary",
    "ChatRequest", "ChatResponse", "ChatMessage",
]
