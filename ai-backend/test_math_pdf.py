"""
Quick visual test for math rendering in question paper PDFs.

Run from the ai-backend directory:
    python3 test_math_pdf.py

Opens (or saves) a sample question paper PDF with real rendered math.
Inspect the output file at: /tmp/test_math_paper.pdf
"""

import sys
sys.path.insert(0, ".")

from io import BytesIO
from generation.paper_exporter import generate_question_paper, generate_answer_key
from generation.schemas import (
    PaperOutput, PaperSection, GeneratedVariant,
    GeneratedQuestion, MCQOption, MarkingPoint,
)


def make_sample_paper() -> PaperOutput:
    sections = [
        # MCQ with inline math in question and options
        PaperSection(
            question_no=1,
            marks=2,
            co_mapped=None,
            bloom_level="understand",
            variants=[
                GeneratedVariant(
                    variant_label="Q1",
                    question=GeneratedQuestion(
                        question_type="mcq",
                        question_text=r"Which of the following correctly represents the quadratic formula for \( ax^2 + bx + c = 0 \)?",
                        bloom_level="understand",
                        difficulty="easy",
                        marks=2,
                        options=[
                            MCQOption(label="A", text=r"\( x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a} \)"),
                            MCQOption(label="B", text=r"\( x = \frac{b \pm \sqrt{b^2 + 4ac}}{2a} \)"),
                            MCQOption(label="C", text=r"\( x = \frac{-b \pm \sqrt{b^2 + 4ac}}{a} \)"),
                            MCQOption(label="D", text=r"\( x = \frac{b - \sqrt{b^2 - 4ac}}{2a} \)"),
                        ],
                        answer_key="A",
                        marking_scheme=[],
                        source_chunk_ids=[],
                        source_asset_ids=[],
                        unit_ids=[1],
                    ),
                )
            ],
        ),

        # Descriptive with inline and display math
        PaperSection(
            question_no=2,
            marks=5,
            co_mapped=None,
            bloom_level="apply",
            variants=[
                GeneratedVariant(
                    variant_label="Q2",
                    question=GeneratedQuestion(
                        question_type="descriptive",
                        question_text=(
                            r"Evaluate the definite integral \( \int_0^1 x^2\,dx \) "
                            r"and verify that the result equals \( \frac{1}{3} \). "
                            r"Also find the area under the curve \( y = x^2 \) from \( x = 0 \) to \( x = 2 \)."
                        ),
                        bloom_level="apply",
                        difficulty="medium",
                        marks=5,
                        options=[],
                        answer_key=(
                            r"Using the power rule: \( \int_0^1 x^2\,dx = \left[\frac{x^3}{3}\right]_0^1 = \frac{1}{3} - 0 = \frac{1}{3} \). "
                            r"For the second part: \( \int_0^2 x^2\,dx = \left[\frac{x^3}{3}\right]_0^2 = \frac{8}{3} \approx 2.67 \) square units."
                        ),
                        marking_scheme=[
                            MarkingPoint(point=r"Correct application of power rule: \( \int x^n dx = \frac{x^{n+1}}{n+1} \)", marks=2),
                            MarkingPoint(point=r"Correct substitution of limits to get \( \frac{1}{3} \)", marks=1),
                            MarkingPoint(point=r"Second integral evaluated correctly as \( \frac{8}{3} \)", marks=2),
                        ],
                        source_chunk_ids=[],
                        source_asset_ids=[],
                        unit_ids=[1],
                    ),
                )
            ],
        ),

        # OR question with math in both variants
        PaperSection(
            question_no=3,
            marks=4,
            co_mapped=None,
            bloom_level="analyze",
            variants=[
                GeneratedVariant(
                    variant_label="Q3a",
                    question=GeneratedQuestion(
                        question_type="descriptive",
                        question_text=(
                            r"Prove using induction that \( \sum_{k=1}^{n} k = \frac{n(n+1)}{2} \) for all \( n \geq 1 \)."
                        ),
                        bloom_level="analyze",
                        difficulty="medium",
                        marks=4,
                        options=[],
                        answer_key=(
                            r"Base case: n=1, LHS = 1, RHS = \( \frac{1 \cdot 2}{2} = 1 \). Holds. "
                            r"Inductive step: Assume true for n=k. Then sum to k+1 = \( \frac{k(k+1)}{2} + (k+1) = \frac{(k+1)(k+2)}{2} \). QED."
                        ),
                        marking_scheme=[
                            MarkingPoint(point=r"Correct base case verification", marks=1),
                            MarkingPoint(point=r"Inductive hypothesis stated correctly: \( \sum_{k=1}^{n} k = \frac{n(n+1)}{2} \)", marks=1),
                            MarkingPoint(point=r"Inductive step completed with algebraic manipulation", marks=2),
                        ],
                        source_chunk_ids=[],
                        source_asset_ids=[],
                        unit_ids=[2],
                    ),
                ),
                GeneratedVariant(
                    variant_label="Q3b",
                    question=GeneratedQuestion(
                        question_type="descriptive",
                        question_text=(
                            r"Find the derivative of \( f(x) = x^3 \sin(x) \) using the product rule, "
                            r"and evaluate \( f'(\pi) \)."
                        ),
                        bloom_level="apply",
                        difficulty="medium",
                        marks=4,
                        options=[],
                        answer_key=(
                            r"By product rule: \( f'(x) = 3x^2 \sin(x) + x^3 \cos(x) \). "
                            r"At \( x = \pi \): \( f'(\pi) = 3\pi^2 \sin(\pi) + \pi^3 \cos(\pi) = 0 - \pi^3 = -\pi^3 \)."
                        ),
                        marking_scheme=[
                            MarkingPoint(point=r"Product rule applied: \( (uv)' = u'v + uv' \)", marks=1),
                            MarkingPoint(point=r"Correct derivatives: \( u'=3x^2 \), \( v'=\cos(x) \)", marks=1),
                            MarkingPoint(point=r"Final answer \( -\pi^3 \) correct", marks=2),
                        ],
                        source_chunk_ids=[],
                        source_asset_ids=[],
                        unit_ids=[2],
                    ),
                ),
            ],
        ),
    ]

    return PaperOutput(
        subject_id=1,
        total_marks=11,
        sections=sections,
    )


def run():
    paper = make_sample_paper()

    print("Generating question paper PDF...")
    qp_buf = generate_question_paper(paper, subject_name="Mathematics", college_name="PICT, Pune")

    print("Generating answer key PDF...")
    ak_buf = generate_answer_key(paper, subject_name="Mathematics", college_name="PICT, Pune")

    qp_path = "/tmp/test_math_paper.pdf"
    ak_path = "/tmp/test_math_answer_key.pdf"

    with open(qp_path, "wb") as f:
        f.write(qp_buf.read())
    with open(ak_path, "wb") as f:
        f.write(ak_buf.read())

    print(f"\nQuestion paper : {qp_path}")
    print(f"Answer key     : {ak_path}")
    print("\nOpen these files to verify that math is rendered as proper symbols, not raw LaTeX.")

    # Try to open automatically on macOS
    import subprocess
    subprocess.run(["open", qp_path], check=False)
    subprocess.run(["open", ak_path], check=False)


if __name__ == "__main__":
    run()
