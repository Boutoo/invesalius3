#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
#--------------------------------------------------------------------------

import queue
import threading
import time
import numpy as np
import wx

from invesalius import constants
from invesalius.pubsub import pub as Publisher
import invesalius.constants as const

class SerialPortConnection(threading.Thread):
    def __init__(self, com_port, baud_rate, serial_port_queue, event, sleep_nav):
        """
        Thread created to communicate using the serial port to interact with software during neuronavigation.
        """
        threading.Thread.__init__(self, name='Serial port')

        self.connection = None
        self.stylusplh = False

        self.com_port = com_port
        self.baud_rate = baud_rate
        self.serial_port_queue = serial_port_queue
        self.event = event
        self.sleep_nav = sleep_nav

        # Pulse Generator
        self.sending_signal = False

    def Connect(self):
        if self.com_port is None:
            print("Serial port init error: COM port is unset.")
            return
        try:
            import serial
            self.connection = serial.Serial(self.com_port, baudrate=self.baud_rate, timeout=0)
            print("Connection to port {} opened.".format(self.com_port))

            Publisher.sendMessage('Serial port connection', state=True)
        except:
            print("Serial port init error: Connecting to port {} failed.".format(self.com_port))

    def Disconnect(self):
        if self.connection:
            self.connection.close()
            print("Connection to port {} closed.".format(self.com_port))

            Publisher.sendMessage('Serial port connection', state=False)

    def SendPulse(self):
        try:
            self.connection.send_break(constants.PULSE_DURATION_IN_MILLISECONDS / 1000)
            self.connection.write(b'\x00')
            self.connection.write(b'\xff')
            Publisher.sendMessage('Serial port pulse triggered')
        except:
            print("Error: Serial port could not be written into.")

    def TogglePulseGenerator(self):
        const.PULSE_GENERATOR_ON = not const.PULSE_GENERATOR_ON
        if const.PULSE_GENERATOR_ON:
            # Start the pulse generator thread
            self.pulse_generator_thread = threading.Thread(target=self.PulseGenerator)
            self.pulse_generator_thread.daemon = True  # Daemonize the thread so it terminates when the main thread exits
            self.pulse_generator_thread.start()
            print("Pulse generator started.")
        else:
            # Terminate the pulse generator thread (if it's running)
            if hasattr(self, 'pulse_generator_thread') and self.pulse_generator_thread.is_alive():
                print("Stopping pulse generator.")
                self.pulse_generator_thread.join()  # Wait for the thread to terminate
            else:
                print("Pulse generator is not running.")

    def PulseGenerator(self):
        """Function to send signals every X to Y second through the COM port."""
        pulse_count = 0
        while const.PULSE_GENERATOR_ON:
            try:
                if self.connection:
                    if const.PERMISSION_TO_STIMULATE:
                        print(f"Sending pulse ({pulse_count})...")
                        self.connection.write(b'\x00')
                        self.connection.write(b'\xff')
                        pulse_count += 1
                        # Random between 2 and 3 seconds
                        random_time = np.random.uniform(2, 3)
                        print(f"Waiting for {random_time:.2f} seconds...")
                        time.sleep(random_time)
                    else:
                        print("Please, make sure that you are on target. (Or allow off target TMS).")
                else:
                    print("Error: Serial connection is not established.")
                    break
            except Exception as e:
                print(f"Error in PulseGenerator: {e}")
                break

    def run(self):
        while not self.event.is_set():
            trigger_on = False
            try:
                lines = self.connection.readlines()
                if lines:
                    trigger_on = True
            except:
                print("Error: Serial port could not be read.")

            if self.stylusplh:
                trigger_on = True
                self.stylusplh = False

            try:
                self.serial_port_queue.put_nowait(trigger_on)
            except queue.Full:
                print("Error: Serial port queue full.")

            time.sleep(self.sleep_nav)

            # XXX: This is needed here because the serial port queue has to be read
            #      at least as fast as it is written into, otherwise it will eventually
            #      become full. Reading is done in another thread, which has the same
            #      sleeping parameter sleep_nav between consecutive runs as this thread.
            #      However, a single run of that thread takes longer to finish than a
            #      single run of this thread, causing that thread to lag behind. Hence,
            #      the additional sleeping here to ensure that this thread lags behind the
            #      other thread and not the other way around. However, it would be nice to
            #      handle the timing dependencies between the threads in a more robust way.
            #
            time.sleep(0.3)
        else:
            self.Disconnect()
