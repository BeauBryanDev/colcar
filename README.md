# Auto-Repair Services — AI Vehicle Inspection Platform

A full-stack web application that inspects a vehicle from photographs and produces a
repair diagnosis, an itemized price quote, and a legal roadworthiness assessment under
Colombian regulation.

A customer uploads photographs of a damaged vehicle. Three YOLO11m computer-vision
models, running locally as ONNX graphs, segment the body panels, identify surface
defects, and detect tyre damage. A spatial-matching stage attributes each defect to the
part it lies on and grades its severity. A Claude agent then reasons over those
detections through a ReAct tool-use loop, pricing the repairs against a catalog, checking
each defect against a vector-indexed corpus of Colombian technical-inspection law, and
booking a workshop appointment — all within the same conversation.

The workshop side is a separate authenticated dashboard: appointment management, a
drag-to-reschedule weekly calendar, inspection history, and user administration under a
three-tier role model.

**Stack.** FastAPI, Python 3.13, MongoDB Atlas, Qdrant, ONNX Runtime, OpenCV, Anthropic
Claude, React 18, TypeScript, Tailwind CSS, Vite.

**Status.** Backend complete and verified end to end against real photographs, the live
Qdrant cluster, and MongoDB Atlas. Frontend complete for both the customer flow and the
admin dashboard. 196 offline unit tests run in CI on every push. Approximately 95 percent
of planned scope; see [Status and roadmap](#status-and-roadmap).

---

## Table of contents

- [What it does](#what-it-does)
- [System architecture](#system-architecture)
- [The AI layer](#the-ai-layer)
  - [Computer vision](#computer-vision)
  - [Retrieval-augmented compliance](#retrieval-augmented-compliance)
  - [The agent](#the-agent)
- [Technology](#technology)
- [Running the project](#running-the-project)
- [Project layout](#project-layout)
- [API reference](#api-reference)
- [Testing and CI](#testing-and-ci)
- [Deployment](#deployment)
- [Status and roadmap](#status-and-roadmap)
- [License](#license)

---

## What it does

### The customer flow

```
  1. SELECT VEHICLE        Brand, model and year. The brand determines a price
                           multiplier applied to every figure in the quote.

  2. UPLOAD PHOTOS         Up to 3 surface images, or 1 tyre image. The two
                           panels are mutually exclusive: they drive different
                           model pipelines.

  3. VISION RUNS           0.6 - 1.6 s. Parts and defects are segmented, defects
                           are attributed to parts, severity is graded. Masks
                           are painted over the customer's own photograph as
                           soon as this stage finishes, before the agent replies.

  4. AGENT REASONS         14 - 18 s. Claude receives a compact JSON payload of
                           the detections, prices each defect, checks each one
                           against Colombian inspection law, and writes a
                           Spanish-language diagnosis.

  5. CONVERSATION          The customer asks follow-up questions, requests prices
                           for repairs that were not detected, negotiates a
                           first-visit discount, and books an appointment -
                           all through the same agent thread.
```

### The workshop flow

An authenticated dashboard at `/admin`, sharing nothing with the customer flow but the
HTTP client:

- **Appointments.** Filter by date range, status, or booking code. Move a booking through
  its lifecycle. Customer contact details are visible to both staff and admin roles,
  because confirming bookings by telephone is the primary use.
- **Calendar.** A weekly time-grid view of every open booking, with drag-and-drop
  rescheduling validated against the same workshop-hours rules the agent applies.
- **Inspections.** Every stored inspection, filterable by date, brand, or whether the
  vehicle is likely to fail its technical inspection.
- **Users.** Full account administration, restricted to the admin role.

---

## System architecture

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │                      React 18 + TypeScript SPA                       │
   │                                                                      │
   │   Customer flow  /                        Admin dashboard  /admin    │
   │   - vehicle selection                     - appointments table       │
   │   - photo upload                          - weekly calendar          │
   │   - mask overlay (SVG)                    - inspection history       │
   │   - agent chat (markdown)                 - user administration      │
   └──────────────────────────────┬───────────────────────────────────────┘
                                  │  JSON over HTTP
                                  │  snake_case requests, camelCase responses
                                  │  Bearer JWT on /admin routes only
   ┌──────────────────────────────▼───────────────────────────────────────┐
   │                         FastAPI  (port 8015)                         │
   │                                                                      │
   │   routers/    inspection  chat  vehicles  health  appointments       │
   │               auth  admin  admin_users                               │
   │   core/       config  logging  session  security  auth  exceptions   │
   │   schemas/    pydantic request and response contracts                │
   └───────┬───────────────────┬──────────────────────┬───────────────────┘
           │                   │                      │
   ┌───────▼────────┐  ┌───────▼────────┐  ┌──────────▼─────────┐
   │  VISION        │  │  AGENT         │  │  PERSISTENCE       │
   │  app/vision/   │  │  app/agent/    │  │  app/db/           │
   │                │  │                │  │                    │
   │  ONNX Runtime  │  │  ReAct loop    │  │  MongoDB Atlas     │
   │  OpenCV        │  │  10 tools      │  │  pymongo (sync)    │
   │  NumPy         │  │  memory window │  │                    │
   │                │  │  prompt cache  │  │  pricing_catalog   │
   │  3 YOLO11m     │  │                │  │  car_brands        │
   │  graphs        │  │  Claude        │  │  inspections       │
   │                │  │  Haiku 4.5     │  │  appointments      │
   │  segment x2    │  │                │  │  users             │
   │  detect   x1   │  │                │  │  discounts         │
   └────────────────┘  └───────┬────────┘  │  counters          │
                               │           └────────────────────┘
                       ┌───────▼────────┐
                       │  KNOWLEDGE     │
                       │  app/rag/      │
                       │                │
                       │  Qdrant Cloud  │
                       │  387 vectors   │
                       │  bge-m3, 1024d │
                       │                │
                       │  pricing trie  │
                       │  brand index   │
                       │  RTM verdict   │
                       └────────────────┘
```

### Request lifecycle

An inspection is asynchronous because vision plus the agent loop far exceeds a comfortable
HTTP wait. The client starts the work, then polls:

```
  CLIENT                          SERVER                         WORKERS

  POST /inspections/start  ──────▶ create session
                           ◀────── sessionId

  POST /inspections/upload ──────▶ store files, validate type and count
                           ◀────── accepted

  POST /inspections/run    ──────▶ schedule BackgroundTask
                           ◀────── 202, returns immediately
                                                        │
                                                        ├──▶ ONNX inference
                                                        ├──▶ NMS, mask decode
                                                        ├──▶ spatial matching
                                                        ├──▶ severity grading
  GET  /inspections/{id}/status ─▶ "analyzing" ◀─────────┘
                           ◀────── vision done; agent running
                                                        │
  GET  /inspections/{id}/overlay ▶ polygons + image URLs │
                           ◀────── painted at ~1 s      │
                                                        ├──▶ Claude tool loop
                                                        │    pricing, compliance,
                                                        │    specs, booking
                                                        ├──▶ persist to MongoDB
  GET  /inspections/{id}/status ─▶ "complete" ◀──────────┘

  GET  /inspections/{id}/results ▶ full payload + agent report
  POST /inspections/chat   ──────▶ follow-up on the same thread
```

The overlay is fetched the moment vision finishes rather than waiting for the agent. The
customer sees their own photograph with the damage outlined in about one second, and the
written diagnosis fills in afterwards.

### Measured performance

One surface image and one tyre image, end to end against the live server:

| Phase                    | Surface flow | Tyre flow |
| ------------------------ | ------------ | --------- |
| Upload and run dispatch  | 0.002 s      | 0.002 s   |
| Vision                   | 1.1 - 1.6 s  | 0.57 s    |
| Agent                    | 14.6 s       | 17.7 s    |
| Results payload (15 KB)  | 0.001 s      | —         |
| Overlay payload (5.6 KB) | 0.001 s      | —         |
| Image retrieval (38 KB)  | 0.010 s      | —         |

All HTTP accounts for roughly 0.014 s, under 0.1 percent of total latency. The agent is
approximately 94 percent of every inspection in both flows. Transport, ONNX thread counts
and payload size are therefore not meaningful optimization targets; response streaming is.

---

## The AI layer

### Computer vision

Three YOLO11m models, exported to ONNX and executed by ONNX Runtime on CPU. Tensor
geometry is read from the graph files themselves and class names are parsed from ONNX
metadata, so retraining cannot silently desynchronize the code from the weights.

| Model                   | Task         | Output tensors                  | Classes |
| ----------------------- | ------------ | ------------------------------- | ------- |
| `car_parts_model.onnx`  | Segmentation | `(1,59,8400)` + `(1,32,160,160)` | 23      |
| `car_defects_model.onnx`| Segmentation | `(1,42,8400)` + prototypes      | 6       |
| `tyres_defect_model.onnx`| Detection   | `(1,10,8400)`                   | 6       |

Channel layout is `4 + nc + 32` for segmentation and `4 + nc` for detection.

**Two independent pipelines.** The surface flow runs both segmentation models, then
attributes each defect to a body part and grades severity as defect area divided by the
part's own mask area. The tyre flow runs a detection-only model with no parts model and no
spatial matching, so severity is graded by defect type rather than area.

```
  SURFACE FLOW                            TYRE FLOW

  image                                   image
    │                                       │
    ├──▶ parts model ──┐                    ├──▶ tyre model
    │    (segment)     │                    │    (detect)
    │                  │                    │
    └──▶ defects model │                    ▼
         (segment)     │                  NMS
           │           │                    │
           ▼           ▼                    ▼
          NMS         NMS                severity by
           │           │                 defect type
           └─────┬─────┘                    │
                 ▼                          ▼
          spatial matching             pieza = "tire"
          by containment
                 │
                 ▼
          severity by area ratio
          (defect area / part mask area)
```

**Spatial matching by containment, not IoU.** A defect is attributed to the part it lies
on by intersection divided by defect area. Intersection-over-union fails here for a
structural reason: a scratch lying entirely on a door scores an IoU near 0.002 because the
door dwarfs it, while containment scores 1.0. Matching is performed on mask pixels when
both shapes carry masks and on bounding boxes otherwise. Among overlapping candidates the
match resolves by highest containment, then by smallest part, then by confidence, so a
specific panel wins over the general region that encloses it.

Two gates were calibrated against real photographs rather than chosen by intuition. The
containment threshold sits at 0.50: every correct match measured at least 0.556, while the
two observed misattributions measured 0.188 and 0.406. An affinity rule additionally
constrains which defects may attach to which parts — a broken lamp may only attach to a
light, shattered glass only to glass. Geometry alone cannot enforce this: when the parts
model misses a headlight, the lamp defect can sit entirely inside the door behind it, so no
containment threshold would reject it. Ineligible parts are excluded outright and the
defect is reported as unmatched rather than attributed to the wrong panel.

**Severity grading** produces three internal bands, `leve`, `moderado` and `grave`, which
are the pricing catalog's own keys.

| Flow                     | Denominator            | Thresholds  |
| ------------------------ | ---------------------- | ----------- |
| Matched surface defect   | defect area / part mask area | 0.10, 0.25 |
| Unmatched surface defect | defect area / image area     | 0.20, 0.45 |
| Tyre defect              | defect type, not area        | see below  |

Tyres are graded by type because area is the wrong signal: real tyre defects occupy between
0.3 and 6.5 percent of the frame, so an area rule graded a sidewall bulge detected at 0.800
confidence as minor — a blowout risk classified as cosmetic. Bulges grade severe;
punctures, cracks and flat spots grade moderate; pitting grades minor. Cracks and flat
spots escalate to severe beyond a 0.15 area ratio, since a full-tread flat spot was
measured at 62.7 percent.

A legal floor overrides area entirely: shattered glass and broken lamps are always graded
severe, because operating a vehicle in either condition is unlawful. Every grading decision
records which rule produced it, so a surprising quote can be audited after the fact.

**Mask rescaling order is load-bearing.** Masks are decoded, stripped of letterbox padding,
resized to original resolution, and only then cropped to their bounding box in original
pixel space. Cropping in 160x160 prototype space instead quantizes to roughly 12 pixels on
a 1080p photograph, which inflated mask areas by about 4 percent and allowed masks to
escape their own bounding boxes. Since severity is an area ratio, that error propagates
directly into the customer's quote.

The pipeline emits two payloads from a single run: a full payload for the browser
containing polygons and match diagnostics, at roughly 17 KB, and a flat agent payload at
roughly 1.3 KB. The thirteen-fold difference matters because the agent payload is
retransmitted on every turn of the tool-use loop, so it carries normalized bounding boxes
and never polygons.

Validated against eleven annotated photographs: all eleven produced correct detections,
both multi-defect images returned both defects, and masks traced actual damage at roughly
506 ms per image including decode. A known recall limit is that subtle hail dimples on a
dark, wet panel were missed, while hail damage on the windscreen of the same vehicle was
caught.

Training notebooks and evaluation artifacts, including per-model confusion matrices, are in
[`ml/`](ml/). The exported ONNX weights are not yet published; they will be released on
Hugging Face and linked here.

### Retrieval-augmented compliance

Colombian vehicles must pass a periodic technical-mechanical inspection, the RTM. The
system tells a customer whether the damage found in their photographs is a cause for
rejection, and cites the clause that says so.

A Qdrant Cloud collection holds 387 points at 1024 dimensions under cosine distance,
embedded with `BAAI/bge-m3`. Three source documents are indexed, each chunked by a strategy
matched to its structure:

| Document                  | Chunks | Chunking strategy                                        |
| ------------------------- | ------ | -------------------------------------------------------- |
| `ntc_5375`                | 339    | Narrative sections, plus one chunk per defect-table row   |
| `resolucion_3768_2013`    | 42     | One chunk per article; derogated text split into current and historical |
| `concepto_20251340167841` | 6      | Split on section headers; non-binding legal opinion       |

Defect-table severity classes are recovered from word bounding-box x-positions rather than
from the extracted character, because plain text extraction loses the column alignment that
distinguishes a Type A defect from a Type B one.

Two retrieval rules were derived from measured results rather than from theory.

**Translate to the standard's own wording before embedding.** English class labels retrieve
poorly against a Spanish corpus, but more importantly, the corpus's exact phrasing
outperforms a literal translation. Embedding `Cracks` as the dictionary term *grietas*
scored 0.361 and returned an irrelevant clause about re-grooved treads. Embedding it as the
standard's own phrase, *despegue o rotura en las bandas laterales*, scores 0.627 and returns
the correct clause three times over. The same holds for pitting mapped to *corrosión*,
which scores 0.540 against the exterior-corrosion clause.

**Route before searching.** NTC 5375 is a roadworthiness standard containing no
cosmetic-damage provisions, so a scratched bumper has no correct answer and retrieval
returns the least-bad match. A relevance gate classifies each part-and-defect combination
before any embedding occurs; cosmetic combinations return empty and never reach the encoder.
This cannot be solved with a similarity threshold: a wrong cosmetic match was measured at
0.513 while a correct windscreen match scored 0.518, so the score distributions overlap.
Without the gate, the system tells a customer their dented door fails inspection while
citing a clause about emergency-exit door handles.

**The verdict is policy, not retrieval.** Retrieval returns clauses; deciding whether a
vehicle passes is a separate decision that lives in one module so that the agent, the SPA
and any future report writer cannot disagree. A binding clause classified Type A or B
constitutes rejection, Type A taking precedence. Non-binding sources may inform an
explanation but can never be the reason a customer is told their vehicle fails. Above both,
a legal floor rejects broken lamps and shattered glass regardless of what was retrieved, so
that an unreachable vector database can never silently downgrade a legal failure to a
cosmetic note. Consumers read the verdict fields directly and never re-derive pass or fail
from the number of clauses returned.

### The agent

The detection payload is seeded as the first message of a tool-use loop running on Claude
Haiku 4.5. Vision executes locally in ONNX, so the model never receives an image; it
reasons over compact JSON and calls ten tools.

```
  seed: detections JSON  ─────────────────────────────────┐
                                                          │
   ┌──────────────────────────────────────────────────────▼────────────┐
   │                                                                   │
   │   ┌─────────────────────────────────────────────────────────┐     │
   │   │  Claude Haiku 4.5                                       │     │
   │   │  system prompt + 10 tool schemas   (prompt-cached)      │     │
   │   └───────────────┬─────────────────────────────────────────┘     │
   │                   │                                               │
   │        stop_reason == "tool_use" ?                                │
   │                   │                                               │
   │          yes ─────┴──── no ──▶ final Spanish diagnosis ───────────┼──▶
   │           │                                                       │
   │           ▼                                                       │
   │   dispatch tool ──▶ execute ──▶ append tool_result ──▶ loop       │
   │                                                                   │
   │   iteration cap: 8. Tool failure degrades, never aborts.          │
   └───────────────────────────────────────────────────────────────────┘
```

| Tool                          | Purpose                                                        |
| ----------------------------- | -------------------------------------------------------------- |
| `query_pricing_batch`         | Prices every detected defect in one call; returns a total       |
| `query_compliance`            | Checks every detected defect against the RTM corpus            |
| `query_car_specs`             | Engine data from an external vehicle API; context only          |
| `check_repair_prices`         | Prices repairs the customer asks about, detected or not        |
| `check_availability`          | Tests whether a requested appointment slot is free             |
| `make_appointment`            | Books a slot after explicit customer confirmation              |
| `query_email_and_plate_number`| Determines first-visit discount eligibility                    |
| `grant_discount`              | Applies a welcome discount and mints a ticket number           |
| `reschedule_appointment`      | Moves an existing booking                                      |
| `cancel_appointment`          | Cancels an existing booking                                    |

**The loop is written by hand rather than delegated to the SDK's tool runner**, for three
reasons specific to this application. The iteration cap must surface as a domain error
rather than a generic exception. Tool failures must degrade rather than abort: an
unreachable vector database still yields a diagnosis and a quote, with the agent correctly
reporting that it could not verify legal compliance and inventing no citations. And the
full message history must be returned to the caller for persistence, so that follow-up
conversation continues the same thread rather than restarting it.

**Two operations are enforced in code rather than requested in the prompt.** The quote total
is summed in Python and the brand multiplier is applied in Python, because a small model
adding six-figure currency values is an avoidable source of incorrect quotes. The vehicle's
brand is supplied to tools from the server-side session rather than accepted as a tool
argument, because a model that omits or misremembers it would silently misquote. The same
rule governs vehicle identity for engine lookups and the inspection identifier for bookings.

**A bounded memory window** keeps token cost flat across a long conversation. The model sees
the pinned seed, the pinned pricing tool exchange, and the last five messages; the complete
transcript is retained server-side for audit. Trimming is pair-aware, because slicing
between a tool call and its result orphans one of them and the API rejects the request.
Measured effect: input tokens per turn fall by roughly 45 percent and stay flat, and after
five unrelated turns the agent still reproduced the exact quote breakdown without re-calling
any tool.

**Prompt caching** covers the roughly 6,000-token prefix of system prompt and tool schemas,
which the loop would otherwise retransmit once per iteration. Three cache breakpoints are
placed on the system block, on the stable head of the memory window, and on the last
message. The system block carries the first marker deliberately: Haiku 4.5 requires a
minimum cacheable prefix of 4,096 tokens, the system prompt alone falls below that, and
tools render before system — so marking system covers both and clears the floor. Caching is
metadata only; a test strips the markers and asserts the model receives a byte-identical
prompt.

**Appointment security.** Rescheduling, cancellation and eligibility checks require a
booking code together with the customer's email address and license plate. A six-hex-digit
code alone proves nothing, and a code-only gate would make the tool an appointment lookup —
and a cancel button — for anyone who guesses one. Rejections never identify which of the
three factors failed, for the same reason the login endpoint returns a single
indistinguishable 401: naming the failing field turns the tool into an oracle for which
plates and email addresses exist.

---

## Technology

### Backend

**Python 3.13.** The implementation language for the API, the vision pipeline, the
retrieval layer and the agent loop. Type hints are used throughout and evaluated lazily via
`from __future__ import annotations`, keeping heavy imports out of module load paths.

**FastAPI.** The web framework. Provides the routing layer, dependency injection for
authentication guards and settings, `BackgroundTasks` for the asynchronous inspection run,
multipart upload handling, and an OpenAPI schema generated from the Pydantic models, served
at `/docs`. Route guards are applied per-route rather than globally so customer-facing
endpoints remain public while every admin endpoint requires a bearer token.

**Pydantic v2 and pydantic-settings.** Defines every request and response contract, the
MongoDB document models, and the application settings object. Field aliasing converts
between snake_case Python attributes and camelCase JSON responses at the serialization
boundary. `SecretStr` wraps every credential so that a validation error body or a logged
model dump prints a mask rather than a value. Settings are read from the environment at
import time and validated once.

**ONNX Runtime.** Executes the three exported YOLO11m graphs on CPU. Chosen over a
framework-native runtime so that inference requires neither PyTorch nor Ultralytics at
serving time, and so that tensor shapes and class metadata can be read directly from the
graph.

**OpenCV and NumPy.** Image preprocessing, letterbox resizing, mask prototype decoding,
contour extraction for polygon output, and the vectorized geometry behind non-maximum
suppression and containment scoring.

**Qdrant.** The vector database holding the compliance corpus, hosted on Qdrant Cloud.
Queried with payload filters over indexed fields for document identity, binding status,
validity and severity class. Payload indexes are mandatory: a filter on an unindexed field
is rejected.

**FlagEmbedding (`BGEM3FlagModel`).** Produces the 1024-dimension query embeddings at
runtime. This is the same library used to build the index, so runtime queries take an
identical code path to ingestion. The stored vectors exist in this model's space and cannot
be reproduced by another encoder, so the model cannot be swapped without re-embedding all
387 chunks.

**MongoDB Atlas with pymongo.** The durable store, accessed synchronously. Holds the
pricing catalog, the brand index, completed inspections, appointments, user accounts,
discounts and an atomic ticket counter. The synchronous driver is used deliberately;
Motor is deprecated, and `pymongo.AsyncMongoClient` is the forward path when asynchronous
access is needed. Unique compound indexes enforce booking invariants at the database level
rather than in application code.

**Anthropic SDK.** The client for Claude Haiku 4.5. Used for message construction, tool
schema transport and cache-control metadata; the tool-use loop itself is hand-written.

**argon2-cffi and PyJWT.** Password hashing and token signing. Argon2id is used directly
rather than through a wrapper library, with cost parameters held in application settings so
that a dependency upgrade cannot silently change the cost of newly minted hashes. Tokens
are HS256, and the verification algorithm is pinned to the configured value rather than read
from the token header, which is the standard JWT forgery vector.

**pytest.** The test runner. The suite is fully offline by construction, enforced by a
fixture that patches socket creation to raise.

### Frontend

**React 18.** The user interface, written as function components with hooks. A class
component is used in exactly one place, the error boundary, because `componentDidCatch` has
no hook equivalent.

**TypeScript.** Types are defined against the backend's actual wire format, and `tsc -b` in
the build step is what catches contract drift between the two halves of the application.

**Vite.** The build tool and development server. Proxies the API prefix to the backend
during development, so the browser sees a single origin and no CORS preflight in the local
loop.

**Tailwind CSS.** Utility-first styling with a project palette defined in the Tailwind
configuration. One constraint applies: third-party component CSS overrides must sit outside
Tailwind's component layer, since the purge step removes layered rules whose selectors never
appear in source, and calendar class names are generated at runtime.

**Zustand.** Client state for the customer inspection flow — session identity, uploaded
files, progress steps, detections and chat history — in a single store with no provider
boilerplate.

**React Router.** Client-side routing separating the public customer flow from the guarded
admin area, with role-aware route guards.

**FullCalendar.** The weekly appointment grid with drag-and-drop rescheduling. All packages
are pinned to a single major version, because mixing versions installs two copies of the
calendar core and produces a page that builds cleanly and fails at runtime.

**Axios.** The HTTP client, with a request interceptor that attaches the stored bearer
token. The customer flow sends no token and needs none.

**react-markdown with remark-gfm.** Renders the agent's Spanish-language replies. The GFM
plugin is required, since the agent's quote breakdowns are markdown tables.

---

## Running the project

### Prerequisites

- Python 3.13
- Node.js 20 or later
- A MongoDB Atlas cluster, or none — the catalogs fall back to bundled JSON
- A Qdrant Cloud cluster with the compliance collection populated
- An Anthropic API key
- The three ONNX model files in `models/`

The ONNX weights are not currently distributed with the repository and will be published
separately on Hugging Face. Without them the API starts and every non-vision route
functions, but an inspection run cannot execute.

### Configuration

All credentials are read from a `.env` file at the repository root, which is excluded from
version control. Nothing in the codebase reads the environment except the settings module,
and every secret is registered with a logging filter that redacts it by substring, so that a
stray debug statement or a traceback quoting a connection string cannot leak a value.

| Variable | Required | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | Agent authentication |
| `ANTHROPIC_MODEL` | no | Defaults to `claude-haiku-4-5` |
| `QDRANT_URL` | yes | Vector database endpoint |
| `QDRANT_API_KEY` | yes | Vector database authentication |
| `QDRANT_COLLECTION` | no | Defaults to `compliance_normativa` |
| `MONGODB_URI` | no | Unset falls back to bundled JSON catalogs |
| `MONGODB_DB` | no | Defaults to `car_scanner` |
| `JWT_SECRET` | yes for admin | HS256 signing key, minimum 32 characters |
| `JWT_ACCESS_TOKEN_MINUTES` | no | Defaults to 60 |
| `API_NINJA_KEY` | no | Engine specifications; the tool degrades without it |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_FULL_NAME`, `ADMIN_EMAIL`, `ADMIN_PHONE_NUMBER` | seeding only | Read by the admin seed script |
| `STAFF_USERNAME`, `STAFF_PASSWORD` | seeding only | Optional second account |

There is no default JWT secret. A missing or under-length value causes the authentication
routes to return 503 rather than falling back, since a hardcoded fallback would be a
publicly known signing key.

### Backend

```bash
pip install -r requirements.txt

# The service listens on 8015, not uvicorn's default.
uvicorn app.main:app --reload --port 8015 --host 0.0.0.0
```

Interactive API documentation is then served at `http://localhost:8015/docs`.

Startup performs a warmup pass, loading the embedding model in about seven seconds and the
ONNX graphs in under half a second. This is deliberate: loading lazily pushes the cost onto
the first customer, and an unauthenticated model-cache check was once observed stalling
inside a live request for eight minutes. Warmup failures degrade rather than abort — an
unreachable vector database still leaves vision and quoting operational.

### Database seeding

```bash
python scripts/seed_catalog.py --dry-run   # counts only, opens no connection
python scripts/seed_catalog.py             # upsert both catalogs, idempotent
python scripts/seed_catalog.py --verify    # confirm the stored catalog matches the file

python scripts/seed_admin.py --dry-run     # show accounts, no connection, no hashing
python scripts/seed_admin.py               # upsert accounts and indexes, idempotent
python scripts/seed_admin.py --verify      # read back and verify the stored hash
python scripts/seed_admin.py --rotate      # re-hash the password from the environment
```

Both scripts are idempotent. The admin seed does not re-hash an existing password on a
repeat run, because Argon2 is salted and a fresh digest on every invocation would make an
idempotent operation appear to mutate the record. Verification calls the same password
verification routine the login endpoint uses, so a passing verify guarantees a working
login.

### Retrieval diagnostics

```bash
python scripts/smoke_test_rag.py           # retrieval, filters, payload shape
python scripts/smoke_test_rag.py --full    # additionally verify encoder parity
```

The default mode reuses a vector already stored in the collection, exercising retrieval and
payload structure in seconds without loading the encoder. The full mode re-embeds stored
chunks and asserts cosine similarity near 1.0 against their stored vectors, which is the
check that proves the runtime encoder still matches the one used at ingestion.

### Frontend

```bash
cd frontend
npm install
npm run dev      # development server on 5173, proxying the API to 8015
npm run build    # type-check and produce a production bundle
npm run lint
```

`npm run build` is the frontend's only automated verification, since `tsc -b` is what
detects drift against the backend contract.

---

## Project layout

```
.
├── app/
│   ├── core/            configuration, logging with secret redaction, session
│   │                    store, exceptions, password hashing, JWT, route guards
│   ├── db/              MongoDB client and the repository layer for every
│   │                    collection
│   ├── models/          Pydantic document models: inspection, appointment, user
│   ├── vision/          ONNX inference, preprocessing, NMS, segmentation and
│   │                    detection post-processing, spatial matching, severity
│   │                    grading, pipeline orchestration
│   ├── rag/             vocabulary and relevance routing, compliance retrieval,
│   │                    RTM verdict policy, pricing trie, brand index,
│   │                    Qdrant client, external vehicle specifications
│   ├── agent/           tool schemas and implementations, memory window, the
│   │                    Claude loop, and the appointment, availability,
│   │                    discount and rescheduling tools
│   ├── schemas/         request and response contracts
│   ├── routers/         health, inspection, chat, vehicles, appointments,
│   │                    auth, admin, admin users
│   └── main.py          lifespan warmup, CORS, exception handlers
│
├── frontend/src/
│   ├── components/      common, upload, vehicle, inspection and admin components
│   ├── pages/           customer home, admin login, appointments, calendar,
│   │                    inspections, users, error pages
│   ├── services/        API client, inspection, report, summary, catalog,
│   │                    auth and admin service layers
│   ├── stores/          Zustand inspection store, authentication context
│   ├── hooks/           file upload, inspection polling, responsive layout
│   └── types/           wire contracts mirrored from the backend
│
├── ml/                  training and ingestion notebooks, evaluation artifacts
├── models/              exported ONNX weights (not distributed)
├── scripts/             catalog seeding, admin seeding, retrieval diagnostics
├── tests/               196 offline unit tests across 16 groups
└── .github/workflows/   continuous integration
```

---

## API reference

All routes are served under the `/api` prefix. Requests use snake_case field names,
responses use camelCase.

### Public — inspection

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/inspections/start` | Create a session; vehicle information optional |
| `POST` | `/inspections/upload` | Multipart upload of images with panel selection |
| `POST` | `/inspections/run` | Dispatch the pipeline; returns immediately |
| `GET` | `/inspections/{id}/status` | Progress, polled by the client |
| `GET` | `/inspections/{id}/results` | Full vision payload and agent report |
| `POST` | `/inspections/chat` | Continue the agent conversation |
| `GET` | `/inspections/{id}/overlay` | Segmentation polygons in original pixel space |
| `GET` | `/inspections/{id}/images/{image_id}` | Retrieve a stored upload |
| `DELETE` | `/inspections/{id}` | Drop a session and its uploads |
| `GET` | `/inspections/{id}/appointments` | Bookings made from this inspection |
| `GET` | `/appointments/{codigo}` | Look up a booking by code |
| `GET` | `/vehicles/brands` | Brand, model and year catalog |

The overlay is deliberately a separate lane from the agent. Masks are hundreds of
coordinate pairs per defect and the agent payload is retransmitted on every loop iteration,
so rendering geometry goes to the browser while the model receives only normalized bounding
boxes. Image identifiers are validated against the session's own recorded payload rather
than used to construct a filesystem path, with a resolved-path check preventing escape from
the session directory.

The appointments router is read-only, which is a security boundary rather than a stylistic
choice: it is mounted publicly and the customer client sends no token, so any write route
there would be an unauthenticated write route. The agent and the dashboard share the
repository layer, not an HTTP endpoint.

### Health

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness |
| `GET` | `/health/ready` | Readiness, including catalog source |
| `GET` | `/health/models` | Forces model loading; for manual diagnosis only |

Readiness deliberately does not force model loading, since that would turn a probe into a
slow-start denial of service.

### Authentication

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/auth/login` | Exchange credentials for a bearer token |
| `GET` | `/auth/me` | The account behind the presented token |

Every login failure path returns an identical 401 body — unknown account, wrong password
and disabled account are indistinguishable to the caller, with the actual reason recorded
server-side. Token expiry is signalled by a distinct error code on the same status, so the
client can redirect to login rather than report a wrong password.

Each authenticated request performs two checks: the role is read from the signed claim, and
the account is re-read from the database to confirm it still exists and remains active. A
disabled account therefore loses access on its next request rather than at token expiry.

### Admin — staff and admin roles

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/admin/appointments` | Filter by date range, status or code |
| `GET` | `/admin/appointments/{codigo}` | Full booking including inspection snapshot |
| `PATCH` | `/admin/appointments/{codigo}` | Advance the booking lifecycle |
| `PATCH` | `/admin/appointments/{codigo}/schedule` | Move a booking to another slot |
| `GET` | `/admin/inspections` | Filter by date, brand or rejection likelihood |
| `GET` | `/admin/inspections/{id}` | The complete stored record |

Appointment status follows a transition table in which served and cancelled are terminal
states. A booking must be confirmed before it can be marked served, and neither terminal
state can be reopened — reopening is modelled as a new booking, so that history remains
meaningful. Setting the status a booking already holds is a no-op rather than a conflict,
so a double-submitting client does not surface a spurious error.

Date filters are interpreted in workshop-local time rather than UTC. Slots are stored in
UTC, but a query for bookings on a given day means the workshop's day; at UTC-5 those
windows differ by five hours at each end, which would place an entire evening of bookings
on the wrong date.

### Admin — admin role only

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/admin/users` | List, filterable by role and active status |
| `POST` | `/admin/users` | Create an account |
| `GET` | `/admin/users/{username}` | Read one account |
| `PATCH` | `/admin/users/{username}` | Update any field, including password reset |
| `DELETE` | `/admin/users/{username}` | Remove an account |

Roles are ranked rather than compared for equality, so an administrator satisfies a staff
guard without needing a second account. Account management is restricted to administrators:
a staff member able to create an administrator, or to change their own role, would make the
role split decorative.

Two invariants are enforced at the route layer, because the database cannot express them:
the last active administrator cannot be deleted, deactivated or demoted, and no
administrator can perform any of those operations on themselves. Either would leave the
account collection with no reachable administrator, recoverable only by re-running the seed
script directly against the cluster.

Partial updates apply only the fields present in the request body, so an update that
toggles one flag does not blank the fields the caller omitted. Request models forbid unknown
fields, so a client cannot smuggle a password hash or an identifier into a create call.

---

## Testing and CI

196 unit tests across 16 groups, executing in approximately 11 seconds.

```bash
python -m pytest                            # the full suite
python -m pytest tests/test_pricing_rag.py  # one group
```

| Group | Tests | Coverage |
| --- | --- | --- |
| `test_vocabulary.py` | 8 | Normalization, relevance routing, affinity, query phrasing |
| `test_rtm_rules.py` | 5 | Legal floor, binding verdicts, advisory sources |
| `test_pricing_rag.py` | 9 | Trie keys, fallback levels, severity floor, batch arithmetic |
| `test_brand_index.py` | 4 | Multipliers, baseline degradation, catalog shape |
| `test_severity_rules.py` | 8 | Bands, denominators, legal floor, tyre type rules |
| `test_vision_geometry.py` | 11 | Boxes, NMS, letterboxing, detection decode, spatial matching |
| `test_agent.py` | 12 | Memory repair, tool dispatch, prompt and schema consistency, cache behaviour |
| `test_core.py` | 8 | Session lifecycle, exceptions, log redaction, wire casing |
| `test_api.py` | 6 | HTTP layer with vision and the agent stubbed |
| `test_car_specs.py` | 7 | Context-only identity, degradation, premium field handling |
| `test_catalog_source.py` | 7 | Database and file catalog sources, fallback, parity |
| `test_check_repair_prices.py` | 7 | Detail levels, floor collapse, brand from context |
| `test_appointments.py` | 20 | Documents, code minting, every rejection path, idempotency |
| `test_auth.py` | 35 | Hashing, JWT claims and forgery, role guard, user management |
| `test_admin_queries.py` | 33 | Role reach, transition table, local date windows, rescheduling |
| `test_discounts.py` | 16 | Availability, duplicate-key branches, eligibility, ticket minting |

**The suite is offline by construction rather than by convention.** An autouse fixture
patches socket creation to raise, so a test that reaches the Anthropic API, the vector
database or a model repository fails by name rather than consuming quota. Dummy credentials
and a blank database URI are injected before the first application import, because settings
are read at import time and a later patch would arrive too late; this also forces the file
catalog path even on a machine whose environment points at a live cluster.

No test loads an ONNX model, produces an embedding, or contacts a network service. The
detection decode path is exercised with a hand-constructed tensor and synthetic metadata,
which covers the geometry without the weights. Spatial-matching assertions use the two
containment values measured on real photographs rather than round numbers, so that
re-tuning the threshold past the calibration data fails loudly.

Continuous integration runs the suite on every push and pull request to the default branch,
on Python 3.13, with superseded runs cancelled automatically. CI installs a slim dependency
set rather than the full requirements file: the suite imports neither PyTorch nor
transformers, so installing them would pull several gigabytes of wheels for nothing. The
headless OpenCV build replaces the standard one, since a CI runner has no display libraries.
No secrets are configured, by design.

---

## Deployment

A multi-stage Dockerfile and a Compose file are provided. The image runs as a non-root user
and serves on port 8015.

Four deployment decisions are encoded in the build. PyTorch is installed from the CPU wheel
index before the main dependency pass, since resolving it from the default index pulls
roughly 2.5 GB of CUDA wheels that this CPU-only service never executes. OpenCV is
substituted for its headless build at image-build time, preserving a single dependency
source while avoiding display libraries a container cannot use. The ONNX graphs are baked in
as versioned application artifacts, because the service cannot function without them. The
embedding weights, at roughly 4 GB, are deliberately not baked in; they download once into a
named cache volume, since embedding them would force a re-download on every code change.

Credentials are supplied through an environment file mounted at runtime and excluded from
the build context, so no secret enters an image layer. The health check polls the readiness
endpoint with a start period long enough to cover warmup and, on a first run, the weight
download. On that first run the offline embedding flag must be disabled, since an offline
cache check against an empty volume fails outright; it should be re-enabled afterwards.

The container configuration is written but has not yet been built or executed. The frontend
is not containerized; it runs under the Vite development server or builds to static files,
which require history fallback so that client-side routes resolve.

---

## Status and roadmap

The project is approximately 95 percent complete against its planned scope. The backend is
verified end to end against real photographs, a live Qdrant cluster and MongoDB Atlas. The
frontend is complete for both the customer flow and the administrative dashboard, verified
against the live backend.

**Remaining work:**

- **Appointment lookup tool.** The agent can move and cancel a booking but cannot read one
  back, so a customer who has forgotten their appointment date cannot be answered in
  conversation. The verification routine the existing tools share is most of the
  implementation; the tool must inherit the same three-factor gate and the same
  non-specific rejection.
- **Data retention.** Inspection and appointment records are customer data and no
  time-to-live policy is defined.
- **Image lifetime.** Session expiry removes uploaded images after two hours, so a
  persisted inspection older than that retains its report but not its pixels and cannot
  render an overlay. Object storage is the intended resolution.
- **Customer-facing appointment view.** Bookings are visible to the customer only within
  the chat transcript; the calendar is the workshop's view.
- **Model publication.** The three ONNX graphs will be released on Hugging Face and linked
  from this document.
- **Container verification.** The Docker build has not yet been executed.
- **Frontend test suite.** Type checking is currently the only automated frontend
  verification.

The session store remains the hot path and is intentionally in-process: MongoDB holds the
durable copy written after a run completes, not the live state the client polls. A server
restart therefore loses in-flight inspections and chat transcripts.

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
