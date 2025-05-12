__version__ = "1.0.1"  # 2023-07-10 12:41

import maya.api.OpenMaya as om
from maya import cmds as mc, mel


class UndoChunk:
    is_open = False

    def __init__(self, name=''):
        self.name = name

    def open(self):
        if not self.is_open:
            mc.undoInfo(ock=True, cn=self.name)
            self.is_open = True

    def close(self):
        if self.is_open:
            mc.undoInfo(cck=True, cn=self.name)
            self.is_open = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        self.close()


class UndoState:
    """Enable/Disable undo WITHOUT flushing the undo queue, this can be dangerous."""
    default_state = True

    def __init__(self, target_state):
        self.target_state = target_state

    @staticmethod
    def on():
        mc.undoInfo(swf=True)

    @staticmethod
    def off():
        mc.undoInfo(swf=False)

    @staticmethod
    def setState(state):
        mc.undoInfo(swf=state)

    def __enter__(self):
        self.default_state = mc.undoInfo(q=True, swf=True)
        self.setState(self.target_state)

    def __exit__(self, _type, value, traceback):
        self.setState(self.default_state)


def getMObject(node):
    sel = om.MSelectionList()
    sel.add(node)
    return sel.getDependNode(0)


def getDnName(mobj):
    dn_fn = om.MFnDependencyNode(mobj)
    return dn_fn.name()


def replaceTransformsWithShapes(nodes: list[str], first_only=False, no_intermediate=True) -> list:
    """
    Replaces transforms in a list with its shapes. Transforms with no shapes remain.
    """
    nodes_replaced = []
    for node in nodes:
        shapes = mc.listRelatives(node, shapes=True, ni=no_intermediate, fullPath=True)
        if shapes is None:
            nodes_replaced.append(node)
        elif first_only:
            nodes_replaced.append(shapes[0])
        else:
            nodes_replaced.extend(shapes)

    # dict keys instead of set to remove dups but maintain order
    nodes_replaced = {node: None for node in nodes_replaced}
    return list(nodes_replaced.keys())
