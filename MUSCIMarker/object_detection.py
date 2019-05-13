"""This module implements a class that..."""
from __future__ import print_function, unicode_literals

from builtins import str
from builtins import object
import logging
import os
import pickle
import socket
import uuid

import numpy
import time
from kivy.properties import ObjectProperty, StringProperty, NumericProperty
from kivy.uix.widget import Widget

from muscima.io import parse_cropobject_list, export_cropobject_list

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


HOST = None   # TODO: replace by config values
PORT = 33555       # TODO: replace by config values


class ObjectDetectionHandler(Widget):
    """The ObjectDetectionHandler class is the interface between MUSCIMarker
    and its CropObjectAnnotatorModel and the ``mhr.omrapp`` client-server
    musical symbol detection setup."""
    input = ObjectProperty(None, allownone=True)
    '''The input of the remote OMR engine should be stored
    here to trigger detection call.'''

    input_bounding_box = ObjectProperty(None, allownone=True)
    '''Remembers the bounding box of the current input, so that
    the positions of detected CropObjects with respect to the input
    image can be derived from it.'''

    input_bounding_box_margin = ObjectProperty(None, allownone=True)
    '''Remembers the margin used for clearing detecction boundary
    artifacts. Also in the (t, l, b, r) format.'''

    result = ObjectProperty(None, allownone=True)
    '''The output of the remote OMR engine is stored here. An external
    method should be bound to this property. The result is a list
    of CropObjects.'''

    response_cropobjects = ObjectProperty(None, allownone=True)
    '''Intermediate storage for the CropObject list received from the server.'''

    tmp_dir = StringProperty()

    current_request = ObjectProperty(None, allownone=True)

    def __init__(self, tmp_dir, port=33555, hostname="127.0.0.1", **kwargs):
        super(ObjectDetectionHandler, self).__init__(**kwargs)

        self.tmp_dir = tmp_dir
        self.port = port

        # Load the symbol detection configuration:
        #  - target host
        #  - target port
        #  - temp directory for received raw data

    def on_input(self, instance, pos):
        if pos is not None:
            try:
                self.call(pos)
            except Exception as e:
                logging.warning('ObjectDetectionHandler: encountered error in call.'
                                ' Error message: {0}'.format(e))
                self.response_cropobjects = []

    def call(self, request):

        logging.info('ObjectDetectionHandler: Calling with input bounding box {0}'
                     ''.format(self.input_bounding_box))

        self.current_request = request

        # Format request for client
        #  (=pickle it, plus pickle-within-pickle for image array)
        f_request = self._format_request(request)

        _rstring = str(uuid.uuid4())
        temp_basename = 'MUSCIMarker.omrapp-request.' + _rstring + '.pkl'
        request_fname = os.path.join(self.tmp_dir, temp_basename)
        with open(request_fname, 'w') as fh:
            pickle.dump(f_request, fh, protocol=0)

        # Send to ObjectDetectionOMRAppClient
        # We didn't want to introduce "mhr" as a dependency,
        # so we wrote our own client for omrapp.

        response_basename = 'MUSCIMarker.omrapp-response.' + _rstring + '.xml'
        response_fname = os.path.join(self.tmp_dir, response_basename)

        client = ObjectDetectionOMRAppClient(host=HOST, port=self.port,
                                             request_file=request_fname,
                                             response_file=response_fname)
        client.call()
        #   ...this happens in ObjectDetectionOMRAppClient...
        # Open socket according to conf
        # Send request to server
        # Collect raw result
        # Close connection

        # Convert raw result (XML) to output representation (CropObjects)
        if not os.path.isfile(response_fname):
            raise OSError('ObjectDetectionHandler: Did not receive'
                          ' response file {0}'.format(response_fname))

        try:
            cropobjects = parse_cropobject_list(response_fname)
            print(export_cropobject_list(cropobjects))
            # Verify that result is valid (re-request on failure?)
            if os.path.isfile(response_fname):
                os.unlink(response_fname)

        except:
            logging.warn('ObjectDetectionHandler: Could not parse'
                         ' response file {0}'.format(response_fname))
            cropobjects = []
        # finally:
        #     # Cleanup files.
        #     logging.info('Cleaning up files.')
        #     if os.path.isfile(request_fname):
        #         os.unlink(request_fname)

        # Bind output representation to self.result to fire bindings
        #  - Subsequent processing means adding the CropObjects
        #    into the current annotation, in this case.
        #  - This can also trigger auto-parse.
        self.response_cropobjects = cropobjects

    def on_response_cropobjects(self, instance, pos):
        processed_cropobjects = self.postprocess_cropobjects(pos)
        self.result = processed_cropobjects

    def postprocess_cropobjects(self, cropobjects):
        """Handler-specific CropObject postprocessing. Can be configurable
        through MUSCIMarker settings."""
        filtered_cropobjects = filter_small_cropobjects(cropobjects)
        filtered_cropobjects = filter_thin_cropobjects(cropobjects)
        return filtered_cropobjects

    def reset(self):
        self.result = None
        self.input = None
        self.input_bounding_box = None
        self.current_request = None


    def _format_request(self, request):
        f_request = dict()
        for k in request:
            if k == 'image???':
                f_request[k] = self._format_request_image(request[k])
            else:
                f_request[k] = request[k]
        return f_request

    def _format_request_image(self, image):
        return numpy.ndarray.dumps(image)




class ObjectDetectionOMRAppClient(object):
    """Handles the client-side networking for object
    detection. Very lightweight -- only builds the socket,
    sends the request, receives the response and writes it
    to the file specified by ObjectDetectionHandler.

    Not a Kivy widget."""
    def __init__(self, host, port, request_file, response_file):
        self.host = host
        self.port = port
        self.request_file = request_file
        self.response_file = response_file

        self.BUFFER_SIZE = 256

    def call(self):
        logging.info('ObjectDetectionOMRAppClient.run(): starting')
        _start_time = time.clock()

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host = '127.0.0.1' # socket.gethostname()

        logging.info('ObjectDetectionOMRAppClient: connecting to host {0}, port {1}'
                     ''.format(host, self.port))
        s.connect((host, self.port))
        logging.info('ObjectDetectionOMRAppClient.run(): connected to'
                     ' host {0}, port {1}'.format(host, self.port))

        with open(self.request_file, 'rb') as fh:
            data = fh.read(self.BUFFER_SIZE)
            _n_data_packets_sent = 0
            while data:
                logging.info('ObjectDetectionOMRAppClient.run(): sending data,'
                             'iteration {0}'.format(_n_data_packets_sent))
                s.send(data)
                data = fh.read(self.BUFFER_SIZE)
                _n_data_packets_sent += 1

        # s.send(b"Hello server!")
        logging.info('Shutting down socket for writing...')
        s.shutdown(socket.SHUT_WR)

        logging.info('Finished sending, waiting to receive.')
        # Server does its thing now. We wait at s.recv()

        # TODO: Change this to StringIO...
        with open(self.response_file, 'wb') as f:
            _n_data_packets_received = 0
            logging.info('file opened: {0}'.format(self.response_file))
            while True:
                logging.info('ObjectDetectionOMRAppClient.run(): receiving data,'
                             'iteration {0}'.format(_n_data_packets_received))
                data = s.recv(self.BUFFER_SIZE)

                if not data:
                    break
                f.write(data)

                _n_data_packets_received += 1
        f.close()

        logging.info('Successfully got the file')

        s.close()
        logging.info('connection closed')

        del s

        _end_time = time.clock()
        logging.info('MUSCIMarker.ObjectDetectionOMRAppClient.run():'
                     ' done in {0:.3f} s'.format(_end_time - _start_time))


##############################################################################


def filter_small_cropobjects(cropobjects, threshold=20):
    return [c for c in cropobjects if c.mask.sum() > threshold]

def filter_thin_cropobjects(cropobjects, threshold=2):
    return [c for c in cropobjects if min(c.width, c.height) > threshold]

