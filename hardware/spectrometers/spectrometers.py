### import ####################################################################


import os

import project
import project.project_globals as g

main_dir = g.main_dir.read()
app = g.app.read()
import hardware.hardware as hw


### define ####################################################################


directory = os.path.dirname(os.path.abspath(__file__))
ini = project.ini_handler.Ini(os.path.join(directory, "spectrometers.ini"))


### driver ####################################################################


class Driver(hw.Driver):
    def __init__(self, *args, **kwargs):
        self.hardware_ini = ini
        hw.Driver.__init__(self, *args, **kwargs)
        self.limits.write(0.0, 10000.0)


### gui #######################################################################


class GUI(hw.GUI):
    pass


### hardware ##################################################################


class Hardware(hw.Hardware):
    def __init__(self, *args, **kwargs):
        self.kind = "spectrometer"
        hw.Hardware.__init__(self, *args, **kwargs)


### import ####################################################################


ini_path = os.path.join(directory, "spectrometers.ini")
hardwares, gui, advanced_gui = hw.import_hardwares(
    ini_path, name="Spectrometers", Driver=Driver, GUI=GUI, Hardware=Hardware
)
