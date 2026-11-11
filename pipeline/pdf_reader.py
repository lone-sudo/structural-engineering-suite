from __future__ import annotations

import re
from typing import Dict, List, Optional

import pymupdf
from PIL import Image


class PDFPlanReader:
    """Extracts dimensions, annotations and page images from architectural PDFs.

    Every extracted value carries a companion "*_detected" flag. When the
    text search finds nothing, the field is returned as None rather than a
    fabricated default — the caller must show that explicitly and require the
    engineer to enter it manually.

    Span detection is deliberately restricted to text lines that actually
    contain a span/grid/bay label. The previous version scanned the whole
    document for any four-digit number, so a phone number, a drawing number
    or a date could be presented as a "detected span". That is worse than
    detecting nothing.

    Uses PyMuPDF only (text extraction AND page rendering) — a separate
    pypdfium2 dependency previously handled rendering alone, which was
    redundant since PyMuPDF's own get_pixmap() does the same job. Neither
    library performs OCR: a scanned/image-only PDF with no text layer will
    have nothing to extract regardless of which renderer is used.
    """

    _SPAN_LABEL = re.compile(r"\b(SPAN|SPANS|GRID|BAY|BAYS|L\s*X|L\s*Y|Lx|Ly)\b", re.IGNORECASE)
    _NUMBER = re.compile(r"\b(\d{3,5})\b")

    @staticmethod
    def render_all_pages(file_bytes: bytes) -> List[Image.Image]:
        """Renders every page of the PDF into PIL images for instant switching."""
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0))
            images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return images

    @staticmethod
    def _spans_from_labelled_lines(full_text: str) -> List[float]:
        candidates: List[float] = []
        for line in full_text.splitlines():
            if not PDFPlanReader._SPAN_LABEL.search(line):
                continue
            for raw in PDFPlanReader._NUMBER.findall(line):
                value = float(raw)
                value_m = value / 1000.0 if value > 100.0 else value
                if 1.5 <= value_m <= 15.0:
                    candidates.append(round(value_m, 2))
        return sorted(set(candidates))

    @staticmethod
    def extract_plan_parameters(file_bytes: bytes) -> Dict:
        """Extracts spans, footing sizes, slab thickness and material class.

        Returns None (not a guessed number) for any field the text search
        does not find, plus a note explaining where a detected span came
        from, so the UI can show the engineer what to verify.
        """
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + "\n"

        # 1. Spans, only from lines that actually name a span/grid/bay.
        spans_m = PDFPlanReader._spans_from_labelled_lines(full_text)

        # 2. Footing dimensions (matches e.g., "1350MM", "L = B = 1100MM")
        footing_matches = re.findall(r"(?:BASE\s*|L\s*=\s*B\s*=\s*)(\d{3,4})\s*MM", full_text, re.IGNORECASE)
        pad_sizes = [float(f) for f in footing_matches if 800 <= float(f) <= 3000]

        # 3. Slab thickness (matches e.g., "SLAB THICKNESS = 150MM")
        slab_match = re.search(r"SLAB\s+THICKNESS\s*=\s*(\d{2,3})\s*MM", full_text, re.IGNORECASE)

        # 4. Concrete strength class, if explicitly stated
        fcu_match = re.search(r"(?:CLASS|GRADE)\s*(20|25|30|35|40|45|50)\b", full_text, re.IGNORECASE)

        return {
            "spans_m": spans_m if spans_m else None,
            "spans_detected": bool(spans_m),
            "span_detection_note": (
                "Spans are read only from text lines containing SPAN/GRID/BAY/Lx/Ly. "
                "Confirm every value against the drawing."
                if spans_m else
                "No labelled span text found. Enter the spans manually."
            ),
            "detected_pad_dim": pad_sizes[0] if pad_sizes else None,
            "pad_dim_detected": bool(pad_sizes),
            "detected_slab_thick": float(slab_match.group(1)) if slab_match else None,
            "slab_thick_detected": bool(slab_match),
            "fcu": float(fcu_match.group(1)) if fcu_match else None,
            "fcu_detected": bool(fcu_match),
            "total_pages": len(doc),
            "text_characters": len(full_text),
        }
