### import ####################################################################


import os
import collections
import time

import numpy as np

from PyQt4 import QtGui, QtCore

import project.classes as pc
import project.widgets as pw
import project.project_globals as g
from project.ini_handler import Ini
from hardware.delays.delays import Driver as BaseDriver
from hardware.delays.delays import GUI as BaseGUI

from library.ThorlabsAPT.APT import APTMotor


### define ####################################################################


main_dir = g.main_dir.read()


### driver ####################################################################


class Driver(BaseDriver):

    def __init__(self, *args, **kwargs):
        kwargs['native_units'] = 'ps'
        self.index = kwargs.pop('index')
        self.native_per_mm = 6.671281903963041
        BaseDriver.__init__(self, *args, **kwargs)

    def close(self):
        self.motor.close()

    def get_motor_position(self):
        p = self.motor.position
        self.motor_position.write(p, self.motor_units)
        return p

    def get_position(self):
        position = self.get_motor_position()
        # calculate delay
        delay = (position - self.zero_position.read()) * self.native_per_mm * self.factor.read()
        self.position.write(delay, self.native_units)
        # return
        return delay

    def initialize(self):
        self.motor = APTMotor(serial_number=int(self.serial), hardware_type=42)
        self.motor_limits.write(self.motor.minimum_position, self.motor.maximum_position, self.motor_units)

    def is_busy(self):
        return self.motor.status == 'moving'

    def set_position(self, destination):
        destination_mm = self.zero_position.read() + destination/(self.native_per_mm * self.factor.read())
        self.set_motor_position(destination_mm)

    def set_motor_position(self, motor_position):
        self.motor.set_position(motor_position)
        while self.is_busy():
            time.sleep(0.01)
            self.get_position()
        BaseDriver.set_motor_position(self, motor_position)


### gui #######################################################################


class GUI(BaseGUI):
    pass
