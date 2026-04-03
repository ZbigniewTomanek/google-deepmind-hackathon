# Domain-Specific Ontology Seeds

Reference for Stage 2. Each domain lists the recommended node and edge types.
These are derived from analyzing the current (broken) graphs to find the types
that ARE semantically correct and would cover 90%+ of the actual data.

---

## Universal Base Types (all schemas)

### Node Types (20)
| Type | Description |
|------|-------------|
| Person | Human individual |
| Organization | Company, institution, or group |
| Location | Physical place or address |
| Event | Something that happened at a specific time |
| Project | Planned endeavor with goals and tasks |
| Tool | Software tool, library, or technology |
| Concept | Abstract idea or topic |
| Document | Source document or file |
| Preference | User preference or opinion |
| Activity | Physical or mental activity |
| Asset | Physical object or piece of equipment |
| Substance | Supplement, medication, or consumed substance |
| Metric | Quantitative measurement or score |
| Symptom | Health symptom or medical condition |
| Goal | Objective or target to achieve |
| Task | Specific action to complete |
| Emotion | Emotional or psychological state |
| Recipe | Instructions for preparing food |
| Protocol | Structured intervention or procedure |
| Routine | Recurring behavioral pattern or habit |

### Edge Types (23)
| Type | Description |
|------|-------------|
| RELATES_TO | General relationship |
| MENTIONS | Source mentions target |
| CAUSED_BY | Target caused source |
| FOLLOWS | Source follows target in sequence |
| AUTHORED | Source authored target |
| USES | Source uses target |
| CONTRADICTS | Source contradicts target |
| SUPPORTS | Source supports/confirms target |
| SUMMARIZES | Source is a summary of target |
| DERIVED_FROM | Source was derived from target |
| SUPERSEDES | Source replaces target (target is outdated) |
| CORRECTS | Source corrects an error in target |
| HAS_GOAL | Entity has a goal or objective |
| WORKS_ON | Person works on project |
| WORKS_FOR | Person works for organization |
| LOCATED_AT | Entity is at a location |
| PART_OF | Entity is part of another entity |
| EXPERIENCED | Person experienced event or state |
| CONSUMES | Person consumes substance or food |
| PERFORMS | Person performs activity or routine |
| OWNS | Person or org owns an asset |
| RECOMMENDS | Source recommends target |
| IMPROVES | Source improves or alleviates target |

---

## User Profile & Preferences

### Additional Node Types (15)
| Type | Description |
|------|-------------|
| Dream | Dream or sleep experience |
| HealthState | Physical or mental health state or energy level |
| Trip | Planned or completed journey or vacation |
| FoodItem | Dish, meal, or food product |
| Ingredient | Food substance used in cooking |
| MediaWork | Book, movie, podcast, or creative work |
| Vehicle | Car, bicycle, or transportation |
| Reflection | Subjective assessment of experiences or emotions |
| Interest | Hobby or leisure interest |
| Contract | Legal agreement or insurance policy |
| FinancialEvent | Transaction, salary change, or significant purchase |
| BodyPart | Anatomical location or body region |
| Specification | Technical specification of an asset |
| Insight | Lesson learned or guiding principle |
| Skill | Cognitive or physical ability |

### Additional Edge Types (25)
| Type | Description |
|------|-------------|
| HAS_STATUS | Current physical or mental state |
| EXPERIENCES_SYMPTOM | Health condition observed or experienced |
| PERFORMS_ROUTINE | Recurring habit or practice |
| HAS_PARTNER | Romantic partner relationship |
| HAS_PET | Pet ownership |
| VISITS_LOCATION | Visited a specific place |
| HAD_DREAM | Dream experienced by person |
| HAS_ASSET | Person owns or manages a physical object |
| HAS_METRIC | Measurement associated with health or activity |
| HAS_INGREDIENT | Food item contains an ingredient |
| ATTENDED_EVENT | Person attended an event |
| CONSUMES_MEDIA | Person read/watched a media work |
| TRIGGERS_EMOTION | Event or state triggers an emotion |
| HAS_REFLECTION | Person reflects on a period or event |
| LEARNED_LESSON | Person learned a lesson from experience |
| PURCHASED_ASSET | Person bought an asset |
| FILED_CLAIM | Insurance claim filed for asset |
| HAS_FINANCIAL_EVENT | Financial transaction involving person |
| IMPLEMENTED_PROTOCOL | Person followed a health protocol |
| IMPROVED_SYMPTOM | Intervention improved a symptom |
| RECEIVED_GIFT | Person received an item as gift |
| RECOMMENDED_BY | Item recommended by another person |
| SHIFTS_SENTIMENT | Experience changed a person's attitude |
| DISCONTINUED | Person stopped using a substance |
| FAMILY_RELATION | Family relationship between individuals |

---

## Technical Knowledge

### Additional Node Types (15)
| Type | Description |
|------|-------------|
| Component | Software module, class, or service |
| Schema | Data structure, database schema, or format |
| DataFormat | Specific data format (JSON, XML, CSV) |
| Model | Machine learning model or AI system |
| Algorithm | Computational method or procedure |
| Infrastructure | Computing resource (CPU, GPU, storage) |
| ConfigurationSetting | Environment variable or tuning parameter |
| Strategy | Plan or methodology for a technical process |
| Rule | Logic or heuristic for filtering or matching |
| BenchmarkResult | Outcome of a performance test |
| Repository | Code repository or version-controlled project |
| Issue | Software defect or known problem |
| WorkflowStep | Script, job, or automated action |
| ArchitecturePattern | Software design pattern or system organization |
| Discipline | Field of study or branch of knowledge |

### Additional Edge Types (20)
| Type | Description |
|------|-------------|
| DEPENDS_ON | Component depends on another |
| DEPLOYED_ON | System deployed on infrastructure |
| IMPLEMENTS | Component implements a protocol or pattern |
| EXTRACTS | Component extracts data from source |
| TRANSFORMS | Component transforms data format |
| VALIDATES | Component validates data against rules |
| OPTIMIZES | Strategy improves performance of target |
| HAS_CONFIGURATION | System has a configuration setting |
| HAS_SCHEMA | Component uses a data schema |
| HAS_BENCHMARK_RESULT | System has a performance measurement |
| HAS_ISSUE | Component has a known problem |
| HAS_WORKAROUND | Issue has a temporary fix |
| ROOT_CAUSE_OF | Factor is the root cause of an issue |
| RUNS_ON_HARDWARE | Software executes on hardware |
| HOSTED_ON | Component hosted on infrastructure |
| DEFINED_IN | Config or component defined in a file |
| COMPATIBLE_WITH | Component works with another |
| MIGRATED_FROM | Component migrated from legacy system |
| SUPPORTS_FORMAT | Component handles a data format |
| LOCATED_AT | File or resource at a path |

---

## Work & Projects

### Additional Node Types (15)
| Type | Description |
|------|-------------|
| Epic | High-level project container grouping related tasks |
| Ticket | Specific work item in project management |
| Benchmark | Performance test or experimental run |
| Presentation | Talk, slide deck, or knowledge sharing session |
| Company | Business entity or client |
| ProfessionalRole | Job title or position |
| Article | Blog post, white paper, or journal entry |
| Hackathon | Collaborative development event |
| Salary | Financial compensation amount |
| Benefit | Reward or financial gain from work |
| Challenge | Obstacle or technical difficulty |
| ReviewProcess | Recurring ceremony (retrospective, standup) |
| ResearchProject | Discovery or feasibility study |
| Experiment | Controlled test or trial |
| Phase | Stage within a project or initiative |

### Additional Edge Types (15)
| Type | Description |
|------|-------------|
| ASSIGNED_TO | Person assigned to task |
| BELONGS_TO_EPIC | Task belongs to an epic |
| HAS_DEADLINE | Task has a deadline |
| HAS_OBJECTIVE | Project has an objective |
| PARTICIPATED_IN | Person participated in event |
| EARNED_REWARD | Person earned a financial reward |
| DISCUSSED_WITH | Person discussed topic with another |
| PRESENTED_TO | Person presented to audience |
| HAS_PLAN | Project has an implementation plan |
| ON_TICKET | Work tracked by a ticket |
| ASSOCIATED_WITH | Event associated with organization |
| RESEARCHES | Task focused on research |
| CREATED_PRESENTATION | Person created a presentation |
| HAS_COST | Event has a financial cost |
| REVIEWED_BY | Work reviewed by person or process |

---

## Domain Knowledge

### Additional Node Types (15)
| Type | Description |
|------|-------------|
| Dish | Prepared food item or recipe |
| Ingredient | Specific food substance for cooking |
| PreparationTechnique | Cooking method or technique |
| Utensil | Kitchen tool or appliance |
| FlavorProfile | Taste characteristic (sweet, salty, umami) |
| FoodCategory | Category of meal (main, side, dessert) |
| Publication | Blog post, article, or newsletter |
| Service | Commercial service or subscription |
| Vehicle | Specific vehicle model or type |
| Component | Part of a vehicle or hardware system |
| Brand | Manufacturer or product brand |
| Agreement | Legal document, lease, or contract |
| Supplement | Dietary supplement or vitamin |
| Condition | Medical or health condition |
| MedicalReport | Diagnostic test results or report |

### Additional Edge Types (15)
| Type | Description |
|------|-------------|
| HAS_INGREDIENT | Dish contains ingredient |
| BELONGS_TO_CATEGORY | Dish is in a food category |
| HAS_FLAVOR_PROFILE | Dish has a taste characteristic |
| USES_TECHNIQUE | Recipe uses preparation technique |
| USES_UTENSIL | Recipe uses a kitchen tool |
| ORIGINATES_FROM | Dish originates from a culture/region |
| PREPARED_BY_GUIDE | Dish prepared using instructions |
| HAS_SPECIFICATION | Vehicle has technical specification |
| INSTALLED_ON | Component installed on hardware |
| MANUFACTURED_BY | Product made by a brand |
| HAS_COST | Service or asset has a price |
| HAS_DEADLINE | Task has an administrative deadline |
| REQUIRES_DOCUMENT | Process requires a specific document |
| HAS_CONDITION | Person has health condition |
| HAS_RESULT_VALUE | Report has a diagnostic result |
