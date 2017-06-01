### import ####################################################################


from __future__ import absolute_import, division, print_function, unicode_literals

import os
import imp
import time
import shutil
import datetime
import dateutil
import collections

try:
    import configparser as configparser  # python 3
except ImportError:
    import ConfigParser as configparser  # python 2

from PyQt4 import QtCore, QtGui

import WrightTools as wt

import project.project_globals as g
import project.classes as pc
import project.widgets as pw
import project.ini_handler as ini_handler
import project.file_dialog_handler as file_dialog_handler


### define ####################################################################


app = g.app.read()

main_window = g.main_window.read()

somatic_folder = os.path.dirname(__file__)
saved_folder = os.path.join(somatic_folder, 'saved')
temp_folder = os.path.join(somatic_folder, 'temp')
data_folder = main_window.data_folder


### ensure folders exist ######################################################


for p in [saved_folder, temp_folder]:
    if not os.path.isdir(p):
        os.mkdir(p)


### queue item classes ########################################################


class Item(QtCore.QObject):
    updated = QtCore.pyqtSignal()
    
    def __init__(self, name='', info='', description=''):
        QtCore.QObject.__init__(self)
        # basic information
        self.name = name  # filled by user, up to 10 charachters long
        self.info = info  # filled by user, can be arbitrarily long
        self.description = description  # filled programmatically, to be displayed in table 
        # status: can be one of 'ENQUEUED', 'RUNNING', 'COMPLETE', 'FAILED'
        self.status = 'ENQUEUED'
        self.finished = pc.Bool(initial_value=False)
        # timestamps
        self.created = wt.kit.TimeStamp()
        self.started = None
        self.exited = None
        
    def write_to_ini(self, ini, section):
        pass


class Acquisition(Item):

    def __init__(self, aqn_path, module, **kwargs):
        Item.__init__(self, **kwargs)
        self.aqn_path = aqn_path
        self.type = 'acquisition'
        self.module = module
        self.url = None
    
    def write_to_ini(self, ini, section):
        ini.write(section, 'path', self.aqn_path)
        ini.write(section, 'url', self.url)


class Device(Item):

    def __init__(self, **kwargs):
        Item.__init__(self, **kwargs)
        self.type = 'acquisition'


class Hardware(Item):

    def __init__(self, **kwargs):
        Item.__init__(self, **kwargs)
        self.type = 'hardware'
    
    def execute(self):
        # TODO:
        print('hardware excecute')


class Interrupt(Item):

    def __init__(self, **kwargs):
        Item.__init__(self, **kwargs)
        self.type = 'interrupt'


class Script(Item):

    def __init__(self, **kwargs):
        Item.__init__(self, **kwargs)
        self.type = 'script'


class Wait(Item):

    def __init__(self, operation, amount, **kwargs):
        Item.__init__(self, **kwargs)
        self.type = 'wait'
        self.operation = operation
        self.amount = amount
    
    def write_to_ini(self, ini, section):
        ini.write(section, 'operation', self.operation)
        ini.write(section, 'amount', self.amount)


### worker ####################################################################


class Worker(QtCore.QObject):
    action_complete = QtCore.pyqtSignal()

    def __init__(self, enqueued, busy, queue_status, queue_url):
        QtCore.QObject.__init__(self)
        self.enqueued = enqueued
        self.busy = busy
        self.queue_status = queue_status
        self.fraction_complete = pc.Number(initial_value=0.)
        self.queue_url = queue_url
        
    def check_busy(self, _=[]):
        if self.enqueued.read():  # there are items in enqueued
            time.sleep(0.1)  # don't loop like crazy
            self.busy.write(True)
        else:
            self.busy.write(False)   
        
    @QtCore.pyqtSlot(str, list)
    def dequeue(self, method, inputs):
        """
        Slot to accept enqueued commands from main thread.
        
        Method passed as qstring, inputs as list of [args, kwargs].
        """
        args, kwargs = inputs
        if g.debug.read():
            print('worker dequeue:', method, inputs)
        # the queue should only be adding items to execute
        item = args[0]
        g.queue_control.write(True)
        self.queue_status.going.write(True)
        self.fraction_complete.write(0.)
        item.started = wt.kit.TimeStamp()
        if item.type == 'acquisition':
            self.execute_acquisition(item)
        elif item.type == 'device':
            self.execute_device(item)
        elif item.type == 'hardware':
            self.execute_hardware(item)
        elif item.type == 'wait':
            self.execute_wait(item)
        item.exited = wt.kit.TimeStamp()
        self.fraction_complete.write(1.)
        self.queue_status.going.write(False)
        g.queue_control.write(False)
        self.action_complete.emit()
        # remove item from enqueued
        self.enqueued.pop()
        if not self.enqueued.read():
            self.check_busy([])
    
    def execute_acquisition(self, item):
        # create acquisition folder on google drive
        folder_name = os.path.abspath(item.aqn_path)[:-4]
        if g.google_drive_enabled.read():
            url = g.google_drive_control.read().create_folder(folder_name)
            ini = wt.kit.INI(item.aqn_path)
            ini.write('info', 'url', url)
            item.url = url
        # create acquisition worker object
        module = item.module
        worker = module.Worker(item.aqn_path, self, item.finished)
        # run it
        if False:
            try:
                worker.run()
            except Exception as error:
                # TODO: log error
                print('ACQUISITION ERROR:', error)
        else:
            worker.run()
        # upload aqn file
        if g.google_drive_enabled.read():
            g.google_drive_control.read().upload_file(item.aqn_path)
        # send message on slack
        if g.slack_enabled.read():
            name = os.path.split(folder_name)[1]
            message = ':checkered_flag: acquisition complete - {0} - {1}'.format(name, item.url)
            g.slack_control.read().send_message(message)

    def execute_device(self, item):
        # TODO:
        time.sleep(5)
        item.finished.write(False)
        
    def execute_hardware(self, item):
        # TODO:
        time.sleep(5)
        item.finished.write(False)
        
    def execute_script(self, item):
        # TODO:
        time.sleep(5)
        item.finished.write(False)
        
    def execute_wait(self, item):
        # get stop time
        tz = dateutil.tz.tzlocal()
        now = datetime.datetime.now(tz)
        if item.operation == 'For':
            h, m, s = [float(s) if s is not '' else 0. for s in item.amount.split(':')]
            total_seconds = 3600.*h + 60.*m + s
            stop_time = now + datetime.timedelta(0, total_seconds)
        elif item.operation == 'Until':
            inputs = {}
            inputs['hour'], inputs['minute'], s = [int(s) if s is not '' else 0 for s in item.amount.split(':')]
            stop_time = collections.OrderedDict()
            stop_time['seconds'] = s
            def get(current, previous):
                if current in inputs.keys():
                    input = inputs[current]
                else:
                    input = 0
                if stop_time[previous] == 0 or not input == 0:
                    stop_time[current] = input
                else:
                    current_now = getattr(now, current)
                    previous_now = getattr(now, previous)
                    if previous_now <= stop_time[previous]:
                        stop_time[current] = current_now
                    else:
                        stop_time[current] = current_now + 1
            previous = 'seconds'
            keys = ['minute', 'hour', 'day', 'month', 'year']
            for key in keys:
                get(key, previous)
                previous = key
            stop_time = datetime.datetime(*stop_time.values()[::-1]+[0, tz])
        # wait until stop time
        total_time = (stop_time-now).total_seconds()
        time_remaining = total_time
        while time_remaining > 0:
            time.sleep(1)
            now = datetime.datetime.now(tz)
            time_remaining = (stop_time-now).total_seconds()
            self.fraction_complete.write((total_time-time_remaining)/total_time)
            # check for pause
            while self.queue_status.pause.read():
                self.queue_status.paused.write(True)
                self.queue_status.pause.wait_for_update()
            if not self.queue_status.go.read():
                return
        # send message on slack
        if g.slack_enabled.read():
            message = ':timer_clock: wait complete - {0}'.format(item.description)
            g.slack_control.read().send_message(message)
        
        item.finished.write(True)


### queue class ###############################################################


class QueueStatus(QtCore.QObject):
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.go = pc.Busy()
        self.going = pc.Busy()
        self.pause = pc.Busy()
        self.paused = pc.Busy()
        self.stop = pc.Busy()
        self.stopped = pc.Busy()
        self.runtime = 0.  # seconds
        self.last_started = None
        self.tz = dateutil.tz.tzlocal()
    
    def run_timer(self):
        self.last_started = datetime.datetime.now(self.tz)
    
    def stop_timer(self):
        now = datetime.datetime.now(self.tz)
        self.runtime += (now-self.last_started).total_seconds()
    
    def get_runtime(self):
        '''
        returns total seconds run
        '''        
        out = self.runtime
        if self.last_started is not None:
            now = datetime.datetime.now(self.tz)
            out += (now-self.last_started).total_seconds()
        return out


class Queue():

    def __init__(self, name, gui, folder=None, url=None):
        self.name = name[:10]  # cannot be more than 10 charachters
        self.gui = gui
        self.status = gui.queue_status
        self.timestamp = wt.kit.TimeStamp()
        # create queue folder
        if folder is None:
            folder_name = ' '.join([self.timestamp.path, self.name])
            self.folder = os.path.join(g.main_window.read().data_folder, folder_name)
            os.mkdir(self.folder)
        else:
            self.folder = folder
            folder_name = os.path.basename(self.folder)
        # create queue file
        self.ini_path = os.path.abspath(os.path.join(self.folder, 'queue.ini'))
        if not os.path.isfile(self.ini_path):
            with open(self.ini_path, 'a'):
                os.utime(self.ini_path, None)  # quickly create empty file
        self.ini = wt.kit.INI(self.ini_path)  # I don't use ini_handler here
        # parameters and status indicators
        self.items = []
        self.index = 0
        self.going = pc.Busy()
        self.paused = pc.Busy()
        # create storage folder on google drive
        if url is None:
            if g.google_drive_enabled.read():
                self.url = g.google_drive_control.read().create_folder(self.folder)
            else:
                self.url = None
        else:
            self.url = url
        # initialize worker
        self.worker_enqueued = pc.Enqueued()
        self.worker_busy = pc.Busy()
        self.worker = Worker(self.worker_enqueued, self.worker_busy, self.status, self.url)
        self.worker.fraction_complete.updated.connect(self.update_progress)
        self.worker.action_complete.connect(self.on_action_complete)
        self.worker_thread = QtCore.QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()
        self.worker_q = pc.Q(self.worker_enqueued, self.worker_busy, self.worker)
        # message on slack
        if g.slack_enabled.read():
            message = ':baby: new queue created - {0} - {1}'.format(folder_name, self.url)
            g.slack_control.read().send_message(message)
        
    def _start_next_action(self):
        print('this is start next action', self.index)
        self.status.pause.write(False)
        self.status.paused.write(False)
        self.status.stop.write(False)
        self.status.stopped.write(False)
        self.gui.progress_bar.begin_new_scan_timer()
        item = self.items[self.index]
        item.status = 'RUNNING'
        self.worker_q.push('excecute', item)
        self.gui.message_widget.setText(item.description.upper())

    def append_acquisition(self, aqn_path, update=True):
        # get properties
        ini = wt.kit.INI(aqn_path)
        aqn_index_str = str(len(self.items)).zfill(3)
        module_name = ini.read('info', 'module')
        item_name = ini.read('info', 'name')
        info = ini.read('info', 'info')
        description = ini.read('info', 'description')
        module = self.gui.modules[module_name]
        # move aqn file into queue folder
        aqn_name = ' '.join([aqn_index_str, module_name, item_name]).rstrip() + '.aqn'
        new_aqn_path = os.path.join(self.folder, aqn_name)
        if not aqn_path == new_aqn_path:
            shutil.copyfile(aqn_path, os.path.abspath(new_aqn_path))
            aqn_path = os.path.abspath(new_aqn_path)
        # create item
        acquisition = Acquisition(aqn_path, module, name=item_name, info=info, description=description)
        # append and update
        self.items.append(acquisition)
        if update:
            self.update()

    def append_device(self):
        # TODO:
        print('append_device')

    def append_hardware(self):
        # TODO:
        print('append_hardware')

    def append_interrupt(self):
        # TODO:
        print('append_interrupt')

    def append_script(self):
        # TODO:
        print('append_script')

    def append_wait(self, operation, amount, name, info, description):
        # create item
        wait = Wait(operation, amount, name=name, info=info, description=description)
        # append and update
        self.items.append(wait)
        self.update()
    
    def change_index(self, current_index, new_index):
        item = self.items.pop(current_index)
        if new_index < self.index:
            new_index = self.index + 1
        self.items.insert(new_index, item)
        self.update()
        return item
    
    def exit(self):
        # cleanly exit thread
        self.worker_thread.exit()
        self.worker_thread.quit()
    
    def get_runtime(self):
        seconds = self.status.get_runtime()
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        string = ':'.join([str(int(h)).zfill(3), str(int(m)).zfill(2), str(int(s)).zfill(2)])
        return string

    def interrupt(self, message='Please choose how to proceed.'):
        self.gui.queue_control.set_style('WAITING', 'stop')
        # pause
        self.status.pause.write(True)
        while not self.status.paused.read():
            self.status.paused.wait_for_update()
        # ask user how to proceed
        options = ['RESUME', 'SKIP', 'STOP']
        self.gui.interrupt_choice_window.set_text(message)
        index_chosen = self.gui.interrupt_choice_window.show()
        chosen = options[index_chosen]
        # proceed
        if chosen == 'RESUME':
            self.status.pause.write(False)
        elif chosen == 'SKIP':
            self.status.stop.write(True)
            self.status.pause.write(False)
        elif chosen == 'STOP':
            self.status.stop.write(True)
            self.status.go.write(False)
            self.status.pause.write(False)
        # wait for stop
        if chosen in ['SKIP', 'STOP']:
            while not self.status.stopped.read():
                self.status.stopped.wait_for_update()
        # finish
        self.status.stop.write(False)
        self.status.pause.write(False)
        self.update()

    def finish(self):
        self.status.stop_timer()
        self.gui.on_queue_finished()
        self.update()
        if g.slack_enabled.read():
            g.slack_control.read().send_message(':bell: queue emptied - total runtime {}'.format(self.get_runtime()))

    def on_action_complete(self):
        # update current item
        item = self.items[self.index]
        if item.finished.read():
            item.status = 'COMPLETE'
        else:
            item.status = 'FAILED'
        # upload queue.ini to google drive
        if g.google_drive_enabled.read():
            g.google_drive_control.read().upload_file(self.ini_path)
        # onto next item
        self.index += 1
        queue_done = len(self.items) == self.index
        print('queue done', queue_done)
        # check if any more items exist in queue
        if queue_done:
            self.finish()
        # continue (if still going)
        if self.status.go.read() and not queue_done:
            self._start_next_action()
        # finish
        self.update()

    def pop(self, index):
        out = self.items.pop(index)
        self.update()
        return out

    def run(self):
        # status
        self.status.run_timer()
        self.status.go.write(True)
        self.status.pause.write(False)
        # excecute next item
        self._start_next_action()
        # finish
        self.update()
    
    def update(self):
        print('queue update')
        # update ini
        self.ini.clear()
        self.ini.add_section('info')
        self.ini.write('info', 'PyCMDS version', g.version.read())
        self.ini.write('info', 'created', self.timestamp.RFC3339)
        self.ini.write('info', 'runtime', self.get_runtime())
        self.ini.write('info', 'name', self.name)
        self.ini.write('info', 'url', self.url)
        for index, item in enumerate(self.items):
            index_str = str(index).zfill(3)
            self.ini.add_section(index_str)
            self.ini.write(index_str, 'type', item.type)
            self.ini.write(index_str, 'name', item.name)
            self.ini.write(index_str, 'info', item.info)
            self.ini.write(index_str, 'description', item.description)
            self.ini.write(index_str, 'status', item.status)
            self.ini.write(index_str, 'created', item.created.RFC3339)
            if item.started is not None:
                self.ini.write(index_str, 'started', item.started.RFC3339)
            if item.exited is not None:
                self.ini.write(index_str, 'exited', item.exited.RFC3339)
            # allow item to write additional information
            item.write_to_ini(self.ini, index_str)
        # update display
        self.gui.update_ui()
        # upload ini
        if g.google_drive_enabled.read():
            g.google_drive_control.read().upload_file(self.ini_path)
    
    def update_progress(self):
        # progress bar
        self.gui.progress_bar.set_fraction(self.worker.fraction_complete.read())
        # queue timer
        runtime_string = self.get_runtime()
        self.gui.runtime.write(runtime_string)
            

### GUI #######################################################################


class GUI(QtCore.QObject):

    def __init__(self, parent_widget, message_widget):
        QtCore.QObject.__init__(self)
        self.progress_bar = g.progress_bar
        # frame, widgets
        self.message_widget = message_widget
        parent_widget.setLayout(QtGui.QHBoxLayout())
        parent_widget.layout().setContentsMargins(0, 10, 0, 0)
        self.layout = parent_widget.layout()
        self.create_frame()
        self.interrupt_choice_window = pw.ChoiceWindow('QUEUE INTERRUPTED', button_labels=['RESUME', 'SKIP', 'STOP'])
        # queue
        self.queue = None
        self.queue_status = QueueStatus()
        
    def add_button_to_table(self, i, j, text, color, method):
        # for some reason, my lambda function does not work when called outside
        # of a dedicated method - Blaise 2016-09-14
        button = pw.SetButton(text, color=color)
        button.setProperty('TableRowIndex', i)
        button.clicked.connect(lambda: method(button.property('TableRowIndex')))
        self.table.setCellWidget(i, j, button)
        return button
    
    def add_index_to_table(self, i, max_value):
        # for some reason, my lambda function does not work when called outside
        # of a dedicated method - Blaise 2016-09-14
        index = QtGui.QDoubleSpinBox()
        StyleSheet = 'QDoubleSpinBox{color: custom_color; font: 14px;}'.replace('custom_color', g.colors_dict.read()['text_light'])
        StyleSheet += 'QScrollArea, QWidget{background: custom_color;  border-color: black; border-radius: 0px;}'.replace('custom_color', g.colors_dict.read()['background'])
        StyleSheet += 'QWidget:disabled{color: custom_color_1; font: 14px; border: 0px solid black; border-radius: 0px;}'.replace('custom_color_1', g.colors_dict.read()['text_disabled']).replace('custom_color_2', g.colors_dict.read()['widget_background'])                
        index.setStyleSheet(StyleSheet)
        index.setButtonSymbols(QtGui.QAbstractSpinBox.NoButtons)
        index.setSingleStep(1)
        index.setDecimals(0)
        index.setMaximum(max_value)
        index.setAlignment(QtCore.Qt.AlignCenter)
        index.setValue(i)
        index.setProperty('TableRowIndex', i)
        index.editingFinished.connect(lambda: self.on_index_changed(index.property('TableRowIndex'), int(index.value())))
        self.table.setCellWidget(i, 0, index)
        return index    
    
    def create_acquisition_frame(self):
        frame = QtGui.QWidget()
        frame.setLayout(QtGui.QVBoxLayout())
        layout = frame.layout()
        layout.setMargin(0)
        layout.setContentsMargins(0, 0, 0, 0)
        # load aqn file
        self.load_aqn_button = pw.SetButton('LOAD FROM FILE')
        self.load_aqn_button.clicked.connect(self.on_load_aqn)
        layout.addWidget(self.load_aqn_button)
               
        input_table = pw.InputTable()
        # module combobox
        self.module_combobox = pc.Combo()
        input_table.add('Acquisition Module', self.module_combobox)
        # name
        self.acquisition_name = pc.String(max_length=10)
        input_table.add('Name', self.acquisition_name)
        # info
        self.acquisition_info = pc.String()
        input_table.add('Info', self.acquisition_info)
        layout.addWidget(input_table)
        # module container widget
        self.module_container_widget = QtGui.QWidget()
        self.module_container_widget.setLayout(QtGui.QVBoxLayout())
        module_layout = self.module_container_widget.layout()
        module_layout.setMargin(0)
        module_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.module_container_widget)
        # save aqn file
        self.save_aqn_button = pw.SetButton('SAVE FILE')
        self.save_aqn_button.clicked.connect(self.on_save_aqn)
        layout.addWidget(self.save_aqn_button)
        return frame

    def create_device_frame(self):
        frame = QtGui.QWidget()
        frame.setLayout(QtGui.QVBoxLayout())
        layout = frame.layout()
        layout.setContentsMargins(0, 0, 0, 0)
        # name and info
        input_table = pw.InputTable()
        self.device_name = pc.String(max_length=10)
        input_table.add('Name', self.device_name)
        self.device_info = pc.String()
        input_table.add('Info', self.device_info)       
        layout.addWidget(input_table)        
        # not implemented message
        label = QtGui.QLabel('device not currently implemented')
        StyleSheet = 'QLabel{color: custom_color; font: bold 14px}'.replace('custom_color', g.colors_dict.read()['text_light'])
        label.setStyleSheet(StyleSheet)
        layout.addWidget(label)
        return frame

    def create_frame(self):
        # queue display -------------------------------------------------------
        # container widget
        display_container_widget = pw.ExpandingWidget()
        display_layout = display_container_widget.layout()
        display_layout.setMargin(0)
        self.layout.addWidget(display_container_widget)
        # table
        self.table = pw.TableWidget()
        self.table.verticalHeader().hide()
        self.table_cols = collections.OrderedDict()
        self.table_cols['Index'] = 50
        self.table_cols['Type'] = 75
        self.table_cols['Status'] = 85
        self.table_cols['Started'] = 110
        self.table_cols['Exited'] = 110
        self.table_cols['Description'] = 200  # expanding
        self.table_cols['Remove'] = 75
        self.table_cols['Load'] = 75
        for i in range(len(self.table_cols.keys())):
            self.table.insertColumn(i)
        labels = list(self.table_cols.keys())
        labels[-1] = ''
        labels[-2] = ''
        self.table.setHorizontalHeaderLabels(labels)
        self.table.horizontalHeader().setResizeMode(5, QtGui.QHeaderView.Stretch)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        for i, width in enumerate(self.table_cols.values()):
            self.table.setColumnWidth(i, width)
        display_layout.addWidget(self.table)
        # line ----------------------------------------------------------------
        line = pw.Line('V')
        self.layout.addWidget(line)
        # controls ------------------------------------------------------------
        settings_container_widget = QtGui.QWidget()
        settings_scroll_area = pw.scroll_area()
        settings_scroll_area.setWidget(settings_container_widget)
        settings_scroll_area.setMinimumWidth(300)
        settings_scroll_area.setMaximumWidth(300)
        settings_container_widget.setLayout(QtGui.QVBoxLayout())
        settings_layout = settings_container_widget.layout()
        settings_layout.setMargin(5)
        self.layout.addWidget(settings_scroll_area)
        # new queue name
        input_table = pw.InputTable()
        self.new_queue_name = pc.String('queue', max_length=10)
        input_table.add('Create Queue', None)
        input_table.add('New Name', self.new_queue_name)
        settings_layout.addWidget(input_table)
        # new queue button
        self.new_queue_button = pw.SetButton('MAKE NEW QUEUE')
        self.new_queue_button.clicked.connect(self.create_new_queue)
        settings_layout.addWidget(self.new_queue_button)
        # load button
        self.load_button = pw.SetButton('OPEN QUEUE')
        self.load_button.clicked.connect(self.on_open_queue)
        settings_layout.addWidget(self.load_button)
        # current queue name
        input_table = pw.InputTable()
        self.queue_name = pc.String(display=True)
        input_table.add('Name', self.queue_name)
        # current queue timestamp
        self.queue_timestamp = pc.String(display=True)
        input_table.add('Timestamp', self.queue_timestamp)
        settings_layout.addWidget(input_table)
        # horizontal line
        line = pw.line('H')
        settings_layout.addWidget(line)
        # adjust queue label
        input_table = pw.InputTable()
        input_table.add('Control Queue', None)
        settings_layout.addWidget(input_table)
        # go button
        self.queue_control = pw.QueueControl()
        self.queue_control.clicked.connect(self.on_queue_control_clicked)
        settings_layout.addWidget(self.queue_control)
        self.queue_control.setDisabled(True)
        # queue runtime
        input_table = pw.InputTable()
        self.runtime = pc.String(initial_value='000:00:00', display=True)
        input_table.add('Queue Runtime', self.runtime)
        settings_layout.addWidget(input_table)
        # horizontal line
        line = pw.Line('H')
        settings_layout.addWidget(line)
        # type combobox
        input_table = pw.InputTable()
        allowed_values = ['Acquisition', 'Wait', 'Interrupt', 'Hardware', 'Device', 'Script']
        allowed_values.remove('Interrupt')  # not ready yet
        allowed_values.remove('Hardware')  # not ready yet
        allowed_values.remove('Device')  # not ready yet
        allowed_values.remove('Script')  # not ready yet
        self.type_combo = pc.Combo(allowed_values=allowed_values)
        self.type_combo.updated.connect(self.update_type)
        input_table.add('Add to Queue', None)
        input_table.add('Type', self.type_combo)
        settings_layout.addWidget(input_table)
        # frames
        self.type_frames = collections.OrderedDict()
        self.type_frames['Acquisition'] = self.create_acquisition_frame()
        self.type_frames['Wait'] = self.create_wait_frame()
        self.type_frames['Interrupt'] = self.create_interrupt_frame()
        self.type_frames['Hardware'] = self.create_hardware_frame()
        self.type_frames['Device'] = self.create_device_frame()
        self.type_frames['Script'] = self.create_script_frame()
        for frame in self.type_frames.values():
            settings_layout.addWidget(frame)
            frame.hide()
        self.update_type()
        # append button
        self.append_button = pw.SetButton('APPEND TO QUEUE')
        self.append_button.setDisabled(True)
        self.append_button.clicked.connect(self.on_append_to_queue)
        settings_layout.addWidget(self.append_button)
        # finish --------------------------------------------------------------
        settings_layout.addStretch(1)

    def create_hardware_frame(self):
        frame = QtGui.QWidget()
        frame.setLayout(QtGui.QVBoxLayout())
        layout = frame.layout()
        layout.setContentsMargins(0, 0, 0, 0)
        # name and info
        input_table = pw.InputTable()
        self.hardware_name = pc.String(max_length=10)
        input_table.add('Name', self.hardware_name)
        self.hardware_info = pc.String()
        input_table.add('Info', self.hardware_info)       
        layout.addWidget(input_table)        
        # not implemented message
        label = QtGui.QLabel('hardware not currently implemented')
        StyleSheet = 'QLabel{color: custom_color; font: bold 14px}'.replace('custom_color', g.colors_dict.read()['text_light'])
        label.setStyleSheet(StyleSheet)
        layout.addWidget(label)
        return frame

    def create_interrupt_frame(self):
        # since there is no options to choose, return an empty frame
        frame = QtGui.QWidget()
        frame.setLayout(QtGui.QVBoxLayout())
        layout = frame.layout()
        layout.setMargin(0)
        layout.setContentsMargins(0, 0, 0, 0)
        # name and info
        input_table = pw.InputTable()
        self.interrupt_name = pc.String(max_length=10)
        input_table.add('Name', self.interrupt_name)
        self.interrupt_info = pc.String()
        input_table.add('Info', self.interrupt_info)       
        layout.addWidget(input_table)
        return frame
    
    def create_new_queue(self):
        # exit old queue
        if self.queue is not None:
            self.queue.exit()
        # make new queue
        self.queue = Queue(self.new_queue_name.read(), self)
        self.queue_name.write(self.queue.name)
        self.queue_timestamp.write(self.queue.timestamp.path[-5:])
        self.message_widget.setText('QUEUE NOT YET RUN')
        self.queue.update()  # will call self.update_ui

    def create_script_frame(self):
        frame = QtGui.QWidget()
        frame.setLayout(QtGui.QVBoxLayout())
        layout = frame.layout()
        layout.setMargin(0)
        layout.setContentsMargins(0, 0, 0, 0)
        input_table = pw.InputTable()
        self.script_name = pc.String(max_length=10)
        input_table.add('Name', self.script_name)
        self.script_info = pc.String()
        input_table.add('Info', self.script_info)       
        self.script_path = pc.Filepath()
        input_table.add('Script Path', self.script_path)
        layout.addWidget(input_table)
        return frame

    def create_wait_frame(self):
        frame = QtGui.QWidget()
        frame.setLayout(QtGui.QVBoxLayout())
        layout = frame.layout()
        layout.setContentsMargins(0, 0, 0, 0)
        input_table = pw.InputTable()
        self.wait_name = pc.String(max_length=10)
        input_table.add('Name', self.wait_name)
        self.wait_info = pc.String()
        input_table.add('Info', self.wait_info)  
        allowed_values = ['For', 'Until']
        self.wait_operation = pc.Combo(allowed_values=allowed_values)
        input_table.add('Operation', self.wait_operation)
        self.wait_amount = pc.String()
        input_table.add('Amount (H:M:S)', self.wait_amount)
        layout.addWidget(input_table)
        return frame
    
    def get_status(self):
        # called by slack
        make_field = g.slack_control.read().make_field
        make_attachment = g.slack_control.read().make_attachment
        if self.queue is None:
            return ':information_desk_person: no queue has been created', {}
        else:
            message = ':information_desk_person: {}'.format(self.message_widget.text())
            time_remaining_str = g.progress_bar.time_remaining.text()
            if not time_remaining_str == '00:00:00':
                message += ' - {} remaining'.format(time_remaining_str)
            attachments = []
            colors = {'ENQUEUED': '#808080',
                      'RUNNING': '#FFFF00',
                      'COMPLETE': '#00FF00',
                      'FAILED': '#FF0000'}
            # queue status
            fields = []
            fields.append(make_field('name', self.queue.name, short=True))
            fields.append(make_field('created', self.queue.timestamp.human, short=True))
            fields.append(make_field('runtime', self.queue.get_runtime(), short=True))
            fields.append(make_field('done/total', '/'.join([str(self.queue.index), str(len(self.queue.items))]), short=True))
            fields.append(make_field('url', self.queue.url, short=False))
            attachments.append(make_attachment('', fields=fields, color='#00FFFF'))
            # queue items 
            for item_index, item in enumerate(self.queue.items):
                name = ' - '.join([str(item_index).zfill(3), item.type, item.description])
                fields = []
                if item.started is not None:
                    fields.append(make_field('started', item.started.human, short=True))
                if item.exited is not None:
                    fields.append(make_field('exited', item.exited.human, short=True))
                if item.type == 'acquisition' and item.status in ['COMPLETE', 'FAILED']:
                    fields.append(make_field('url', item.url, short=False))
                attachments.append(make_attachment('', title=name, fields=fields, color=colors[item.status]))
            return message, attachments
    
    def load_modules(self):
        # called by MainWindow.__init__
        g.queue_control.write(False)
        if g.debug.read():
            print('load modules')
        # create acquisition thread
        acquisition_thread = QtCore.QThread()
        g.scan_thread.write(acquisition_thread)
        acquisition_thread.start()
        # import modules
        # done from modules.ini
        # modules appear in order of import (order of appearance in ini)
        config = configparser.SafeConfigParser()
        p = os.path.join(somatic_folder, 'modules.ini')
        config.read(p)
        self.modules = collections.OrderedDict()
        for name in config.options('load'):
            if config.get('load', name) == 'True':
                path = os.path.join(somatic_folder, 'modules', name + '.py')
                module = imp.load_source(name, path)
                self.modules[module.module_name] = module
                self.module_container_widget.layout().addWidget(module.gui.frame)
        # update module combo
        self.module_combobox.set_allowed_values(list(self.modules.keys()))
        self.module_combobox.updated.connect(self.on_module_combobox_updated)
        self.on_module_combobox_updated()

    def on_append_to_queue(self):
        current_type = self.type_combo.read()
        if current_type == 'Acquisition':
            p = self.save_aqn(temp_folder)
            self.queue.append_acquisition(p)
            # TODO: remove temporary aqn file
        elif current_type == 'Wait':
            name = self.wait_name.read()
            info = self.wait_info.read()
            operation = self.wait_operation.read()
            amount = self.wait_amount.read()
            description = ' '.join(['wait', operation.lower(), amount])
            self.queue.append_wait(operation, amount, name=name, info=info, description=description)
        elif current_type == 'Interrupt':
            name = self.interrupt_name.read()
            info = self.interrupt_info.read()
            description = 'interrupt'
            self.queue.append_interrupt(name=name, info=info, description=description)
        elif current_type == 'Hardware':
            # TODO:
            self.queue.append_hardware()
        elif current_type == 'Device':
            # TODO:
            self.queue.append_device()
        elif current_type == 'Script':
            # TODO:
            self.queue.append_script()
        else:
            raise Warning('current_type not recognized in on_append_to_queue')
        # run queue
        if self.queue_status.go.read() and not self.queue_status.going.read():
            self.queue.run()

    def on_queue_control_clicked(self):
        if self.queue_status.going.read():
            self.queue.interrupt()
        else:  # queue not currently running
            queue_full = len(self.queue.items) == self.queue.index
            if not queue_full:
                self.queue.run()
        self.update_ui()

    def on_queue_finished(self):
        self.queue_control.set_style('RUN QUEUE', 'go')

    def on_index_changed(self, row, new_index):
        index = row.toInt()[0]  # given as QVariant
        new_index = new_index
        self.queue.change_index(index, new_index)

    def on_load_aqn(self):
        # get path from user
        caption = 'Choose an aqn file'
        directory = os.path.join(somatic_folder, 'saved')
        options = 'AQN (*.aqn);;All Files (*.*)'
        p = file_dialog_handler.open_dialog(caption=caption, directory=directory, options=options)
        # load basic info
        ini = wt.kit.INI(p)
        self.acquisition_name.write(ini.read('info', 'name'))
        self.acquisition_info.write(ini.read('info', 'info'))
        self.module_combobox.write(ini.read('info', 'module'))
        # allow module to load from file
        self.modules[self.module_combobox.read()].gui.load(p)

    def on_load_item(self, row):
        index = row.toInt()[0]  # given as QVariant
        item = self.queue.items[index]
        if item.type == 'acquisition':
            self.type_combo.write('Acquisition')
            # load basic info
            p = item.aqn_path
            aqn = wt.kit.INI(p)
            self.acquisition_name.write(aqn.read('info', 'name'))
            self.acquisition_info.write(aqn.read('info', 'info'))
            self.module_combobox.write(aqn.read('info', 'module'))
            # allow module to load from file
            self.modules[self.module_combobox.read()].gui.load(p)
        elif item.type == 'device':
            raise NotImplementedError()
        elif item.type == 'hardware':
            raise NotImplementedError()
        elif item.type == 'interrupt':
            raise NotImplementedError()
        elif item.type == 'script':
            raise NotImplementedError()
        elif item.type == 'wait':
            self.type_combo.write('Wait')
            self.wait_name.write(item.name)
            self.wait_info.write(item.info)
            self.wait_operation.write(item.operation)
            self.wait_amount.write(item.amount)
        else:
            raise Exception('item.type not recognized in queue.GUI.on_load_item')
        
    def on_module_combobox_updated(self):
        for module in self.modules.values():
            module.gui.hide()
        self.modules[self.module_combobox.read()].gui.show()

    def on_open_queue(self):
        # get queue folder
        caption = 'Choose Queue directory'
        directory = data_folder
        f = file_dialog_handler.dir_dialog(caption=caption, directory=directory)
        p = os.path.join(f, 'queue.ini')
        ini = wt.kit.INI(p)
        # choose operation
        if self.queue is None:
            operation = 'REPLACE'
        else:
            # ask user how to proceed
            options = ['APPEND', 'REPLACE']
            choice_window = pw.ChoiceWindow('OPEN QUEUE', button_labels=options)
            index_chosen = choice_window.show()
            operation = options[index_chosen]
        # prepare queue
        if operation == 'REPLACE':
            if self.queue is not None:
                self.queue.exit()
            name = ini.read('info', 'name')
            url = ini.read('info', 'url')
            self.queue = Queue(name, self, folder=f, url=url)
            self.queue.status.run_timer()
            runtime = ini.read('info', 'runtime')
            h, m, s = [int(s) for s in runtime.split(':')]
            self.queue.status.runtime = h*3600 + m*60 + s
        # append items to queue
        i = 0
        while True:
            section = str(i).zfill(3)
            print('section', section)
            try:
                item_type = ini.read(section, 'type')
            except:
                break
            if item_type == 'acquisition':
                p = ini.read(section, 'path')
                self.queue.append_acquisition(p, update=False)
            elif item_type == 'device':
                raise NotImplementedError
            elif item_type == 'hardware':
                raise NotImplementedError
            elif item_type == 'interrupt':
                raise NotImplementedError
            elif item_type == 'script':
                raise NotImplementedError
            elif item_type == 'wait':
                raise NotImplementedError
            else:
                raise KeyError
            if operation == 'REPLACE':
                item = self.queue.items[i]
                status = ini.read(section, 'status')
                if status == 'RUNNING':
                    item.status = 'FAILED'
                    item.started = wt.kit.TimeStamp()
                    item.exited = wt.kit.TimeStamp()
                else:
                    item.status = status
                item.created = wt.kit.timestamp_from_RFC3339(ini.read(section, 'created'))
                if ini.has_section('started'):
                    item.started = wt.kit.timestamp_from_RFC3339(ini.read(section, 'started'))
                    item.exited = wt.kit.timestamp_from_RFC3339(ini.read(section, 'exited'))
                    if item.status == 'COMPLETE':
                        item.finished.write(True)                
            i += 1
        # manage queue index
        for index, item in enumerate(self.queue.items):
            if item.status == 'ENQUEUED':
                break
            else:
                self.queue.index += 1
        if not self.queue.items[-1].status == 'ENQUEUED':
            self.queue.index += 1
        # finish
        self.queue.update()
        self.queue_name.write(self.queue.name)
        self.queue_timestamp.write(self.queue.timestamp.path[-5:])

    def on_remove_item(self, row):
        index = row.toInt()[0]  # given as QVariant
        self.queue.pop(index)
        
    def on_save_aqn(self):
        self.save_aqn(saved_folder)

    def save_aqn(self, folder):
        # all aqn files are first created using this method
        now = time.time()
        # get filepath
        module_name = self.module_combobox.read()
        name = self.acquisition_name.read()
        timestamp = wt.kit.get_timestamp(style='short', at=now)
        aqn_name = ' '.join([timestamp, module_name, name]).rstrip() + '.aqn'
        p = os.path.join(folder, aqn_name)
        # create file
        with open(p, 'a'):
            os.utime(p, None)  # quickly create empty file
        # fill with general information
        ini = wt.kit.INI(p)
        ini.add_section('info')
        ini.write('info', 'PyCMDS version', g.version.read())
        ini.write('info', 'created', wt.kit.get_timestamp(at=now))
        ini.write('info', 'module', module_name)
        ini.write('info', 'name', name)
        ini.write('info', 'info', self.acquisition_info.read())
        ini.write('info', 'description', module_name)  # optionally overwritten by module
        # fill with module specific information
        self.modules[module_name].gui.save(p)
        # finish
        return p
        
    def update_ui(self):
        # buttons -------------------------------------------------------------
        if self.queue:
            queue_go = self.queue_status.go.read()
            queue_going = self.queue_status.going.read()
            queue_has_items = not len(self.queue.items) == 0
            # queue control
            self.queue_control.setDisabled(False)
            if queue_go:
                if queue_going:
                    self.queue_control.set_style('INTERRUPT QUEUE', 'stop')
                else:
                    self.queue_control.set_style('STOP QUEUE', 'stop')
                    self.message_widget.setText('QUEUE WAITING')
            else:
                self.queue_control.set_style('RUN QUEUE', 'go')
                self.message_widget.setText('QUEUE STOPPED')
            # append button
            self.append_button.setDisabled(False)
        # table ---------------------------------------------------------------
        # clear table
        for _ in range(self.table.rowCount()):
            self.table.removeRow(0)
        # add elements from queue
        for i, item in enumerate(self.queue.items):
            self.table.insertRow(i)
            # index
            index = self.add_index_to_table(i, len(self.queue.items)-1)
            if not item.status == 'ENQUEUED':
                index.setDisabled(True)
            # type
            label = pw.Label(item.type)
            label.setAlignment(QtCore.Qt.AlignCenter)
            label.setMargin(3)
            self.table.setCellWidget(i, 1, label)
            # status
            label = pw.Label(item.status)
            label.setAlignment(QtCore.Qt.AlignCenter)
            label.setMargin(3)
            self.table.setCellWidget(i, 2, label)
            # started
            if item.started is not None:
                text = item.started.hms
                label = pw.Label(text)
                label.setAlignment(QtCore.Qt.AlignCenter)
                label.setMargin(3)
                self.table.setCellWidget(i, 3, label)
            # exited
            if item.exited is not None:
                text = item.exited.hms
                label = pw.Label(text)
                label.setAlignment(QtCore.Qt.AlignCenter)
                label.setMargin(3)
                self.table.setCellWidget(i, 4, label)
            # description
            label = pw.Label(item.description)
            label.setMargin(3)
            label.setToolTip(item.description)
            self.table.setCellWidget(i, 5, label)
            # remove
            button = self.add_button_to_table(i, 6, 'REMOVE', 'stop', self.on_remove_item)
            if not item.status == 'ENQUEUED':
                button.setDisabled(True)
            # load
            button = self.add_button_to_table(i, 7, 'LOAD', 'go', self.on_load_item)

    def update_type(self):
        for frame in self.type_frames.values():
            frame.hide()
        self.type_frames[self.type_combo.read()].show()