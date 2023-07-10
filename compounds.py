import os
from maya import cmds as mc, mel
from . import __MP__, signature, bobify
from .packages import bifrostUtils as bif

# Location where compounds will be published
LIB_PATH = os.path.expanduser('~').replace("\\", "/") + "/Autodesk/Bifrost/Compounds/AllTheInputs"
NAMESPACE = "ATI"  # Compounds namespace
TYPE_CHECK_NAME = "bobify_type_check"


def verifyLib():
    """
    This runs when the module is imported.
    It checks for, and publishes core compounds if they are missing.
    """

    ns_exists = NAMESPACE in mc.vnn(lib='BifrostGraph')
    ns_nodes = mc.vnn(nd=['BifrostGraph', NAMESPACE]) if ns_exists else []

    if not (ns_exists and TYPE_CHECK_NAME in ns_nodes):
        publishTypeCheck()

    if not (ns_exists and "break_set" in ns_nodes and "make_set" in ns_nodes):
        publishMakeBreakSet()


def publishTypeCheck(graph=None):
    """
    This compound published by this function returns true if the input object matches the 'node_type' property.
    This should be run any time a signature is created/edited, so that the combobox is updated.
    'node_type' is a string, so republishing this should never break existing graphs.
    """

    node_types = signature.listSignatureTypes(filter_ignored=True)
    graph = mc.createNode("bifrostBoard", ss=True) if graph is None else graph

    mc.vnnCompound(graph, "/", create=f"{TYPE_CHECK_NAME}")
    bif.createOutputPort(graph, f"/{TYPE_CHECK_NAME}/input", "object", "Object")
    port = bif.createOutputPort(graph, f"/{TYPE_CHECK_NAME}/input", "node_type", "string")
    mc.vnnNode(graph, f"/{TYPE_CHECK_NAME}", setMetaDataFromString='NodeValueDisplay={show=1;format="Is Bobify {node_type}"}')

    if node_types:
        mc.vnnNode(graph, f"/{TYPE_CHECK_NAME}", spv=[port, node_types[0]])
        mc.vnnNode(graph, f"/{TYPE_CHECK_NAME}", spm=[port, "UIWidget", "ComboBox"])
        mc.vnnNode(graph, f"/{TYPE_CHECK_NAME}", spm=[port, "UIWidgetProp", "items={%s}" % ";".join(node_types)])

    # get_property
    mc.vnnCompound(graph, f"/{TYPE_CHECK_NAME}", addNode="BifrostGraph,Core::Object,get_property")
    mc.vnnNode(graph, f"/{TYPE_CHECK_NAME}/get_property", spt=["default_and_type", "string"])
    mc.vnnNode(graph, f"/{TYPE_CHECK_NAME}/get_property", spv=["key", "node_type"])
    mc.vnnConnect(graph, f"/{TYPE_CHECK_NAME}/input.object", f"/{TYPE_CHECK_NAME}/get_property.object")

    # equal
    mc.vnnCompound(graph, f"/{TYPE_CHECK_NAME}", addNode="BifrostGraph,Core::Logic,equal")
    mc.vnnConnect(graph, f"/{TYPE_CHECK_NAME}/get_property.value", f"/{TYPE_CHECK_NAME}/equal.first")
    mc.vnnConnect(graph, f"/{TYPE_CHECK_NAME}/input.node_type", f"/{TYPE_CHECK_NAME}/equal.second")

    # output
    bif.createInputPort(graph, f"/{TYPE_CHECK_NAME}/output", "output", "bool")
    mc.vnnConnect(graph, f"/{TYPE_CHECK_NAME}/equal.output", f"/{TYPE_CHECK_NAME}/output.output")

    # publish
    os.makedirs(LIB_PATH, exist_ok=True)
    mc.vnnCompound(graph, f"/{TYPE_CHECK_NAME}", publish=[f"{LIB_PATH}/{TYPE_CHECK_NAME}.json", NAMESPACE, f"{TYPE_CHECK_NAME}", False])
    mc.delete(graph)


def publishMakeBreakSet():
    """
    Publish make/break compounds specifically for Input Sets.
    This should only ever run once unless the user deletes the compound file.
    """
    graph = mc.createNode("bifrostBoard", ss=True)
    mel.eval(f'string $gInputSetGraph = "{graph}";source "{__MP__}/scripts/makeSet_compound.mel";source "{__MP__}/scripts/breakSet_compound.mel";')

    os.makedirs(LIB_PATH, exist_ok=True)
    dst = LIB_PATH + "/make_break_set.json"
    mc.vnnCompound(graph, "/make_set", publish=[dst, NAMESPACE, "make_set", False])
    mc.vnnCompound(graph, "/break_set", publish=[dst, NAMESPACE, "break_set", False])
    mc.delete(graph)


def publishMakeAndBreakSig(node_type):
    """
    Publish make/break compounds for the given node type based on its signature.
    """
    sig = signature.getSignature(node_type)

    dummy_node = mc.createNode(node_type, ss=True)
    graph = bobify.createBobifyGraph(dummy_node)
    signature.deleteDummyNode(dummy_node)

    if not graph:
        publishTypeCheck()
        return False

    #### Get property node info
    prop_nodes: list = mc.vnnCompound(graph, "/", ln=True)
    prop_nodes.remove("input")
    prop_nodes.remove("output")
    prop_keys = [mc.vnnNode(graph, f"/{prop_node}", qpv="key") for prop_node in prop_nodes]
    prop_types = [mc.vnnNode(graph, f"/{prop_node}", qpt="value") for prop_node in prop_nodes]
    index = prop_keys.index("node_type")
    prop_keys.pop(index)
    prop_types.pop(index)

    #### Create Make Node
    make_compound = f"make_{node_type}"
    cmd = f'vnnCompound -create "{make_compound}" '
    for node in prop_nodes:
        cmd += f'-moveNodeIn "{node}" '

    cmd += graph + ' "/";'
    mel.eval(cmd)  # mel is used to allow multiple moveNodeIn flags at once
    output_port = mc.vnnNode(graph, f"/{make_compound}/output", listPorts=True)[0].split(".")[-1]
    mc.vnnCompound(graph, f"/{make_compound}", renamePort=(output_port, node_type))  # rename output port

    if sig.geo_attr is not None:  # if sig has geo_attr, move its port to top
        port = mc.vnnNode(graph, f"/{make_compound}/input", lp=True)[-1].split(".", 1)[-1]
        mc.vnnCompound(graph, f"/{make_compound}", movePort=[port, 0])

    #### Create Break Node
    break_compound = f"break_{node_type}"
    mc.vnnCompound(graph, "/", create=break_compound)

    # create object input
    in_port_path = f'/{break_compound}/input.{bif.createOutputPort(graph, f"/{break_compound}/input", node_type, "Object")}'
    out_node = f"/{break_compound}/output"
    for key, _type in zip(prop_keys, prop_types):
        new_port = bif.createInputPort(graph, out_node, key, _type)  # create port

        # Setup get_property node
        get_property = f"/{break_compound}/" + mc.vnnCompound(graph, f"/{break_compound}", addNode="BifrostGraph,Core::Object,get_property")[0]

        mc.vnnNode(graph, get_property, spv=("key", key))
        mc.vnnNode(graph, get_property, spt=("default_and_type", _type))
        mc.vnnConnect(graph, in_port_path, f"{get_property}.object")
        mc.vnnConnect(graph, f"{get_property}.value", f"{out_node}.{new_port}")

    #### Publish
    dst = LIB_PATH + f"/make_break_{node_type}.json"
    mc.vnnCompound(graph, f"/{make_compound}", publish=[dst, "ATI", make_compound, False])
    mc.vnnCompound(graph, f"/{break_compound}", publish=[dst, "ATI", break_compound, False])

    publishTypeCheck(graph)  # this will also del graph

    return True
