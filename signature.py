"""
A Signature represents a Maya node type, with a list of its attributes that are relevant to Bifrost.
The Signature contains other information such as which Maya attribute should serve as the Bifrost object's geometry.

This module also contains functions for auto-generating compounds based on Signatures.
"""

import os
from .packages.userdata import Userdata
from .packages import bifrostUtils as bif
from maya import cmds as mc, mel
from . import bobify, compounds
from . import __MP__

USER_ATTRS = False  # This has not been tested and probably should NOT be enabled
SIGNATURES = {}  # Signatures are only loaded as needed, then cached here
DEF_IGNORE_LIST = [
    "displayScalePivot",
    "caching",
    "renderInfo",
    "ghostDriver",
    "minTransLimit",
    "rmbCommand",
    "xformMatrix",
    "drawOverride",
    "objectColorRGB",
    "minRotLimit",
    "useObjectColor",
    "minScaleLimit",
    "dagLocalInverseMatrix",
    "boundingBox",
    "frozen",
    "useOutlinerColor",
    "objectColor",
    "creationDate",
    "customTreatment",
    "rotatePivotTranslate",
    "maxTransLimit",
    "templateName",
    "offsetParentMatrix",
    "nodeState",
    "ghostFrames",
    "maxRotLimit",
    "renderLayerInfo",
    "wireColorRGB",
    "rotatePivot",
    "transMinusRotatePivot",
    "dagLocalMatrix",
    "minRotLimitEnable",
    "displayHandle",
    "template",
    "minScaleLimitEnable",
    "minTransLimitEnable",
    "lodVisibility",
    "showManipDefault",
    "selectionChildHighlighting",
    "displayRotatePivot",
    "uiTreatment",
    "ghostUseDriver",
    "shear",
    "rotationInterpolation",
    "instObjGroups",
    "hiddenInOutliner",
    "ghostingMode",
    "viewName",
    "rotateAxis",
    "outlinerColor",
    "creator",
    "maxTransLimitEnable",
    "maxScaleLimit",
    "blackBox",
    "ghostColorPost",
    "intermediateObject",
    "scalePivot",
    "ghostOpacityRange",
    "templateVersion",
    "parentInverseMatrix",
    "parentMatrix",
    "scalePivotTranslate",
    "inheritsTransform",
    "worldInverseMatrix",
    "selectHandle",
    "center",
    "maxScaleLimitEnable",
    "borderConnections",
    "viewMode",
    "containerType",
    "iconName",
    "templatePath",
    "inverseMatrix",
    "ghostCustomSteps",
    "ghostColorPre",
    "displayLocalAxis",
    "maxRotLimitEnable",
    "ghosting",
]  # Auto generated using transform, not a great solution


class Signature(Userdata):
    attrs = ()
    geo_attr = None
    ignore = False

    def __init__(self, node_type, load=False, **kwargs):
        super(Signature, self).__init__(f"{__MP__}/userdata/signatures/{node_type}.json", load=load, **kwargs)
        self.p.node_type = node_type

    def copy(self):
        sig = Signature(self.p.node_type)
        sig.ignore = self.ignore
        sig.attrs = list(self.attrs)
        sig.geo_attr = self.geo_attr
        return sig

    def save(self, publish=True):
        super(Signature, self).save()
        SIGNATURES[self.p.node_type] = self
        if publish:
            compounds.publishMakeAndBreakSig(self.p.node_type)


def getSignature(node_type):
    if node_type not in SIGNATURES:
        sig = Signature(node_type)
        if sig.exists():
            sig.load()
            SIGNATURES[node_type] = sig
        else:
            SIGNATURES[node_type] = autoSignature(node_type)

    return SIGNATURES[node_type].copy()


def deleteDummyNode(node):
    parent = mc.listRelatives(node, parent=True)
    mc.delete(parent) if parent else mc.delete(node)


def createDefaultSignatures():
    # Current functions throughout this package really expect graphs as inputs.
    sig = Signature("bifrostGraphShape", ignore=True)
    if not sig.exists():
        sig.save(publish=False)
    sig = Signature("bifrostBoard", ignore=True)
    if not sig.exists():
        sig.save(publish=False)


def listSignatureTypes(filter_ignored=False):
    node_types = []
    for filename in os.listdir(f"{__MP__}/userdata/signatures"):
        node_types.append(os.path.splitext(filename)[0])

    if filter_ignored:
        node_types = [node_type for node_type in node_types if not getSignature(node_type).ignore]

    return node_types


def filterChildAttrs(node, attrs):
    attrs = [attr for attr in attrs if "." not in attr]
    attrs2 = []
    for attr in attrs:
        parent_attrs = mc.attributeQuery(attr, node=node, listParent=True)
        if not (parent_attrs and parent_attrs[0] in attrs):
            attrs2.append(attr)

    return attrs2


def listUserAttrs(node, filter_children=True):
    attrs = mc.listAttr(node, userDefined=True)
    if not attrs:
        return []
    elif filter_children:
        return filterChildAttrs(node, attrs)
    else:
        return attrs


def autoSignature(node_type):
    sig = Signature(node_type)
    node = mc.createNode(node_type, ss=True)
    sig.attrs = mc.listAttr(node, read=True, visible=True)
    sig.attrs = filterChildAttrs(node, sig.attrs)

    # remove plugin attrs
    plugin_attrs = mc.listAttr(node, fp=True)
    if plugin_attrs:
        sig.attrs = [attr for attr in sig.attrs if attr not in plugin_attrs]

    # remove default ignore attrs
    sig.attrs = [attr for attr in sig.attrs if attr not in DEF_IGNORE_LIST]

    # search for geo attr
    for attr in sig.attrs:
        attr_type = mc.getAttr(f"{node}.{attr}", type=True)
        if attr_type == "mesh" or attr_type == "nurbsCurve":
            sig.geo_attr = attr
            sig.attrs.remove(attr)
            break

    deleteDummyNode(node)
    return sig


def prepareSignature(node):
    sig = getSignature(mc.nodeType(node))

    if not sig.exists():
        sig = setSignatureDialog(None, sig=sig)

    if sig.ignore:
        print(f"Ignoring {node}")
        return sig

    sig.attrs = [attr for attr in sig.attrs if mc.objExists(f"{node}.{attr}")]  # verify attrs exist

    if USER_ATTRS:
        sig.attrs.extend(listUserAttrs(node))

    return sig


def setSignatureWindow(sig):
    from PySide2.QtWidgets import QMessageBox, QLabel, QLineEdit, QPlainTextEdit
    msg = QMessageBox()
    msg.setWindowTitle(f"Set Signature for '{sig.p.node_type}'")
    msg.layout().addWidget(QLabel(f"Attrs:"), 0, 0)
    msg.attrs_edit = QPlainTextEdit("\n".join(sig.attrs), minimumWidth=250, minimumHeight=400)
    msg.layout().addWidget(msg.attrs_edit, 0, 1)
    msg.layout().addWidget(QLabel(f"Geo Attr:"), 1, 0)
    msg.geo_attr_edit = QLineEdit(sig.geo_attr)
    msg.geo_attr_edit.setPlaceholderText("Base geometry attr (optional)")
    msg.layout().addWidget(msg.geo_attr_edit, 1, 1)
    msg.addButton(QMessageBox.Save)
    msg.addButton(QMessageBox.Cancel)
    btn = msg.addButton(QMessageBox.Discard)
    btn.setText("Ignore and Save")
    msg.exec_()
    return msg


def setSignatureDialog(node_type, sig: Signature = None):
    if sig is not None:
        node_type = sig.p.node_type
    elif node_type is not None:
        sig = getSignature(node_type)
    else:
        raise ValueError("Must provide valid node type or Signature")

    # Get user input
    msg = setSignatureWindow(sig)
    if msg.result() != msg.Save:
        sig.ignore = True
        if msg.result() == msg.Discard:
            sig.save()
        return sig

    # Geo attr
    sig.geo_attr = msg.geo_attr_edit.text().strip(" ")
    if not sig.geo_attr:
        sig.geo_attr = None
    elif not mc.attributeQuery(sig.geo_attr, type=node_type, exists=True):
        mc.warning(f"Node type '{node_type}' does not have attribute '{sig.geo_attr}'")

    # Attrs
    sig.attrs = []
    for attr in msg.attrs_edit.toPlainText().split("\n"):
        attr = attr.strip(" ")
        if attr:
            sig.attrs.append(attr)
            if not mc.attributeQuery(attr, type=node_type, exists=True):
                mc.warning(f"Node type '{node_type}' does not have attribute '{attr}'")

    if sig.geo_attr in sig.attrs:
        sig.attrs.remove(sig.geo_attr)

    # Finalize
    sig.ignore = False
    sig.save()
    return sig


def setSelSignature():
    node = mc.ls(sl=True)
    if not node:
        mc.warning("Nothing selected")
        return
    else:
        node = node[-1]

    shapes = mc.listRelatives(node, shapes=True, ni=True, fullPath=True)
    setSignatureDialog(mc.nodeType(shapes[0] if shapes else node))


createDefaultSignatures()
