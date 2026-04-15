from .email import EmailSink
from .zotero import ZoteroSink


def get_sinks(config):
    mode = config.output.mode
    if mode == "email":
        return [EmailSink(config)]
    if mode == "zotero":
        return [ZoteroSink(config)]
    if mode == "both":
        return [EmailSink(config), ZoteroSink(config)]
    raise ValueError(f"Unsupported output mode: {mode}")
