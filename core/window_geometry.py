"""Transfer window placement before showing a replacement window."""

def transfer_window_geometry(source, target):
    # Qt's geometry snapshot includes the normal placement and maximized /
    # fullscreen state. restoreGeometry also handles native window placement;
    # setGeometry + setWindowState on a hidden Windows window can leave its
    # native client area maximized while QWidget keeps the restored size.
    target.restoreGeometry(source.saveGeometry())
