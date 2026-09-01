"""Preprocessing for photographed and scanned pages.

For camera-snapped documents this is the highest-leverage code in the project.
A vision model reading a shadowed, skewed 12-degree phone photo makes far more
transcription errors than the same model reading a flattened, deskewed,
contrast-normalised version of the identical page. Nothing else you can do
buys as much accuracy per line of code.

Order matters and is deliberate:
  deshadow -> deskew -> enhance
Deshadowing first, because uneven lighting confuses the skew estimate.
Enhancing last, because sharpening before rotation amplifies resampling noise.

OpenCV is used for perspective correction when present, but every other step
is pure NumPy/Pillow so the module degrades gracefully without it.
"""

from typing import Optional

import numpy as np
from PIL import Image, ImageFilter, ImageOps

try:
    import cv2
    HAS_CV2 = True
except ImportError:                                    # pragma: no cover
    HAS_CV2 = False


# --------------------------------------------------------------------------
# Uneven lighting / shadow removal
# --------------------------------------------------------------------------

def deshadow(img: Image.Image, blur_radius: int = 41) -> Image.Image:
    """Flatten uneven illumination — the single most common phone-photo defect.

    Estimate the background by heavily blurring the page (text is small and
    high-frequency, so it blurs away; the shadow gradient survives), then
    divide the original by that background. A page lit brightly on one side
    and dimly on the other comes out uniformly white.
    """
    gray = img.convert("L")
    background = gray.filter(ImageFilter.GaussianBlur(blur_radius))

    a = np.asarray(gray, dtype=np.float32)
    b = np.asarray(background, dtype=np.float32)
    b = np.maximum(b, 1.0)

    flat = np.clip(a / b * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(flat)


# --------------------------------------------------------------------------
# Skew correction
# --------------------------------------------------------------------------

def _skew_score_pil(binary_img: Image.Image, angle: float) -> float:
    rotated = binary_img.rotate(angle, resample=Image.NEAREST, fillcolor=0)
    profile = np.asarray(rotated, dtype=np.float32).sum(axis=1)
    return float(np.var(profile))


def estimate_skew(img: Image.Image, limit: float = 8.0,
                  coarse: float = 1.0, fine: float = 0.2) -> float:
    """Two-pass search for the rotation that maximises profile variance.

    Coarse pass over the full range, fine pass around the winner. Costs about
    30 cheap rotations of a downscaled copy instead of 80 of the full image.
    """
    small = img.convert("L")
    if max(small.size) > 1000:
        scale = 1000 / max(small.size)
        small = small.resize((int(small.width * scale), int(small.height * scale)),
                             Image.BILINEAR)

    # Flatten lighting on the working copy before thresholding. Without this, a
    # global threshold on a shadowed page marks the whole dark side as ink and
    # the variance search runs to the limit of its range. Cheap insurance for
    # callers that use deskew() on its own.
    small = deshadow(small, blur_radius=25)

    arr = np.asarray(small, dtype=np.uint8)
    threshold = arr.mean() - arr.std() * 0.5
    binary = Image.fromarray(((arr < threshold) * 255).astype(np.uint8))

    angles = np.arange(-limit, limit + coarse, coarse)
    best = max(angles, key=lambda a: _skew_score_pil(binary, float(a)))

    angles = np.arange(best - coarse, best + coarse + fine, fine)
    best = max(angles, key=lambda a: _skew_score_pil(binary, float(a)))
    return float(best)


def deskew(img: Image.Image, limit: float = 8.0,
           min_angle: float = 0.15) -> tuple[Image.Image, float]:
    """Rotate the page level. Returns the image and the angle applied."""
    angle = estimate_skew(img, limit=limit)
    if abs(angle) < min_angle:
        return img, 0.0
    fill = 255 if img.mode in ("L", "1") else (255, 255, 255)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True,
                      fillcolor=fill), angle


# --------------------------------------------------------------------------
# Perspective correction (photos taken at an angle) — needs OpenCV
# --------------------------------------------------------------------------

def dewarp(img: Image.Image, min_area_ratio: float = 0.35) -> Optional[Image.Image]:
    """Find the page's four corners and flatten it to a rectangle.

    Only fires when it finds a convincing quadrilateral covering a large share
    of the frame — a photo of a page lying on a desk. Returns None when it is
    not confident, so the caller keeps the original rather than accepting a
    mangled crop. Skew correction alone handles flat-bed scans.
    """
    if not HAS_CV2:
        return None

    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    scale = 900 / max(h, w) if max(h, w) > 900 else 1.0
    small = cv2.resize(arr, (int(w * scale), int(h * scale))) if scale != 1.0 else arr

    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    frame_area = small.shape[0] * small.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) != 4 or cv2.contourArea(approx) < frame_area * min_area_ratio:
            continue

        quad = approx.reshape(4, 2).astype(np.float32) / scale
        s, d = quad.sum(axis=1), np.diff(quad, axis=1).ravel()
        ordered = np.array([quad[np.argmin(s)], quad[np.argmin(d)],
                            quad[np.argmax(s)], quad[np.argmax(d)]],
                           dtype=np.float32)      # tl, tr, br, bl

        tl, tr, br, bl = ordered
        out_w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
        out_h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
        if out_w < 200 or out_h < 200:
            continue

        dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1],
                        [0, out_h - 1]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(ordered, dst)
        warped = cv2.warpPerspective(arr, matrix, (out_w, out_h),
                                     flags=cv2.INTER_CUBIC,
                                     borderValue=(255, 255, 255))
        return Image.fromarray(warped)

    return None


# --------------------------------------------------------------------------
# Contrast and sharpness
# --------------------------------------------------------------------------

def enhance(img: Image.Image, cutoff: float = 1.0) -> Image.Image:
    """Stretch contrast and restore edge definition lost to resampling.

    Deliberately stops short of binarisation. Thresholding to pure black and
    white destroys faint pencil marks, carbon-copy text and light table rules
    that a vision model can still read from a greyscale image.
    """
    gray = img.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=cutoff)
    return gray.filter(ImageFilter.UnsharpMask(radius=1.5, percent=110,
                                               threshold=3))


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def prepare(img: Image.Image, do_dewarp: bool = True,
            do_deshadow: bool = True, do_deskew: bool = True,
            do_enhance: bool = True, min_edge: int = 1000) -> tuple[Image.Image, list[str]]:
    """Run the full clean-up. Returns the image and notes on what was done."""
    notes: list[str] = []

    if max(img.size) < min_edge:
        scale = min_edge / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)),
                         Image.LANCZOS)
        notes.append(f"upscaled {scale:.1f}x — source resolution was low, "
                     f"expect reduced accuracy")

    if do_dewarp:
        warped = dewarp(img)
        if warped is not None:
            img = warped
            notes.append("perspective corrected")

    if do_deshadow:
        img = deshadow(img)
        notes.append("lighting flattened")

    if do_deskew:
        img, angle = deskew(img)
        if angle:
            notes.append(f"deskewed {angle:+.1f}°")

    if do_enhance:
        img = enhance(img)

    return img, notes


# --------------------------------------------------------------------------
# OCR-specific variant
# --------------------------------------------------------------------------

def ocr_variant(img: Image.Image) -> Image.Image:
    """Prepare an image for Tesseract specifically.

    This differs from `prepare()` on purpose. A vision model reads greyscale
    happily and benefits from the faint detail that thresholding destroys.
    Tesseract is the opposite: it was built around clean bi-level input, and
    it reads sharpened sensor noise as text — the failure that turns a scanned
    "87" into a line of gibberish.

    So for the OCR path: denoise first, then threshold hard.
    """
    arr = np.asarray(img.convert("L"))

    if HAS_CV2:
        # Edge-preserving denoise. Median blur alone eats thin strokes; this
        # keeps character edges while flattening the speckle between them.
        arr = cv2.fastNlMeansDenoising(arr, None, h=10, templateWindowSize=7,
                                       searchWindowSize=21)
        # Otsu picks the threshold from this page's own histogram rather than
        # a fixed value that suits one scanner and not the next.
        _, arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        img2 = Image.fromarray(arr).filter(ImageFilter.MedianFilter(3))
        arr = np.asarray(img2)
        arr = ((arr > arr.mean() - arr.std() * 0.4) * 255).astype(np.uint8)

    return Image.fromarray(arr)
