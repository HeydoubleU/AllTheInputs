__version__ = "1.5.2"  # 2023-07-02 10:41

import os, json
from warnings import warn, simplefilter

simplefilter('always')
PRINT = True
USERDATA_DIR = os.path.expanduser('~').replace("\\", "/")  # not implemented


def setPrint(state):
    global PRINT
    PRINT = state


def printStatus(*args):
    if PRINT:
        print(*args)


def readJson(filename):
    if os.path.isfile(filename):
        with open(filename) as file:
            data = json.load(file)
        return data
    else:
        return None


def writeJson(filename, data, make_dirs=True):
    if make_dirs:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)


class Params:
    filename = ""
    require = ()
    autosave = False
    stack_level = 3


class Userdata:
    def __init__(self, filename="", load=False, autosave=False, require=(), **kwargs):
        self.p = Params()
        self.p.filename = filename
        self.p.require += require
        if kwargs:
            self.merge(kwargs)
        if self.p.filename and load:
            self.load(False)
        self.p.autosave = autosave

        for attr in self.p.require:
            if not hasattr(self, attr):
                raise AttributeError(f"Missing required attribute: {attr}")

    def __setattr__(self, key, value):
        self.__dict__[key] = value
        if self.p.autosave and key != "p":
            self.save()

    def merge(self, data, loading=False):

        # Prep data dict
        if data is None:
            return
        elif isinstance(data, Userdata):
            data_dict = data.__dict__
        elif isinstance(data, dict):
            data_dict = data
        else:
            raise TypeError(f"Can't merge {type(data)}, type must be userdata.Data or dict")

        autosave_state = self.p.autosave
        self.p.autosave = False

        # Merge data dict
        for key, value in data_dict.items():
            if key != "p":
                setattr(self, key, value)

        self.p.autosave = autosave_state
        if self.p.autosave and not loading:
            self.save()

    def load(self, filename=None, clear=True):
        if filename:
            self.p.filename = filename

        data_dict = readJson(self.p.filename)
        if data_dict is None:
            warn(f"userdata file does not exist: {self.p.filename}", Warning, stacklevel=self.p.stack_level)
            return False
        else:
            if clear:
                self.clear()
            self.merge(data_dict, loading=True)
            self.processLoad()
            printStatus("Userdata Loaded:", self.p.filename)
            return True

    def dump(self):
        dump = dict(self.__dict__)
        del dump["p"]
        return self.processDump(dump)

    def processDump(self, dump: dict) -> dict:
        # Override this method to process the dict returned by dump()
        return dump

    def processLoad(self):
        # Override this method to further process the object after load()
        pass

    def save(self):
        if not self.p.filename:
            raise AttributeError("Failed to save: UserData has no filename")
        writeJson(self.p.filename, self.dump())
        print("Userdata Saved:", self.p.filename)

    def clear(self):
        keys = list(self.__dict__.keys())
        keys.remove("p")
        for key in keys:
            delattr(self, key)

    def factoryReset(self, save=True):
        self.merge(self.__class__(self.p.filename, autoload=False))
        if save:
            self.save()

    def deleteFile(self):
        if os.path.isfile(self.p.filename):
            os.remove(self.p.filename)

    def exists(self):
        return os.path.isfile(self.p.filename)

