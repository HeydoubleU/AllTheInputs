AllTheInputs.inputSet.removeAllCallbacks()

from importlib import reload

import AllTheInputs.packages.userdata
import AllTheInputs.packages.bifrostUtils
import AllTheInputs.signature
import AllTheInputs.inputSet
import AllTheInputs.compounds
import AllTheInputs.bobify
import AllTheInputs

reload(AllTheInputs.packages.userdata)
reload(AllTheInputs.packages.bifrostUtils)
reload(AllTheInputs.signature)
reload(AllTheInputs.inputSet)
reload(AllTheInputs.compounds)
reload(AllTheInputs.bobify)
reload(AllTheInputs)

print("beep boop")

AllTheInputs.inputSet.recreateCallbacks()
