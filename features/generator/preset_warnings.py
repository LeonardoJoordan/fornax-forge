ASPECT_RATIO_TOLERANCE = 0.005
WARNING_PREFIX = "⚠️ "


def _as_positive_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def model_ratio(width_mm, height_mm):
    width = _as_positive_float(width_mm)
    height = _as_positive_float(height_mm)
    if width is None or height is None:
        return None
    return width / height


def with_model_ratio_snapshot(settings: dict, model_w_mm: float, model_h_mm: float):
    data = dict(settings or {})
    width = _as_positive_float(model_w_mm)
    height = _as_positive_float(model_h_mm)
    ratio = model_ratio(width, height)

    if width is None or height is None or ratio is None:
        return data

    data["model_w_at_save"] = width
    data["model_h_at_save"] = height
    data["model_ratio_at_save"] = ratio
    return data


def preset_ratio_warning(preset: dict, current_w_mm: float, current_h_mm: float):
    saved_ratio = _as_positive_float((preset or {}).get("model_ratio_at_save"))
    current_ratio = model_ratio(current_w_mm, current_h_mm)

    if saved_ratio is None or current_ratio is None:
        return False

    relative_change = abs(current_ratio - saved_ratio) / saved_ratio
    return relative_change > ASPECT_RATIO_TOLERANCE


def warning_display_name(name: str, preset: dict, current_w_mm: float, current_h_mm: float):
    if preset_ratio_warning(preset, current_w_mm, current_h_mm):
        return f"{WARNING_PREFIX}{name}"
    return name


def warning_tooltip(name: str, preset: dict, current_w_mm: float, current_h_mm: float):
    if not preset_ratio_warning(preset, current_w_mm, current_h_mm):
        return ""

    saved_w = _as_positive_float((preset or {}).get("model_w_at_save"))
    saved_h = _as_positive_float((preset or {}).get("model_h_at_save"))

    saved_text = f"{saved_w:.2f} x {saved_h:.2f} mm" if saved_w and saved_h else "uma proporção diferente"
    current_text = f"{float(current_w_mm):.2f} x {float(current_h_mm):.2f} mm"

    return (
        f"<b>⚠️ Predefinição possivelmente desatualizada: {name}</b><br><br>"
        f"Ela foi salva quando o modelo tinha {saved_text}.<br>"
        f"O modelo atual está em {current_text}.<br><br>"
        "Revise as dimensões de impressão para evitar escala ou distorção indesejada."
    )
