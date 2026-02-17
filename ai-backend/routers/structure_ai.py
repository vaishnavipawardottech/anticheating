"""
Structure AI Router
LLM-powered syllabus normalization endpoint

This router is ADVISORY ONLY and does NOT write to the database.
It helps teachers convert raw syllabus text into a clean structure draft.
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import os
from openai import OpenAI

router = APIRouter(prefix="/structure", tags=["structure-ai"])


# ==========================================
# GOOGLE GEMINI (OpenAI-Compatible API)
# ==========================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY environment variable not set.")

client = OpenAI(
    api_key=GOOGLE_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)


# ==========================================
# SCHEMAS
# ==========================================

class SyllabusNormalizeRequest(BaseModel):
    raw_text: str = Field(
        ...,
        min_length=10,
        description="Raw syllabus text to normalize"
    )
    subject_hint: Optional[str] = Field(
        None,
        description="Optional hint for subject name if not in text"
    )


class ConceptDraft(BaseModel):
    pass


class UnitDraft(BaseModel):
    name: str = Field(..., description="Unit name")
    concepts: List[str] = Field(..., description="List of concept names")


class StructureDraft(BaseModel):
    status: str = Field(default="DRAFT", description="Always 'DRAFT'")
    subject: str = Field(..., description="Subject name")
    units: List[UnitDraft] = Field(..., description="List of units with concepts")


# ==========================================
# NORMALIZATION PROMPT
# ==========================================


NORMALIZATION_PROMPT_TEMPLATE = """
You are helping normalize an academic syllabus into a clean internal structure.

IMPORTANT RULES:
- You are NOT defining the syllabus. The teacher is the authority.
- You must ONLY extract and clean what is already present.
- Do NOT invent topics.
- Do NOT merge or remove units.
- If unsure, keep the original wording.
- Output is a DRAFT and will be reviewed by a teacher.
- Return JSON ONLY. No explanations.

TASK:
Convert the raw syllabus text below into the following structure:

Subject → Units → Concepts

DEFINITIONS:
- Subject: The overall course name (if explicitly mentioned).
  If not explicitly mentioned, infer from context conservatively.
- Unit: High-level syllabus sections (e.g., Unit-I, Section 1, Chapter 1).
- Concept: Main topics listed under each unit. Keep related sub-topics together.

HIERARCHICAL GROUPING RULES:
- When you see "Topic: subtopic1, subtopic2, subtopic3", treat the ENTIRE thing as ONE concept
- Example: "Data Modeling: Entity Relationship (ER) Model, Extended ER Model, Relational Model"
  Should become ONE concept: "Data Modeling: Entity Relationship (ER) Model, Extended ER Model, Relational Model"
- Do NOT split comma-separated items if they are clearly sub-parts of a main topic
- Only create separate concepts when topics are on separate lines OR clearly independent

EXAMPLES:
BAD (too granular):
  - "Data Modeling: Entity Relationship (ER) Model"
  - "Extended ER Model"
  - "Relational Model"

GOOD (preserves hierarchy):
  - "Data Modeling: Entity Relationship (ER) Model, Extended ER Model, Relational Model, Codd's Rules"

BAD (too granular):
  - "SQL: DDL"
  - "DML"
  - "Select Queries"

GOOD (keeps related items together):
  - "SQL: DDL, DML, Select Queries, Set/String/Date Functions, Aggregate Functions, Joins, Nested Queries"

INPUT:
\"\"\"
{raw_text}
\"\"\"

OUTPUT FORMAT (STRICT JSON):

{{
  "status": "DRAFT",
  "subject": "<string>",
  "units": [
    {{
      "name": "<unit name>",
      "concepts": [
        "<concept 1 with all its sub-topics>",
        "<concept 2 with all its sub-topics>"
      ]
    }}
  ]
}}

CONSTRAINTS:
- Preserve original terminology as much as possible
- Keep related sub-topics grouped under their main topic
- Ignore page numbers, hours, formatting noise
- Do NOT reorder units
- Do NOT split hierarchical topics into flat lists
- If a line has "MainTopic: subtopic1, subtopic2", keep it as ONE concept

REMEMBER: Return ONLY valid JSON. No markdown, no explanations, no code blocks.
"""


# ==========================================
# GEMINI CALL
# ==========================================

async def call_gemini_flash(prompt: str) -> str:
    """
    Calls Gemini 2.5 Flash Lite using OpenAI-compatible API.
    Returns raw JSON string.
    """

    try:
        print(f"Calling Gemini API (prompt length: {len(prompt)} chars)...")
        response = client.chat.completions.create(
            model="gemini-2.5-flash-lite",
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=1200,
        )

        content = response.choices[0].message.content
        print(f"Gemini API success (response length: {len(content)} chars)")
        return content

    except Exception as e:
        print(f"Gemini API error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gemini API failed: {str(e)}"
        )


# ==========================================
# JSON EXTRACTION 
# ==========================================

def extract_json_from_response(response: str) -> dict:
    text = response.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    start_idx = text.find("{")
    end_idx = text.rfind("}") + 1

    if start_idx == -1 or end_idx == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM did not return valid JSON."
        )

    json_str = text[start_idx:end_idx]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse LLM JSON response: {str(e)}"
        )


# ==========================================
# ENDPOINTS
# ==========================================

@router.post("/normalize", response_model=StructureDraft)
async def normalize_syllabus(request: SyllabusNormalizeRequest):
    try:
        approx_tokens = len(request.raw_text) // 4
        if approx_tokens > 2000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Input text too long."
            )

        prompt = NORMALIZATION_PROMPT_TEMPLATE.format(
            raw_text=request.raw_text
        )

        print(f"Calling Gemini for TOC normalization...")
        llm_response = await call_gemini_flash(prompt)
        print(llm_response)
        print(f"Gemini response received ({len(llm_response)} chars)")

        structure_dict = extract_json_from_response(llm_response)

        try:
            return StructureDraft(**structure_dict)
        except Exception as e:
            print(f"Failed to parse structure: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM returned invalid structure format: {str(e)}"
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Fatal error in normalize_syllabus: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Normalization failed: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Health check for Gemini API
    """
    try:
        response = client.chat.completions.create(
            model="gemini-2.5-flash-lite",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )

        return {
            "status": "healthy",
            "provider": "Google Gemini",
            "model": "gemini-2.5-flash-lite"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Gemini health check failed: {str(e)}"
        )
