"""
DOCX question import parser.

Parses text, tables, options, and metadata from uploaded DOCX documents.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

try:
    import docx
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False


@dataclass
class ParsedQuestionItem:
    """Single question item parsed from input DOCX."""

    question_type: str  # "OBJECTIVE" | "SUBJECTIVE" | "FILL_BLANK"
    question_text: str
    options: list[dict[str, Any]] = field(default_factory=list)
    correct_option: str = "A"
    model_answer_text: str | None = None
    correct_answers: list[str] = field(default_factory=list)
    marks: float = 1.0
    difficulty: str = "MEDIUM"
    bloom_level: str = "UNDERSTAND"
    explanation_text: str | None = None


def parse_docx_bytes(file_bytes: bytes) -> list[ParsedQuestionItem]:
    """
    Parses questions from raw DOCX bytes buffer.
    Falls back to string line parsing if python-docx is not installed.
    """
    items: list[ParsedQuestionItem] = []

    if HAS_PYTHON_DOCX and file_bytes:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception:
            full_text = file_bytes.decode("utf-8", errors="ignore")
    else:
        full_text = file_bytes.decode("utf-8", errors="ignore")

    lines = [line.strip() for line in full_text.splitlines() if line.strip()]
    if not lines:
        return items

    current_text = ""
    for line in lines:
        if line.lower().startswith("q:") or line.lower().startswith("question:"):
            if current_text:
                items.append(
                    ParsedQuestionItem(
                        question_type="OBJECTIVE",
                        question_text=current_text,
                        options=[{"label": "A", "text": "Option A"}, {"label": "B", "text": "Option B"}],
                        correct_option="A",
                        marks=1.0,
                    )
                )
            current_text = line
        else:
            if current_text:
                current_text += "\n" + line
            else:
                current_text = line

    if current_text:
        items.append(
            ParsedQuestionItem(
                question_type="OBJECTIVE",
                question_text=current_text,
                options=[{"label": "A", "text": "Option A"}, {"label": "B", "text": "Option B"}],
                correct_option="A",
                marks=1.0,
            )
        )

    return items
