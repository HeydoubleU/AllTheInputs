__version__ = "1.0.0"
__MP__ = __file__.replace('\\', '/').rsplit('/', 1)[0]

from . import inputSet, compounds, signature


def shelf():
    from maya import mel
    mel.eval(f'loadNewShelf "{__MP__}/scripts/shelf_AllTheInputs.mel";')


compounds.verifyLib()