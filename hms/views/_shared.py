import logging
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger("hms.views")

# ======================================================
# FONT REGISTRATION (UNICODE SAFE - Rs SUPPORT)
# ======================================================
FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts", "DejaVuSans.ttf")
pdfmetrics.registerFont(TTFont("HospitalFont", FONT_PATH))
