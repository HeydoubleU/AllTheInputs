try:
    import AllTheInputs
    AllTheInputs.inputSet.recreateCallbacks()
except ModuleNotFoundError:
    from maya import cmds
    cmds.evalDeferred("cmds.warning('This scene contains Input Sets which depend on AllTheInputs, but module was not found.')")