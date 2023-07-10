"""
Input Sets are maya set nodes (ie. object set, shading group, etc.) paired with a Bifrost Graph.
The Graph is automatically updated with the contents of the set.
"""

import maya.api.OpenMaya as om
from maya import cmds as mc, mel
from PySide2.QtCore import QTimer

from .packages import bifrostUtils as bif
from .packages import mayaUtils as mu
from . import bobify
from . import __MP__
from .signature import deleteDummyNode

"""
Normally anything that inherits from transform or locator would be treated as an 'input by path' transform input.
This covers many nodes. For example nParticle emitters inherit from transform, but if the user is including
such node type in their graph its likely they'd want additional attributes and for it to be bobified.
So instead we explicitly list the node types that should be treated as 'input by path' transforms.
"""
TRANSFORM_CLASSES = ["transform", "locator", "joint", "BetterLocator"]
CALLBACKS = []


with open(f"{__MP__}/scripts/scriptNode_openScene.py", "r") as f:
    OPEN_SCRIPT = f.read()
with open(f"{__MP__}/scripts/scriptNode_closeScene.py", "r") as f:
    CLOSE_SCRIPT = f.read()


class Callback:
    callback: int
    has_callback: bool = False
    pending_update: bool = False

    def __init__(self, node: str | om.MObject):
        if isinstance(node, om.MObject):
            self.mobj = node
        elif isinstance(node, str):
            self.mobj = mu.getMObject(node)
        else:
            raise ValueError("Must provide a valid set name or MObject")
        self.add()

    def add(self):
        print("Callback created for: ", self.dnName())
        self.callback = om.MObjectSetMessage.addSetMembersModifiedCallback(self.mobj, self.setMembersChanged)
        self.has_callback = True

    def remove(self):
        om.MMessage.removeCallback(self.callback)
        self.has_callback = False

    def dnName(self):
        return mu.getDnName(self.mobj)

    def setPending(self, state):
        self.pending_update = state

    def setMembersChanged(self, mobj=None, cd=None):
        if self.pending_update:
            return  # update already pending

        self.setPending(True)

        set_name = self.dnName()
        input_set = InputSet(set_name)
        if not input_set.graph:
            self.remove()
            CALLBACKS.remove(self)
            mc.warning(f"Object set '{input_set.name}' has no graph, callback removed")
            return

        def updateGraph():
            with mu.UndoState(False):
                input_set.updateGraph()

        mc.evalDeferred(updateGraph)
        mc.evalDeferred(lambda: self.setPending(False))


class InputSet:
    bobify_all = False
    bobify_other = True
    members: list[str]

    def __init__(self, set_name, new=False):
        self.name = set_name
        self.graph = self.getGraph()
        if new and not self.graph:
            self.graph = self.createGraph()
            self.updateGraph()

    def listMembers(self):
        nodes = []
        dag_nodes = mc.listConnections(self.name + ".dagSetMembers", s=True, d=False)
        dn_nodes = mc.listConnections(self.name + ".dnSetMembers", s=True, d=False)
        if dag_nodes is not None:
            nodes.extend(dag_nodes)
        if dn_nodes is not None:
            nodes.extend(dn_nodes)

        self.members = nodes
        return nodes

    def createGraph(self):
        # Create Graph
        graph = bif.createGraph(f"{self.name}_graph", as_board=False)
        mc.setAttr(graph + ".displayOutputsInViewport", 0)
        mc.setAttr(graph + ".displayOutputsInRenderer", 0)
        mel.eval(f'string $gInputSetGraph = "{graph}";source "{__MP__}/scripts/objectSet_graph.mel";')

        # Del bif shape
        # mc.delete(mc.listConnections(f"{graph}.object_set", d=True, s=False))

        # Add message attr to graph
        mc.addAttr(graph, ln="inputSet", at="message")
        mc.connectAttr(f"{self.name}.message", f"{graph}.inputSet", f=True)

        return graph

    def getGraph(self, none_ok=True):
        conns = mc.listConnections(self.name + ".message", s=False, d=True, p=True)
        if conns:
            for conn in conns:
                _node, attr = conn.split(".", 1)
                if attr == "inputSet" and bif.isBifrostGraph(_node):
                    return _node
        if none_ok:
            return None
        else:
            raise RuntimeError(f"Graph for object set '{self.name}' is None")

    def updateGraph(self):
        # Keep graph name in sync with set name, idk if I want this
        # graph = mc.rename(graph, f"{set_name}_graph")

        # Used to use 'input by path' and recreate ports every update, now connections are managed manually for better stability
        # mc.vnnCompound(self.graph, "/", removeNode="input")
        # in_node_path = bif.addIONode(self.graph)
        in_node_path = "/input"

        # Clear outdated inputs
        for x in range(mc.getAttr(f"{self.graph}.meshes", size=True)):
            mc.removeMultiInstance(f"{self.graph}.meshes[*]", b=True)
        for x in range(mc.getAttr(f"{self.graph}.strands", size=True)):
            mc.removeMultiInstance(f"{self.graph}.strands[*]", b=True)
        for x in range(mc.getAttr(f"{self.graph}.transforms", size=True)):
            mc.removeMultiInstance(f"{self.graph}.transforms[*]", b=True)
        for x in range(mc.getAttr(f"{self.graph}.bobs", size=True)):
            mc.removeMultiInstance(f"{self.graph}.bobs[*]", b=True)

        if not self.listMembers():
            return

        if self.bobify_all:
            other = self.members
        else:
            meshes, curves, transforms, other = sortNodesByInputType(self.members)
            # print(meshes, curves, transforms, other)

            if meshes:
                for x, mesh in enumerate(meshes):
                    mc.connectAttr(f"{mesh}.worldMesh[0]", f"{self.graph}.meshes[{x}]")
            if curves:
                for x, curve in enumerate(curves):
                    mc.connectAttr(f"{curve}.worldSpace[0]", f"{self.graph}.strands[{x}]")
                mc.bifrostGraph(self.graph, setInputByPathFlag=["strands", "path", " ".join(curves)])
            if transforms:
                for x, transform in enumerate(transforms):
                    mc.connectAttr(f"{transform}.worldMatrix[0]", f"{self.graph}.transforms[{x}]")

        if other and (self.bobify_other or self.bobify_all):
            bobify_graphs = bobify.bobifyNodes(other)
            if bobify_graphs:
                for x, bobify_graph in enumerate(bobify_graphs):
                    mc.connectAttr(f"{bobify_graph}.{bobify.OUT_PORT_NAME}", f"{self.graph}.bobs[{x}]")


# Manage Callbacks =====================================================================================================
def findCallback(callback) -> Callback:
    """
    Find a callback by set name or MObject
    """
    if isinstance(callback, om.MObject):
        for cb in CALLBACKS:
            if callback == cb.mobj:
                return cb

    elif isinstance(callback, str):
        for cb in CALLBACKS:
            if callback == cb.dnName():
                return cb
    else:
        raise TypeError(f"Must provide a valid set name or MObject, got: {type(callback)}")


def removeCallback(callback):
    if isinstance(callback, Callback):
        pass
    else:
        callback = findCallback(callback)
        if not callback:
            raise RuntimeError(f"Could not find callback: {callback}")

    callback.remove()
    CALLBACKS.remove(callback)


def removeAllCallbacks():
    [cb.remove() for cb in CALLBACKS if cb.has_callback]
    CALLBACKS.clear()
    print("InputSet callbacks removed")


def recreateCallbacks():
    removeAllCallbacks()
    for input_set in listInputSetsFromScene():
        CALLBACKS.append(Callback(input_set.name))


# Manage InputSets =====================================================================================================
def nodeCanBeInputSet(node):
    if node not in mc.ls(type="objectSet"):
        return False
    if not mc.objExists(f"{node}.dnSetMembers"):
        return False
    if not mc.objExists(f"{node}.dagSetMembers"):
        return False
    return True


def newInputSet(set_name):
    """
    Function for the user to designate an ObjectSet as an InputSet
    """
    if not nodeCanBeInputSet(set_name):
        raise RuntimeError(f"'{set_name}' Is not a valid set")

    input_set = InputSet(set_name, new=True)
    if not findCallback(input_set.name):
        CALLBACKS.append(Callback(input_set.name))
    createScriptNode()
    return input_set.graph


def newInputSetSel(graph=None):
    sel = mc.ls(sl=True)
    if not sel:
        return mc.warning("Selection is empty.")

    graph = bif.getEditorGraph() if graph is None else graph

    set_graphs = []
    for item in sel:
        if nodeCanBeInputSet(item):
            set_graphs.append(newInputSet(item))
        else:
            mc.warning(f"'{item}' Skipped, not a valid set")

    if not set_graphs:
        return  # all nodes were ignored

    # Connect graphs
    if len(set_graphs) == 1:
        port_name = bif.addMayaAttr(set_graphs[0], "object_set", graph, port_name="object_set")

    else:
        # Setup object array input
        in_node = bif.addIONode(graph, name="bobified_nodes")
        port_name = bif.createOutputPort(graph, in_node, "object_sets", "array<Object>")

        # Connect
        for x, bobify_graph in enumerate(set_graphs):
            mc.connectAttr(f"{bobify_graph}.object_set", f"{graph}.{port_name}[{x}]", f=True)

    # Restore graph editor
    mc.vnnCompoundEditor(name="bifrostGraphEditorControl", ed=graph)


def listInputSetsFromScene():
    input_sets = []
    for set_name in mc.ls(type="objectSet"):
        input_set = InputSet(set_name)
        if input_set.graph:
            input_sets.append(input_set)

    return input_sets


def sortNodesByInputType(nodes):
    meshes, curves, transforms, other = [], [], [], []
    for node in mu.replaceTransformsWithShapes(nodes, no_intermediate=bobify.NO_INTERMEDIATE):
        # inherited_types = mc.nodeType(_node, inherited=True)
        node_type = mc.nodeType(node)
        if node_type == "mesh":
            meshes.append(node)
        elif node_type == "nurbsCurve":
            curves.append(node)
        elif node_type in TRANSFORM_CLASSES:
            transforms.append(node)
        else:
            other.append(node)
    return meshes, curves, transforms, other


def createScriptNode(script_node="AllTheInputs_Callback_Script"):
    if mc.objExists(script_node):
        return script_node
    script_node = mc.scriptNode(
        name=script_node,
        stp="python",
        scriptType=1,  # Execute on file load or node deletion
        bs=OPEN_SCRIPT,
        afterScript=CLOSE_SCRIPT
    )
    return script_node


def removeUnused():
    for graph in mc.ls(type="bifrostGraphShape") + mc.ls(type="bifrostBoard"):
        if not mc.objExists(f"{graph}.inputSet"):
            continue

        # has any outgoing connections
        elif mc.listConnections(f"{graph}.object_set", s=False, d=True):
            continue

        else:
            deleteDummyNode(graph)

    recreateCallbacks()
