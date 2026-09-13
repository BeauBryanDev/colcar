# Deprecated module name, kept so old imports do not break.

# This file previously held a Markdown/JSON design document with a `.py`
# extension. The real models now live in:

#  app.schemas.detections  -- vision output + tool results
#  app.schemas.inspection  -- endpoint request/response
#  app.schemas.defects     -- the agent's final report
#  app.schemas.common      -- shared base models and vocabularies


from app.schemas.detections import (  # noqa: F401
    AgentDefect, 
    AgentPayload, 
    DefectDetection, 
    PartDetection, 
    VisionResult,
)
