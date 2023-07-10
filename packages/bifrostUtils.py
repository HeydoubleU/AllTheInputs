__version__ = "1.2.1"  # 2023-07-08 09:27
"""
General purpose utility for scripts involving Bifrost.
"""

from maya import cmds as mc

ATTR_TO_PORT_TYPE = {  # Maya attr type to Bifrost port type
    "float": "float",
    "float2": "Math::float2",
    "float3": "Math::float3",
    "float4": "Math::float4",
    "double": "float",
    "double2": "Math::float2",
    "double3": "Math::float3",
    "double4": "Math::float4",
    "doubleLinear": "float",
    "doubleAngle": "float",
    "long": "long",
    "enum": "uint",
    "string": "string",
    "bool": "bool",
    "matrix": "Math::float4x4",
    "bifData": "Object",
    "mesh": "Object",
    "nurbsCurve": "Object",
    "doubleArray": "Object",
    "vectorArray": "Object",
}


def createGraph(name=None, as_board=False, skip_sel=True):
    if as_board:
        graph = mc.createNode("bifrostBoard", ss=skip_sel)
        if name:  # rename separately to avoid bug, I forgot what it was
            graph = mc.rename(graph, name)
    else:
        transform = mc.createNode("transform", ss=skip_sel, n="bifrostGraph")
        graph = mc.createNode("bifrostGraphShape", ss=True, p=transform)
        # sets -edit -forceElement initialShadingGroup $newBoard;
        mc.sets(graph, e=True, forceElement="initialShadingGroup")
        if name:
            graph = mc.rename(graph, name + "Shape")
            mc.rename(transform, name)

    return graph


def attrToPortName(attr: str) -> str:
    attr = attr.replace(".", "_").replace("[", "_").replace("]", "_")
    attr = attr.strip("_")
    return attr


def isBifrostGraph(node):
    """Returns True if node is a Bifrost graph or board"""
    if not (isinstance(node, str) and mc.objExists(node)):
        return False

    node_type = mc.nodeType(node)

    if node_type == "bifrostGraphShape":
        return True
    elif node_type == "bifrostBoard":
        return True
    else:
        return False


def getEditorGraph(preserve_sel=True):
    sel = mc.ls(sl=True) if preserve_sel else []  # store selection

    # send D key to editor which selects current graph
    mc.vnnCompoundEditor(name="bifrostGraphEditorControl", sk=[68, 0])
    graph_sel = mc.ls(sl=True)

    if preserve_sel:  # restore selection
        mc.select(sel)

    if graph_sel and isBifrostGraph(graph_sel[0]):
        return graph_sel[0]
    else:
        return None


def renameNode(graph, path, name_src, name_dst) -> str:
    nodes = mc.vnnCompound(graph, path, listNodes=True)
    mc.vnnCompound(graph, path, rn=[name_src, name_dst])
    if name_dst not in nodes:
        return name_dst
    for node in mc.vnnCompound(graph, path, listNodes=True):
        if node not in nodes:
            return node


def addIONode(graph, path="/", name="", is_input=True):
    input_node = mc.vnnCompound(graph, path, addIONode=is_input)[0]
    if name:
        input_node = renameNode(graph, path, input_node, name)

    if path.endswith("/"):
        return path + input_node
    else:
        return path + "/" + input_node


def createOutputPort(graph, path, name, port_type="float", port_options=""):
    mc.vnnNode(graph, path, createOutputPort=(name, port_type), portOptions=port_options)
    return mc.vnnNode(graph, path, lp=True)[-1].split(".", 1)[-1]


def createInputPort(graph, path, name, port_type="float", port_options=""):
    mc.vnnNode(graph, path, createInputPort=(name, port_type), portOptions=port_options)
    return mc.vnnNode(graph, path, lp=True)[-1].split(".", 1)[-1]


def addMayaAttr(maya_node, maya_attr, graph, input_node=None, port_name=None, replace_existing=False):
    """
    Adds given Maya node/attr to the graph, automatically creating and connecting in-port of same or similar type.
    Returns name of new port or None if attr type is unsupported.
    """

    # solve port name and type
    attr_type = mc.getAttr(f"{maya_node}.{maya_attr}", type=True)
    is_indexed = maya_attr.endswith("]")
    is_multi = not is_indexed and mc.attributeQuery(maya_attr, node=maya_node, m=True)
    if port_name is None:
        port_name = maya_attr
    port_name = attrToPortName(port_name)

    if replace_existing and mc.objExists(f"{graph}.{port_name}"):
        # dst port exists, so we can go straight to connecting
        # TODO: check existing port type matches
        pass

    else:  # Create new port of bifrost equivalent type
        if input_node is None:
            input_node = addIONode(graph, name=maya_node.rsplit("|", 1)[-1])

        if attr_type not in ATTR_TO_PORT_TYPE:
            mc.warning(f"Could not add Maya attribute, unsupported type: {maya_node}.{maya_attr} -> {attr_type}")
            return None  # unsupported attr type

        port_type = ATTR_TO_PORT_TYPE[attr_type]
        if is_multi:
            port_type = f"array<{port_type}>"

        if attr_type == "nurbsCurve":
            options = curveOptionsArg(maya_node)
        else:
            options = ""

        port_name = createOutputPort(graph, input_node, port_name, port_type, port_options=options)

    # Try connecting
    if is_multi:
        try:
            mc.connectAttr(f"{maya_node}.{maya_attr}", f"{graph}.{port_name}", f=True)
        except RuntimeError:
            # if fails try again using index 0
            mc.vnnCompound(graph, "/", deletePort=port_name)
            addMayaAttr(maya_node, maya_attr + "[0]", graph, input_node, port_name, replace_existing)

    else:
        mc.connectAttr(f"{maya_node}.{maya_attr}", f"{graph}.{port_name}", f=True)

    return port_name


def curveOptionsArg(path, tangents=True, lengths=False, sample_mode=1, multiplier=1, evenly_spaced=False, seg_length=1, match_ends=False):
    args = f"path={path};setOperation=+;active=true;channels=*;computeTangents={str(tangents).lower()};computeLengths={str(lengths).lower()};" \
           f"sampleMode={sample_mode};multiplier={multiplier};evenlySpaced={str(evenly_spaced).lower()};targetSegLength={seg_length};matchEnds={str(match_ends).lower()}"
    return "pathinfo={%s}" % args


def meshOptionsArg(path):
    args = f"path={path};setOperation=+;active=true;channels=*;computeTangents=true;computeLengths=false;sampleMode=1;multiplier=1;" \
           f"evenlySpaced=false;targetSegLength=1;matchEnds=false"
    return "pathinfo={%s}" % args
