#Slacker implementation for pyCMDS


import os
import sys
import time
import glob
import datetime

from PyQt4 import QtGui, QtCore

import project.classes as pc
import project.logging_handler as logging_handler
import project.project_globals as g
from project.ini_handler import Ini
from . import bots
main_dir = g.main_dir.read()
ini = Ini(os.path.join(main_dir, 'project', 'slack', 'bots.ini'))
#import daq.daq as daq

import WrightTools as wt


### container objects #########################################################


class Messages(QtCore.QMutex):

    def __init__(self):
        '''
        holds list of enqueued options
        '''
        QtCore.QMutex.__init__(self)
        self.value = []

    def read(self):
        self.lock()
        out = self.value
        self.value = []
        self.unlock()
        return out

    def push(self, value):
        self.lock()
        self.value.append(value)
        self.unlock()

    def pop(self):
        self.lock()
        self.value = self.value[1:]
        self.unlock()
        
messages_mutex = Messages()

        
### address & control objects #################################################


class Address(QtCore.QObject):
    update_ui = QtCore.pyqtSignal()
    queue_emptied = QtCore.pyqtSignal()

    def __init__(self, busy, enqueued):
        QtCore.QObject.__init__(self)
        self.busy = busy
        self.enqueued = enqueued
        self.ctrl = bots.witch
        self.name = 'slack'

    def check_busy(self):
        """
        Handles writing of busy to False.
        
        Must always write to busy.
        """
        if self.is_busy():
            time.sleep(0.01)  # don't loop like crazy
            self.busy.write(True)
        elif self.enqueued.read():
            time.sleep(0.1)  # don't loop like crazy
            self.busy.write(True)
        else:
            self.busy.write(False)
            self.update_ui.emit()

    @QtCore.pyqtSlot(str, list)
    def dequeue(self, method, inputs):
        """
        Slot to accept enqueued commands from main thread.
        
        Method passed as qstring, inputs as list of [args, kwargs].
        
        Calls own method with arguments from inputs.
        """
        self.update_ui.emit()
        method = str(method)  # method passed as qstring
        args, kwargs = inputs
        self.enqueued.pop()
        getattr(self, method)(*args, **kwargs) 
        if not self.enqueued.read(): 
            self.queue_emptied.emit()
            self.check_busy()
            
    def get_messages(self, inputs):
        newer_than = inputs[0]
        messages = self.ctrl.get_messages(newer_than=newer_than)
        for message in messages:
            messages_mutex.push(message)

    def is_busy(self):
        return False

    def send_message(self, inputs):
        text, channel, attachments = inputs
        self.ctrl.send_message(text, channel, attachments)
        
    def upload_file(self, inputs):
        file_path, Title, first_comment, channel = inputs
        self.ctrl.upload_file(file_path, Title, first_comment, channel)
        
    def delete_files(self, inputs):
        self.ctrl.delete_files
        
    def sign_off(self, inputs):
        message = inputs[0]
        self.ctrl.send_message(message)


class Control:
    
    def __init__(self):
        self.most_recent_delete = time.time()
        # create control containers
        self.busy = pc.Busy()
        self.enqueued = pc.Enqueued()
        # create address object
        self.thread = QtCore.QThread()
        self.address = Address(self.busy, self.enqueued)
        self.address.moveToThread(self.thread)
        self.thread.start()
        # create q
        self.q = pc.Q(self.enqueued, self.busy, self.address)
        # connect
        g.shutdown.add_method(self.close)
        # signal startup
        self.send_message(':wave: signing on', ini.read('bots', 'channel'))
        g.slack_control.write(self)
        
    def append(self, text, channel):
        self.send_message(':confounded: sorry, that feature hasn\'t been implemented')        
        
    def close(self):
        self.q.push('sign_off', [':spock-hand: signing off'])
        time.sleep(1)
        # quit thread
        self.thread.exit()
        self.thread.quit()
        
    def get(self, text, channel):
        # interpret text as integer
        try:
            i = int(text)
        except:
            self.send_message(':interrobang: I couldn\'t find a number in your request')
            return
        print(i)

    def interrupt(self, text, channel):
        self.send_message(':confounded: sorry, that feature hasn\'t been implemented')        

    def log(self, text, channel):
        log_filepath = logging_handler.filepath
        print(text)
        if 'get' in text:
            print(log_filepath)
            self.upload_file(log_filepath, channel=channel)
            return
        # extract numbers from text
        numbers = [int(s) for s in text.split() if s.isdigit()]
        if len(numbers) > 0:
            number = numbers[0]
        else:
            number = 10
        # get log text
        with open(log_filepath) as f:
            lines = f.readlines()
        lines.reverse()
        num_lines = len(lines)
        if len(lines) < number:
            number = len(lines)
        lines = lines[:number]
        # send message
        list_string = self._make_list(lines)
        attachment = self._make_attachment(list_string) 
        self.send_message('here are the {0} most recent log items (out of {1})'.format(number, num_lines), channel, [attachment])
    
    def ls(self, text, channel):
        # extract numbers from text
        numbers = [int(s) for s in text.split() if s.isdigit()]
        if len(numbers) > 0:
            number = numbers[0]
        else:
            number = 10
        # get files
        folder_names = self._get_data_folders()
        if len(folder_names) == 0:
            self.send_message('PyCMDS currently has no data')
            return
        num_folders = len(folder_names)
        if len(folder_names) < number:
            number = len(folder_names)
        folder_names = folder_names[:number]
        # send message
        list_string = self._make_list(folder_names)
        attachment = self._make_attachment(list_string)
        self.send_message('here are the {0} most recent aquisitions (out of {1})'.format(number, num_folders), channel, [attachment])

    def make_attachment(self, text, title=None, pretext=None, fields=None, color='#808080'):
        attachment = {}
        if pretext is not None:
            attachment['pretext'] = pretext
        if fields is not None:
            attachment['fields'] = fields
        if title is not None:
            attachment['title'] = title
        attachment['color'] = color
        attachment['text'] = text
        attachment['mrkdwn_in'] = ['fields']
        return attachment
        
    def make_field(self, title, value, short=False):
        field = {}
        field['title'] = title
        field['value'] = value
        field['short'] = short
        return field

    def move(self, text, channel):
        self.send_message(':confounded: sorry, that feature hasn\'t been implemented')

    def poll(self):
        if not self.busy.read():
            self.q.push('get_messages', [60])
        self.read_messages()
            
    def read_messages(self):
        messages = messages_mutex.read()
        for message in messages:
            print('!!!', message)
            # only process messages
            if not 'type' in message.keys():
                continue
            if not message['type'] == 'message':
                continue        
            # unpack some things
            text = message['text']
            channel = message['channel']
            # only process messages that are posted in the appropriate channel
            if not channel == ini.read('bots', 'channel'):
                continue
            # only process messages that start with '@witch'
            if False: #not text.startswith('<@U0qEALA010>'):
                continue
            else:
                text = text.split(' ', 1)[1]
                print('message read from slack:', text)
            # process
            if 'echo ' in text.lower():
                out = text.split('echo ', 1)[1]
                message = ':mega: ' + out
                self.send_message(message, channel)
            elif 'get' == text[:3].lower():
                self.get(text, channel)
            elif 'status' in text.lower():
                self.status(text, channel)
            elif 'remove' in text.lower():
                self.remove(text, channel)
            elif 'move' in text.lower():
                self.move(text, channel)
            elif 'append' in text.lower():
                self.append(text, channel)
            elif 'interrupt' in text.lower():
                self.interrupt(text, channel)
            elif 'help' in text.lower():
                self.send_help(channel)
            else:
                self.send_message(':thinking_face: command \'{}\' not recognized - type \'help\' for a list of available commands'.format(text), channel)

    def remove(self, text, channel):
        self.send_message(':confounded: sorry, that feature hasn\'t been implemented')

    def send_help(self, channel):
        command_fields = []
        command_fields.append(self.make_field('status', 'Get the current status of PyCMDS.'))
        command_fields.append(self.make_field('get i', 'Get more information about the ith item in the queue.'))
        command_fields.append(self.make_field('remove i', 'Remove the ith item from the queue.'))
        command_fields.append(self.make_field('move i to j', 'Move item i to position j. All other items retain their order.'))
        command_fields.append(self.make_field('append [name] [info]', 'Append a file to the queue. Must be made as a comment of an attached file.'))
        command_fields.append(self.make_field('interrupt', 'Interrupt the queue.'))
        attachment = self.make_attachment('', fields=command_fields)
        self.send_message(':robot_face: here are my commands', channel, [attachment])

    def send_message(self, text, channel=None, attachments=[]):
        self.q.push('send_message', [text, channel, attachments])
        
    def status(self, text, channel):
        text, attachments = g.main_window.read().get_status()
        self.send_message(text, channel, attachments)
        
    def upload_file(self, file_path, title=None, first_comment=None, channel=None):
        self.q.push('upload_file', [file_path, title, first_comment, channel])

control = Control()
