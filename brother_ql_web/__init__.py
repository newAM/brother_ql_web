import argparse
import functools
import json
import logging
import os
import random
import sys
from systemd.journal import JournalHandler
from io import BytesIO

import bottle
from bottle import (
    response,
    request,
    jinja2_view,
    static_file,
    redirect,
    Bottle,
)
from PIL import Image, ImageDraw, ImageFont

from brother_ql.devicedependent import label_type_specs, label_sizes
from brother_ql.devicedependent import ENDLESS_LABEL, DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL
from brother_ql import BrotherQLRaster, create_label
from brother_ql.backends import backend_factory, guess_backend

from .font_helpers import get_fonts

bottle.TEMPLATE_PATH.insert(0, os.getenv("VIEWS_PATH"))

logger = logging.getLogger(__name__)

LABEL_SIZES = [(name, label_type_specs[name]["name"]) for name in label_sizes]

CONFIG = {}


# https://stackoverflow.com/a/31093434
def log_to_logger(fn):
    """Wrap a Bottle request so that a log line is emitted after it's handled."""

    @functools.wraps(fn)
    def _log_to_logger(*args, **kwargs):
        logger = logging.getLogger("bottle")
        actual_response = fn(*args, **kwargs)
        logger.debug(
            f"{request.remote_addr} {request.method} {request.url} {response.status}"
        )
        return actual_response

    return _log_to_logger


app = Bottle()
app.install(log_to_logger)


@app.route("/")
def index():
    redirect("/labeldesigner")


@app.route("/static/<filename:path>")
def serve_static(filename):
    return static_file(filename, root=os.getenv("STATIC_PATH"))


@app.route("/labeldesigner")
@jinja2_view("labeldesigner.jinja2")
def labeldesigner():
    font_family_names = sorted(list(FONTS.keys()))
    return {
        "font_family_names": font_family_names,
        "fonts": FONTS,
        "label_sizes": LABEL_SIZES,
        "website": CONFIG["WEBSITE"],
        "label": CONFIG["LABEL"],
    }


def get_label_context(request):
    """might raise LookupError()"""

    d = request.params.decode()  # UTF-8 decoded form data

    font_family = d.get("font_family").rpartition("(")[0].strip()
    font_style = d.get("font_family").rpartition("(")[2].rstrip(")")
    context = {
        "text": d.get("text", None),
        "font_size": int(d.get("font_size", 100)),
        "font_family": font_family,
        "font_style": font_style,
        "label_size": d.get("label_size", "62"),
        "kind": label_type_specs[d.get("label_size", "62")]["kind"],
        "margin": int(d.get("margin", 10)),
        "threshold": int(d.get("threshold", 70)),
        "align": d.get("align", "center"),
        "orientation": d.get("orientation", "standard"),
        "margin_top": float(d.get("margin_top", 24)) / 100.0,
        "margin_bottom": float(d.get("margin_bottom", 45)) / 100.0,
        "margin_left": float(d.get("margin_left", 35)) / 100.0,
        "margin_right": float(d.get("margin_right", 35)) / 100.0,
    }
    context["margin_top"] = int(context["font_size"] * context["margin_top"])
    context["margin_bottom"] = int(context["font_size"] * context["margin_bottom"])
    context["margin_left"] = int(context["font_size"] * context["margin_left"])
    context["margin_right"] = int(context["font_size"] * context["margin_right"])

    context["fill_color"] = (255, 0, 0) if "red" in context["label_size"] else (0, 0, 0)

    def get_font_path(font_family_name, font_style_name):
        try:
            if font_family_name is None or font_style_name is None:
                font_family_name = CONFIG["LABEL"]["DEFAULT_FONTS"]["family"]
                font_style_name = CONFIG["LABEL"]["DEFAULT_FONTS"]["style"]
            font_path = FONTS[font_family_name][font_style_name]
        except KeyError:
            raise LookupError("Couln't find the font & style")
        return font_path

    context["font_path"] = get_font_path(context["font_family"], context["font_style"])

    def get_label_dimensions(label_size):
        try:
            ls = label_type_specs[context["label_size"]]
        except KeyError:
            raise LookupError("Unknown label_size")
        return ls["dots_printable"]

    width, height = get_label_dimensions(context["label_size"])
    if height > width:
        width, height = height, width
    if context["orientation"] == "rotated":
        height, width = width, height
    context["width"], context["height"] = width, height

    return context


def create_label_im(text, **kwargs):
    label_type = kwargs["kind"]
    im_font = ImageFont.truetype(kwargs["font_path"], kwargs["font_size"])
    im = Image.new("L", (20, 20), "white")
    draw = ImageDraw.Draw(im)
    # workaround for a bug in multiline_textsize()
    # when there are empty lines in the text:
    lines = []
    for line in text.split("\n"):
        if line == "":
            line = " "
        lines.append(line)
    text = "\n".join(lines)
    # TODO: this was assigned but never used
    # linesize = im_font.getsize(text)
    textsize = draw.multiline_textsize(text, font=im_font)
    width, height = kwargs["width"], kwargs["height"]
    if kwargs["orientation"] == "standard":
        if label_type in (ENDLESS_LABEL,):
            height = textsize[1] + kwargs["margin_top"] + kwargs["margin_bottom"]
    elif kwargs["orientation"] == "rotated":
        if label_type in (ENDLESS_LABEL,):
            width = textsize[0] + kwargs["margin_left"] + kwargs["margin_right"]
    im = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(im)
    if kwargs["orientation"] == "standard":
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            vertical_offset = (height - textsize[1]) // 2
            vertical_offset += (kwargs["margin_top"] - kwargs["margin_bottom"]) // 2
        else:
            vertical_offset = kwargs["margin_top"]
        horizontal_offset = max((width - textsize[0]) // 2, 0)
    elif kwargs["orientation"] == "rotated":
        vertical_offset = (height - textsize[1]) // 2
        vertical_offset += (kwargs["margin_top"] - kwargs["margin_bottom"]) // 2
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            horizontal_offset = max((width - textsize[0]) // 2, 0)
        else:
            horizontal_offset = kwargs["margin_left"]
    offset = horizontal_offset, vertical_offset
    draw.multiline_text(
        offset, text, kwargs["fill_color"], font=im_font, align=kwargs["align"]
    )
    return im


@app.get("/api/preview/text")
@app.post("/api/preview/text")
def get_preview_image():
    context = get_label_context(request)
    im = create_label_im(**context)
    return_format = request.query.get("return_format", "png")
    if return_format == "base64":
        import base64

        response.set_header("Content-type", "text/plain")
        return base64.b64encode(image_to_png_bytes(im))
    else:
        response.set_header("Content-type", "image/png")
        return image_to_png_bytes(im)


def image_to_png_bytes(im):
    image_buffer = BytesIO()
    im.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    return image_buffer.read()


@app.post("/api/print/text")
@app.get("/api/print/text")
def print_text():
    """
    API to print a label

    returns: JSON

    Ideas for additional URL parameters:
    - alignment
    """

    return_dict = {"success": False}

    try:
        context = get_label_context(request)
    except LookupError as e:
        return_dict["error"] = e.msg
        return return_dict

    if context["text"] is None:
        return_dict["error"] = "Please provide the text for the label"
        return return_dict

    im = create_label_im(**context)

    if context["kind"] == ENDLESS_LABEL:
        rotate = 0 if context["orientation"] == "standard" else 90
    elif context["kind"] in (ROUND_DIE_CUT_LABEL, DIE_CUT_LABEL):
        rotate = "auto"

    qlr = BrotherQLRaster(CONFIG["PRINTER"]["MODEL"])
    red = False
    if "red" in context["label_size"]:
        red = True
    create_label(
        qlr,
        im,
        context["label_size"],
        red=red,
        threshold=context["threshold"],
        cut=True,
        rotate=rotate,
    )

    if not DEBUG:
        try:
            be = BACKEND_CLASS(CONFIG["PRINTER"]["PRINTER"])
            be.write(qlr.data)
            be.dispose()
            del be
        except Exception as e:
            return_dict["message"] = str(e)
            logger.warning("Exception happened: %s", e)
            return return_dict

    return_dict["success"] = True
    if DEBUG:
        return_dict["data"] = str(qlr.data)
    return return_dict


def main():
    global DEBUG, FONTS, BACKEND_CLASS, CONFIG
    parser = argparse.ArgumentParser(description="Brother QL WebUI")
    parser.add_argument("config", help="Path to the config file")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        CONFIG = json.load(f)

    loglevel = CONFIG["SERVER"]["LOGLEVEL"]
    if loglevel == "DEBUG":
        DEBUG = True
    else:
        DEBUG = False

    additional_font_folder = CONFIG["SERVER"]["ADDITIONAL_FONT_FOLDER"]

    handler = JournalHandler(SYSLOG_IDENTIFIER="brother_ql_web")
    handler.setLevel(loglevel)
    formatter = logging.Formatter("[{name}] {message}", style="{")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)

    logger.debug("logging initialized")

    try:
        selected_backend = guess_backend(CONFIG["PRINTER"]["PRINTER"])
    except ValueError:
        parser.error(
            "Couln't guess the backend to use from the printer string descriptor"
        )
    BACKEND_CLASS = backend_factory(selected_backend)["backend_class"]

    if CONFIG["LABEL"]["DEFAULT_SIZE"] not in label_sizes:
        parser.error(
            "Invalid default label size. Please choose on of the following:\n"
            + " ".join(label_sizes)
        )

    FONTS = get_fonts()
    if additional_font_folder:
        FONTS.update(get_fonts(additional_font_folder))

    if not FONTS:
        logger.error("Not a single font was found on your system. Please install some.")
        sys.exit(2)

    for font in CONFIG["LABEL"]["DEFAULT_FONTS"]:
        try:
            FONTS[font["family"]][font["style"]]
            CONFIG["LABEL"]["DEFAULT_FONTS"] = font
            logger.debug(f"Selected the following default font: {font}")
            break
        except Exception:
            pass
    if CONFIG["LABEL"]["DEFAULT_FONTS"] is None:
        logger.error("Could not find any of the default fonts. Choosing a random one.")
        family = random.choice(list(FONTS.keys()))
        style = random.choice(list(FONTS[family].keys()))
        CONFIG["LABEL"]["DEFAULT_FONTS"] = {"family": family, "style": style}
        logger.error(
            "The default font is now set to: {family} ({style})\n".format(
                **CONFIG["LABEL"]["DEFAULT_FONTS"]
            )
        )

    app.run(host=CONFIG["SERVER"]["HOST"], port=CONFIG["SERVER"]["PORT"], quiet=True)
