"""
Step 6 — Paper Assembly Engine

Assembles individual GeneratedQuestion objects into a complete PaperOutput.
Handles OR-pair questions (Q1 or Q2 → two variants in one section).
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone

from generation.schemas import (
    BlueprintSpec, GeneratedQuestion, PaperOutput,
    PaperSection, GeneratedVariant, QuestionSpec,
)


def _make_variant_label(spec: QuestionSpec, is_second: bool = False) -> str:
    """Return variant label for display: 'Q1', 'Q2', or blank."""
    if spec.is_or_pair:
        q_no = spec.or_pair_with if is_second else spec.question_no
        return f"Q{q_no}"
    return f"Q{spec.question_no}"


def assemble_paper(
    blueprint: BlueprintSpec,
    questions_per_spec: Dict[int, GeneratedQuestion],
    co_map: Dict[int, str],
) -> PaperOutput:
    """
    Step 6: Assemble final PaperOutput from individual generated questions.

    Args:
        blueprint: Full blueprint with all QuestionSpec objects
        questions_per_spec: Maps question_no → GeneratedQuestion
        co_map: unit_id → CO label mapping

    Returns:
        Complete PaperOutput with sections and variants
    """
    # Track which question_nos have been assembled (to avoid duplicating OR pairs)
    assembled_nos = set()
    sections: List[PaperSection] = []

    for spec in blueprint.questions:
        if spec.question_no in assembled_nos:
            continue

        # Resolve CO
        primary_unit = spec.units[0] if spec.units else None
        co_label = co_map.get(primary_unit) if primary_unit else "CO1"
        if not co_label:
            co_label = f"CO{min(spec.units)}" if spec.units else "CO1"

        generated = questions_per_spec.get(spec.question_no)
        if generated is None:
            # Create placeholder if generation failed
            from generation.schemas import MarkingPoint
            generated = GeneratedQuestion(
                question_type=spec.question_type,
                question_text=f"[Question {spec.question_no} — generation failed]",
                bloom_level=spec.bloom_targets[0] if spec.bloom_targets else "understand",
                difficulty=spec.difficulty,
                marks=spec.marks,
                answer_key="",
                options=[],
                marking_scheme=[MarkingPoint(point="Full marks for complete answer", marks=spec.marks)],
                source_chunk_ids=[],
                source_asset_ids=[],
                co_mapped=co_label,
                unit_ids=spec.units,
            )

        generated.co_mapped = co_label

        if spec.is_or_pair and spec.or_pair_with is not None:
            # Find the paired spec
            paired_spec = next(
                (s for s in blueprint.questions if s.question_no == spec.or_pair_with),
                None,
            )
            paired_gen = questions_per_spec.get(spec.or_pair_with)
            if paired_gen:
                paired_unit = paired_spec.units[0] if paired_spec and paired_spec.units else primary_unit
                paired_co = co_map.get(paired_unit) if paired_unit else co_label
                paired_gen.co_mapped = paired_co or co_label

            variants = [
                GeneratedVariant(
                    variant_label=f"Q{spec.question_no}",
                    question=generated,
                ),
            ]
            if paired_gen:
                variants.append(GeneratedVariant(
                    variant_label=f"Q{spec.or_pair_with}",
                    question=paired_gen,
                ))
                assembled_nos.add(spec.or_pair_with)

            sections.append(PaperSection(
                question_no=spec.question_no,
                marks=spec.marks,
                co_mapped=co_label,
                bloom_level=generated.bloom_level,
                variants=variants,
            ))
        else:
            # Normal single question
            sections.append(PaperSection(
                question_no=spec.question_no,
                marks=spec.marks,
                co_mapped=co_label,
                bloom_level=generated.bloom_level,
                variants=[
                    GeneratedVariant(
                        variant_label=f"Q{spec.question_no}",
                        question=generated,
                    )
                ],
            ))

        assembled_nos.add(spec.question_no)

    # Sort sections by question_no
    sections.sort(key=lambda s: s.question_no)

    return PaperOutput(
        subject_id=blueprint.subject_id,
        total_marks=blueprint.total_marks,
        sections=sections,
        created_at=datetime.now(timezone.utc),
        generation_metadata={
            "question_count": len(sections),
            "or_pairs": sum(1 for s in sections if len(s.variants) > 1),
            "bloom_distribution": _bloom_distribution(sections),
        },
    )


def _bloom_distribution(sections: List[PaperSection]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for sec in sections:
        bl = sec.bloom_level or "unknown"
        dist[bl] = dist.get(bl, 0) + 1
    return dist
