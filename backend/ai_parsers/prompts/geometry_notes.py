VISUAL_GEOMETRY_NOTE = (
    "VISUALISATION GEOMETRY (coordinates normalised 0..1 relative to the whole image, x to the right, y downward; origin top-left). "
    "For EVERY 'anomalies' object, besides 'box' (a box that FITS the abnormality, not the whole structure/organ) include "
    "when you can determine them from the visible pixels: "
    '"polygon": [[x,y],...] (6-16 points along the abnormality edge, clockwise), '
    '"centerline": [[x,y],...] (4-12 points along the centreline of the involved vessel/tubular structure, proximal to distal), '
    '"keypoints": [{"name":"point of narrowest lumen","x":0.0,"y":0.0}, ...] (key points: maximal narrowing, proximal/distal reference, etc.). '
    "If you are unsure of the point locations, OMIT the field - better no polygon/centerline than invented coordinates. "
    "The box must be tight around the visible abnormality only: a focal lesion is normally under ~15% of the image area, and no box may cover a whole lung unless the opacity truly fills it. "
    "Every box and outline must lie INSIDE the aerated lung field (or inside the heart/mediastinum band for cardiac or mediastinal findings), never below the diaphragm dome, over the abdomen or gastric bubble, over the neck, shoulders, ribs or chest-wall soft tissue."
)


def build_image_scale_note(img_wh=None, fov=None) -> str:
    """Prompt block: the EXACT size of the image sent, one coordinate format, and forbidden areas for boxes."""
    size = f"{img_wh[0]} x {img_wh[1]} pixels (width x height)" if img_wh else "as-is size"
    fov_note = (f"FIELD OF VIEW: the part of the image that contains picture (not black borders) lies at x {fov[0]:.2f}-{fov[2]:.2f} and y {fov[1]:.2f}-{fov[3]:.2f}; "
                "ALL structures and lesions lie inside this area. Coordinates remain normalised to the WHOLE image (not to this area). "
                if fov else "")
    return (
        "\n\nSIZE & COORDINATES (MANDATORY): the image you see is " + size + ". "
        "ALL coordinates (box, polygon, polyline, centerline, keypoints) MUST be decimals normalised 0.0 to 1.0 relative to this whole "
        "image: x = horizontal position / width, y = vertical position / height, origin top-left. "
        + fov_note +
        "DO NOT use pixels, percentages, or a 0..1000 scale. Make sure xmin < xmax and ymin < ymax, and the box covers only that "
        "abnormal segment (not the whole vessel or whole image).\n"
        "FORBIDDEN AREAS FOR BOX/POLYGON/POINT: ECG traces or waveforms at the image edge, stock-photo watermarks/logos, text, "
        "footers, rulers/scales, frames, and black borders outside the field of view. Only the patient's anatomy inside the field of "
        "view may be given a location. If you are unsure of the location, do not invent coordinates: write the finding in "
        "'summary' and leave the box empty."
    )


VISUAL_GEOMETRY_NOTE_DETECT = (
    "VISUALISATION GEOMETRY (coordinates normalised 0..1 relative to the whole image, x to the right, y downward; origin top-left). "
    "For EVERY 'anomalies' object give a 'box' that FITS the abnormality, not the whole structure/organ, plus the 'pointer'. "
    "Do NOT give polygon, centerline or keypoints in this call (segmentation comes later). "
    "The box must be tight around the visible abnormality only: a focal lesion is normally under ~15% of the image area, and no box may cover a whole lung unless the opacity truly fills it. "
    "Every box must lie INSIDE the aerated lung field (or inside the heart/mediastinum band for cardiac or mediastinal findings), never below the diaphragm dome, over the abdomen or gastric bubble, over the neck, shoulders, ribs or chest-wall soft tissue."
)
