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
* Simple XML-based data formats, with parsing tools

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

* The MungNode XML schema defines X as the **horizontal** dimension
  from the **left** and Y as the **vertical** dimension from the **top**.
* Numpy, and by extension OpenCV, defines X as the **vertical**  dimension
  from the **top** and Y as the **horizontal** dimension from the **left**.
* Kivy defines X as the **horizontal** dimension from the **left** and Y as
  the **vertical** dimension from the **bottom**.

This causes much wailing and gnashing of teeth.

Upon loading the MungNodes from the XML, the parsing function
``muscima_io.parse_cropobject_list()`` automatically swaps X and Y around
from the XML schema world into the Numpy world. Upon export, the
``MungNode.__str__()`` method again automatically swaps X and Y to export
the MungNode back to the XML schema world.

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

The MungNodes in the :class:`CropObjectAnnotatorModel` are always kept
in the Numpy world. There may be image processing operations associated
with the annotated objects model.

The CropObjectViews, on the other hand, are kept in the Kivy world,
as they are responsible for visualizing the model. (The Views do not
have X, Y, width and height; they have - being in essence
ToggleButtons - `size` and `pos`, just like any other Kivy widget.)

Note that while X and Y needs to be transposed in various ways during
the journey of a MungNode from XML file to visualization and back,
the interpretation of the ``width`` and ``height`` parameters
*does not change*.

Scaling
-------

Another grief-inducing hitch is the relationship between position input
in the scalable editor widget and the coordinates of the original image.


Tracking activities
==================

.. todo:: Implement this!

Annotator activity can be tracked. In general, events that we could track are:

* Model-level activity
  * cropobject deletion
  * cropobject creation
  * cropobject modification
  * image loading
  * mlclass list change
* Interface-level activity
  * app start
  * app exit
  * tool selection
  * tool deselection
  * image move
  * image zoom
  * centering
  * backup requests
  * recovery requests
  * settings modification
  * settings request
  * importing a CropObjectList
  * exporting a CropObjectList

Each logged event has:

* timestamp
* type of activity
* app state
* model state

How to use tracking
-------------------

Tracking is implemented through decorators in the `tracker.py` module::

>>> import MUSCIMarker.tracker as tr
>>> @tr.Tracker(track_names=['foo', 'bar'])
... def do_something(foo='foo', bar='bar', baz='baz'):
...     print(foo, bar, baz)

Now, calling `do_something` will produce a tracking event that captures
the values of the `foo` and `bar` arguments.

The tracker writes all its output as a JSON list of the event dicts to a file.
The default tracking dir is in `$HOME/.muscimarker-tracking`. It is
further organized into directories by day. Each launch of MUSCIMarker
generates one tracking file, named `muscimarker-tracking.YYYY-mm-dd_hh:mm:ss`.

Each tracked event generates one JSON dictionary. All events have:

* `time` (timestamp from `time.time()`)
* `time_human` (equivalent to `time` in YYYY-mm-dd_hh:mm:ss format)
* `-tracker-` (label for the event: meant for grouping events into
  categories such as navigation, toolkit usage, import/export, etc.)
* `-fn-` (name of the function whose call produces a tracking event)
* `-comment-` (optional string explaining what the event is)
* `-count-` (optional, how many times has the event occurred in the given session)

The arguments with which the tracked function was called can also be
captured. The tracker also allows for some simple transformations for
the tracked arguments: for instance, cropobject creation tracking
logs just the `objid` and `clsname` attributes instead of the entire MungNode.

Tracking implementation
-----------------------

Two kinds of objects are involved in tracking: trackers and handlers.
The `Tracker` object decorates the event-producing callable and produces
the tracking event. Then, it hands the event off to the handler object,
which is responsible for writing the event data into the tracking file.

"""
from __future__ import division
from __future__ import print_function, unicode_literals

from future import standard_library

standard_library.install_aliases()
from builtins import zip
from builtins import str
from past.utils import old_div
import copy
import logging
import os
import pprint
import time

import pickle
import datetime

import numpy
import scipy.misc

from kivy.app import App
from kivy.config import Config
from kivy.properties import ObjectProperty, StringProperty, ListProperty, NumericProperty, DictProperty, AliasProperty
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.gridlayout import GridLayout
from kivy.uix.togglebutton import ToggleButton
from mung.io import parse_cropobject_list, parse_cropobject_class_list
from mung.node import Node as MungNode
from MUSCIMarker.image_processing import ImageProcessing
from MUSCIMarker.help import Help
from MUSCIMarker.objid_selection import ObjidSelectionDialog
from MUSCIMarker.mlclass_selection import MLClassSelectionDialog
from MUSCIMarker.syntax.dependency_grammar import DependencyGrammar
from MUSCIMarker.edge_view import ObjectGraphRenderer
from MUSCIMarker.rendering import CropObjectRenderer
from MUSCIMarker.utils import FileNameLoader, ImageToModelScaler, ConfirmationDialog, keypress_to_dispatch_key, \
    MessageDialog, OnBindFileSaver, compute_connected_components, filename2docname
from MUSCIMarker.annotator_model import CropObjectAnnotatorModel
import MUSCIMarker.toolkit as toolkit
import MUSCIMarker.tracker as tr

import kivy

kivy.require('1.9.1')

__version__ = "1.0a"
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
#     """This widget is the visual representation of a MungNode."""
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

    * MungNode splitting and merging. (DONE)
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
    they always work the same way (such as exporting the current MungNodes,
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
    is being used and the current MungNodes).


    Visualizing the MungNodes
    ----------------------------

    We want to see the annotated objects, each as a colored semi-transparent
    bounding box. The chain from an annotation object to the visual representation:

    MungNode -(A)-> SelectableCropObject -(B)-> CropObjectView

    **B** The conversion from a selectable MungNode to the View (the visible
    rectangle) is done through a DictAdapter. The output widget is then "posted"
    upon a separate RelativeLayout that is overlaid over the edited image.

    We want the entire chain to be event-driven: listen to the model's
    ``cropobject_list``, maintain a dictionary of SelectableCropObjects
    (at this point, we need access to the editor widget's dimensions, because
    the vertical (X) position of the MungNode is represented from top-left,
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.annot_model = CropObjectAnnotatorModel()

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
    MungNode bounding boxes and the exports, which need to be aligned
    to the image file.

    However, real-time recomputing is also wrong, because the coordinates
    do get recomputed inside the ScatterLayout in which the Image lives.
    The coordinates of added MungNodes are therefore always kept in relation
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

    grammar_loader = ObjectProperty(FileNameLoader())

    mlclass_list_length = NumericProperty(0)
    '''Current number of MLClasses. Not essential.'''

    cropobject_list_loader = ObjectProperty(FileNameLoader())
    '''Handler for reloading the CropObjectList definition.'''

    # Set overwriting to False for production.
    cropobject_list_saver = ObjectProperty(OnBindFileSaver(overwrite=True))
    cropobject_list_export_path = StringProperty()

    cropobject_current_docname = StringProperty(MungNode.UID_DEFAULT_DOCUMENT_NAMESPACE)
    cropobject_current_dataset_namespace = StringProperty(MungNode.UID_DEFAULT_DATASET_NAMESPACE)

    ##########################################################################
    # View of the annotated MungNodes and relationships, and exposing
    # them to the rest of the app.
    cropobject_list_renderer = ObjectProperty()
    '''The renderer is responsible for showing the current state
    of the annotation as (semi-)transparent bounding boxes overlaid
    over the editor image.'''

    selected_cropobjects = ListProperty()
    '''Bind fixed UI elements that need to know which MungNodes
     are selected to this. It has to be actively updated by the Views.'''

    def _get_n_selected_cropobjects(self): return len(self.selected_cropobjects)
    n_selected_cropobjects = AliasProperty(_get_n_selected_cropobjects, None,
                                           bind=['selected_cropobjects'])
    '''For counting how many MungNodes are selected.'''

    graph_renderer = ObjectProperty()
    '''The edge renderer is responsible for showing the current state
    of the object graph as lines overlaid on the editor image.'''

    selected_relationships = ListProperty()
    '''Bind fixed UI elements that need to know which Edges
     are selected to this.'''

    def _get_n_selected_relationships(self): return len(self.selected_relationships)
    n_selected_relationships = AliasProperty(_get_n_selected_relationships, None,
                                           bind=['selected_relationships'])
    '''For counting how many MungNodes are selected.'''

    #######################################
    # In-app messages (not working yet)
    message = ObjectProperty(None)

    #######################################
    # Keyboard shortcuts (keyboard shortcut handling is pretty
    # decentralized & not great)
    keyboard_dispatch = DictProperty(None)
    '''
    '''

    ##########################################################################
    # App build & config methods

    def build(self):

        self.init_tracking()

        self.clean_tmp_dir()

        # Why is this here?
        Window.bind(on_key_down=self.on_key_down)
        Window.bind(on_key_up=self.on_key_up)

        # Define bindings for compartmentalized portions of the application
        self.mlclass_list_loader.bind(filename=self.import_mlclass_list)
        self.image_loader.bind(filename=self.import_image)
        self.cropobject_list_loader.bind(filename=self.import_cropobject_list)

        self.grammar_loader.bind(filename=self.import_grammar)

        # Resuming annotation from previous state
        conf = self.config
        logging.info('Current configuration: {0}'.format(str(conf)))
        _image_abspath = os.path.abspath(conf.get('default_input_files',
                                                  'image_file'))
        self.image_loader.filename = _image_abspath
        logging.info('Build: Loaded image fname from config: {0}'
                     ''.format(self.image_loader.filename))

        # Rendering MungNodes
        self.cropobject_list_renderer = CropObjectRenderer(
            annot_model=self.annot_model,
            editor_widget=self._get_editor_widget())
        e = self._get_editor_widget()
        logging.info('Build: Adding renderer to editor widget {0}'
                     ''.format(e))
        e.add_widget(self.cropobject_list_renderer)

        # Rendering ObjectGraph
        self.graph_renderer = ObjectGraphRenderer(
            annot_model=self.annot_model,
            graph=self.annot_model.graph,
            editor_widget=self._get_editor_widget()
        )
        e = self._get_editor_widget()
        logging.info('Build: Adding graph renderer to editor widget {0}'
                     ''.format(e))
        e.add_widget(self.graph_renderer, index=0)

        Window.bind(on_resize=self.window_resized)

        # Editor scale broadcasting
        e_scatter = self._get_editor_scatter_container_widget()
        e_scatter.bind(scale=self.setter('editor_scale'))

        logging.info('Build: Started loading mlclasses from config')
        _mlclass_list_abspath = os.path.abspath(conf.get('default_input_files',
                                                         'mlclass_list_file'))
        self.mlclass_list_loader.filename = _mlclass_list_abspath
        logging.info('Build: Loaded mlclass list fname from config: {0}'
                     ''.format(self.mlclass_list_loader.filename))

        logging.info('Build: Started loading cropobjects from config')
        _cropobject_list_abspath = os.path.abspath(conf.get('default_input_files',
                                                            'cropobject_list_file'))
        self.cropobject_list_loader.filename = _cropobject_list_abspath
        logging.info('Build: Finished loading cropobject list fname from config: {0}'
                     ''.format(self.cropobject_list_loader.filename))

        saver_output_path = self.cropobject_list_loader.filename
        logging.info('Build: Setting default export dir to the cropobject list dir: {0}'
                     ''.format(saver_output_path))
        self.cropobject_list_saver.last_output_path = saver_output_path
        self.cropobject_list_saver.bind(filename=lambda *args, **kwargs: self.annot_model.export_cropobjects(
            self.cropobject_list_saver.filename,
            docname=filename2docname(self.cropobject_list_saver.filename),
            dataset_name=self.cropobject_current_dataset_namespace))

        logging.info('Build: started loading grammar from config')
        _grammar_abspath = os.path.abspath(conf.get('default_input_files',
                                                    'grammar_file'))
        self.grammar_loader.filename = _grammar_abspath
        logging.info('Build: Finished loading grammar from config: {0}'
                     ''.format(self.grammar_loader.filename))

        # self.cropobject_list_loader.bind(filename=self.cropobject_list_renderer.clear)

        # XXX:
        # ??? Why was this here? It should work based on whether stuff is cleared out
        #     in the *MODEL*.
        # self.mlclass_list_loader.bind(filename=self.cropobject_list_renderer.clear)
        # self.image_loader.bind(filename=self.cropobject_list_renderer.clear)

        # Keyboard control
        # self._keyboard = Window.request_keyboard(self._keyboard_close, self.root)
        # self._keyboard.bind(on_key_down=self._on_key_down)
        # self._keyboard.bind(on_key_up=self._on_key_up)

        # Finally, swap around order of tool selection sidebar & editor cell.
        main_area = self.root.ids['main_area']
        logging.info('App: main area children: {0}'.format(main_area.children))
        command_sidebar, editor_window, tool_sidebar = main_area.children
        main_area.remove_widget(tool_sidebar)
        main_area.add_widget(tool_sidebar)
        logging.info('App: main area children: {0}'.format(main_area.children))

        # Attempt recovery
        attempt_recovery = conf.get('recovery', 'attempt_recovery_on_build')
        if attempt_recovery is True:
            logging.info('App.build: Requested an attempt to recover last application'
                         ' state at build time.')
            self.do_recovery()

        recovery_dump_freq = int(conf.get('recovery', 'recovery_dump_frequency_seconds'))
        if (recovery_dump_freq is not None) and (recovery_dump_freq != 0):
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

        _scatter = self._get_editor_scatter_container_widget()
        logging.info('App.build: Scatter parent pos before do_layout:'
                     ' {0}'.format(_scatter.parent.pos))
        _scatter.parent.parent.do_layout()
        logging.info('App.build: Scatter parent position after do_layout:'
                     ' {0}'.format(_scatter.parent.pos))
        # logging.info('App.build: _scatter.parent.pos={0}'
        #              ''.format(_scatter.parent))
        # logging.info('App.build: _scatter.parent.parent.pos={0}'
        #              ''.format(_scatter.parent.parent.pos))
        # logging.info('App.build: _scatter.parent.parent.parent.pos={0}'
        #              ''.format(_scatter.parent.parent.parent.pos))

        self._enforce_center_current_image_once()
        self.init_tool_selection_keyboard_dispatch()
        # Needs re-doing on init: centering is called before the sidebars
        # have widths
        #Clock.schedule_once(lambda *args, **kwargs: self.init_tool_selection_keyboard_dispatch)

        self.annot_model.init_object_detection_handler()

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
                'mlclass_list_file': os.path.abspath('data/mff-muscima-mlclasses-annot.xml'),
                'cropobject_list_file': os.path.abspath('static/example_annotation.xml'),
                'image_file': os.path.abspath('static/default_score_image.png'),
                'grammar_file': os.path.abspath('data/grammars/mff-muscima-mlclasses-annot.deprules')
            })
        config.setdefaults('default_input_files',
            {
                'mlclass_list_file': os.path.abspath('data/mff-muscima-mlclasses-annot.xml'),
                'cropobject_list_file': os.path.abspath('static/example_annotation.xml'),
                'image_file': os.path.abspath('static/default_score_image.png'),
                'grammar_file': os.path.abspath('data/grammars/mff-muscima-mlclasses-annot.deprules')
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
                'cropobject_mask_nonzero_only': 1,
                # If set, will automatically restrict all masks to nonzero
                # pixels of the input image only.
                'trimmed_lasso_helper_line': 1,
                'trimmed_lasso_helper_line_length': 100,
                'active_selection': 0,
                'binarization_retain_foreground': 1,
                'split_on_eraser': 1,
                'selection_ignore_staff': 1,
                'detection_classes': 'staff_line,notehead-full,notehead-empty,ledger_line,' + \
                                     'sharp,flat,natural,stem,beam,duration-dot,' + \
                                     'thin_barline,g-clef,f-clef,c-clef',
                'detection_use_current_class': True,
            })
        config.setdefaults('tracking',
            {
                'tracking_root_dir': self._get_default_tracking_root_dir(),
            })
        config.setdefaults('interface', {'center_on_resize': False})
        config.setdefaults('automation',
            {
                'sparse_cropobject_threshold': 0.1,
                'sparse_exclusive_cropobject_threshold': 0.2
            })
        config.setdefaults('image_preprocessing',
            {
                'do_image_preprocessing': False,
                'auto_invert': False,
                'stretch_intensity': False,
                'warp_registration': False,
                # 'median_kernel_size': 10,
                # 'do_background_thresholding': False,
                # 'binarization_lightness_tolerance': 127,
            })
        config.setdefaults('parsing',
                           {
                               'smart_parsing': False,
                               'smart_parsing_model': os.path.join(os.path.dirname(__file__),
                                                                   'data', 'parsing',
                                                                   'MM++_OPs_delta-bbox-all200.classifier.pkl'),
                               'smart_parsing_vectorizer': os.path.join(os.path.dirname(__file__),
                                                                   'data', 'parsing',
                                                                   'MM++_OPs_delta-bbox-all200.vectorizer.pkl'),
                           })
        config.setdefaults('symbol_detection_client',
                           {
                               'port': 33554,
                               'hostname': '127.0.0.1',
                           })
        config.setdefaults('midi',
                           {
                               'soundfont': '~/.fluidsynth/FluidR3_GM.sf2',
                               'default_tempo': 120,
                           })

        Config.set('kivy', 'exit_on_escape', '0')

    def build_settings(self, settings):
        with open(os.path.join(os.path.dirname(__file__), 'muscimarker_config.json')) as hdl:
            jsondata = hdl.read()
        settings.add_json_panel('MUSCIMarker',
                                self.config, data=jsondata)

        with open(os.path.join(os.path.dirname(__file__),
                               'muscimarker_image_preprocessing.json')) as hdl:
            jsondata = hdl.read()
        settings.add_json_panel('Image Processing',
                                self.config, data=jsondata)

        with open(os.path.join(os.path.dirname(__file__),
                               'muscimarker_detection_client.json')) as hdl:
            jsondata = hdl.read()
        settings.add_json_panel('Symbol Detection Client',
                                self.config, data=jsondata)

        with open(os.path.join(os.path.dirname(__file__),
                               'muscimarker_midi.json')) as hdl:
            jsondata = hdl.read()
        settings.add_json_panel('MIDI settings',
                                self.config, data=jsondata)


    @tr.Tracker(track_names=[],
                tracker_name='app',
                comment='User accessed the settings.')
    def open_settings(self, *largs):
        super(MUSCIMarkerApp, self).open_settings(*largs)

    ##########################################################################
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
        self.annot_model.ensure_consistent()
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
            # We'll use the model to get the list of current MungNodes.
            # The cropobjects member of annot_model is a kivy Property,
            # so it fails on pickle -- we must get the data itself
            # by different means.
            'cropobjects': list(self.annot_model.cropobjects.values()),
            # We also want to save the state of the image, as it may have been
            # manually binarized and we do not want to lose that work.
            'image_state': self.annot_model.image.tostring(),
            'image_shape': self.annot_model.image.shape,
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
        image_state_string = state['image_state']

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
        # CropObjectList filename. After loading, we then replace the MungNodes
        # replace it by the model's MungNodes instead - clear it and replace
        # with saved MungNodes).
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

        # Building the MungNodes from the model:
        logging.info('App._build_from_app_state: Replacing file-based MungNodes'
                     ' with MungNodes loaded from the model in the app state.')
        logging.info('App._build_from_app_state: no. of MungNodes: from file:'
                     ' {0}, from state: {1}'.format(len(self.annot_model.cropobjects),
                                                    len(cropobjects)))
        self.annot_model.clear_cropobjects()
        # This should trigger a redraw.
        self.annot_model.import_cropobjects(cropobjects)

        # Finally, load the saved state of the image.
        try:
            image_state = numpy.fromstring(image_state_string, dtype='uint8')
            image_shape = state['image_shape']
            image_data = numpy.reshape(image_state, image_shape)
            self.update_image(image_data)
        except:
            logging.warn('App._build_from_app_state: Loading image state'
                         ' failed, falling back on image file.')
            image_fname = self.image_loader.filename
            self.image_loader.filename = image_fname # Force update

        logging.info('App._build_from_state: Finished successfully.')

    def _save_app_state(self):
        recovery_path = self._get_recovery_path()
        logging.debug('App.recover: Saving recovery file {0}'.format(recovery_path))

        state = self._get_app_state()

        # Cautious behavior: let's try not to destroy the previous
        # backup until we are sure the backup has been made correctly.
        rec_temp_name = recovery_path + '.temp'
        logging.debug('App.save_app_state: Saving to recovery file {0}'
                      ''.format(recovery_path))
        try:
            with open(rec_temp_name, 'wb') as hdl:
                pickle.dump(state, hdl, protocol=pickle.HIGHEST_PROTOCOL)
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
                state = pickle.load(hdl)
        except pickle.PickleError:
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

    @tr.Tracker(track_names=[],
                tracker_name='commands')
    def do_recovery_user(self):
        """Link user-requested recovery to this method. Separate from
        ``do_recovery()`` because of tracking."""
        logging.info('App: user requested recovery dump.')
        self.do_recovery()

    def do_save_app_state_clock_event(self, *args):
        logging.info('App: making scheduled recovery dump.')
        self.do_save_app_state()
        logging.debug('App: scheduled recovery dump done.')

    ##########################################################################
    # Keyboard control
    def _keyboard_close(self):
        self._keyboard.unbind(on_key_down=self.on_key_down,
                              on_key_up=self.on_key_up)
        self._keyboard = None

    def on_key_down(self, window, key, scancode, codepoint, modifier):
        logging.debug('App: Keyboard: Down {0}'.format((key, scancode, codepoint, modifier)))

        dispatch_key = keypress_to_dispatch_key(key, scancode, codepoint, modifier)

        logging.debug('App: processing on_key_down(), dispatch_key: {0}'
                      ''.format(dispatch_key))
        is_handled = self.handle_dispatch_key(dispatch_key)
        return is_handled

    def handle_dispatch_key(self, dispatch_key):
        """Does the "heavy lifting" in keyboard controls of the App:
        responds to a dispatch key.

        Decoupling this into a separate method facillitates giving commands to
        the ListView programmatically, not just through user input,
        and this way makes automation easier.

        :param dispatch_key: A string of the form e.g. ``109+alt,shift``: the ``key``
            number, ``+``, and comma-separated modifiers.

        :returns: True if the dispatch key got handled, False if there is
            no response defined for the given dispatch key.
        """
        if dispatch_key == '27':  # Escape
            self.currently_selected_tool_name = '_default'

        elif dispatch_key == '99': # c
            logging.info('Doing current MLClass selection dialog.')
            self.open_mlclass_selection_dialog()
        # This is a shortcut that can be used even if there
        # are selected MungNodes that would respond to "c"
        elif dispatch_key == '99+alt': # alt+c
            logging.info('Doing current MLCLass selection dialog, forced')
            self.open_mlclass_selection_dialog()

        elif dispatch_key == '111':   # o -- objid selection
            logging.info('Doing objid-based selection dialog.')
            self.open_objid_selection_dialog()

        elif dispatch_key == '115+shift':  # "shift+s" -- select all of current clsname
            logging.info('Selecting all MungNodes of the current clsname.')
            view = self.cropobject_list_renderer.view
            view.select_class(self.currently_selected_mlclass_name)

        elif dispatch_key == '118':  # "v" -- validate
            self.find_cropobjects_with_errors()
        elif dispatch_key == '118+alt':  # "alt+v" -- validate edges
            self.find_wrong_edges()

        # alt+shift for automation commands
        elif dispatch_key == '98+alt,shift':   # "alt+shift+b" -- barlines automation
            self.auto_add_measure_separators()
        elif dispatch_key == '116+alt,shift':  # "alt+shift+t" -- suspiciously "sparse" cropobjects
            self.find_objects_with_unannotated_pixels(exclusive=False)
        elif dispatch_key == '114+alt,shift':  # "alt+shift+r" -- exclusively "sparse" cropobjects, exclusive
            self.find_objects_with_unannotated_pixels(exclusive=True)
        elif dispatch_key == '100+alt,shift':  # "alt+shift+d" -- disconnected cropobjects
            self.find_objects_with_disconnected_masks(leaves_only=False)
        elif dispatch_key == '115+alt,shift':  # "alt+shift+s" -- disconnected cropobjects that have no outlinks,
            self.find_objects_with_disconnected_masks(leaves_only=True)
        elif dispatch_key == '111+alt,shift':  # "alt+shift+o" -- perfectly overlapping cropobjects,
            self.find_objects_with_identical_bounding_box()
        elif dispatch_key == '113+alt,shift':  # "alt+shift+q" -- suspiciously small
            self.find_suspiciously_small_objects()

        # f to infer MIDI
        elif dispatch_key == '102':
            logging.info('App: Inferring MIDI without playing.')
            self.infer_midi(play=False)
        # shift+f to infer MIDI and play it
        elif dispatch_key == '102+shift':
            logging.info('App: Inferring MIDI and playing.')
            self.infer_midi(play=True)
        # ctrl+alt+shift+f: clear all the inferred pitch/duration/onset info
        elif dispatch_key == '102+alt,ctrl,shift':
            logging.info('App: Removing inferred MIDI information.')
            self.annot_model.clear_midi_information()


        # logging.info('App: Checking keyboard dispatch, {0}'
        #              ''.format(self.keyboard_dispatch.keys()))
        elif dispatch_key in self.keyboard_dispatch:
            action = self.keyboard_dispatch[dispatch_key]
            logging.info('App: \t Found dispatch key! Action: {0}'
                         ''.format(action))
            action()
        else:
            return False

        return True   # Stop bubbling

    def on_key_up(self, window, key, scancode, *args, **kwargs):
        logging.debug('App: Keyboard: Up {0}'.format((key, scancode)))

    ##########################################################################
    # Importing methods: interfacing the raw data to the model

    def import_mlclass_list(self, instance, pos):
        try:
            #mlclass_list = muscimarker_io.parse_mlclass_list(pos)
            mlclass_list = parse_cropobject_class_list(pos)
        except:
            logging.info('App: Loading MLClassList from file \'{0}\' failed.'
                         ''.format(pos))
            return

        logging.info('App: === Reloading mlclass list from app fired. List has {0} items.'
                     ''.format(len(mlclass_list)))
        self.mlclass_list_length = len(mlclass_list)
        self.annot_model.import_classes_definition(mlclass_list)

        self.currently_selected_mlclass_name = list(self.annot_model.mlclasses.values())[0].name

    @tr.Tracker(track_names=['pos'],
                transformations={'pos': [lambda x: ('cropobjects_file', x)]},
                tracker_name='commands')
    def import_cropobject_list(self, instance, pos):
        logging.info('App: === Reloading CropObjectList fired with file \'{0}\''
                     ''.format(pos))

        # Timing it
        _start_time = time.clock()

        # Check for XML
        if not pos.endswith('xml'):
            logging.info('App: Detected non-XML file in import_cropobject_list request!')
            confirmation = ConfirmationDialog(text='We detected a non-XML file when'
                                                   ' loading annotations: are'
                                                   ' you trying to load'
                                                   ' an image?')
            confirmation.bind(on_ok=lambda x: self.import_image(instance, pos))
            confirmation.open()
            return


        try:
            cropobject_list = parse_cropobject_list(pos,
                                                    #with_refs=True,
                                                    #tolerate_ref_absence=True,
                                                    #fill_mlclass_names=True,
                                                    #mlclass_dict=self.annot_model.mlclasses
                                                    )

            # # Handling MLClassList and Image conflicts. Currently just warns.
            # if mfile is not None:
            #     if mfile != self.mlclass_list_loader.filename:
            #         logging.warn('Loaded CropObjectList for different MLClassList ({0}),'
            #                      ' colors are off and any annotation entered is invalid!'
            #                      ''.format(mfile))
            # if ifile is not None:
            #     if ifile != self.image_loader.filename:
            #         logging.warn('Loaded CropObjectList for different image file ({0}),'
            #                      ' colors are off and any annotation entered is invalid!'
            #                      ''.format(ifile))
        except:
            logging.info('App: Loading CropObjectList from file \'{0}\' failed.'
                         ''.format(pos))
            raise
            #return

        ###############
        # docname behavior:
        #  - If importing an existing MungNode list, take their docname.
        #    Chances are, someone is editing a list after a pause, or QC is going
        #    on; in both of these cases, the document name should not change.
        #  - The only exception is when loading a file with the default docname.
        #    In that case, because MUSCIMarker *must* have first loaded an image,
        #    use the docname derived from the image file.
        # Set docname for UIDs
        docnames = list(set([c.doc for c in cropobject_list]))
        if len(docnames) > 1:
            raise ValueError('Mixing MungNodes from {0} different documents:'
                             ' {1}!'.format(len(docnames), '\n'.join(docnames)))
        if len(docnames) > 0:
            if docnames[0] != MungNode.UID_DEFAULT_DOCUMENT_NAMESPACE:
                self.cropobject_current_docname = docnames[0]

        datasets = list(set([c.dataset for c in cropobject_list]))
        if len(datasets) > 1:
            raise ValueError('Mixing MungNodes from {0} different datasets:'
                             ' {1}!'.format(len(datasets), '\n'.join(datasets)))
        if len(datasets) > 0:
            if datasets[0] != MungNode.UID_DEFAULT_DATASET_NAMESPACE:
                self.cropobject_current_dataset_namespace = datasets[0]


        logging.info('App: Imported CropObjectList has {0} items.'
                     ''.format(len(cropobject_list)))
        self.cropobject_list_renderer.view.unselect_all()
        self.annot_model.import_cropobjects(cropobject_list, clear=True)

        logging.info('App: Importing MungNodes took {0:.3f} seconds.'.format(time.clock() - _start_time))

    @tr.Tracker(track_names=['pos'],
                transformations={'pos': [lambda x: ('image_file', x)]},
                tracker_name='commands')
    def import_image(self, instance, pos, clear_cropobjects=True):

        logging.info('App: === Got image file: {0}'.format(pos))

        # Check for XML
        if pos.endswith('xml'):
            logging.info('App: Detected XML file in import_image request!')
            confirmation = ConfirmationDialog(text='We detected a XML file when'
                                                   ' loading an image: are'
                                                   ' you trying to load'
                                                   ' an annotation file?')
            #p = partial(self.import_cropobject_list, instance, pos)
            confirmation.bind(on_ok=lambda x: self.import_cropobject_list(instance, pos))
            confirmation.open()
            return

        try:
            img = scipy.misc.imread(pos, mode='L')
            logging.info('App: Image dtype: {0}, min: {1}, max: {2}, shape: {3}'
                         ''.format(img.dtype, img.min(), img.max(), img.shape))
        except:
            logging.info('App: Loading image from file \'{0}\' failed.'
                         ''.format(pos))
            return

        _do_clear_cropobjects = False
        if clear_cropobjects:
            _do_clear_cropobjects = True
        elif (self.annot_model.image is None) \
                or (img.shape != self.annot_model.image.shape):
            _do_clear_cropobjects = True

        if _do_clear_cropobjects:
            self.annot_model.clear_cropobjects()

        # Define image processing here, based on config
        image_processor = ImageProcessing(
            do_image_processing=self.config.getboolean('image_preprocessing',
                                                       'do_image_preprocessing'),
            auto_invert=self.config.getboolean('image_preprocessing',
                                               'auto_invert'),
            stretch_intensity=self.config.getboolean('image_preprocessing',
                                                     'stretch_intensity'),
            warp_registration=self.config.getboolean('image_preprocessing',
                                                     'warp_registration'),
        )
        logging.info('App.import_image(): Image preprocessing with auto_invert={0},'
                     ' stretch_intensity={1}'.format(image_processor.auto_invert,
                                                     image_processor.stretch_intensity))
        self.annot_model._image_processor = image_processor

        self.annot_model.load_image(img,
                                    do_preprocessing=True,
                                    update_temp=True)

        # Only change the displayed image after loading into model.
        image_fname = pos
        time.sleep(3)
        if os.path.isfile(self.annot_model._current_tmp_image_filename):
            image_fname = self.annot_model._current_tmp_image_filename
        self.currently_edited_image_filename = image_fname

        # compute scale
        self.current_image_height = img.shape[0]
        self.current_image_width = img.shape[1]
        editor = self._get_editor_widget()
        editor_height = float(editor.height)
        editor_width = float(editor.width)
        self.image_height_ratio_in = old_div(editor_height, self.current_image_height)
        self.image_width_ratio_in = old_div(editor_width, self.current_image_width)

        self.image_scaler = ImageToModelScaler(self._get_editor_widget(),
                                               self.annot_model.image)

        # move image to middle
        self.do_center_and_rescale_current_image()
        image_widget = self._get_editor_widget()
        image_widget.texture.mag_filter = 'nearest'

        if not _do_clear_cropobjects:
            self.cropobject_list_renderer.redraw += 1

        ###############
        # docname behavior:
        #  - If importing an image, the current annotation gets deleted.
        #    The assumption is that for a new image, you will either:
        #     - (a) import an existing MungNode list, in which case its docname
        #       will supersede whatever we set here in accordance with the policy
        #       of "getting back to work",
        #     - (b) this is the first time you are  annotating this image, and so
        #       we should choose a good docname for you.
        # - Therefore, at this point, we just come up with what we think is the
        #   right docname for an annotation of this image.
        # - This "good enough" docname is the base filename of the image file,
        #   minus the file type extension.
        # Set docname for UIDs
        self.cropobject_current_docname = os.path.splitext(os.path.basename(pos))[0]

    def update_image(self, image,
                     # allow_size_change_without_cropobjects=False,
                     do_preprocessing=False,
                     update_temp=False):
        """Nondestructively swaps out underlying image in the model and displays
        it."""
        if image.shape != self.annot_model.image.shape:
            #if allow_size_change_without_cropobjects and (len(self.annot_model.cropobjects) == 0):
            #    pass
            #else:
            raise ValueError('Trying to swap original image with shape {0} for a new'
                             ' image with a different shape {1}!'
                             ''.format(self.annot_model.image.shape, image.shape))

        self.annot_model.load_image(image,
                                    do_preprocessing=do_preprocessing,
                                    update_temp=update_temp)
        # This function is used to update the image on the fly, so the preprocessing
        # applied when the image is first imported does not have to be done.

        self.update_image_texture_from_model()

    def revert_image_to_source(self):
        image_fname = self.annot_model._current_tmp_image_filename
        image = scipy.misc.imread(image_fname, mode='L')
        self.update_image(image)

    def update_image_texture_from_model(self):
        """Manually synchronize the model image to the editor window
        texture."""
        image = self.annot_model.image
        self.do_sync_model_image(None, image)

    def do_sync_model_image(self, instance, image):
        """Synchronize model image to editor window on image change.

        Note that directly editing the numpy array will *not* trigger this,
        only re-assigning to it. This does happen in model.load_image(),
        so calling model.load_image() will trigger the update.
        """
        # Reformatting image to conform to how Kivy displays textures
        # formatted_image = numpy.fliplr(
        #     numpy.swapaxes(
        #         numpy.rot90(image),
        #     0, 1)
        # )   ...not necessary??
        formatted_image = image #numpy.fliplr(image)
        image_data = formatted_image.tostring()
        editor_widget = self._get_editor_widget()
        texture = editor_widget.texture

        logging.info('Original image shape: {0}'.format(image.shape))
        logging.info('Formatted image shape: {0}'.format(formatted_image.shape))
        logging.info('Texture size: {0}'.format(texture.size))

        if (texture.height, texture.width) != formatted_image.shape:
            texture.blit_buffer(formatted_image.flatten(),
                                #size=(formatted_image.shape[1],
                                #      formatted_image.shape[0]),
                                colorfmt='luminance',
                                bufferfmt='ubyte')
            editor_widget.canvas.ask_update()
        else:
            texture.blit_buffer(formatted_image.flatten(),
                                colorfmt='luminance',
                                bufferfmt='ubyte')


    @tr.Tracker(track_names=['pos'],
                transformations={'pos': [lambda x: ('grammar_file', x)]},
                tracker_name='commands')
    def import_grammar(self, instance, pos):
        logging.info('App: === Got grammar file: {0}'.format(pos))
        g = DependencyGrammar(grammar_filename=pos,
                              mlclasses=self.annot_model.mlclasses)
        self.annot_model.grammar = g

    ##########################################################################
    # Centering the current image (e.g. if you get lost during high-scale work)

    def do_center_current_image(self, *args, **kwargs):
        Clock.schedule_once(lambda *anything: self.center_current_image())

    @tr.Tracker(tracker_name='commands')
    def do_center_and_rescale_current_image_user(self):
        self.do_center_and_rescale_current_image()

    def do_center_and_rescale_current_image(self):
        Clock.schedule_once(lambda *args: self.center_and_rescale_current_image())

    def center_and_rescale_current_image(self):
        self.center_current_image()
        self.rescale_current_image()

    def rescale_current_image(self, padding=0.02):
        """Scales current image to fit into the editor area of the screen."""

        # Compute available width.
        w = self.root.width
        _r_margin_size = max(100, self.root.ids['command_sidebar'].width)
        _l_margin_size = max(400, self.root.ids['tool_selection_sidebar'].width)
        available_width = w - (_r_margin_size + _l_margin_size)
        padded_width = available_width - 2 * (padding * available_width)

        image_width = self.annot_model.image.shape[1]


        # Determine the scale so that the image fits onto the screen
        scatter = self._get_editor_scatter_container_widget()
        _scatter_width = scatter.width
        scale = old_div(float(padded_width), float(_scatter_width))

        logging.info('App: Scaling image: root width = {0},'
                     'lmargin = {1}, rmargin = {2}, scatter = {3}'
                     ''.format(w, _l_margin_size, _r_margin_size, _scatter_width))
        logging.info('App: Scaling image: available_width = {0}, padded_width = {1},'
                     ' image_width = {2}, scale = {3}'
                     ''.format(available_width, padded_width, image_width, scale))


        scatter.scale = scale
        # scatter.scale = 1.0

    #@tr.Tracker(tracker_name='view')
    def center_current_image(self):
        """Centers the current image.

        Implementation: gives the centering ``pos_hint`` to the ScatterLayout
            that is holding the Image, force a redraw of its parent, and then
            retracts the pos_hint so that the image can be moved around freely
            again.
        """
        logging.info('App.center_current_image: ====== Centering image ======')
        scatter = self._get_editor_scatter_container_widget()

        logging.info('App.center_current_image: current scatter position: {0}'
                     ''.format(scatter.pos))
        logging.info('App.center_current_image: current scatter pos_hint: {0}'
                     ''.format(scatter.pos_hint))

        cached_pos_hint = scatter.pos_hint
        scatter.pos_hint = {'center_y': 0.5, 'center_x': 0.5}
        # Hack to read the what the center should be
        # self.root.do_layout()
        scatter.parent.do_layout()
        logging.info('App.center_current_image: After redrawing layout with centered'
                     ' pos_hint, scatter position: {0}'
                     ''.format(scatter.pos))
        # Remember the position after centering
        cached_pos = scatter.pos

        # Unlock moving the ScatterLayout around again...
        scatter.pos_hint = cached_pos_hint

        # ...but give it the position corresponding to the center.
        # This involves computing how much space is available
        # between the sidebars, because the scatter centers w.r.t. the window,
        # for some reason.
        _r_margin_size = self.root.ids['command_sidebar'].width
        _l_margin_size = self.root.ids['tool_selection_sidebar'].width
        _delta_x = ((old_div(_l_margin_size, 2.0)) - (old_div(_r_margin_size, 2.0)))

        center_x = cached_pos[0] + _delta_x
        center_y = cached_pos[1]
        center_pos = (center_x, center_y)
        scatter.pos = center_pos

        logging.info('App.center_current_image: end scatter position: {0}'
                     ''.format(scatter.pos))
        logging.info('App.center_current_image: end scatter pos_hint: {0}'
                     ''.format(scatter.pos_hint))

    def _enforce_center_current_image_once(self):
        """We need to enforce the image to be centered at the beginning,
        but we have to wait until the window is actually drawn in order
        to know all the sizes, positions, etc.
        The uncertain period (n. of clock ticks?) between build()
        and the window being drawn was probably the cause of the
        unpredictable centering or non-centering of the initial image
        on application start. This way, we attach a callback to the Window's
        on_draw event that centers the image and unschedules itself."""
        Window.bind(on_draw=self._do_center_current_image_and_unenforce)

    def _do_center_current_image_and_unenforce(self, *args, **kwargs):
        """Second part of the bound trigger."""
        self.do_center_current_image()
        Window.unbind(on_draw=self._do_center_current_image_and_unenforce)

    ##########################################################################
    # Basic image manipulation
    def rotate_image(self, clockwise=False):
        logging.info('App: Rotating image, clockwise={0}')
        n_rot = 1
        deg_rot = 90
        if clockwise:
            n_rot = 3
            deg_rot = 270
        new_image = numpy.rot90(self.annot_model.image, k=n_rot)
        self.annot_model.load_image(new_image,
                                    do_preprocessing=False,
                                    update_temp=True)
        editor_container = self._get_editor_scatter_container_widget()
        # self.update_image(new_image,
        #                   # allow_size_change_without_cropobjects=True,
        #                   do_preprocessing=False,
        #                   update_temp=True)
        editor_container.rotation += deg_rot

    ##########################################################################
    # Tracking image movement

    @tr.Tracker(track_names=['touch', 'editor'],
                transformations={'touch': [lambda t: ('x', t.x),
                                           lambda t: ('y', t.y),
                                           lambda t: ('orig_scale', t.ud['editor_start_scale']),
                                           lambda t: ('orig_pos', t.ud['editor_start_pos'])],
                                 'editor': [lambda e: ('new_scale', e.scale),
                                            lambda e: ('new_pos', e.pos)]},
                tracker_name='view')
    def image_was_moved_with_touch(self, touch, editor):
        pass

    @tr.Tracker(track_names=['touch', 'editor'],
                transformations={'touch': [lambda t: ('x', t.x),
                                           lambda t: ('y', t.y),
                                           lambda t: ('orig_scale', t.ud['editor_start_scale']),
                                           lambda t: ('orig_pos', t.ud['editor_start_pos'])],
                                 'editor': [lambda e: ('new_scale', e.scale),
                                            lambda e: ('new_pos', e.pos)]},
                tracker_name='view')
    def image_was_scaled_with_touch(self, touch, editor):
        pass

    def is_image_moved_with_touch(self, touch):
        ud = touch.ud
        image = self._get_editor_widget()
        editor = self._get_editor_scatter_container_widget()

        out = False
        if len(editor._touches) > 1: # Ignore touches unless we're sure we are translating.
            pass
        elif 'multitouch_sim' in touch.profile:
            pass
        elif 'editor_start_pos' in ud:
            if editor.pos != ud['editor_start_pos']:
                out = True
        #logging.info('App: Was image moved with touch {0}? {1}'
        #             ''.format(touch, out))
        return out

    def is_image_scaled_with_touch(self, touch):
        ud = touch.ud
        image = self._get_editor_widget()
        editor = self._get_editor_scatter_container_widget()

        out = False

        if len(editor._touches) < 2:  # Check that there was the second scaling touch
            pass
        elif 'editor_start_scale' in ud:
            if editor.scale != ud['editor_start_scale']:
                out = True
        #logging.info('App: Was image scaled with touch {0}? {1}'
        #             ''.format(touch, out))
        return out

    def _image_touch_up(self, touch):
        editor = self._get_editor_scatter_container_widget()

        # Problem with multi-touches for scaling:
        # the double-click touch got grabbed as well, so it passes thorough
        # the grab contition, but it still remembers the original scale.
        # So it gets logged a second time, when the red circle is un-clicked.

        # This is the important check that determines whether the touch
        # that just went up is actually a touch that the editor Scatter
        # could have processed.
        #
        # Workaround (assuming there is only one editor!!!):
        # There is some problem with ``touch.grab_current is not editor``,
        # the id() result for the two is somehow different (maybe grab_current is a weakref?)
        if not isinstance(touch.grab_current, editor.__class__):
            #logging.info('App: image on_touch_up, but editor did not grab it.'
            #             ' Touch {0} grabbed by: {1}, editor: {2}'.format(touch, touch.grab_current, editor))
            return

        #logging.info('App: image on_touch_up, touch {0} grabbed by editor.'
        #             ' Determining whether the image was actually moved.'.format(touch))

        # Scaling changes pos, but moving does not change scale.
        # Maybe this could be rewritten as events?
        if self.is_image_scaled_with_touch(touch):
            self.image_was_scaled_with_touch(touch, editor)
        elif self.is_image_moved_with_touch(touch):
            self.image_was_moved_with_touch(touch, editor)

    def _image_touch_down(self, touch):
        editor = self._get_editor_scatter_container_widget()
        #if touch.grab_current is not editor:
        #    #logging.info('App: image on_touch_down, but editor did not grab it.'
        #    #             ' Grabbed by: {0}'.format(touch.grab_current))
        #    #return  # ...editor does not grab before this is called?

        ud = touch.ud
        ud['editor_start_pos'] = editor.pos
        ud['editor_start_scale'] = editor.scale
        # image = self._get_editor_widget()
        # ud['image_start_pos'] = image.pos
        # ud['image_start_size'] = image.size
        # x, y = touch.x, touch.y
        # ud['touch_start_x'] = x
        # ud['touch_start_y'] = y
        #logging.info('App: image touched, recording data for tracking'
        #             ' user navigation around the image.')


    ##########################################################################
    # Resizing
    @tr.Tracker(track_names=['width', 'height'],
                tracker_name='app')
    def window_resized(self, instance, width, height):
        logging.info('App: Window resize to: {0}'.format((width, height)))
        e = self._get_editor_widget()
        self.image_height_ratio_in = old_div(float(e.height), self.current_image_height)
        self.image_width_ratio_in = old_div(float(e.width), self.current_image_width)

        self.do_center_current_image()


    ##########################################################################
    # Interfacing editor actions to the model.
    def map_point_from_editor_to_model(self, editor_x, editor_y):
        """Recomputes coordinates of an (Xe, Ye) point from editor coords
        (where X is horizontal from left, Y is vertical from bottom) to model
        (Xm, Ym) coords (where X is vertical from top, Y is horizontal from left)."""
        e_vertical = float(editor_y)
        e_horizontal = float(editor_x)

        e_vertical_inverted = self._get_editor_widget().height - e_vertical
        m_vertical = old_div(e_vertical_inverted, self.image_height_ratio_in)

        m_horizontal = old_div(e_horizontal, self.image_width_ratio_in)

        return m_vertical, m_horizontal

    def generate_cropobject_from_selection(self, selection, clsname=None, mask=None,
                                           integer_bounds=True):
        """After a selection is made, create the new MungNode.
        (To add it to the model, use add_cropobject_from_selection() instead.)

        Recomputes the X, Y and sizes back to the Numpy world & original image
        size.

        :param selection: A dict with the members `top`, `left`, `bottom` and `right`.
            These coordinates are assumed to be in the Kivy world.

        :param mask: Model-world mask to apply to the MungNode.

        :param integer_bounds: Whether the created MungNode should be scaled
            to integer bounds.

        """
        logging.info('App: Generating cropobject from selection {0}'.format(selection))
        # The current MungNode definition is weird this way...
        # x, y is the top-left corner, X is horizontal, Y is vertical.
        # Kivy counts position from bottom left, while MungNodes count them
        # from top left. So we need to invert the Y dimension.
        # Plus, for Kivy, X is vertical and Y is horizontal.
        # (To add to the confusion, numpy indexes from top-left and uses X
        # for rows, Y for columns.)
        new_cropobject_objid = self.annot_model.get_next_cropobject_id()
        new_cropobject_clsname = clsname
        if clsname is None:
            new_cropobject_clsname = self.currently_selected_mlclass_name


        # (The scaling from model-world to editor should be refactored out:
        #  working on utils/ImageToModelScaler)
        # Another problem: MungNodes that get recorded in the model should have
        # dimensions w.r.t. the image, not the editor. So, we need to resize them
        # first to the original ratios...
        x_unscaled = float(selection['top'])
        x_unscaled_inverted = self._get_editor_widget().height - x_unscaled
        x_scaled_inverted = float(old_div(x_unscaled_inverted, self.image_height_ratio_in))
        y_unscaled = float(selection['left'])
        y_scaled = float(old_div(y_unscaled, self.image_width_ratio_in))

        height_unscaled = float(selection['top'] - selection['bottom'])
        height_scaled = float(old_div(height_unscaled, self.image_height_ratio_in))
        width_unscaled = float(selection['right'] - selection['left'])
        width_scaled = float(old_div(width_unscaled, self.image_width_ratio_in))

        # Try scaler
        mT, mL, mB, mR = self.image_scaler.bbox_widget2model(selection['top'],
                                                             selection['left'],
                                                             selection['bottom'],
                                                             selection['right'])
        mH = mB - mT
        mW = mR - mL
        logging.info('App.scaler: Scaler would generate numpy-world'
                     ' x={0}, y={1}, h={2}, w={3}'.format(mT, mL, mH, mW))

        uid = MungNode.build_uid(global_name=self.cropobject_current_dataset_namespace,
                                   document_name=self.cropobject_current_docname,
                                   numid=new_cropobject_objid)
        c = MungNode(objid=new_cropobject_objid,
                       clsname=new_cropobject_clsname,
                       # Hah -- here, having the Image as the parent widget
                       # of the bbox selection tool is kind of useful...
                       top=x_scaled_inverted,
                       left=y_scaled,
                       width=width_scaled,
                       height=height_scaled,
                       mask=mask,
                       uid=uid)
        if integer_bounds:
            c.to_integer_bounds()
        logging.info('App: Generated cropobject from selection {0} -- properties: {1}'
                     ''.format(selection, {'objid': c.objid,
                                           'clsname': c.clsname,
                                           'x': c.x, 'y': c.y,
                                           'width': c.width,
                                           'height': c.height}))
        return c

    def generate_cropobject_from_model_selection(self, selection, clsname=None, mask=None,
                                                 integer_bounds=True):
        """After a selection is made **in the model world**, create the new MungNode.
        (To add it to the model, use add_cropobject_from_model_selection() instead.)

        :param selection: A dict with the members `top`, `left`, `bottom` and `right`.
            These coordinates are assumed to be in the model/numpy world.

        :param mask: Model-world mask to apply to the MungNode.

        :param integer_bounds: Whether the created MungNode should be scaled
            to integer bounds.
        """
        logging.info('App: Generating cropobject from model selection {0}'.format(selection))
        new_cropobject_objid = self.annot_model.get_next_cropobject_id()
        new_cropobject_clsname = clsname
        if clsname is None:
            new_cropobject_clsname = self.currently_selected_mlclass_name


        mT, mL, mB, mR = selection['top'], selection['left'], \
                         selection['bottom'], selection['right']
        mH = mB - mT
        mW = mR - mL

        uid = MungNode.build_uid(global_name=self.cropobject_current_dataset_namespace,
                                   document_name=self.cropobject_current_docname,
                                   numid=new_cropobject_objid)
        c = MungNode(objid=new_cropobject_objid,
                       clsname=new_cropobject_clsname,
                       top=mT, left=mL, width=mW, height=mH,
                       mask=mask,
                       uid=uid)
        if integer_bounds:
            c.to_integer_bounds()
        logging.info('App: Generated cropobject from selection {0} -- properties: {1}'
                     ''.format(selection, {'objid': c.objid,
                                           'clsname': c.clsname,
                                           'x': c.x, 'y': c.y,
                                           'width': c.width,
                                           'height': c.height}))
        return c

    def add_cropobject_from_selection(self, selection, clsname=None, mask=None):
        logging.info('App: Will add cropobject from selection {0}'.format(selection))
        c = self.generate_cropobject_from_selection(selection,
                                                    clsname=clsname,
                                                    mask=mask)
        logging.info('App: Adding cropobject from selection {0}'.format(selection))
        self.annot_model.add_cropobject(c)  # This should trigger rendering
        # self.current_n_cropobjects = len(self.annot_model.cropobjects)

    def add_cropobject_from_model_selection(self, selection, clsname=None, mask=None):
        logging.info('App: Will add cropobject from model_selection {0}'.format(selection))
        c = self.generate_cropobject_from_model_selection(selection,
                                                          clsname=clsname,
                                                          mask=mask)
        logging.info('App: Adding cropobject from model_selection {0}'.format(selection))
        self.annot_model.add_cropobject(c)  # This should trigger rendering

    def generate_model_bbox_from_selection(self, selection):
        c = self.generate_cropobject_from_selection(selection, clsname=None)
        t, l, b, r = c.bounding_box
        return t, l, b, r

    @tr.Tracker(track_names=['ask'],
                tracker_name='commands')
    def do_clear_cropobjects(self, ask=False):
        confirmation = ConfirmationDialog(text='Do you really want to clear'
                                               ' all current annotations?')
        confirmation.bind(on_ok=self.do_clear_cropobjects)
        if ask is True:
            confirmation.open()
        else:
            self.annot_model.clear_cropobjects()
            confirmation.unbind(on_ok=self.do_clear_cropobjects)

    def do_clear_precedence(self, ask=False):
        confirmation = ConfirmationDialog(text='Do you really want to clear'
                                               ' all current Precedence relationships?')
        confirmation.bind(on_ok=self.do_clear_precedence)
        if ask is True:
            confirmation.open()
        else:
            self.annot_model.clear_relationships(label='Precedence')
            confirmation.unbind(on_ok=self.do_clear_precedence)

    @tr.Tracker(track_names=[],
                tracker_name='commands')
    def find_cropobjects_with_errors(self):
        selected_objids = [c.objid for c in
                           self.cropobject_list_renderer.view.adapter.selection]
        logging.info('App: looking for cropobjects with errors: {0} selected'
                     ''.format(len(selected_objids)))

        vertices, reasons = self.annot_model.find_wrong_vertices(provide_reasons=True)
        vertex_set = set(vertices)
        logging.info('App: find_cropobjects_with_errors: Reasons:\n{0}'
                     ''.format(pprint.pformat(reasons)))

        if len(vertices) == 0:
            confirmation = MessageDialog(text='No wrong vertex detected.')
            confirmation.open()
            return

        view = self.cropobject_list_renderer.view
        view.unselect_all()

        for c in view.container.children[:]:
            if c._model_counterpart.objid in vertex_set:
                if len(selected_objids) > 0:
                    if c._model_counterpart.objid in selected_objids:
                        c.dispatch('on_release')
                else:
                    c.dispatch('on_release')

    def find_wrong_edges(self):
        cropobjects = [c for c in self.cropobject_list_renderer.view.selected_views]
        if len(cropobjects) == 0:
            cropobjects = list(self.annot_model.cropobjects.values())

        edges = self.annot_model.find_wrong_edges()
        # TODO: Integrate on alt+V

        for objid_from, objid_to in edges:
            ev = self.graph_renderer.view.get_edge_view(objid_from, objid_to)
            if ev is not None:
                if not ev.is_selected:
                    ev.dispatch('on_release')
            else:
                logging.warn('Found wrong edge {0}, but it is not currently rendered,'
                             ' so it cannot be selected. You should run edge validation'
                             ' with all edges visible.')

    ##########################################################################
    # MLClass selection tracking
    @tr.Tracker(track_names=['pos'],
                transformations={'pos': [lambda p: ('mlclass_name', p)]},
                tracker_name='commands')
    def on_currently_selected_mlclass_name(self, instance, pos):
        pass

    def _mlclass_selection_spinner_state_change(self, is_open):
        if is_open:
            self._mlclass_selection_spinner_opened()
        else:
            self._mlclass_selection_spinner_closed()

    @tr.Tracker(track_names=[],
                tracker_name='commands')
    def _mlclass_selection_spinner_opened(self):
        pass

    @tr.Tracker(track_names=[],
                tracker_name='commands')
    def _mlclass_selection_spinner_closed(self):
        pass

    @tr.Tracker(track_names=[],
                tracker_name='commands')
    def open_mlclass_selection_dialog(self):

        Clock.schedule_once(lambda *args, **kwargs: MLClassSelectionDialog().open())
        # dialog = MLClassSelectionDialog()
        # dialog.open()

    @tr.Tracker(track_names=[],
                tracker_name='commands')
    def open_objid_selection_dialog(self):
        Clock.schedule_once(lambda *args, **kwargs: ObjidSelectionDialog().open())

    ##########################################################################
    # Tool selection
    @property
    def available_tool_buttons(self):
        tool_sidebar = self.root.ids['tool_selection_sidebar']
        tool_buttons = [b for b in tool_sidebar.children[:]
                        if isinstance(b, ToggleButton)
                        and b.group == 'tool_selection_button_group']
        return list(reversed(tool_buttons))

    @property
    def available_tool_names(self):
        tool_names = [b.name for b in self.available_tool_buttons]
        return tool_names

    def init_tool_selection_keyboard_dispatch(self):

        logging.info('App: Initializing tool selection keyboard dispatch.')
        logging.info('App:\t Available tools: {0}'.format(self.available_tool_names))

        key_0 = 48
        for i, (n, b) in enumerate(zip(self.available_tool_names,
                                       self.available_tool_buttons)):
            k = key_0 + i + 1    # Starting at 1
            str_k = str(k)
            action = lambda button=b: self.process_tool_selection(button)
            logging.info('App:\t Key {0}: tool {1} with action {2}'
                         ''.format(str_k, n, action))
            self.keyboard_dispatch[str_k] = action

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

    @tr.Tracker(track_names=['pos'],
                transformations={'pos': [lambda t: ('tool', t)]},
                tracker_name='toolkit')
    def on_currently_selected_tool_name(self, instance, pos):
        """This does the "heavy lifting" of deactivating the old tool
        and activating the new one."""
        try:
            logging.info('App.on_currently_selected_tool: Deactivating current tool: {0}'
                         ''.format(self.tool))
            self.tool.deactivate()
            logging.info('App.on_currently_selected_tool: ...success!')
        except AttributeError:
            logging.info('App.on_currently_selected_tool: Failed on AttributeError,'
                         ' assuming tool was None & continuing.')
            pass

        if pos == '_default':
            logging.info('App.on_currently_selected_tool: Selected _default, no tool'
                         ' will be active.')
            # Make sure no tool buttons are selected
            tool_sidebar = self._get_tool_selection_sidebar()
            for tb in [b for b in tool_sidebar.children[1:-1]]:
                if tb.state is not 'normal':
                    tb.state = 'normal'

            return

        # The tool is a controller...
        tool_kwargs = toolkit.get_tool_kwargs_dispatch(pos)
        logging.info('App.on_currently_selected_tool: Tool kwargs are {0}'
                     ''.format(tool_kwargs))
        tool = toolkit.tool_dispatch[pos](app=self,
                                          editor_widget=self._get_editor_widget(),
                                          command_widget=self._get_tool_command_palette(),
                                          **tool_kwargs)
        # Tools need information about app state to initialize themselves correctly.
        # The tool will attach them to the editor widget.
        tool.init_editor_widgets()
        # The tool can also export some commands (like 'clear everything').
        # It gets space on the bottom right of the command sidebar.
        tool.init_command_palette()
        # Finally, the tool can define some keyboard shortcuts.
        tool.init_keyboard_shortcuts()

        self.tool = tool

        # Make sure the right button is *shown* as pressed
        for tb in self.available_tool_buttons:
            if tb.name == self.currently_selected_tool_name:
                tb.state = 'down'
            else:
                tb.state = 'normal'

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

    def _get_tool_selection_sidebar(self):
        return self.root.ids['tool_selection_sidebar']

    ##########################################################################
    # Cleanup.
    @tr.Tracker(track_names=[],
                tracker_name='app',
                comment='Application exited.')
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

        # Stop tracking
        handler = self.get_tracking_handler()
        handler.ensure_closed()

        # Clean tmp dir
        self.clean_tmp_dir()

        self.stop()

    ##########################################################################
    # Help
    @tr.Tracker(track_names=[],
                tracker_name='app',
                comment='Help requested.')
    def open_help(self):
        Help().open()

    ##########################################################################
    # Temporary files
    @property
    def tmp_dir(self):
        return os.path.join(os.path.dirname(__file__), 'tmp')

    def clean_tmp_dir(self):
        tmp_dir = self.tmp_dir
        for f in os.listdir(tmp_dir):
            if f != '.tmp-placeholder':
                try:
                    os.unlink(os.path.join(tmp_dir, f))
                except OSError:
                    logging.warn('Cleaning tmp dir: could not unlink file {0}'
                                 ''.format(os.path.join(tmp_dir, f)))

    ##########################################################################
    # Tracking
    def init_tracking(self):
        # First make sure the directory for tracking exists.
        path = self._tracking_path
        # path = self._get_default_tracking_dir()
        logging.info('App: Initializing tracking into dir {0}'.format(path))
        if not os.path.isdir(path):
            logging.info('App: tracking dir needs to be created: {0}'.format(path))
            os.makedirs(path)

        # Now initialize the handler's file to that output.
        handler = tr.DefaultTrackerHandler
        tracking_file = self.get_tracking_filename()

        logging.info('App: Tracking will be logged into file {0}'
                     ''.format(tracking_file))
        handler.output_file = tracking_file

    def get_tracking_filename(self):
        """Generates the tracking filename used for the given session."""
        t = self.get_tracking_handler()
        if t.output_file is not None:
            return t.output_file
        else:
            return self._generate_tracking_filename()

    def _generate_tracking_filename(self):
        # The tracking filename contains a timestamp
        t = time.time()
        now = datetime.datetime.fromtimestamp(t)
        timestamp_string = '{:%Y-%m-%d__%H-%M-%S}'.format(now)
        filename = 'muscimarker-tracking.{0}.json'.format(timestamp_string)
        return os.path.join(self._tracking_path, filename)

    def get_tracking_handler(self):
        return tr.DefaultTrackerHandler

    @property
    def _tracking_root(self):
        p = self.config.get('tracking', 'tracking_root_dir')
        if not p:
            p = self._get_default_tracking_root_dir()
        return p

    @property
    def _tracking_path(self):
        t = time.time()
        now = datetime.datetime.fromtimestamp(t)
        day_tag = '{:%Y-%m-%d}'.format(now)
        return os.path.join(self._tracking_root, day_tag)

    def _get_default_tracking_root_dir(self):
        home = os.path.expanduser('~') #os.environ['HOME']
        muscimarker_tracking_user_dir = '.muscimarker-tracking'
        return os.path.join(home, muscimarker_tracking_user_dir)

    def _get_default_tracking_dir(self):
        root_dir = self._get_default_tracking_root_dir()
        t = time.time()
        now = datetime.datetime.fromtimestamp(t)
        day_tag = '{:%Y-%m-%d}'.format(now)
        return os.path.join(root_dir, day_tag)

    ##########################################################################
    # Automation
    def auto_add_measure_separators(self):
        """Automatically wraps each *_barline that does not yet have
        a parent in a ``measure_separator`` object."""
        BARLINE_CLASSES = ['thin_barline', 'thick_barline', 'dotted_barline']
        MEASURE_SEPARATOR_CLSNAME = 'measure_separator'

        c_l_view = self.cropobject_list_renderer.view
        _prev_selection = [c.objid for c in c_l_view.selected_views]
        c_l_view.unselect_all()

        _prev_clsname = self.currently_selected_mlclass_name
        self.currently_selected_mlclass_name = MEASURE_SEPARATOR_CLSNAME


        for c in list(self.annot_model.cropobjects.values()):
            if (c.clsname in BARLINE_CLASSES) and (len(c.inlinks) == 0):
                # Add a measure separator from this one:
                #  - create the new MungNode
                #  - add the link from the measure_separator
                # Basically, it's like passing shift+M on the barline
                # with the measure_separator as current class.
                c_view = c_l_view.get_cropobject_view(c.objid)
                c_view.ensure_selected()
                c_l_view.handle_dispatch_key('109+shift')
                c_view.ensure_deselected()

        # Restoring prev selection state and clsname
        self.currently_selected_mlclass_name = _prev_clsname
        for _objid in _prev_selection:
            c_l_view.get_cropobject_view(_objid).ensure_selected()

    def find_objects_with_unannotated_pixels(self, threshold=None, exclusive=False):
        """Finds all objects that have more than ``threshold`` of foreground
        pixels within their bounding box not marked as part of the object.

        The purpose is to find inaccuracies where the box is relatively OK,
        but the annotator did not mark the object accurately within the box.

        :param exclusive: If True, will only count pixels that are not a part
            of any other MungNode against the threshold. (This will make
            the computation much slower.)
        """
        if threshold is None:
            if exclusive:
                threshold = float(self.config.get('automation', 'sparse_exclusive_cropobject_threshold'))
            else:
                threshold = float(self.config.get('automation', 'sparse_cropobject_threshold'))

        c_l_view = self.cropobject_list_renderer.view
        cropobjects = [cv._model_counterpart for cv in c_l_view.selected_views]
        if len(cropobjects) == 0:
            cropobjects = list(self.annot_model.cropobjects.values())

        image = self.annot_model.image

        #### Precompute which pixels are part of no object.
        # These are exactly the pixels which will count towards
        # the exclusive threshold.
        if exclusive:
            # _bbox = [
            #     min([c.top for c in cropobjects]),
            #     min([c.left for c in cropobjects]),
            #     max([c.bottom for c in cropobjects]),
            #     max([c.right for c in cropobjects])
            # ]
            image = copy.deepcopy(image)
            for c in cropobjects:
                # Modifies the copied image in-place. This will be sufficient
                # later in the threshold-counting cycle.
                crop = image[c.top:c.bottom, c.left:c.right]
                crop[c.mask != 0] = 0

        _objids_over_threshold = []
        for c in cropobjects:
            # Find proportion of bad pixels
            n_fg = old_div(image[c.top:c.bottom, c.left:c.right].sum(), 255.0)
            n_mask = float(c.mask.sum())
            logging.info('App.automation: Object {0} has {1} masked pixels, {2} image fg pixels, proportion:'
                         ' {3}'.format(c.objid, n_mask, n_fg, old_div(n_mask, n_fg)))

            if exclusive:
                # FG pixels are only the "not a part of any object" pixels within
                # the bounding box.
                if (old_div(n_fg, (n_fg + n_mask))) > threshold:
                    _objids_over_threshold.append(c.objid)
            elif (1 - (old_div(n_mask, n_fg))) > threshold:
                _objids_over_threshold.append(c.objid)

        logging.info('App.automation: Total objects over threshold: {0}'.format(len(_objids_over_threshold)))

        c_l_view.unselect_all()
        c_l_view.ensure_selected_objids(_objids_over_threshold)

    def find_objects_with_disconnected_masks(self, leaves_only=False):
        """Find all objects with masks consisting of more than one
        connected foreground component.

        :param leaves_only: If set, will only highlight those objects
            with disconnected masks that have no descendants in the
            object graph.
        """
        c_l_view = self.cropobject_list_renderer.view
        cropobjects = [cv._model_counterpart for cv in c_l_view.selected_views]
        if len(cropobjects) == 0:
            cropobjects = list(self.annot_model.cropobjects.values())

        _objids_disconnected = []
        for c in cropobjects:
            if leaves_only and len(c.outlinks) > 0:
                    continue

            cc, labels, _ = compute_connected_components(c.mask)
            if cc > 1:
                _objids_disconnected.append(c.objid)

        c_l_view.unselect_all()
        c_l_view.ensure_selected_objids(_objids_disconnected)

    def find_objects_with_identical_bounding_box(self):
        """Find all objects which share bounding box, but are not connected
        with an Attachment relationship. This is helpful for discovering
        duplicate annotations, which are otherwise visible only through
        the combined alpha of their CropObjectViews.
        """
        c_l_view = self.cropobject_list_renderer.view
        cropobjects = [cv._model_counterpart for cv in c_l_view.selected_views]
        if len(cropobjects) == 0:
            cropobjects = list(self.annot_model.cropobjects.values())

        _objids_duplicate = set()
        sorted_cropobjects = sorted(cropobjects, key=lambda c: c.bounding_box)
        current_cropobject = sorted_cropobjects[0]
        for other_cropobject in sorted_cropobjects[1:]:
            if other_cropobject.bounding_box == current_cropobject.bounding_box:
                if (current_cropobject.objid not in other_cropobject.inlinks) \
                    and (current_cropobject.objid not in other_cropobject.outlinks):
                    _objids_duplicate.add(current_cropobject.objid)
                    _objids_duplicate.add(other_cropobject.objid)
            else:
                # Move along the list
                current_cropobject = other_cropobject

        c_l_view.unselect_all()
        c_l_view.ensure_selected_objids(_objids_duplicate)

    def find_suspiciously_small_objects(self):
        c_l_view = self.cropobject_list_renderer.view
        cropobjects = [cv._model_counterpart for cv in c_l_view.selected_views]
        if len(cropobjects) == 0:
            cropobjects = list(self.annot_model.cropobjects.values())

        small_object_objids = self.annot_model.find_very_small_objects(bbox_threshold=40,
                                                                       mask_threshold=35)

        logging.info('Suspiciously small objects found: {0}'.format(len(small_object_objids)))
        c_l_view.unselect_all()
        c_l_view.ensure_selected_objids(small_object_objids)

    ##########################################################################
    # Playback
    def infer_midi(self, play=True):
        """Plays the current selection as MIDI."""
        selection = [v._model_counterpart
                     for v in self.cropobject_list_renderer.view.selected_views]
        self.annot_model.infer_midi(selection, play=play)