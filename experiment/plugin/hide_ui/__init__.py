import krita
from .hide_ui import HideUIExtension


Scripter.addExtension(HideUIExtension(krita.Krita.instance()))
