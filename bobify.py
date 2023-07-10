"""
Bobifing is the process of constructing a Bifrost object from a Maya node.
Signatures are used to determine what attributes to include and how to connect them.
"""

from maya import cmds as mc, mel
from .packages import bifrostUtils as bif
from .packages import mayaUtils as mu
from . import signature

OUT_PORT_NAME = "bob_output"
NO_INTERMEDIATE = True


def createBobifyGraph(node):
    """
    Creates a bifrost which constructs a bifrost object from a given node's attributes
    """
    sig = signature.prepareSignature(node)
    if sig.ignore:  # user cancelled
        return

    # Create base graph
    graph = bif.createGraph(f"{node.rsplit('|', 1)[-1]}_bobify", as_board=True)
    mc.addAttr(graph, ln="bobifySource", at="message")
    mc.connectAttr(f"{node}.message", f"{graph}.bobifySource")
    mc.vnnNode(graph, "/output", createInputPort=(OUT_PORT_NAME, "Object"))
    mc.delete(mc.listConnections(f"{graph}.{OUT_PORT_NAME}", d=True, s=False))

    dst_port = f"/output.{OUT_PORT_NAME}"  # port that the next set_property node will connect to
    for attr in sig.attrs:

        # Add Maya attr to graph
        new_port = bif.addMayaAttr(node, attr, graph, "/input")
        if not new_port:  # unsupported type
            continue

        # Setup set_property node
        set_property = mc.vnnCompound(graph, "/", addNode="BifrostGraph,Core::Object,set_property")[0]
        mc.vnnConnect(graph, f"/input.{new_port}",  f"/{set_property}.value")
        mc.vnnConnect(graph, f"/{set_property}.out_object", dst_port)

        # Property name
        mc.vnnNode(graph, f"/{set_property}", spv=("key", attr))

        # update destination for next iteration
        dst_port = f"/{set_property}.object"

    # add node type property
    set_property = mc.vnnCompound(graph, "/", addNode="BifrostGraph,Core::Object,set_property")[0]
    mc.vnnNode(graph, f"/{set_property}", spv=("key", "node_type"))
    mc.vnnNode(graph, f"/{set_property}", setPortDataType=("value", "string"), spv=("value", sig.p.node_type))
    mc.vnnConnect(graph, f"/{set_property}.out_object", dst_port)

    if sig.geo_attr is not None:  # If applicable, connect geo port (ie mesh port) into the start of the set properties
        dst_port = f"/{set_property}.object"
        new_port = bif.addMayaAttr(node, sig.geo_attr, graph, "/input")
        if new_port:  # false if unsupported type
            mc.vnnConnect(graph, f"/input.{new_port}", dst_port)

    return graph


def bobifyNodes(nodes: list[str], replace_transforms=True, use_existing=True) -> list[str]:
    """
    Extends createBobifyGraph for handling a list of nodes.
    Also with options for replacing transforms with shapes and using existing bobify graphs.
    Disabling these parameters is equivalent to calling createBobifyGraph on each node.
    """

    if replace_transforms:
        nodes = mu.replaceTransformsWithShapes(nodes, no_intermediate=NO_INTERMEDIATE)

    # Create graphs
    bobify_graphs = []
    for node in nodes:
        if use_existing:
            bobify_graph = getBobifyGraph(node)
            if bobify_graph:
                bobify_graphs.append(bobify_graph)
                continue

        bg = createBobifyGraph(node)
        if bg:
            bobify_graphs.append(bg)
    return bobify_graphs


def bobifySel(graph=None, port_name=None, replace_transforms=True, use_existing=True):
    """
    Extends bobifyNodes using selected nodes as the input. Since this is intended for the user, it also
    connects the resulting graphs to the editor's current graph.
    """

    sel = mc.ls(sl=True)
    if not sel:
        return mc.warning("Selection is empty.")

    graph = bif.getEditorGraph() if graph is None else graph
    if not bif.isBifrostGraph(graph):
        raise ValueError(f"{graph} Is not a Bifrost graph")

    bobify_graphs = bobifyNodes(sel, replace_transforms=replace_transforms, use_existing=use_existing)
    if not bobify_graphs:
        return  # all nodes were ignored

    # Connect graphs
    if len(bobify_graphs) == 1:
        port_name = bif.addMayaAttr(bobify_graphs[0], OUT_PORT_NAME, graph, port_name=port_name if port_name else bobify_graphs[0].rsplit("_", 1)[0])

    else:
        # Setup object array input
        in_node = bif.addIONode(graph, name="bobified_nodes")
        port_name = bif.createOutputPort(graph, in_node, port_name if port_name else "bobified", "array<Object>")

        # Connect
        for x, bobify_graph in enumerate(bobify_graphs):
            mc.connectAttr(f"{bobify_graph}.{OUT_PORT_NAME}", f"{graph}.{port_name}[{x}]", f=True)

    # Restore graph editor
    mc.vnnCompoundEditor(name="bifrostGraphEditorControl", ed=graph)
    return bobify_graphs, port_name


def getBobifyGraph(node):
    conns = mc.listConnections(node + ".message", s=False, d=True, p=True, type="bifrostBoard")

    if not conns:
        return None

    for conn in conns:
        if conn.endswith(".bobifySource"):
            return conn.split(".")[0]

    return None


def removeUnused():
    """
    Delete bobify graphs with no output connection
    """
    for graph in mc.ls(type="bifrostBoard"):
        if not mc.objExists(graph + ".bobifySource"):
            continue

        if not mc.listConnections(f"{graph}.{OUT_PORT_NAME}", s=False, d=True):
            mc.delete(graph)
