import mimetypes

for ext, mime in (
    (".js", "application/javascript"),
    (".mjs", "application/javascript"),
    (".css", "text/css"),
    (".wasm", "application/wasm"),
    (".json", "application/json"),
    (".svg", "image/svg+xml"),
):
    mimetypes.add_type(mime, ext)
