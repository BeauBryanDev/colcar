export type {
  Severidad,
  DefectSeverity,
  DefectCategory,
  SurfaceDefectClass,
  TyreDefectClass,
  VehiclePart,
  SeverityBasisKind,
  Defect,
  PartDetection,
  DefectSummary,
  InspectionSummaryData,
} from './defect'

export { SEVERIDAD_DISPLAY, PART_DISPLAY, DEFECT_DISPLAY } from './defect'

export type {
  ImageRole,
  ImageMeta,
  PipelineFlags,
  VisionResult,
  OverlayKind,
  OverlayShape,
  OverlayImage,
  OverlayResponse,
} from './vision'

export type {
  OverallStatus,
  VehicleInfo,
  VehicleSummary,
} from './vehicle'

export type {
  DetectionModel,
  InspectionStatus,
  ProcessingStep,
  UploadedFile,
  InspectionSession,
} from './inspection'

export type {
  CarBrand,
  CarModelOption,
  VehicleSelection,
} from './catalog'

export type {
  FallbackLevel,
  PricingEntry,
  PricingItem,
  PricingSummary,
  PricingResult,
  ComplianceNorm,
  ComplianceResult,
  ComplianceReport,
  InspectionReport,
  MessageRole,
  ChatMessage,
} from './report'
