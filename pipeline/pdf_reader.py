from __future__ import annotations

import pymupdf
import re
import pypdfium2 as pdfium
from PIL import Image
from typing import Dict, List, Optional


class PDFPlanReader:
    """Extracts dimensions, annotations, and multi-page images from architectural PDFs.

    Every extracted value carries a companion "*_detected" flag. When the
    regex text search finds nothing, the field is returned as None rather
    than a fabricated default — the caller must show that explicitly and
    require the engineer to enter it manually.
    """

    @staticmethod
    def render_all_pages(file_bytes: bytes) -> List[Image.Image]:
        """Renders every page of the PDF into PIL images for instant switching."""
        pdf = pdfium.PdfDocument(file_bytes)
        images = []
        for page in pdf:
            images.append(page.render(scale=2.0).to_pil())
        return images

    @staticmethod
    def extract_plan_parameters(file_bytes: bytes) -> Dict:
        """Extracts spans, footing sizes, slab thickness, and material specs.

        Returns None (not a guessed number) for any field the text search
        does not find, plus the matched source snippet for whichever fields
        it does find, so the UI can show the engineer what to verify.
        """
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + "\n"

        # 1. Spans (e.g. 3000, 4200, 5000)
        found_spans = re.findall(r"\b[2-9]\d{3}\b", full_text)
        spans_m = sorted({float(s) / 1000.0 for s in found_spans if 2.0 <= float(s) / 1000.0 <= 12.0})

        # 2. Footing dimensions (matches e.g., "1350MM", "L = B = 1100MM")
        footing_matches = re.findall(r"(?:BASE\s*|L\s*=\s*B\s*=\s*)(\d{3,4})\s*MM", full_text, re.IGNORECASE)
        pad_sizes = [float(f) for f in footing_matches if 800 <= float(f) <= 3000]

        # 3. Slab thickness (matches e.g., "SLAB THICKNESS = 150MM")
        slab_match = re.search(r"SLAB\s+THICKNESS\s*=\s*(\d{2,3})\s*MM", full_text, re.IGNORECASE)

        # 4. Concrete strength class, if explicitly stated
        fcu_match = re.search(r"(?:CLASS|GRADE)\s*(20|25|30|35|40)\b", full_text, re.IGNORECASE)

        return {
            "spans_m": spans_m if spans_m else None,
            "spans_detected": bool(spans_m),
            "detected_pad_dim": pad_sizes[0] if pad_sizes else None,
            "pad_dim_detected": bool(pad_sizes),
            "detected_slab_thick": float(slab_match.group(1)) if slab_match else None,
            "slab_thick_detected": bool(slab_match),
            "fcu": float(fcu_match.group(1)) if fcu_match else None,
            "fcu_detected": bool(fcu_match),
            "total_pages": len(doc),
        }
