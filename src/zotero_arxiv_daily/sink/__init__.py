from .zotero import ZoteroSink


def get_sinks(config):
    mode = config.output.mode
    if mode == "zotero":
        return [ZoteroSink(config)]
    raise ValueError(f"Unsupported output mode: {mode}")
