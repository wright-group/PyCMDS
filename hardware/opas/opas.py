### import ####################################################################


import os
import time
import collections

import numpy as np

from PyQt4 import QtGui

import WrightTools as wt

import project.project_globals as g
import project.widgets as pw
import project.ini_handler as ini
import project.classes as pc
import hardware.hardware as hw
from hardware.opas.PoyntingCorrection.ZaberCorrectionDevice import ZaberCorrectionDevice


### define ####################################################################


directory = os.path.dirname(os.path.abspath(__file__))

main_dir = g.main_dir.read()
app = g.app.read()
ini = ini.opas


### autotune ##################################################################


class AutoTune(QtGui.QWidget):

    def __init__(self, driver):
        QtGui.QWidget.__init__(self)
        self.driver = driver
        self.setLayout(QtGui.QVBoxLayout())
        self.layout = self.layout()
        self.layout.setMargin(0)
        self.initialized = pc.Bool()

    def initialize(self):
        pass

    def load(self, aqn_path):
        raise NotImplementedError

    def run(self, worker):
        raise NotImplementedError

    def save(self, aqn_path):
        raise NotImplementedError

    def update_channel_names(self, channel_names):
        raise NotImplementedError


### driver ####################################################################


class Driver(hw.Driver):

    def __init__(self, *args, **kwargs):
        self.index = kwargs['index']
        self.motor_positions = collections.OrderedDict()
        self.homeable = [False]  # TODO:
        self.homeables = []  # TODO:
        self.poynting_type = kwargs.pop('poynting_type')
        self.poynting_correction  = None
        if self.poynting_type is not None:
            self.motor_names += ['Phi', 'Theta']
        self.poynting_curve_path = kwargs.pop('poynting_curve_path')
        if 'native_units' not in kwargs.keys():
            kwargs['native_units'] = 'nm'
        hw.Driver.__init__(self, args[0], native_units=kwargs['native_units'])
        if not hasattr(self, 'motor_names'):  # for virtual...
            self.motor_names = ['Delay', 'Crystal', 'Mixer']

    def _home_motors(self, motor_indexes):
        raise NotImplementedError

    def _load_curve(self, inputs, interaction):
        # TODO: move into main load_curve method
        colors = np.linspace(400, 10000, 17)
        units = 'nm'
        motors = []
        motors.append(wt.tuning.curve.Motor(((colors-500)/1e4)**2, 'Delay'))
        motors.append(wt.tuning.curve.Motor(-(colors-9000)**0.25, 'Crystal'))
        motors.append(wt.tuning.curve.Motor((colors-30)**0.25, 'Mixer'))
        name = 'curve'
        interaction = 'sig'
        kind = 'Virtual'
        self.curve = wt.tuning.curve.Curve(colors, units, motors, name, interaction, kind)
        self.curve.convert(self.native_units)

    def _set_motors(self, motor_indexes, motor_destinations):
        pass

    def _update_api(self, interaction):
        pass

    def _wait_until_still(self, inputs=[]):
        while self.is_busy():
            time.sleep(0.1)  # I've experienced hard crashes when wait set to 0.01 - Blaise 2015.12.30
            self.get_motor_positions()
        self.get_motor_positions()

    def close(self):
        raise NotImplementedError

    def get_crv_paths(self):
        return [o.read() for o in self.curve_paths.values()]

    def get_points(self):
        return self.curve.colors

    def get_position(self):
        position = self.hardware.destination.read()
        self.position.write(position, self.native_units)
        return position
        
    def get_motor_positions(self):
        pass

    def home_all(self, inputs=[]):
        indexes = range(len(self.motor_names))
        indexes = [i for i in indexes if self.homeable[i%len(self.homeable)] ]
        if self.poynting_correction:
            self.poynting_correction.home()
            indexes = [i for i in indexes if self.motor_names[i] not in self.poynting_correction.motor_names]
        self._home_motors(indexes)

    def home_motor(self, inputs):
        # TODO: clean up for new inputs behavior
        motor_name = inputs[0]
        if self.poynting_correction:
            if motor_name in self.poynting_correction.motor_names:
                self.poynting_correction.home(motor_name)
                return
        motor_index = self.motor_names.index(motor_name)
        if self.homeable[motor_index % len(self.homeable)]:
            self._home_motors([motor_index])

    def initialize(self):
        # virtual stuff
        if self.model == 'Virtual':
            self.interaction_string_combo = pc.Combo(allowed_values=['sig'])
            self.curve_paths = collections.OrderedDict()
            self.motor_positions['Delay'] = pc.Number()
            self.motor_positions['Crystal'] = pc.Number()
            self.motor_positions['Mixer'] = pc.Number()
            self.auto_tune = AutoTune(self)
            self.position.write(800., 'nm')
        # poynting correction
        if self.poynting_type == 'zaber':
            self.poynting_correction = ZaberCorrectionDevice()
        else:
            self.poynting_correction = None
        if self.poynting_correction:
            # initialize
            self.poynting_correction.initialize(self, self.poynting_curve_path)  # TODO: move everything into __init__
            # add
            num_motors = len(self.motor_names)
            if len(self.homeables) < num_motors:
                n = len(self.homeable)
                homeable = [self.homeable[i%n] for i in range(len(self.homeable))]
            self.homeable += [True]*len(self.poynting_correction.motor_names)
            for name in self.poynting_correction.motor_names:
                number = self.poynting_correction.motor_positions[name]
                self.motor_positions[name] = number
                self.recorded['w%d_'%self.index + name] = [number, None, 1., name]
            self.curve_paths['Poynting'] = pc.Filepath(initial_value=self.poynting_correction.curve_path)
        # get position
        self.load_curve()
        self.get_position()
        hw.Driver.initialize(self)

    def load_curve(self, inputs=None):
        '''
        inputs can be none (so it loads current curves) 
        or ['curve type', filepath]
        '''
        if inputs is None:
            # update own curve object
            interaction = self.interaction_string_combo.read()
            curve = self._load_curve(inputs, interaction)
            if self.poynting_correction:
                self.curve = wt.tuning.curve.from_poynting_curve(self.poynting_correction.curve_path, subcurve=curve)
            self.curve.convert(self.native_units)
            # update limits
            min_color = self.curve.colors.min()
            max_color = self.curve.colors.max()
            self.limits.write(min_color, max_color, self.native_units)
            self._update_api(interaction)
        else:
            pass

    def set_motor(self, motor_name, destination):
        motor_index = self.motor_names.index(motor_name)
        if self.poynting_correction:
            if motor_name in self.poynting_correction.motor_names:
                self.poynting_correction.set_motor(motor_name, destination)
                return
        self._set_motors([motor_index], [destination])

    def set_motors(self, inputs):
        motor_indexes = range(len(inputs))
        motor_positions = inputs
        if self.poynting_correction:
            for i,pos in zip(motor_indexes, motor_positions):
                if self.motor_names[i] in self.poynting_correction.motor_names:
                    self.poynting_correction.set_motor(self.motor_names[i], motor_position)
                    index = motor_indexes.index(i)
                    motor_indexes = motor_indexes[:index]+motor_indexes[index+1:]
                    motor_positions = motor_positions[:index]+motor_positions[index+1:]
        self._set_motors(motor_indexes, motor_positions)

    def set_position(self, destination):
        print(self.name, 'SET POSITION', destination, self.native_units, self.curve.units)
        # coerce destination to be within current tune range
        destination = np.clip(destination, self.curve.colors.min(), self.curve.colors.max())
        # get destinations from curve
        motor_names = self.curve.get_motor_names()
        motor_destinations = list(self.curve.get_motor_positions(destination, self.native_units))
        print(self.name, motor_destinations)
        # poynting
        if self.poynting_correction:
            for _ in range(2):
                name = motor_names.pop(-1)
                destination = motor_destinations.pop(-1)
                self.poynting_correction.set_motor(name, destination)
        # OPA
        motor_indexes = [self.motor_names.index(n) for n in motor_names]
        self._set_motors(motor_indexes, motor_destinations)
        # finish
        self.wait_until_still()
        self.get_position()
        
    def set_position_except(self, destination, exceptions):
        '''
        set position, except for motors that follow
        
        does not wait until still...
        '''
        self.hardware.destination.write(destination)
        self.position.write(destination, self.native_units)
        motor_destinations = self.curve.get_motor_positions(destination, self.native_units)
        motor_indexes = []
        motor_positions = []
        for i in [self.motor_names.index(n) for n in self.curve.get_motor_names()]:
            if i not in exceptions:
                motor_indexes.append(i)
                motor_positions.append(motor_destinations[i])
        self._set_motors(motor_indexes, motor_positions)
        if self.poynting_correction and False:
            poynting_curve_names = self.poynting_correction.curve.get_motor_names()
            destinations = self.poynting_correction.curve.get_motor_positions(destination,self.poynting_correction.native_units)
            for name in self.poynting_correction.motor_names:
                if self.motor_names.index(name) not in exceptions:
                    self.poynting_correction.set_motor(name, destinations[poynting_curve_names.index(name)])

    def wait_until_still(self,inputs=[]):
        self._wait_until_still(inputs)
        if self.poynting_correction:
            self.poynting_correction.wait_until_still()


### gui #######################################################################


class GUI(hw.GUI):

    def initialize(self):
        # container widget
        display_container_widget = QtGui.QWidget()
        display_container_widget.setLayout(QtGui.QVBoxLayout())
        display_layout = display_container_widget.layout()
        display_layout.setMargin(0)
        self.layout.addWidget(display_container_widget)
        # plot
        self.plot_widget = pw.Plot1D()
        self.plot_widget.plot_object.setMouseEnabled(False, False)
        self.plot_curve = self.plot_widget.add_scatter()
        self.plot_h_line = self.plot_widget.add_infinite_line(angle=0, hide=False)
        self.plot_v_line = self.plot_widget.add_infinite_line(angle=90, hide=False)
        display_layout.addWidget(self.plot_widget)
        # vertical line
        line = pw.line('V')
        self.layout.addWidget(line)
        # container widget / scroll area
        settings_container_widget = QtGui.QWidget()
        settings_scroll_area = pw.scroll_area()
        settings_scroll_area.setWidget(settings_container_widget)
        settings_scroll_area.setMinimumWidth(300)
        settings_scroll_area.setMaximumWidth(300)
        settings_container_widget.setLayout(QtGui.QVBoxLayout())
        settings_layout = settings_container_widget.layout()
        settings_layout.setMargin(5)
        self.layout.addWidget(settings_scroll_area)
        # opa properties
        input_table = pw.InputTable()
        settings_layout.addWidget(input_table)
        # plot control
        input_table = pw.InputTable()
        input_table.add('Display', None)
        self.plot_motor = pc.Combo(allowed_values=self.driver.curve.get_motor_names())
        self.plot_motor.updated.connect(self.update_plot)
        input_table.add('Motor', self.plot_motor)
        allowed_values = list(wt.units.energy.keys())
        allowed_values.remove('kind')
        self.plot_units = pc.Combo(initial_value=self.driver.native_units, allowed_values=allowed_values)
        self.plot_units.updated.connect(self.update_plot)
        input_table.add('Units', self.plot_units)
        settings_layout.addWidget(input_table)
        # curves
        input_table = pw.InputTable()
        input_table.add('Curves', None)
        for name, obj in self.driver.curve_paths.items():
            input_table.add(name, obj)
            obj.updated.connect(self.update_plot)
        input_table.add('Interaction String', self.driver.interaction_string_combo)
        # limits
        limits = pc.NumberLimits()  # units None
        self.low_energy_limit_display = pc.Number(units=self.driver.native_units, display=True, limits=limits)
        input_table.add('Low Energy Limit', self.low_energy_limit_display)
        self.high_energy_limit_display = pc.Number(units=self.driver.native_units, display=True, limits=limits)
        input_table.add('High Energy LImit', self.high_energy_limit_display)
        settings_layout.addWidget(input_table)
        self.driver.limits.updated.connect(self.on_limits_updated)
        # motors
        input_table = pw.InputTable()
        input_table.add('Motors', None)
        settings_layout.addWidget(input_table)
        for motor_name, motor_mutex in self.driver.motor_positions.items():
            settings_layout.addWidget(MotorControlGUI(motor_name, motor_mutex, self.driver))
        self.home_all_button = pw.SetButton('HOME ALL', 'advanced')
        settings_layout.addWidget(self.home_all_button)
        homeable = any(self.driver.homeable)
        self.home_all_button.clicked.connect(self.on_home_all)
        g.queue_control.disable_when_true(self.home_all_button)
        # poynting manual mode
        if self.driver.poynting_correction:
            self.poynting_manual_control = pc.Bool()
            input_table = pw.InputTable()
            input_table.add('Poynting Control', self.poynting_manual_control)
            self.poynting_manual_control.updated.connect(self.on_poynting_manual_control_updated)
            settings_layout.addWidget(input_table)
        # stretch
        settings_layout.addStretch(1)
        # signals and slots
        self.driver.interaction_string_combo.updated.connect(self.update_plot)
        self.driver.update_ui.connect(self.update)
        # finish
        self.update()
        self.update_plot()
        self.on_limits_updated()
        # autotune
        self.driver.auto_tune.initialize()

    def update(self):
        # set button disable
        if self.driver.busy.read():
            self.home_all_button.setDisabled(True)
            for motor_mutex in self.driver.motor_positions.values():
                motor_mutex.set_disabled(True)
        else:
            self.home_all_button.setDisabled(False)
            for motor_mutex in self.driver.motor_positions.values():
                motor_mutex.set_disabled(False)
        # update destination motor positions
        # TODO: 
        # update plot lines
        motor_name = self.plot_motor.read()
        print(self.hardware.name, motor_name)
        motor_position = self.driver.motor_positions[motor_name].read()
        self.plot_h_line.setValue(motor_position)
        units = self.plot_units.read()
        self.plot_v_line.setValue(self.driver.position.read(units))

    def update_plot(self):
        # units
        units = self.plot_units.read()
        # xi
        colors = self.driver.curve.colors
        xi = wt.units.converter(colors, self.driver.curve.units, units)
        # yi
        self.plot_motor.set_allowed_values(self.driver.curve.get_motor_names())  # can be done on initialization?
        motor_name = self.plot_motor.read()
        motor_index = self.driver.curve.get_motor_names().index(motor_name)
        yi = self.driver.curve.get_motor_positions(xi, units)[motor_index]
        self.plot_widget.set_labels(xlabel=units, ylabel=motor_name)
        self.plot_curve.clear()
        self.plot_curve.setData(xi, yi)
        self.plot_widget.graphics_layout.update()
        self.update()
        
        
        print(self.driver.curve.subcurve)
        self.plot_motor.set_allowed_values(self.driver.curve.get_motor_names())

    def on_home_all(self):
        self.hardware.q.push('home_all')
        
    def on_limits_updated(self):
        low_energy_limit, high_energy_limit = self.driver.limits.read('wn')
        self.low_energy_limit_display.write(low_energy_limit, 'wn')
        self.high_energy_limit_display.write(high_energy_limit, 'wn')
        
    def on_poynting_manual_control_updated(self):
        if self.poynting_manual_control.read():
            self.driver.poynting_correction.port.setMode('manual')
        else:
            self.driver.poynting_correction.port.setMode('computer')


class MotorControlGUI(QtGui.QWidget):
    
    def __init__(self, motor_name, motor_mutex, driver):
        QtGui.QWidget.__init__(self)
        self.motor_name = motor_name
        self.driver = driver
        self.hardware = driver.hardware
        self.layout = QtGui.QVBoxLayout()
        self.layout.setMargin(0)
        # table
        input_table = pw.InputTable()
        input_table.add(motor_name, motor_mutex)
        self.destination = motor_mutex.associate(display=False)
        input_table.add('Dest. ' + motor_name, self.destination)
        self.layout.addWidget(input_table)
        # buttons
        home_button, set_button = self.add_buttons(self.layout, 'HOME', 'advanced', 'SET', 'set')
        #homeable = driver.homeable[driver.motor_names.index(motor_name)%len(driver.homeable)]
        #home_button.set_disabled(homeable)
        home_button.clicked.connect(self.on_home)
        set_button.clicked.connect(self.on_set)
        g.queue_control.disable_when_true(home_button)
        g.queue_control.disable_when_true(set_button)
        # finish
        self.setLayout(self.layout)
            
    def add_buttons(self, layout, button1_text, button1_color, button2_text, button2_color):
        colors = g.colors_dict.read()
        # layout
        button_container = QtGui.QWidget()
        button_container.setLayout(QtGui.QHBoxLayout())
        button_container.layout().setMargin(0)
        # button1
        button1 = QtGui.QPushButton()
        button1.setText(button1_text)
        button1.setMinimumHeight(25)
        StyleSheet = 'QPushButton{background:custom_color; border-width:0px;  border-radius: 0px; font: bold 14px}'.replace('custom_color', colors[button1_color])
        button1.setStyleSheet(StyleSheet)
        button_container.layout().addWidget(button1)
        g.queue_control.disable_when_true(button1)
        # button2
        button2 = QtGui.QPushButton()
        button2.setText(button2_text)
        button2.setMinimumHeight(25)
        StyleSheet = 'QPushButton{background:custom_color; border-width:0px;  border-radius: 0px; font: bold 14px}'.replace('custom_color', colors[button2_color])
        button2.setStyleSheet(StyleSheet)
        button_container.layout().addWidget(button2)
        g.queue_control.disable_when_true(button2)
        # finish
        layout.addWidget(button_container)
        return [button1, button2]
        
    def on_home(self):
        self.driver.hardware.q.push('home_motor', [self.motor_name])
    
    def on_set(self):
        destination = self.destination.read()
        self.hardware.set_motor(self.motor_name, destination)


### hardware ##################################################################


class Hardware(hw.Hardware):
    
    def __init__(self, *arks, **kwargs):
        self.kind = 'OPA'
        hw.Hardware.__init__(self, *arks, **kwargs)

    @property
    def curve(self):
        # TODO: a more thread-safe operation (copy?)
        return self.driver.curve

    def home_motor(self, motor):
        """
        motor list [name]
        """
        self.q.push('home_motor', motor)

    @property
    def motor_names(self):
        # TODO: a more thread-safe operation
        return self.driver.motor_names
        
    def run_auto_tune(self, worker):
        self.driver.auto_tune.run(worker)
    
    def set_motor(self, motor, destination):
        """
        Motor may be index or name.
        """
        self.q.push('set_motor', motor, destination)


### initialize ################################################################


ini_path = os.path.join(directory, 'opas.ini')
hardwares, gui, advanced_gui = hw.import_hardwares(ini_path, name='OPAs', Driver=Driver, GUI=GUI, Hardware=Hardware)
