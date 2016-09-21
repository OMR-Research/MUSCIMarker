#!/usr/bin/env python
"""This file implements the MUSCIMarker application for annotating
regions of music score images.

User guide
==========

The MUSCIMarker application is built for manually annotating musical symbols
and evaluating annotation results.

Requirements & Installation
---------------------------

It is multi-platform, built in pure Python using the Kivy framework.
Other than the requirements for Kivy (which is mostly just the SDL2 library),
it doesn't need anything outside our own ``mhr`` package (which defines
the import/export formats).

To run the app, just install Kivy and ``mhr`` and run ``python main.py``
in the app directory.


Features
---------

* Annotate musical scores with symbol locations and types.
* Automation for making annotation easier.

Tutorial
========

This section will walk you through the basic operations available
to you in MUSCIMarker.

Basic operations are done using the *Main menu*, located across the top
of the application. Various editing tools are available using the *Tool sidebar*
on the left; more actions, including those specific to individual tools,
are shown on the right, in the *Command sidebar*. The edited image then lies
in the middle, the *Editor*.

Inputs
------

Upon launching the app, three things need to be loaded:

* The image that should be annotated,
* The list of symbol classes,
* Optionally, a list of already annotated symbols for the given image.

The image will be represented in grayscale (single-channel).

Implementation
==============

We will follow a Model-View-Controller scheme. The annotation model
is implemented as a separate class, the ``CropObjectAnnotatorModel``.
It implements the annotation logic: what the annotator can do.

The App class ``MUSCIMarkerApp`` acts as the controller. It is responsible
for converting user actions into model objects and actions.

The Kivy Layouts/Widgets are the View(s).

X and Y
-------

There are unfortunately three different interpretations of what X and Y
means in the ecosystem of MUSCIMarker.

* The CropObject XML schema defines X as the **horizontal** dimension
  from the **left** and Y as the **vertical** dimension from the **top**.
* Numpy, and by extension OpenCV, defines X as the **vertical**  dimension
  from the **top** and Y as the **horizontal** dimension from the **left**.
* Kivy defines X as the **horizontal** dimension from the **left** and Y as
  the **vertical** dimension from the **bottom**.

This causes much wailing and gnashing of teeth.

Upon loading the CropObjects from the XML, the parsing function
``mhr.muscima.parse_cropobject_list()`` automatically swaps X and Y around
from the XML schema world into the Numpy world. Upon export, the
``CropObject.__str__()`` method again automatically swaps X and Y to export
the CropObject back to the XML schema world.

To get from the Numpy world to the Kivy world, two steps happen.
First, the :class:`CropObjectRenderer` class swaps the numpy-world vertical
dimension (top-down) into the Kivy-world vertical dimension (bottom-up).
Then, the :class:`CropObjectView` class swaps X and Y around in its
:meth:`__init__` method to swap the axes again.

When interpreting user input, the touch objects have X and Y in the Kivy
world: Y is the vertical dimension, X is horizontal. We try to deal with
this at the lowest possible level: when passing the user action "up" to
tool classes that handle processing, we convert everything
to top/left/bottom/right (if dealing with bounding boxes).

The CropObjects in the :class:`CropObjectAnnotatorModel` are always kept
in the Numpy world. There may be image processing operations associated
with the annotated objects model.

The CropObjectViews, on the other hand, are kept in the Kivy world,
as they are responsible for visualizing the model. (The Views do not
have X, Y, width and height; they have - being in essence
ToggleButtons - `size` and `pos`, just like any other Kivy widget.)

Note that while X and Y needs to be transposed in various ways during
the journey of a CropObject from XML file to visualization and back,
the interpretation of the ``width`` and ``height`` parameters
*does not change*.

Scaling
-------

Another grief-inducing hitch is the relationship between position input
in the scalable editor widget and the coordinates of the original image.

"""
from __future__ import print_function, unicode_literals
import argparse
import codecs
import logging
import os
import time
# from random import random
# from math import sqrt

import cPickle
import cv2

from kivy._event import EventDispatcher
from kivy.app import App
from kivy.config import Config
from kivy.properties import ObjectProperty, StringProperty, ListProperty, NumericProperty, DictProperty, AliasProperty
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget

import muscimarker_io

from editor import BoundingBoxTracer
from rendering import CropObjectRenderer
from utils import FileNameLoader, FileSaver, ImageToModelScaler
from annotator_model import CropObjectAnnotatorModel
import toolkit

import kivy


kivy.require('1.9.1')

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


class MUSCIMarkerLayout(GridLayout):
    pass


##############################################################################
# !!! This should be implemented using an Adapter. Use cls template-based
# view instantiation.


def cropobject_as_bbox_converter(row_index, rec):
    output = {
        'cropobject': rec
    }
    return output


# class CropObjectView(RelativeLayout):
#     """This widget is the visual representation of a CropObject."""
#     # Add ButtonBehaivor, SelectableItemBehavior mixins?
#     bottom = NumericProperty()
#     left = NumericProperty()
#     width = NumericProperty()
#     height = NumericProperty()
#
#     color = ObjectProperty()

##############################################################################


class MUSCIMarkerApp(App):
    """The App serves as the controller here. It responds
    to user actions and updates the model accordingly.

    Supported features
    ------------------

    **Minimum**

    * Load image (File choosng dialogue) (DONE)
    * Load MLClassList (File choosing dialogue) (DONE)
    * Load CropObjectList (File choosing dialogue) (DONE)
    * Set export file (TextInput) (DONE)
    * Export CropObjectList (Button) (DONE)
    * Select current default annotation class (Spinner?) (DONE)
    * Annotate (DONE)
        * Create annotation (DONE)
        * Activate annotation (DONE)
            * New: Draw bounding box (This is non-trivial! Should
              be split into two commands, add annotation and
              edit bounding box.) (DONE)
            * Old: click on the bounding box, use arrows (DONE)
        * Deactivate annotation (DONE)
        * Assign class to active annotation (DONE)
        * Record active annotation (Deferred to CropObjectList export)
        * Delete active annotation (DONE)
        * Edit bounding box of active annotation (DONE)
    * Viewing the image: zoom and move (the annotations
      should move together, of course).  (DONE)
    * Annotation mode vs. viewing-only mode (DONE)
        * This means the interface is stateful. User actions
          are interpreted based on the current state.

    **Important**

    * Undo
    * ConnectedComponentSelect: click to select the connected component. (DONE)
    * Select a subset of classes to view
    * Warn on overwrite export file

    **Nice-to-have**

    * CropObject splitting and merging. (DONE)
    * Be aware of MUSCIMA (Design decision: NO, so far)
    * Pre-annotation (classifier of bounding boxes)

    Interface statefulness
    ----------------------

    The state of the interface is how it will respond to user actions:
    which operations are available and how to request them.
    The state graph (currently tree) is as follows:

    * View (V)
    * Annotate (A)
        * No annotation is active (A+)
        * Have annotation active (A-)

    Note that each annotation tool (such as click-to-select-component)
    is in itself also an interface state. For instance, this would
    redefine what a click in A- state means: instead of selecting
    an existing annotation or nothing (if not inside annotation),
    it means "Create annotation, activate annotation, set its
    bounding box to the bounding box of the connected component
    of the image where the click occurred". Or in the normal mode,
    press+drag+release means "Create annotation, activate annotation,
    set its bounding box to the rectangle delimited by press & release
    points. There is a mini-state graph inside that mode.

    The ability to re-interpret actions clearly requires some
    background mechanism. The Views that are stateful have to
    pass the action to the controller before interpreting it
    in any way: essentially, each stateful Widget has to define
    callbacks to the controller, which is aware of the state and can
    take appropriate action.

    The state, then, is the definition of how to respond within
    the callbacks. The cycle then seems to be::

        UI action --> callback -->
        --> get controller/model actions for given UI action from current mode
        --> apply controller/model actions --> ...

    Note that some parts of the interface might be simplified by assuming
    they always work the same way (such as exporting the current CropObjects,
    or loading a MLClassList -- however, one has to be careful for all
    actions that are not read-only on the model, as it may require some
    stateful controller action such as mode transition. (If you change the
    MLClassList, it's a big deal -- all the current annotations cease
    to be valid, you need to export them, etc. Same thing with image change.)

    A way of implementing modes might be mode inhertance...

    Note that modes are in essence a Finite-State Automaton.


    Model statefulness
    ------------------

    The annotator model also has different states -- corresponding
    to its data (which image is being annotated, what MLClassList
    is being used and the current CropObjects).


    Visualizing the CropObjects
    ----------------------------

    We want to see the annotated objects, each as a colored semi-transparent
    bounding box. The chain from an annotation object to the visual representation:

    CropObject -(A)-> SelectableCropObject -(B)-> CropObjectView

    **B** The conversion from a selectable CropObject to the View (the visible
    rectangle) is done through a DictAdapter. The output widget is then "posted"
    upon a separate RelativeLayout that is overlaid over the edited image.

    We want the entire chain to be event-driven: listen to the model's
    ``cropobject_list``, maintain a dictionary of SelectableCropObjects
    (at this point, we need access to the editor widget's dimensions, because
    the vertical (X) position of the CropObject is represented from top-left,
    but Kivy needs it from bottom-left), then adapt the dictionary of these
    intermediate-stage SelectableCropObject data items into CropObjectView(s).

    The facilities for this process are wrapped into the CropObjectRenderer
    at the app level.

    Keyboard shortcuts
    ------------------

    To use keyboard shortcuts from widgets, define on_key_down() and
    on_key_up() callbacks and bind them to the Window.on_key_up() and
    Window.on_key_down() events. If you don't want the key press events
    bubbling up from your widget, add ``return True`` to the callbacks,
    as you would with any other event type.

    The modifiers for writing keyboard shortcuts are:

    * ``meta`` for Cmd,
    * ``ctrl`` for lctrl,
    * ``alt`` for alt (307) and alt-gr (308),
    * ``shift`` for shift

    Note that the modifiers do *not* get sent in on_key_up events.
    Avoid using ``meta`` for compatibility with non-Apple keyboards,
    or duplicate all ``meta`` commands with ``ctrl``-based ones.

    """

    annot_model = CropObjectAnnotatorModel()

    currently_selected_tool_name = StringProperty('_default')
    tool = ObjectProperty()

    currently_selected_mlclass_name = StringProperty()

    # Some placeholder default image...
    image_loader = ObjectProperty(FileNameLoader())
    currently_edited_image_filename = StringProperty(os.path.join(
        os.path.dirname(__file__),
        'static',
        'OMR-RG_logo_darkbackground.png'))

    current_image_height = NumericProperty()
    image_height_ratio_in = NumericProperty()
    '''The ratio between the loaded image height and the original image size.
    Used on import/export of CropObjectList to interface between displayed
    CropObject bounding boxes and the exports, which need to be aligned
    to the image file.

    However, real-time recomputing is also wrong, because the coordinates
    do get recomputed inside the ScatterLayout in which the Image lives.
    The coordinates of added CropObjects are therefore always kept in relation
    to the size of the image when it is first displayed.

    This number specifically defines the scaling upon CropOpbject *import*.
    For exporting, use 1 / image_height_ratio_in.
    '''

    image_scaler = ObjectProperty()
    '''Experimental: making scaling more principled. (Taken from MMBrowser.)'''

    current_image_width = NumericProperty()
    image_width_ratio_in = NumericProperty()
    '''Dtto for image width.'''

    editor_scale = NumericProperty(1.0)
    '''Broadcasting the editor scale.'''

    mlclass_list_loader = ObjectProperty(FileNameLoader())
    '''Handler for reloading the MLClassList definition.'''

    mlclass_list_length = NumericProperty(0)
    '''Current number of MLClasses. Not essential.'''

    cropobject_list_loader = ObjectProperty(FileNameLoader())
    '''Handler for reloading the CropObjectList definition.'''

    # Set overwriting to False for production.
    cropobject_list_saver = ObjectProperty(FileSaver(overwrite=True))

    cropobject_list_renderer = ObjectProperty()
    '''The renderer is responsible for showing the current state
    of the annotation as (semi-)transparent bounding boxes overlaid
    over the editor image.'''

    #######################################
    # In-app messages (not working yet)
    message = ObjectProperty(None)

    #######################################
    # Keyboard shortcuts (at the app level, there are none so far
    # and keyboard shortcut handling is pretty decentralized & not
    # great)
    keyboard_dispatch = DictProperty(None)
    '''
    '''

    #######################################
    # App build & config methods

    def build(self):

        # Define bindings for compartmentalized portions of the application
        self.mlclass_list_loader.bind(filename=self.import_mlclass_list)
        self.image_loader.bind(filename=self.import_image)
        self.cropobject_list_loader.bind(filename=self.import_cropobject_list)

        # Resuming annotation from previous state
        conf = self.config
        logging.info('Current configuration: {0}'.format(str(conf)))
        self.image_loader.filename = conf.get('current_input_files',
                                              'image_file')
        logging.info('Build: Loaded image fname from config: {0}'
                     ''.format(self.image_loader.filename))

        # Rendering CropObjects
        self.cropobject_list_renderer = CropObjectRenderer(
            annot_model=self.annot_model,
            editor_widget=self._get_editor_widget())
        e = self._get_editor_widget()
        logging.info('Build: Adding renderer to editor widget {0}'
                     ''.format(e))
        e.add_widget(self.cropobject_list_renderer)
        Window.bind(on_resize=self.window_resized)

        # Editor scale broadcasting
        e_scatter = self._get_editor_scatter_container_widget()
        e_scatter.bind(scale=self.setter('editor_scale'))

        logging.info('Build: Started loading mlclasses from config')
        self.mlclass_list_loader.filename = conf.get('current_input_files',
                                                     'mlclass_list_file')
        logging.info('Build: Loaded mlclass list fname from config: {0}'
                     ''.format(self.mlclass_list_loader.filename))

        logging.info('Build: Started loading cropobjects from config')
        self.cropobject_list_loader.filename = conf.get('current_input_files',
                                                        'cropobject_list_file')
        logging.info('Build: Finished loading cropobject list fname from config: {0}'
                     ''.format(self.cropobject_list_loader.filename))

        saver_output_path = self.cropobject_list_loader.filename
        logging.info('Build: Setting default export dir to the cropobject list dir: {0}'
                     ''.format(saver_output_path))
        self.cropobject_list_saver.last_output_path = saver_output_path

        # self.cropobject_list_loader.bind(filename=self.cropobject_list_renderer.clear)
        self.mlclass_list_loader.bind(filename=self.cropobject_list_renderer.clear)
        self.image_loader.bind(filename=self.cropobject_list_renderer.clear)

        # Keyboard control
        # self._keyboard = Window.request_keyboard(self._keyboard_close, self.root)
        # self._keyboard.bind(on_key_down=self._on_key_down)
        # self._keyboard.bind(on_key_up=self._on_key_up)

        Window.bind(on_key_down=self.on_key_down)
        Window.bind(on_key_up=self.on_key_up)

        # Finally, swap around order of tool selection sidebar & editor cell.
        main_area = self.root.ids['main_area']
        logging.info('App: main area children: {0}'.format(main_area.children))
        command_sidebar, editor_window, tool_sidebar = main_area.children
        main_area.remove_widget(tool_sidebar)
        main_area.add_widget(tool_sidebar)
        logging.info('App: main area children: {0}'.format(main_area.children))

        # Attempt recovery
        attempt_recovery = conf.get('recovery', 'attempt_recovery_on_build')
        if attempt_recovery:
            logging.info('App.build: Requested an attempt to recover last application'
                         ' state at build time.')
            self.do_recovery()

        recovery_dump_freq = int(conf.get('recovery', 'recovery_dump_frequency_seconds'))
        if recovery_dump_freq is not None:
            logging.info('App.build: Got recovery dump frequency {0}'
                         ''.format(recovery_dump_freq))
            if recovery_dump_freq < 2:
                logging.info('Making a recovery dump every less than 2 seconds'
                             ' is not sensible. Setting to the default 5.')
                recovery_dump_freq = 5
            logging.info('App.build: Scheduling recovery every {0} seconds'
                         ''.format(recovery_dump_freq))
            Clock.schedule_interval(self.do_save_app_state_clock_event,
                                    recovery_dump_freq)

    def build_config(self, config):
        config.setdefaults('kivy',
            {
                'exit_on_escape': 0,
            })
        config.setdefaults('graphics',
            {
                'fullscreen': '1',
            })
        config.setdefaults('current_input_files',
            {
                'mlclass_list_file': 'data/mff-muscima-mlclasses-primitives.xml',
                'cropobject_list_file': 'test_data/empty_cropobject_list.xml',
                'image_file': os.path.join(os.path.dirname(__file__), 'static',
                                           'OMR-RG_logo_darkbackground.png'),
            })
        config.setdefaults('default_input_files',
            {
                'mlclass_list_file': 'data/mff-muscima-mlclasses-primitives.xml',
                'cropobject_list_file': 'test_data/empty_cropobject_list.xml',
                'image_file': os.path.join(os.path.dirname(__file__), 'static',
                                           'OMR-RG_logo_darkbackground.png'),
            })
        config.setdefaults('recovery',
            {
                'recovery_dir': os.path.join(os.path.dirname(__file__), 'recovery'),
                'recovery_filename': 'MUSCIMarker_state.pkl',
                'attempt_recovery_on_build': True,
                'attempt_recovery_dump_on_exit': True,
                'recovery_dump_frequency_seconds': 5,
            })
        config.setdefaults('toolkit',
            {
                'cropobject_mask_nonzero_only': True,
                # If set, will automatically restrict all masks to nonzero
                # pixels of the input image only.
            })
        Config.set('kivy', 'exit_on_escape', '0')

    def build_settings(self, settings):
        with open(os.path.join(os.path.dirname(__file__), 'muscimarker_config.json')) as hdl:
            jsondata = hdl.read()
        settings.add_json_panel('MUSCIMarker',
                                self.config, data=jsondata)

    #######################################
    # Functions for recovering work from crashes, inadvertent shutdowns, etc.
    # Don't call these directly!

    # TODO: refactor recovery as a separate class.
    def _get_recovery_path(self):
        conf = self.config
        recovery_dir = conf.get('recovery', 'recovery_dir')
        recovery_fname = conf.get('recovery', 'recovery_filename')
        recovery_path = os.path.join(recovery_dir, recovery_fname)
        return recovery_path

    def _get_app_state(self):
        state = {
            # Need the image filename to force reloading, so that all scalers
            # are set correctly.
            'image_filename': self.image_loader.filename,
            # MLClasses are a part of the model, but we need to keep the trigger
            # properties in a consistent state.
            'mlclass_list_filename': self.mlclass_list_loader.filename,
            # Cropobjects are a part of the model, but we need the filename
            # again for internal consistency (it is used e.g. in suggesting
            # an export path).
            'cropobject_list_filename': self.cropobject_list_loader.filename,
            # We'll use the model to get the list of current CropObjects.
            # The cropobjects member of annot_model is a kivy Property,
            # so it fails on pickle -- we must get the data itself
            # by different means.
            'cropobjects': self.annot_model.cropobjects.values(),
        }
        return state

    def _build_from_app_state(self, state):
        """This function actually sets the app into a consistent state
        corresponding to the recovered state.

        In case of failure, it will try to revert any changes made and
        not kill the application. If there is an exception thrown during
        reverting, it will kill the application, though, because that means
        it was in an inconsistent state before recovery even started."""
        logging.info('App._build_from_state: starting')
        cropobjects = state['cropobjects']
        logging.info('Cropobjects {0}'.format(cropobjects))
        mlclass_list_filename = state['mlclass_list_filename']
        image_filename = state['image_filename']
        cropobject_list_filename = state['cropobject_list_filename']

        fail = False
        if not os.path.isfile(mlclass_list_filename):
            logging.warn('App._build_from_app_state: MLClassList {0}'
                         ' does not exist!'.format(mlclass_list_filename))
            fail = True
        if not os.path.isfile(cropobject_list_filename):
            logging.warn('App._build_from_app_state: CropObjectList {0}'
                         ' does not exist!'.format(cropobject_list_filename))
            fail = True
        if not os.path.isfile(image_filename):
            logging.warn('App._build_from_app_state: Image {0}'
                         ' does not exist!'.format(image_filename))
            fail = True
        if fail:
            logging.warn('App._build_from_app_state: could not recover'
                         ' due to missing files.')

        # Trigger MLClass list loading
        logging.info('App._build_from_app_state: Loading MLClasses: {0}'
                     ''.format(mlclass_list_filename))
        # Generically error-resistant loading: ignores errors, tries to revert
        # (but app state may be damaged, so revert might not be possible)
        _old_mlclasslist_filename = self.mlclass_list_loader.filename
        try:
            self.mlclass_list_loader.filename = mlclass_list_filename
        except:
            logging.warn('App._build_from_app_state: Loading MLClasses {0}'
                         ' failed, reverting to old.'
                         ''.format(mlclass_list_filename))
            self.mlclass_list_loader.filename = _old_mlclasslist_filename
            logging.warn('App._build_from_app_state: Recovery failed.')
            # Once we reach an error, we need to get out ASAP.
            return

        # Trigger image loading. Should set all the scaling as well.
        logging.info('App._build_from_app_state: Loading image: {0}'
                     ''.format(image_filename))
        _old_image_filename = self.image_loader.filename
        try:
            self.image_loader.filename = image_filename
        except:
            logging.warn('App._build_from_app_state: Loading Image {0}'
                         ' failed, reverting to old.'
                         ''.format(image_filename))
            # We don't want to stop recovery and not revert the already
            # updated MLClasses
            self.mlclass_list_loader.filename = _old_mlclasslist_filename
            self.image_loader.filename = _old_image_filename
            logging.warn('App._build_from_app_state: Recovery failed.')
            return

        # Trigger CropObjectList loading (but this is irrelevant it's just
        # going through the motions to make sure that there is a consistent
        # CropObjectList filename. After loading, we then replace the CropObjects
        # replace it by the model's CropObjects instead - clear it and replace
        # with saved CropObjects).
        logging.info('App._build_from_app_state: Dummy-loading CropObjectList: {0}'
                     ''.format(cropobject_list_filename))
        _old_cropobject_list_filename = self.cropobject_list_loader.filename
        try:
            self.cropobject_list_loader.filename = cropobject_list_filename
        except:
            logging.warn('App._build_from_app_state: Loading CropObjectList {0}'
                         ' failed, reverting to old.'
                         ''.format(cropobject_list_filename))
            # Dtto: reverting changes in case of failure. (This may itself fail,
            # but if reverting fails, there is a serious problem and it should
            # all fail.)
            self.cropobject_list_loader.filename = _old_cropobject_list_filename
            self.mlclass_list_loader.filename = _old_mlclasslist_filename
            self.image_loader.filename = _old_image_filename
            logging.warn('App._build_from_app_state: Recovery failed.')
            return

        # If we get to this point, there should not be a problem.

        # Building the CropObjects from the model:
        logging.info('App._build_from_app_state: Replacing file-based CropObjects'
                     ' with CropObjects loaded from the model in the app state.')
        logging.info('App._build_from_app_state: no. of CropObjects: from file:'
                     ' {0}, from state: {1}'.format(len(self.annot_model.cropobjects),
                                                    len(cropobjects)))
        self.annot_model.clear_cropobjects()
        # This should trigger a redraw.
        self.annot_model.import_cropobjects(cropobjects)

        logging.info('App._build_from_state: Finished successfully.')

    def _save_app_state(self):
        recovery_path = self._get_recovery_path()
        logging.info('App.recover: Saving recovery file {0}'.format(recovery_path))

        state = self._get_app_state()

        # Cautious behavior: let's try not to destroy the previous
        # backup until we are sure the backup has been made correctly.
        rec_temp_name = recovery_path + '.temp'
        logging.info('App.save_app_state: Saving to recovery file {0}'
                     ''.format(recovery_path))
        try:
            with open(rec_temp_name, 'wb') as hdl:
                cPickle.dump(state, hdl, protocol=cPickle.HIGHEST_PROTOCOL)
        except:
            logging.warn('App.save_app_state: Saving to recovery file failed.')
            if os.path.isfile(rec_temp_name):
                os.remove(rec_temp_name)
            return

        if os.path.isfile(recovery_path):
            os.remove(recovery_path)
        os.rename(rec_temp_name, recovery_path)

    def _recover(self):
        recovery_path = self._get_recovery_path()
        logging.info('App.recover: Loading recovery file {0}'.format(recovery_path))
        if not os.path.exists(recovery_path):
            logging.warn('App.recover: Recovery file {0} not found! '
                         'No recovery will be performed.'.format(recovery_path))
            return

        try:
            with open(recovery_path, 'rb') as hdl:
                state = cPickle.load(hdl)
        except cPickle.PickleError:
            logging.warn('App.recover: Recovery failed! Resuming without recovery.')
            return

        logging.info('App.recover: loaded state, rebuilding from state.')
        self._build_from_app_state(state=state)

    # These functions are the public interface to the recovery manager.
    def do_save_app_state(self):
        """Use this method to invoke recovery state dump.
        So far, it is trivial, but there may be some more complex
        logic & validation here later on."""
        self._save_app_state()

    def do_recovery(self):
        """Use this method to invoke recovery.
        So far, it is trivial, but there may be some more complex
        logic & validation here later on."""
        self._recover()

    def do_save_app_state_clock_event(self, *args):
        logging.info('App: making scheduled recovery dump.')
        self.do_save_app_state()
        logging.info('App: scheduled recovery dump done.')

    #######################################
    # Keyboard control
    def _keyboard_close(self):
        self._keyboard.unbind(on_key_down=self.on_key_down,
                              on_key_up=self.on_key_up)
        self._keyboard = None

    def on_key_down(self, window, key, scancode, codepoint, modifier):
        logging.info('Keyboard: Down {0}'.format((key, scancode, codepoint, modifier)))

    def on_key_up(self, window, key, scancode):
        logging.info('Keyboard: Up {0}'.format((key, scancode)))

    #######################################
    # Importing methods: interfacing the raw data to the model

    def import_mlclass_list(self, instance, pos):
        try:
            mlclass_list = muscimarker_io.parse_mlclass_list(pos)
        except:
            logging.info('App: Loading MLClassList from file \'{0}\' failed.'
                         ''.format(pos))
            return

        logging.info('App: === Reloading mlclass list from app fired. List has {0} items.'
                     ''.format(len(mlclass_list)))
        self.mlclass_list_length = len(mlclass_list)
        self.annot_model.import_classes_definition(mlclass_list)

        self.currently_selected_mlclass_name = self.annot_model.mlclasses.values()[0].name

    def import_cropobject_list(self, instance, pos):
        logging.info('App: === Reloading CropObjectList fired with file \'{0}\''
                     ''.format(pos))
        try:
            cropobject_list, mfile, ifile = muscimarker_io.parse_cropobject_list(pos,
                                                                                 with_refs=True,
                                                                                 tolerate_ref_absence=True)

            # Handling MLClassList and Image conflicts. Currently just warns.
            if mfile is not None:
                if mfile != self.mlclass_list_loader.filename:
                    logging.warn('Loaded CropObjectList for different MLClassList ({0}),'
                                 ' colors are off and any annotation entered is invalid!'
                                 ''.format(mfile))
            if ifile is not None:
                if ifile != self.image_loader.filename:
                    logging.warn('Loaded CropObjectList for different image file ({0}),'
                                 ' colors are off and any annotation entered is invalid!'
                                 ''.format(ifile))
        except:
            logging.info('App: Loading CropObjectList from file \'{0}\' failed.'
                         ''.format(pos))
            raise
            #return

        logging.info('App: Imported CropObjectList has {0} items.'
                     ''.format(len(cropobject_list)))
        # self.current_n_cropobjects = len(cropobject_list)
        self.annot_model.import_cropobjects(cropobject_list)

    def import_image(self, instance, pos):
        logging.info('App: === Got image file: {0}'.format(pos))
        try:
            # img = bb.load_rgb(pos)
            img = cv2.imread(pos)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # img = bb.load_grayscale(pos)
        except:
            logging.info('App: Loading image from file \'{0}\' failed.'
                         ''.format(pos))
            return

        self.annot_model.clear_cropobjects()
        self.annot_model.load_image(img)

        # Only change the displayed image after annotation.
        self.currently_edited_image_filename = pos

        # compute scale
        self.current_image_height = img.shape[0]
        self.current_image_width = img.shape[1]
        editor = self._get_editor_widget()
        editor_height = float(editor.height)
        editor_width = float(editor.width)
        self.image_height_ratio_in = editor_height / self.current_image_height
        self.image_width_ratio_in = editor_width / self.current_image_width

        self.image_scaler = ImageToModelScaler(self._get_editor_widget(),
                                               self.annot_model.image)

    ##########################################################################
    # Resizing
    def window_resized(self, instance, width, height):
        logging.info('App: Window resize to: {0}'.format((width, height)))
        e = self._get_editor_widget()
        self.image_height_ratio_in = float(e.height) / self.current_image_height
        self.image_width_ratio_in = float(e.width) / self.current_image_width

    ##########################################################################
    # Interfacing editor actions to the model,
    def map_point_from_editor_to_model(self, editor_x, editor_y):
        """Recomputes coordinates of an (Xe, Ye) point from editor coords
        (where X is horizontal from left, Y is vertical from bottom) to model
        (Xm, Ym) coords (where X is vertical from top, Y is horizontal from left)."""
        e_vertical = float(editor_y)
        e_horizontal = float(editor_x)

        e_vertical_inverted = self._get_editor_widget().height - e_vertical
        m_vertical = e_vertical_inverted / self.image_height_ratio_in

        m_horizontal = e_horizontal / self.image_width_ratio_in

        return m_vertical, m_horizontal

    def generate_cropobject_from_selection(self, selection, clsid=None, mask=None,
                                           integer_bounds=True):
        """After a selection is made, create the new CropObject.
        (To add it to the model, use add_cropobject_from_selection() instead.)

        Recomputes the X, Y and sizes back to the Numpy world & original image
        size.

        :param selection: A dict with the members `top`, `left`, `bottom` and `right`.
            These coordinates are assumed to be in the Kivy world.

        :param mask: Model-world mask to apply to the CropObject.

        :param integer_bounds: Whether the created CropObject should be scaled
            to integer bounds.

        """
        logging.info('App: Generating cropobject from selection {0}'.format(selection))
        # The current CropObject definition is weird this way...
        # x, y is the top-left corner, X is horizontal, Y is vertical.
        # Kivy counts position from bottom left, while CropObjects count them
        # from top left. So we need to invert the Y dimension.
        # Plus, for Kivy, X is vertical and Y is horizontal.
        # (To add to the confusion, numpy indexes from top-left and uses X
        # for rows, Y for columns.)
        new_cropobject_objid = self.annot_model.get_next_cropobject_id()
        new_cropobject_clsid = clsid
        if clsid is None:
            new_cropobject_clsid = self.annot_model.mlclasses_by_name[self.currently_selected_mlclass_name].clsid

        # (The scaling from model-world to editor should be refactored out:
        #  working on utils/ImageToModelScaler)
        # Another problem: CropObjects that get recorded in the model should have
        # dimensions w.r.t. the image, not the editor. So, we need to resize them
        # first to the original ratios...
        x_unscaled = float(selection['top'])
        x_unscaled_inverted = self._get_editor_widget().height - x_unscaled
        x_scaled_inverted = float(x_unscaled_inverted / self.image_height_ratio_in)
        y_unscaled = float(selection['left'])
        y_scaled = float(y_unscaled / self.image_width_ratio_in)

        height_unscaled = float(selection['top'] - selection['bottom'])
        height_scaled = float(height_unscaled / self.image_height_ratio_in)
        width_unscaled = float(selection['right'] - selection['left'])
        width_scaled = float(width_unscaled / self.image_width_ratio_in)

        # Try scaler
        mT, mL, mB, mR = self.image_scaler.bbox_widget2model(selection['top'],
                                                             selection['left'],
                                                             selection['bottom'],
                                                             selection['right'])
        mH = mB - mT
        mW = mR - mL
        logging.info('App.scaler: Scaler would generate numpy-world'
                     ' x={0}, y={1}, h={2}, w={3}'.format(mT, mL, mH, mW))

        c = muscimarker_io.CropObject(objid=new_cropobject_objid,
                                      clsid=new_cropobject_clsid,
                                      # Hah -- here, having the Image as the parent widget
                          # of the bbox selection tool is kind of useful...
                          x=x_scaled_inverted,
                                      y=y_scaled,
                                      width=width_scaled,
                                      height=height_scaled,
                                      mask=mask)
        if integer_bounds:
            c.to_integer_bounds()
        logging.info('App: Generated cropobject from selection {0} -- properties: {1}'
                     ''.format(selection, {'objid': c.objid,
                                           'clsid': c.clsid,
                                           'x': c.x, 'y': c.y,
                                           'width': c.width,
                                           'height': c.height}))
        return c

    def generate_cropobject_from_model_selection(self, selection, clsid=None, mask=None,
                                                 integer_bounds=True):
        """After a selection is made **in the model world**, create the new CropObject.
        (To add it to the model, use add_cropobject_from_model_selection() instead.)

        :param selection: A dict with the members `top`, `left`, `bottom` and `right`.
            These coordinates are assumed to be in the model/numpy world.

        :param mask: Model-world mask to apply to the CropObject.

        :param integer_bounds: Whether the created CropObject should be scaled
            to integer bounds.
        """
        logging.info('App: Generating cropobject from model selection {0}'.format(selection))
        new_cropobject_objid = self.annot_model.get_next_cropobject_id()
        new_cropobject_clsid = clsid
        if clsid is None:
            new_cropobject_clsid = self.annot_model.mlclasses_by_name[self.currently_selected_mlclass_name].clsid
        mT, mL, mB, mR = selection['top'], selection['left'],\
                         selection['bottom'], selection['right']
        mH = mB - mT
        mW = mR - mL

        c = muscimarker_io.CropObject(objid=new_cropobject_objid,
                                      clsid=new_cropobject_clsid,
                                      x=mT, y=mL, width=mW, height=mH,
                                      mask=mask)
        if integer_bounds:
            c.to_integer_bounds()
        logging.info('App: Generated cropobject from selection {0} -- properties: {1}'
                     ''.format(selection, {'objid': c.objid,
                                           'clsid': c.clsid,
                                           'x': c.x, 'y': c.y,
                                           'width': c.width,
                                           'height': c.height}))
        return c

    def add_cropobject_from_selection(self, selection, clsid=None, mask=None):
        logging.info('App: Will add cropobject from selection {0}'.format(selection))
        c = self.generate_cropobject_from_selection(selection,
                                                    clsid=clsid,
                                                    mask=mask)
        logging.info('App: Adding cropobject from selection {0}'.format(selection))
        self.annot_model.add_cropobject(c)  # This should trigger rendering
        # self.current_n_cropobjects = len(self.annot_model.cropobjects)

    def add_cropobject_from_model_selection(self, selection, clsid=None, mask=None):
        logging.info('App: Will add cropobject from model_selection {0}'.format(selection))
        c = self.generate_cropobject_from_model_selection(selection,
                                                          clsid=clsid,
                                                          mask=mask)
        logging.info('App: Adding cropobject from model_selection {0}'.format(selection))
        self.annot_model.add_cropobject(c)  # This should trigger rendering

    def generate_model_bbox_from_selection(self, selection):
        c = self.generate_cropobject_from_selection(selection, clsid=None)
        t, l, b, r = c.bounding_box
        return t, l, b, r

    ##########################################################################
    # Tool selection
    def process_tool_selection(self, tool_selection_button):
        """Sets the variable that contains the tool name. This could be even
        handled directly in the *.kv file, because everything else is being
        done in the method triggered by changing the requested tool.
        """
        logging.info('App.process_tool_selection: Got tool selection signal: {0}'
                     ''.format(tool_selection_button.name))

        # Unselecting the current tool instead of selecting a new one
        if self.currently_selected_tool_name == tool_selection_button.name:
            self.tool.deactivate()
            self.currently_selected_tool_name = '_default'
        else:
            self.currently_selected_tool_name = tool_selection_button.name

    def on_currently_selected_tool_name(self, instance, pos):
        """This does the "heavy lifting" of deactivating the old tool
        and activating the new one."""
        try:
            logging.info('App.on_currently_selected_tool: Deactivating current tool: {0}'
                         ''.format(self.tool))
            self.tool.deactivate()
            logging.info('App.on_currently_selected_tool: ...success!')
        except AttributeError:
            logging.info('App.on_currently_selected_tool: Failed on AttributeError, assuming tool was None.')
            pass

        if pos == '_default':
            logging.info('App.on_currently_selected_tool: Selected _default, no tool'
                         ' will be active.')
            return

        # The tool is a controller...
        tool = toolkit.tool_dispatch[pos](app=self,
                                          editor_widget=self._get_editor_widget(),
                                          command_widget=self._get_tool_command_palette())
        # Tools need information about app state to initialize themselves correctly.
        # The tool will attach them to the editor widget.
        tool.init_editor_widgets()
        # The tool can also export some commands (like 'clear everything').
        # It gets space on the bottom right of the command sidebar.
        tool.init_command_palette()
        # Finally, the tool can define some keyboard shortcuts.
        tool.init_keyboard_shortcuts()

        self.tool = tool
        logging.info('App.on_currently_selected_tool: Loaded tool: {0}'.format(pos))

    ##########################################################################
    # For routing requests from other widgets to the editor & commands
    # (primarily for tools & rendering):
    def _get_editor_widget(self):
        # Should change to just 'editor', so that tool changes don't happen
        # in the Image itself.
        return self.root.ids['editor_cell'].ids['editor'].ids['edited_image']

    def _get_editor_scatter_container_widget(self):
        return self.root.ids['editor_cell'].ids['editor']

    def _sync_editor_scale_with_editor_scatter_container(self, instance, pos):
        self.editor_scale = pos

    def _get_tool_command_palette(self):
        return self.root.ids['command_sidebar'].ids['command_palette']

    def _get_tool_info_palette(self):
        return self.root.ids['command_sidebar'].ids['info_panel']


    ##########################################################################
    # Cleanup.
    def exit(self):
        # Record current state
        self.config.setall(
            'current_input_files',
            {'mlclass_list_file': self.mlclass_list_loader.filename,
             'cropobject_list_file': self.cropobject_list_loader.filename,
             'image_file': self.image_loader.filename,
             })
        self.config.write()

        attempt_recovery_dump = self.config.get('recovery',
                                                'attempt_recovery_dump_on_exit')
        if attempt_recovery_dump:
            self.do_save_app_state()

        self.stop()
